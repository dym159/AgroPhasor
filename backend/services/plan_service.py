"""Replay dated phases on each terrain cell with the coupled daily solver."""
from datetime import date, timedelta
from dataclasses import replace
from backend.core.edo1_engine import simulate_canopy_diurnal_cycle, compute_shield_state_and_color
from backend.core.edo2_engine import compute_soil_limits, relative_stomatal_conductance
from backend.core.edo3_engine import compute_liebig_factor
from backend.core.physics import thermal_comfort_index
from backend.core.edo4_engine import execute_harvest_event, execute_partial_cut
from backend.core.edo5_engine import (
    compute_soil_color,
    compute_soil_vitality_index,
    compute_terrain_height_variation,
)
from backend.models.crop_parameters import CROP_CATALOG, GLOBAL_CONSTANTS
from backend.services.coupled_model import advance_day, incorporate_residue


def replay_plan(result, phases, selected_date):
    from backend.services.rotation_service import load_climate, number
    if not isinstance(phases, list) or not 1 <= len(phases) <= 12:
        raise ValueError("El plan debe tener entre 1 y 12 fases.")
    plan = []
    for phase in phases:
        crop = CROP_CATALOG.get(phase.get("cropId"))
        if crop is None or crop.key == "suelo_desnudo_transicion":
            raise ValueError("Asigna un cultivo modelado a cada fase.")
        start = date.fromisoformat(phase["start"])
        end = date.fromisoformat(phase["harvest"])
        if end <= start or (plan and start < plan[-1][1]):
            raise ValueError("Las fases deben tener fechas ordenadas y no superponerse.")
        number(phase.get("residue_fraction", .5), 0, 1, "Fracción de rastrojo")
        number(phase.get("irrigation_mm_day", 0), 0, 30, "Riego")
        plan.append((start, end, crop))
    target = date.fromisoformat(selected_date)
    first = plan[0][0]
    if not first <= target <= plan[-1][1] or (target - first).days > 3650:
        raise ValueError("La fecha de consulta debe estar dentro del plan, hasta diez años.")
    cells = result["cells"]
    latitude = sum(c["latitude"] for c in cells) / len(cells)
    longitude = sum(c["longitude"] for c in cells) / len(cells)
    altitude = sum(c["altitude_m"] for c in cells) / len(cells)
    climate = load_climate(round(latitude, 3), round(longitude, 3))
    from backend.services.parcel_edo1 import load_power
    reference_day = date(2023, target.month, min(target.day, 28) if target.month == 2 else target.day)
    observed_day, hourly, radiation_mj = load_power(longitude, latitude, reference_day)
    timestamps = sorted(hourly["T2M"])
    for cell in cells:
        state = (104., (100., 40., 120.), 400., plan[0][2].B0_t_ha, ())
        organic_matter = 3.0
        day = first
        stage = 0
        crop = plan[0][2]
        diagnostic = None
        while day <= target:
            start, end, crop = plan[stage]
            if day == end:
                harvest = execute_harvest_event(state[3], crop, phases[stage].get("residue_fraction", .5))
                state = (*state[:3], harvest.residue_left_t_ha, state[4])
            if stage + 1 < len(plan) and day == plan[stage + 1][0]:
                organic_matter = incorporate_residue(organic_matter, state[3], state[2])
                stage += 1
                start, end, crop = plan[stage]
                state = (*state[:3], crop.B0_t_ha, state[4])
            growing = start <= day < end
            key = (2, 28) if (day.month, day.day) == (2, 29) else (day.month, day.day)
            rain, temp, humidity, radiation = climate[key]
            temp -= .0065 * (cell["altitude_m"] - altitude)
            state, diagnostic = advance_day(state, crop, (rain, temp, humidity, radiation),
                                            cell["slope_deg"], irrigation=phases[stage].get("irrigation_mm_day", 0) if growing else 0,
                                            growing=growing, soil_om=organic_matter)
            day += timedelta(days=1)
        water, nutrients, depth, biomass, _ = state
        limits = compute_soil_limits(crop, depth_mm=depth)
        thermal_crop = replace(crop, W_fc=limits.w_cc, W_pmp=limits.w_pmp, W_crit=limits.w_crit)
        if not growing:
            thermal_crop = replace(thermal_crop, gamma_max=0, lambda_gamma_max=0, Cp=18000, alpha=.72, hc=24)
        air = [hourly["T2M"][ts] - .0065 * (cell["altitude_m"] - altitude) for ts in timestamps]
        thermal = simulate_canopy_diurnal_cycle(
            air, [hourly["ALLSKY_SFC_SW_DWN"][ts] / .0036 if radiation_mj
                  else hourly["ALLSKY_SFC_SW_DWN"][ts] for ts in timestamps],
            [hourly["RH2M"][ts] for ts in timestamps], water, thermal_crop)
        eta_n = compute_liebig_factor(*nutrients, crop.K_N, crop.K_P, crop.K_K)[0]
        eta_w = relative_stomatal_conductance(water, limits)
        thermal_comfort = [thermal_comfort_index(t, crop.T_opt, crop.delta_T_tol) for t in thermal["t_canopy_hourly"]]
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

        height_var = compute_terrain_height_variation(
            precip_mm=rain,
            accumulated_erosion_mm=400.0 - depth,
            slope_deg=cell.get("slope_deg", 0.0),
            biomass_t_ha=biomass,
            is_transition=not growing,
            altitude_m=cell.get("altitude_m", altitude),
        )
        soil_color = compute_soil_color(
            retention_ratio=depth / 400.0,
            eta_nutrientes=eta_n,
            water_saturation=eta_w,
        )
        soil_vitality = compute_soil_vitality_index(
            retention_ratio=depth / 400.0,
            eta_nutrientes=eta_n,
            water_saturation=eta_w,
        )

        cell.update(
            soil_water_mm=water, nutrientes_n_kg_ha=nutrients[0], nutrientes_p_kg_ha=nutrients[1],
            nutrientes_k_kg_ha=nutrients[2], biomass_t_ha=biomass, h_current_mm=depth,
            accumulated_erosion_mm=400-depth,
            rain_height_variation_mm=height_var["rain_height_variation_mm"],
            visual_height_delta_m=height_var["visual_height_delta_m"],
            soil_vitality_index=soil_vitality,
            soil_color_rgb=soil_color,
            shield_enabled=growing,
            eta_lissajous=eta_l if growing else 0.0,
            shield_score=shield_eval["shield_score"] if growing else 0.0,
            shield_state=shield_eval["shield_state"],
            shield_color_rgb=shield_eval["shield_color_rgb"],
            hourly_environmental_index=indices,
            hourly_shield_score=shield_scores if growing else None,
            hourly_air_temps=air, hourly_canopy_temps=thermal["t_canopy_hourly"],
            lissajous_area=thermal["lissajous_area"], mean_canopy_temp=thermal["mean_canopy_temp"],
            eta_nutrientes=eta_n,
            is_irrigation_needed=growing and diagnostic["irrigation_needed"],
            suggested_irrigation_mm=diagnostic["suggested_irrigation_mm"] if growing else 0,
        )
    area = sum(cell["area_m2"] for cell in cells)
    for output, field in [
        ("lot_mean_soil_water_mm", "soil_water_mm"), ("lot_mean_n_kg_ha", "nutrientes_n_kg_ha"),
        ("lot_mean_p_kg_ha", "nutrientes_p_kg_ha"), ("lot_mean_k_kg_ha", "nutrientes_k_kg_ha"),
        ("lot_mean_biomass_t_ha", "biomass_t_ha"), ("lot_mean_h_mm", "h_current_mm"),
        ("lot_mean_temp", "mean_canopy_temp"), ("lot_mean_eta_nutrientes", "eta_nutrientes"),
    ]:
        result[output] = sum(cell["area_m2"] * cell[field] for cell in cells) / area
    result["irrigation_alert"] = any(cell["is_irrigation_needed"] for cell in cells)
    result["suggested_irrigation_mm"] = max(cell["suggested_irrigation_mm"] for cell in cells)
    result.update(date=target.isoformat(), timestamps=timestamps, thermal_reference_date=observed_day.isoformat(),
                  crop=crop.name, crop_id=crop.key, phase="cultivo" if growing else "transicion",
                  climate_source="NASA POWER 2023 · repetición histórica",
                  plan_simulation=True)
    return result
