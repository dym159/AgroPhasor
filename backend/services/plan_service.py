"""Replay dated phases on each terrain cell with Monte Carlo climate forecasting."""
from datetime import date, timedelta
from dataclasses import replace
import math
import numpy as np

from backend.core.climate_generator import mc_day_to_weather
from backend.core.edo1_engine import simulate_canopy_diurnal_cycle, compute_shield_state_and_color
from backend.core.edo2_engine import compute_soil_limits, relative_stomatal_conductance
from backend.core.edo3_engine import compute_liebig_factor
from backend.core.physics import saturation_vapor_pressure, thermal_comfort_index
from backend.core.edo4_engine import execute_harvest_event, execute_partial_cut
from backend.core.edo5_engine import (
    compute_soil_color,
    compute_soil_vitality_index,
    compute_terrain_height_variation,
)
from backend.models.crop_parameters import CROP_CATALOG, GLOBAL_CONSTANTS
from backend.services.climate_service import (
    history_from_annual_climate,
    predict_climate_scenarios,
)
from backend.services.coupled_model import advance_day, avanzar_un_dia_celda, incorporate_residue


def _percentile_summary(values, decimals=2):
    arr = np.asarray(values, dtype=float)
    return {
        "p10": round(float(np.percentile(arr, 10)), decimals),
        "p50": round(float(np.percentile(arr, 50)), decimals),
        "p90": round(float(np.percentile(arr, 90)), decimals),
        "mean": round(float(np.mean(arr)), decimals),
    }


def compute_dynamic_surface_color(
    depth_mm: float,
    eta_w: float,
    eta_n: float,
    biomass_t_ha: float,
    growing: bool,
    thermal_comfort: float = 1.0,
    h0_mm: float = 400.0,
):
    """Compute a composite RGB color reflecting soil moisture, fertility, erosion, and canopy/stover cover."""
    base_retention = max(0.0, min(1.0, depth_mm / max(1.0, h0_mm)))
    erosion_loss_mm = max(0.0, h0_mm - depth_mm)
    # Amplify seasonal erosion (e.g. 0..1.5 mm) so hillslope wear is visually discernible
    erosion_vis = max(1.0 - base_retention, min(0.65, erosion_loss_mm / 1.5))

    w_clamped = max(0.0, min(1.0, float(eta_w)))
    n_clamped = max(0.0, min(1.0, float(eta_n)))
    t_clamped = max(0.0, min(1.0, float(thermal_comfort)))

    # Moist fertile soil (dark loam) vs parched dry earth (pale ochre)
    moist_soil = (72.0, 48.0, 25.0)
    dry_soil = (158.0, 118.0, 76.0)
    soil_r = dry_soil[0] + (moist_soil[0] - dry_soil[0]) * (0.75 * w_clamped + 0.25 * n_clamped)
    soil_g = dry_soil[1] + (moist_soil[1] - dry_soil[1]) * (0.75 * w_clamped + 0.25 * n_clamped)
    soil_b = dry_soil[2] + (moist_soil[2] - dry_soil[2]) * (0.75 * w_clamped + 0.25 * n_clamped)

    # Blend toward eroded bedrock gray (128, 128, 128) as topsoil wears down
    soil_r = soil_r + (128.0 - soil_r) * erosion_vis
    soil_g = soil_g + (128.0 - soil_g) * erosion_vis
    soil_b = soil_b + (128.0 - soil_b) * erosion_vis

    b_pos = max(0.0, float(biomass_t_ha))
    if growing:
        canopy_cover = 1.0 - math.exp(-0.45 * b_pos)
        vigor = max(0.0, min(1.0, 0.45 * w_clamped + 0.30 * n_clamped + 0.25 * t_clamped))
        # Healthy green canopy vs stressed yellowish-olive canopy
        healthy_green = (42.0, 146.0, 68.0)
        stressed_olive = (174.0, 144.0, 52.0)
        veg_r = stressed_olive[0] + (healthy_green[0] - stressed_olive[0]) * vigor
        veg_g = stressed_olive[1] + (healthy_green[1] - stressed_olive[1]) * vigor
        veg_b = stressed_olive[2] + (healthy_green[2] - stressed_olive[2]) * vigor
        alpha = 0.82 * canopy_cover
        r = soil_r * (1.0 - alpha) + veg_r * alpha
        g = soil_g * (1.0 - alpha) + veg_g * alpha
        b = soil_b * (1.0 - alpha) + veg_b * alpha
    else:
        # Harvest stover / crop residue during fallow transition
        stover_cover = 1.0 - math.exp(-0.35 * b_pos)
        stover_gold = (168.0, 134.0, 62.0)
        alpha = 0.65 * stover_cover
        r = soil_r * (1.0 - alpha) + stover_gold[0] * alpha
        g = soil_g * (1.0 - alpha) + stover_gold[1] * alpha
        b = soil_b * (1.0 - alpha) + stover_gold[2] * alpha

    return (
        int(round(max(0.0, min(255.0, r)))),
        int(round(max(0.0, min(255.0, g)))),
        int(round(max(0.0, min(255.0, b)))),
    )


