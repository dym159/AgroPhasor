"""Replay dated phases on each terrain cell with Monte Carlo climate forecasting."""
from datetime import date, timedelta
from dataclasses import replace
import math
import numpy as np

from backend.core.climate_generator import mc_day_to_weather
from backend.core.edo1_engine import simulate_canopy_diurnal_cycle
from backend.core.edo2_engine import compute_soil_limits, relative_stomatal_conductance
from backend.core.edo3_engine import compute_liebig_factor
from backend.core.physics import saturation_vapor_pressure, thermal_comfort_index
from backend.core.edo4_engine import execute_harvest_event
from backend.core.edo5_engine import compute_soil_color
from backend.models.crop_parameters import CROP_CATALOG
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


def _simulate_plan_trajectory(
    plan,
    phases,
    daily_climate,
    first_day,
    end_day,
    slope_deg,
    altitude_offset_c=0.0,
    collect_stats=False,
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
    target_weather = rep_daily[target_offset]
    base_air_ref = [hourly["T2M"][ts] for ts in timestamps]
    base_rad_wm2 = [
        hourly["ALLSKY_SFC_SW_DWN"][ts] / .0036 if radiation_mj else hourly["ALLSKY_SFC_SW_DWN"][ts]
        for ts in timestamps
    ]
    if forecast_active and isinstance(target_weather, dict):
        temp_shift = target_weather["T_NASA"] - (sum(base_air_ref) / len(base_air_ref))
        mean_rad = sum(base_rad_wm2) / len(base_rad_wm2)
        rad_scale = max(0.2, min(2.5, target_weather["f_rad_W_m2"] / mean_rad)) if mean_rad > 10.0 else 1.0
        base_air = [t + temp_shift for t in base_air_ref]
        base_rad = [r * rad_scale for r in base_rad_wm2]
        target_ea_kpa = target_weather["e_a_kPa"]
    else:
        base_air = base_air_ref
        base_rad = base_rad_wm2
        target_ea_kpa = None

    for cell in cells:
        alt_offset_c = -.0065 * (cell["altitude_m"] - altitude)
        state, diagnostic, growing, crop, _, _ = _simulate_plan_trajectory(
            plan,
            phases,
            rep_daily,
            first,
            target,
            cell["slope_deg"],
            altitude_offset_c=alt_offset_c,
            collect_stats=False,
        )
        water, nutrients, depth, biomass, _ = state
        limits = compute_soil_limits(crop, depth_mm=depth)
        thermal_crop = replace(crop, W_fc=limits.w_cc, W_pmp=limits.w_pmp, W_crit=limits.w_crit)
        if not growing:
            thermal_crop = replace(thermal_crop, gamma_max=0, lambda_gamma_max=0, Cp=18000, alpha=.72, hc=24)
        air = [t + alt_offset_c for t in base_air]
        if target_ea_kpa is not None:
            rh_hourly = [
                max(5.0, min(100.0, 100.0 * target_ea_kpa / max(1e-6, saturation_vapor_pressure(t))))
                for t in air
            ]
        else:
            rh_hourly = [hourly["RH2M"][ts] for ts in timestamps]
        thermal = simulate_canopy_diurnal_cycle(air, base_rad, rh_hourly, water, thermal_crop)
        eta_n = compute_liebig_factor(*nutrients, crop.K_N, crop.K_P, crop.K_K)[0]
        eta_w = relative_stomatal_conductance(water, limits)
        indices = [thermal_comfort_index(t, crop.T_opt, crop.delta_T_tol) * eta_w * eta_n
                   for t in thermal["t_canopy_hourly"]]

        cell.update(
            soil_water_mm=water, nutrientes_n_kg_ha=nutrients[0], nutrientes_p_kg_ha=nutrients[1],
            nutrientes_k_kg_ha=nutrients[2], biomass_t_ha=biomass, h_current_mm=depth,
            accumulated_erosion_mm=400-depth, soil_color_rgb=compute_soil_color(depth/400),
            shield_enabled=growing, hourly_environmental_index=indices,
            hourly_air_temps=air, hourly_canopy_temps=thermal["t_canopy_hourly"],
            lissajous_area=thermal["lissajous_area"], mean_canopy_temp=thermal["mean_canopy_temp"],
            eta_nutrientes=eta_n,
            is_irrigation_needed=growing and diagnostic["irrigation_needed"],
            suggested_irrigation_mm=diagnostic["suggested_irrigation_mm"] if growing else 0,
        )

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
        climate_forecast={
            **forecast["metadata"],
            "overall_confidence_pct": overall_confidence_pct,
            "climate_summary": forecast["summary"]["overall"],
            "phase_forecasts": phase_forecasts,
            "monthly_forecast": monthly_forecast,
        },
    )
    return result