def _select_snapshot_offsets(plan, first_day, last_day, target_day, max_regular=60):
    total_days = (last_day - first_day).days + 1
    step = max(1, (total_days - 1) // max(1, max_regular))
    offsets = set(range(0, total_days, step))
    offsets.add(0)
    offsets.add(total_days - 1)
    offsets.add((target_day - first_day).days)
    for idx, (p_start, p_end, _) in enumerate(plan):
        s_off = (p_start - first_day).days
        e_off = (p_end - first_day).days
        mid_off = s_off + max(0, (e_off - s_off) // 2)
        q1_off = s_off + max(0, (e_off - s_off) // 4)
        q3_off = s_off + max(0, (3 * (e_off - s_off)) // 4)
        offsets.update([s_off, q1_off, mid_off, q3_off, max(0, e_off - 1), e_off])
        if idx + 1 < len(plan):
            next_s_off = (plan[idx + 1][0] - first_day).days
            if next_s_off > e_off:
                offsets.add(min(total_days - 1, e_off + 1))
                offsets.add(e_off + (next_s_off - e_off) // 2)
                offsets.add(max(0, next_s_off - 1))
    return sorted(off for off in offsets if 0 <= off < total_days)


def _simulate_plan_trajectory(
    plan,
    phases,
    daily_climate,
    first_day,
    end_day,
    slope_deg,
    altitude_offset_c=0.0,
    collect_stats=False,
    snapshot_offsets=None,
):
    """Advance the coupled 5-ODE system across dated crop phases and fallow transitions."""
    state = (104., (100., 40., 120.), 400., plan[0][2].B0_t_ha, ())
    organic_matter = 3.0
    day = first_day
    stage = 0
    crop = plan[0][2]
    diagnostic = None
    growing = True

    phase_stats = (
        [
            {
                "viable": True,
                "frost_hit": False,
                "heat_hit": False,
                "water_stress_days": 0,
                "harvest_yield_t_ha": 0.0,
                "harvest_water_mm": 0.0,
                "harvest_biomass_t_ha": 0.0,
                "start_depth_mm": 400.0 if idx == 0 else None,
                "end_depth_mm": 400.0,
                "temps": [],
                "rains": [],
                "rads": [],
            }
            for idx in range(len(plan))
        ]
        if collect_stats
        else None
    )
    daily_records = [] if collect_stats else None
    captured_snapshots = {} if snapshot_offsets is not None else None

    while day <= end_day:
        start, end, crop = plan[stage]
        if day == end:
            pre_harvest_biomass = state[3]
            harvest = execute_harvest_event(state[3], crop, phases[stage].get("residue_fraction", .5))
            if collect_stats:
                phase_stats[stage]["harvest_yield_t_ha"] = float(harvest.commercial_yield_t_ha)
                phase_stats[stage]["harvest_water_mm"] = float(state[0])
                phase_stats[stage]["harvest_biomass_t_ha"] = float(pre_harvest_biomass)
                phase_stats[stage]["end_depth_mm"] = float(state[2])
            state = (*state[:3], harvest.residue_left_t_ha, state[4])
        if stage + 1 < len(plan) and day == plan[stage + 1][0]:
            organic_matter = incorporate_residue(organic_matter, state[3], state[2])
            stage += 1
            start, end, crop = plan[stage]
            state = (*state[:3], crop.B0_t_ha, state[4])
            if collect_stats:
                phase_stats[stage]["start_depth_mm"] = float(state[2])

        growing = start <= day < end
        offset = (day - first_day).days
        clima_dia = daily_climate[offset]
        irrigation = phases[stage].get("irrigation_mm_day", 0) if growing else 0

        if isinstance(clima_dia, dict):
            state, diagnostic = avanzar_un_dia_celda(
                state,
                crop,
                clima_dia,
                slope_deg,
                irrigation=irrigation,
                growing=growing,
                soil_om=organic_matter,
                altitude_offset_c=altitude_offset_c,
            )
            rain_val = float(clima_dia["P0_mm"])
            temp_val = float(clima_dia["T_NASA"]) + altitude_offset_c
            rad_val = float(clima_dia["f_rad_W_m2"])
        else:
            rain, temp, humidity, radiation = clima_dia
            temp_adj = temp + altitude_offset_c
            state, diagnostic = advance_day(
                state,
                crop,
                (rain, temp_adj, humidity, radiation),
                slope_deg,
                irrigation=irrigation,
                growing=growing,
                soil_om=organic_matter,
            )
            rain_val = float(rain)
            temp_val = float(temp_adj)
            rad_val = float(radiation) / 0.0864

        if captured_snapshots is not None and offset in snapshot_offsets:
            captured_snapshots[offset] = (
                state,
                dict(diagnostic),
                growing,
                crop,
                stage,
                float(organic_matter),
            )

        if collect_stats:
            if growing:
                pstat = phase_stats[stage]
                if not diagnostic["viable"]:
                    pstat["viable"] = False
                if diagnostic["canopy"] <= crop.T_frost:
                    pstat["frost_hit"] = True
                if diagnostic["canopy"] >= crop.T_lethal:
                    pstat["heat_hit"] = True
                if diagnostic["water_stress"] > 0:
                    pstat["water_stress_days"] += 1
                pstat["temps"].append(temp_val)
                pstat["rains"].append(rain_val)
                pstat["rads"].append(rad_val)
                pstat["end_depth_mm"] = float(state[2])
            daily_records.append(
                {
                    "date": day,
                    "water": float(state[0]),
                    "biomass": float(state[3]),
                    "viable": bool(diagnostic["viable"]),
                    "water_stress": bool(growing and diagnostic["water_stress"] > 0),
                    "crop_label": crop.name if growing else "Transition / Fallow",
                }
            )

        day += timedelta(days=1)

    if captured_snapshots is not None:
        return state, diagnostic, growing, crop, phase_stats, daily_records, captured_snapshots
    return state, diagnostic, growing, crop, phase_stats, daily_records


def _build_phase_forecasts(plan, phases, ensemble_phase_stats):
    phase_forecasts = []
    n_mc = len(ensemble_phase_stats)
    for idx, (start, end, crop) in enumerate(plan):
        items = [run[idx] for run in ensemble_phase_stats]
        viable_count = sum(1 for it in items if it["viable"])
        frost_count = sum(1 for it in items if it["frost_hit"])
        heat_count = sum(1 for it in items if it["heat_hit"])
        phase_temps = [float(np.mean(it["temps"])) for it in items if it["temps"]]
        phase_rains = [float(np.sum(it["rains"])) for it in items]
        phase_rads = [float(np.mean(it["rads"])) for it in items if it["rads"]]
        erosions = [
            max(0.0, (it["start_depth_mm"] or 400.0) - it["end_depth_mm"])
            for it in items
        ]
        phase_forecasts.append({
            "phase_index": idx,
            "crop_id": phases[idx].get("cropId", crop.key),
            "crop_key": crop.key,
            "crop": crop.name,
            "start": start.isoformat(),
            "harvest": end.isoformat(),
            "duration_days": (end - start).days,
            "residue_fraction": float(phases[idx].get("residue_fraction", .5)),
            "irrigation_mm_day": float(phases[idx].get("irrigation_mm_day", 0)),
            "confidence_pct": round(100.0 * viable_count / n_mc, 1),
            "viable_scenarios": viable_count,
            "mc_scenarios": n_mc,
            "frost_risk_pct": round(100.0 * frost_count / n_mc, 1),
            "heat_risk_pct": round(100.0 * heat_count / n_mc, 1),
            "water_stress_days_mean": round(float(np.mean([it["water_stress_days"] for it in items])), 1),
            "yield_t_ha": _percentile_summary([it["harvest_yield_t_ha"] for it in items], 2),
            "soil_water_mm_at_harvest": _percentile_summary([it["harvest_water_mm"] for it in items], 1),
            "biomass_t_ha_at_harvest": _percentile_summary([it["harvest_biomass_t_ha"] for it in items], 2),
            "erosion_mm": _percentile_summary(erosions, 3),
            "climate": {
                "temp_mean_c": round(float(np.mean(phase_temps)), 2) if phase_temps else 0.0,
                "temp_p10_c": round(float(np.percentile(phase_temps, 10)), 2) if phase_temps else 0.0,
                "temp_p90_c": round(float(np.percentile(phase_temps, 90)), 2) if phase_temps else 0.0,
                "precip_total_p10_mm": round(float(np.percentile(phase_rains, 10)), 1),
                "precip_total_p50_mm": round(float(np.percentile(phase_rains, 50)), 1),
                "precip_total_p90_mm": round(float(np.percentile(phase_rains, 90)), 1),
                "rad_mean_wm2": round(float(np.mean(phase_rads)), 1) if phase_rads else 0.0,
            },
        })
    return phase_forecasts


def _build_monthly_forecast(climate_monthly, ensemble_daily_records):
    if not ensemble_daily_records:
        return []
    ref_records = ensemble_daily_records[0]
    month_indices = {}
    for idx, rec in enumerate(ref_records):
        d = rec["date"]
        month_indices.setdefault(f"{d.year:04d}-{d.month:02d}", []).append(idx)

    climate_by_month = {entry["month"]: entry for entry in climate_monthly}
    monthly = []
    for month_key, indices in month_indices.items():
        c_entry = climate_by_month.get(month_key, {})
        waters = [float(np.mean([run[i]["water"] for i in indices])) for run in ensemble_daily_records]
        biomasses = [float(np.mean([run[i]["biomass"] for i in indices])) for run in ensemble_daily_records]
        stress_days = [sum(1 for i in indices if run[i]["water_stress"]) for run in ensemble_daily_records]
        viable_runs = sum(1 for run in ensemble_daily_records if all(run[i]["viable"] for i in indices))
        crops_seen = list(dict.fromkeys(ref_records[i]["crop_label"] for i in indices))
        monthly.append({
            **c_entry,
            "month": month_key,
            "active_crops": crops_seen,
            "soil_water_p50_mm": round(float(np.percentile(waters, 50)), 1),
            "biomass_p50_t_ha": round(float(np.percentile(biomasses, 50)), 2),
            "water_stress_days_mean": round(float(np.mean(stress_days)), 1),
            "viability_pct": round(100.0 * viable_runs / len(ensemble_daily_records), 1),
        })
    return monthly


def replay_plan(
    result,
    phases,
    selected_date,
    *,
    mc_samples=30,
    delta_T_whatif=0.0,
    delta_P_pct_whatif=0.0,
    seed=42,
    use_climate_forecast=True,
):
    from backend.services import rotation_service
    from backend.services.rotation_service import load_climate, number

    if not isinstance(phases, list) or not 1 <= len(phases) <= 12:
        raise ValueError("The plan must have between 1 and 12 phases.")
    mc_samples = int(number(mc_samples, 1, 200, "Monte Carlo samples"))
    delta_T_whatif = number(delta_T_whatif, -10, 15, "Temperature delta")
    delta_P_pct_whatif = number(delta_P_pct_whatif, -90, 200, "Precipitation delta (%)")
    seed = int(seed)

    plan = []
    for phase in phases:
        crop = CROP_CATALOG.get(phase.get("cropId"))
        if crop is None or crop.key == "suelo_desnudo_transicion":
            raise ValueError("Assign a modeled crop to each phase.")
        start = date.fromisoformat(phase["start"])
        end = date.fromisoformat(phase["harvest"])
        if end <= start or (plan and start < plan[-1][1]):
            raise ValueError("Phases must have ordered, non-overlapping dates.")
        number(phase.get("residue_fraction", .5), 0, 1, "Residue fraction")
        number(phase.get("irrigation_mm_day", 0), 0, 30, "Irrigation")
        plan.append((start, end, crop))

    target = date.fromisoformat(selected_date)
    first = plan[0][0]
    last = plan[-1][1]
    if not first <= target <= last or (last - first).days > 3650:
        raise ValueError("The query date must fall within the plan, up to ten years.")

    cells = result["cells"]
    latitude = sum(c["latitude"] for c in cells) / len(cells)
    longitude = sum(c["longitude"] for c in cells) / len(cells)
    altitude = sum(c["altitude_m"] for c in cells) / len(cells)
    area = sum(cell["area_m2"] for cell in cells)
    mean_slope = sum(cell["area_m2"] * cell["slope_deg"] for cell in cells) / area

    is_mocked_climate = load_climate is not rotation_service._DEFAULT_LOAD_CLIMATE
    forecast_active = bool(use_climate_forecast) and not is_mocked_climate
    total_plan_days = (last - first).days + 1

    if forecast_active:
        forecast = predict_climate_scenarios(
            round(latitude, 3),
            round(longitude, 3),
            first,
            last,
            n_mc=mc_samples,
            delta_T_whatif=delta_T_whatif,
            delta_P_pct_whatif=delta_P_pct_whatif,
            seed=seed,
        )
        rep_daily = forecast["representative_scenario"]
        mc_scenarios = forecast["escenarios"]
        climate_source = "NASA POWER + Fourier/AR(1)-Gamma Monte Carlo"
    else:
        annual_climate = load_climate(round(latitude, 3), round(longitude, 3))
        rain_mult = max(0.0, 1.0 + delta_P_pct_whatif / 100.0)
        rep_daily = []
        for offset in range(total_plan_days):
            d = first + timedelta(days=offset)
            key = (2, 28) if (d.month, d.day) == (2, 29) else (d.month, d.day)
            rain, temp, rh, rad = annual_climate[key][:4]
            rep_daily.append((rain * rain_mult, temp + delta_T_whatif, rh, rad))
        history_override = history_from_annual_climate(annual_climate, lat=latitude, lon=longitude)
        forecast = predict_climate_scenarios(
            round(latitude, 3),
            round(longitude, 3),
            first,
            last,
            n_mc=mc_samples,
            delta_T_whatif=delta_T_whatif,
            delta_P_pct_whatif=delta_P_pct_whatif,
            seed=seed,
            history_override=history_override,
        )
        mc_scenarios = forecast["escenarios"]
        climate_source = (
            "NASA POWER 2023 · historical repeat"
            if not use_climate_forecast
            else "NASA POWER (reference) + Monte Carlo"
        )

    from backend.services.parcel_edo1 import load_power
    reference_day = date(2023, target.month, min(target.day, 28) if target.month == 2 else target.day)
    observed_day, hourly, radiation_mj = load_power(longitude, latitude, reference_day)
    timestamps = sorted(hourly["T2M"])

    target_offset = (target - first).days
    base_air_ref = [hourly["T2M"][ts] for ts in timestamps]
    base_rad_wm2 = [
        hourly["ALLSKY_SFC_SW_DWN"][ts] / .0036 if radiation_mj else hourly["ALLSKY_SFC_SW_DWN"][ts]
        for ts in timestamps
    ]
    base_rh_ref = [hourly["RH2M"][ts] for ts in timestamps]
    mean_air_ref = sum(base_air_ref) / len(base_air_ref)
    mean_rad_ref = sum(base_rad_wm2) / len(base_rad_wm2)

    def _diurnal_forcing_for_offset(day_offset):
        day_weather = rep_daily[day_offset]
        if forecast_active and isinstance(day_weather, dict):
            temp_shift = day_weather["T_NASA"] - mean_air_ref
            rad_scale = max(0.2, min(2.5, day_weather["f_rad_W_m2"] / mean_rad_ref)) if mean_rad_ref > 10.0 else 1.0
            rain_w = float(day_weather.get("P0_mm", 0.0))
            return (
                [t + temp_shift for t in base_air_ref],
                [r * rad_scale for r in base_rad_wm2],
                day_weather["e_a_kPa"],
                rain_w,
            )
        if isinstance(day_weather, (tuple, list)):
            rain_w, temp_w, _, _ = day_weather[:4]
            temp_shift = float(temp_w) - mean_air_ref
            return (
                [t + temp_shift for t in base_air_ref],
                base_rad_wm2,
                None,
                float(rain_w),
            )
        return base_air_ref, base_rad_wm2, None, 0.0

    def _evaluate_cell_state(snap_tuple, alt_offset_c, day_air, day_rad, day_ea_kpa, day_rain=0.0):
        state, diagnostic, growing, crop_obj, stage_idx, _ = snap_tuple
        water, nutrients, depth, biomass, _ = state
        limits = compute_soil_limits(crop_obj, depth_mm=depth)
        thermal_crop = replace(crop_obj, W_fc=limits.w_cc, W_pmp=limits.w_pmp, W_crit=limits.w_crit)
        if not growing:
            thermal_crop = replace(thermal_crop, gamma_max=0, lambda_gamma_max=0, Cp=18000, alpha=.72, hc=24)
        air = [t + alt_offset_c for t in day_air]
        if day_ea_kpa is not None:
            rh_hourly = [
                max(5.0, min(100.0, 100.0 * day_ea_kpa / max(1e-6, saturation_vapor_pressure(t))))
                for t in air
            ]
        else:
            rh_hourly = base_rh_ref
        thermal = simulate_canopy_diurnal_cycle(air, day_rad, rh_hourly, water, thermal_crop)
        eta_n = compute_liebig_factor(*nutrients, crop_obj.K_N, crop_obj.K_P, crop_obj.K_K)[0]
        eta_w = relative_stomatal_conductance(water, limits)
        thermal_comfort = [thermal_comfort_index(t, crop_obj.T_opt, crop_obj.delta_T_tol) for t in thermal["t_canopy_hourly"]]
        raw_indices = [tc * eta_w * eta_n for tc in thermal_comfort]
        mean_tc = sum(thermal_comfort) / max(1, len(thermal_comfort))
        mean_psi = sum(raw_indices) / max(1, len(raw_indices))
        al_eff = thermal["lissajous_area"] * eta_w * mean_tc
        shield_eval = compute_shield_state_and_color(
            lissajous_area=al_eff,
            psi_environmental=mean_psi,
            is_crop=growing,
        )
        eta_l = shield_eval["eta_lissajous"]
        indices = [round(p, 4) for p in raw_indices]
        shield_scores = [
            compute_shield_state_and_color(lissajous_area=al_eff, psi_environmental=p, is_crop=growing)["shield_score"]
            for p in raw_indices
        ]

        b_pos = max(0.0, float(biomass))
        canopy_cover_pct = round((1.0 - math.exp(-0.45 * b_pos)) * 100.0, 1) if growing else 0.0
        ndvi_val = round(0.15 + 0.72 * (1.0 - math.exp(-0.45 * b_pos)), 3) if growing else round(0.12 + 0.18 * (1.0 - math.exp(-0.35 * b_pos)), 3)
        base_color = compute_soil_color(
            retention_ratio=depth / 400.0,
            eta_nutrientes=eta_n,
            water_saturation=eta_w,
        )
        height_var = compute_terrain_height_variation(
            precip_mm=day_rain,
            accumulated_erosion_mm=400.0 - depth,
            slope_deg=mean_slope,
            biomass_t_ha=biomass,
            is_transition=not growing,
            altitude_m=altitude,
        )
        soil_color = compute_dynamic_surface_color(
            depth_mm=depth,
            eta_w=eta_w,
            eta_n=eta_n,
            biomass_t_ha=b_pos,
            growing=growing,
            thermal_comfort=mean_tc,
            h0_mm=400.0,
        )
        soil_vitality = compute_soil_vitality_index(
            retention_ratio=depth / 400.0,
            eta_nutrientes=eta_n,
            water_saturation=eta_w,
        )

        return {
            "soil_water_mm": water,
            "nutrientes_n_kg_ha": nutrients[0],
            "nutrientes_p_kg_ha": nutrients[1],
            "nutrientes_k_kg_ha": nutrients[2],
            "biomass_t_ha": biomass,
            "canopy_cover_pct": canopy_cover_pct,
            "ndvi_satelital": ndvi_val,
            "h_current_mm": depth,
            "accumulated_erosion_mm": 400.0 - depth,
            "rain_height_variation_mm": height_var["rain_height_variation_mm"],
            "visual_height_delta_m": height_var["visual_height_delta_m"],
            "soil_vitality_index": soil_vitality,
            "soil_color_rgb": soil_color,
            "base_soil_color_rgb": base_color,
            "shield_enabled": growing,
            "eta_lissajous": eta_l if growing else 0.0,
            "shield_score": shield_eval["shield_score"] if growing else 0.0,
            "shield_state": shield_eval["shield_state"],
            "shield_color_rgb": shield_eval["shield_color_rgb"],
            "hourly_environmental_index": indices,
            "hourly_shield_score": shield_scores if growing else None,
            "hourly_air_temps": air,
            "hourly_canopy_temps": thermal["t_canopy_hourly"],
            "lissajous_area": thermal["lissajous_area"],
            "mean_canopy_temp": thermal["mean_canopy_temp"],
            "eta_nutrientes": eta_n,
            "water_condition_index": round(eta_w, 4),
            "is_irrigation_needed": growing and diagnostic["irrigation_needed"],
            "suggested_irrigation_mm": diagnostic["suggested_irrigation_mm"] if growing else 0,
            "_growing": growing,
            "_crop": crop_obj,
            "_stage": stage_idx,
        }

    snapshot_offsets = _select_snapshot_offsets(plan, first, last, target)
    snapshot_offset_set = set(snapshot_offsets)
    diurnal_by_offset = {off: _diurnal_forcing_for_offset(off) for off in snapshot_offsets}
    cell_snapshots_by_offset = {off: [] for off in snapshot_offsets}

    target_growing = True
    target_crop = plan[0][2]

    for cell in cells:
        alt_offset_c = -.0065 * (cell["altitude_m"] - altitude)
        _, _, _, _, _, _, captured = _simulate_plan_trajectory(
            plan,
            phases,
            rep_daily,
            first,
            last,
            cell["slope_deg"],
            altitude_offset_c=alt_offset_c,
            collect_stats=False,
            snapshot_offsets=snapshot_offset_set,
        )
        for off in snapshot_offsets:
            day_air, day_rad, day_ea_kpa, day_rain = diurnal_by_offset[off]
            evaluated = _evaluate_cell_state(captured[off], alt_offset_c, day_air, day_rad, day_ea_kpa, day_rain=day_rain)
            if off == target_offset:
                target_growing = evaluated["_growing"]
                target_crop = evaluated["_crop"]
                cell.update({k: v for k, v in evaluated.items() if not k.startswith("_")})
            cell_snapshots_by_offset[off].append(evaluated)

    growing = target_growing
    crop = target_crop

    timeline_snapshots = []
    for off in snapshot_offsets:
        snap_date = first + timedelta(days=off)
        eval_cells = cell_snapshots_by_offset[off]
        first_eval = eval_cells[0]
        s_growing = first_eval["_growing"]
        s_crop = first_eval["_crop"]
        s_stage = first_eval["_stage"]
        timeline_snapshots.append({
            "date": snap_date.isoformat(),
            "day_index": off,
            "phase_index": s_stage,
            "phase": "cultivo" if s_growing else "transicion",
            "crop": s_crop.name,
            "crop_id": s_crop.key,
            "lot_mean_soil_water_mm": round(sum(c["area_m2"] * ec["soil_water_mm"] for c, ec in zip(cells, eval_cells)) / area, 2),
            "lot_mean_n_kg_ha": round(sum(c["area_m2"] * ec["nutrientes_n_kg_ha"] for c, ec in zip(cells, eval_cells)) / area, 2),
            "lot_mean_p_kg_ha": round(sum(c["area_m2"] * ec["nutrientes_p_kg_ha"] for c, ec in zip(cells, eval_cells)) / area, 2),
            "lot_mean_k_kg_ha": round(sum(c["area_m2"] * ec["nutrientes_k_kg_ha"] for c, ec in zip(cells, eval_cells)) / area, 2),
            "lot_mean_biomass_t_ha": round(sum(c["area_m2"] * ec["biomass_t_ha"] for c, ec in zip(cells, eval_cells)) / area, 2),
            "lot_mean_canopy_cover_pct": round(sum(c["area_m2"] * ec["canopy_cover_pct"] for c, ec in zip(cells, eval_cells)) / area, 1),
            "lot_mean_h_mm": round(sum(c["area_m2"] * ec["h_current_mm"] for c, ec in zip(cells, eval_cells)) / area, 3),
            "lot_mean_accumulated_erosion_mm": round(sum(c["area_m2"] * ec["accumulated_erosion_mm"] for c, ec in zip(cells, eval_cells)) / area, 3),
            "lot_mean_temp": round(sum(c["area_m2"] * ec["mean_canopy_temp"] for c, ec in zip(cells, eval_cells)) / area, 2),
            "lot_mean_eta_nutrientes": round(sum(c["area_m2"] * ec["eta_nutrientes"] for c, ec in zip(cells, eval_cells)) / area, 3),
            "irrigation_alert": any(ec["is_irrigation_needed"] for ec in eval_cells),
            "suggested_irrigation_mm": round(max(ec["suggested_irrigation_mm"] for ec in eval_cells), 2),
            "cells": [
                {
                    "soil_water_mm": round(ec["soil_water_mm"], 2),
                    "nutrientes_n_kg_ha": round(ec["nutrientes_n_kg_ha"], 2),
                    "nutrientes_p_kg_ha": round(ec["nutrientes_p_kg_ha"], 2),
                    "nutrientes_k_kg_ha": round(ec["nutrientes_k_kg_ha"], 2),
                    "biomass_t_ha": round(ec["biomass_t_ha"], 3),
                    "canopy_cover_pct": ec["canopy_cover_pct"],
                    "ndvi_satelital": ec["ndvi_satelital"],
                    "h_current_mm": round(ec["h_current_mm"], 4),
                    "accumulated_erosion_mm": round(ec["accumulated_erosion_mm"], 4),
                    "rain_height_variation_mm": ec["rain_height_variation_mm"],
                    "visual_height_delta_m": ec["visual_height_delta_m"],
                    "soil_vitality_index": ec["soil_vitality_index"],
                    "soil_color_rgb": list(ec["soil_color_rgb"]),
                    "base_soil_color_rgb": list(ec["base_soil_color_rgb"]),
                    "shield_enabled": ec["shield_enabled"],
                    "eta_lissajous": ec["eta_lissajous"],
                    "shield_score": ec["shield_score"],
                    "shield_state": ec["shield_state"],
                    "shield_color_rgb": list(ec["shield_color_rgb"]),
                    "hourly_environmental_index": [round(v, 4) for v in ec["hourly_environmental_index"]],
                    "hourly_shield_score": [round(v, 4) for v in ec["hourly_shield_score"]] if ec["hourly_shield_score"] else None,
                    "hourly_air_temps": [round(v, 2) for v in ec["hourly_air_temps"]],
                    "hourly_canopy_temps": [round(v, 2) for v in ec["hourly_canopy_temps"]],
                    "lissajous_area": round(ec["lissajous_area"], 3),
                    "mean_canopy_temp": round(ec["mean_canopy_temp"], 2),
                    "eta_nutrientes": round(ec["eta_nutrientes"], 4),
                    "water_condition_index": ec["water_condition_index"],
                    "is_irrigation_needed": ec["is_irrigation_needed"],
                    "suggested_irrigation_mm": round(ec["suggested_irrigation_mm"], 2),
                }
                for ec in eval_cells
            ],
        })

    ensemble_phase_stats = []
    ensemble_daily_records = []
    for scenario in mc_scenarios:
        _, _, _, _, pstats, drecords = _simulate_plan_trajectory(
            plan,
            phases,
            scenario,
            first,
            last,
            mean_slope,
            altitude_offset_c=0.0,
            collect_stats=True,
        )
        ensemble_phase_stats.append(pstats)
        ensemble_daily_records.append(drecords)

    phase_forecasts = _build_phase_forecasts(plan, phases, ensemble_phase_stats)
    monthly_forecast = _build_monthly_forecast(forecast["summary"]["monthly"], ensemble_daily_records)
    overall_viable = sum(1 for run in ensemble_phase_stats if all(p["viable"] for p in run))
    overall_confidence_pct = round(100.0 * overall_viable / len(ensemble_phase_stats), 1)

    for output, field in [
        ("lot_mean_soil_water_mm", "soil_water_mm"), ("lot_mean_n_kg_ha", "nutrientes_n_kg_ha"),
        ("lot_mean_p_kg_ha", "nutrientes_p_kg_ha"), ("lot_mean_k_kg_ha", "nutrientes_k_kg_ha"),
        ("lot_mean_biomass_t_ha", "biomass_t_ha"), ("lot_mean_h_mm", "h_current_mm"),
        ("lot_mean_temp", "mean_canopy_temp"), ("lot_mean_eta_nutrientes", "eta_nutrientes"),
    ]:
        result[output] = sum(cell["area_m2"] * cell[field] for cell in cells) / area
    result["irrigation_alert"] = any(cell["is_irrigation_needed"] for cell in cells)
    result["suggested_irrigation_mm"] = max(cell["suggested_irrigation_mm"] for cell in cells)
    result.update(
        date=target.isoformat(),
        timestamps=timestamps,
        thermal_reference_date=observed_day.isoformat(),
        crop=crop.name,
        crop_id=crop.key,
        phase="cultivo" if growing else "transicion",
        climate_source=climate_source,
        plan_simulation=True,
        montecarlo_confidence_pct=overall_confidence_pct,
        phase_forecasts=phase_forecasts,
        monthly_forecast=monthly_forecast,
        timeline_snapshots=timeline_snapshots,
        climate_forecast={
            **forecast["metadata"],
            "overall_confidence_pct": overall_confidence_pct,
            "climate_summary": forecast["summary"]["overall"],
            "phase_forecasts": phase_forecasts,
            "monthly_forecast": monthly_forecast,
        },
    )
    return result
