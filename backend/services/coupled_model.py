"""Coupled daily column model used by rotation trajectories."""
from dataclasses import replace
import math
from backend.core.edo1_engine import solve_edo1_step
from backend.core.edo2_engine import compute_soil_limits, solve_edo2_step, relative_stomatal_conductance
from backend.core.edo3_engine import solve_edo3_step, SoilChemicalProperties
from backend.core.edo4_engine import solve_edo4_step
from backend.core.edo5_engine import solve_edo5_step
from backend.core.physics import thermal_comfort_index
from backend.core.physics import penman_saturation_slope
from backend.models.crop_parameters import GLOBAL_CONSTANTS


def advance_day(state, crop, weather, slope, irrigation=0, growing=True, soil_om=3.0, dt_days=1.0):
    """Paso multiescala: estados lentos congelados en t; temperatura subintegrada.

    history acepta temperaturas antiguas o pares (aire, dosel), conservando T.
    Forzantes de lluvia/riego en mm/día y radiación en MJ/m²/día.
    """
    if not math.isfinite(dt_days) or dt_days <= 0:
        raise ValueError("dt_days debe ser positivo y finito.")
    water, npk, depth, biomass, history = state
    rain, air, humidity, radiation = weather
    limits = compute_soil_limits(crop, depth_mm=depth)
    crop = replace(crop, W_fc=limits.w_cc, W_pmp=limits.w_pmp, W_crit=limits.w_crit)
    thermal_crop = crop if growing else replace(crop, gamma_max=0, lambda_gamma_max=0,
                                                Cp=18000, alpha=.72, hc=24)
    old_canopy = history[-1][1] if history and isinstance(history[-1], (tuple,list)) else air
    canopy = old_canopy
    remaining = dt_days*86400
    # Recalcular Qlat en subpasos estables; Penman solo estima el paso,
    # nunca sustituye la ecuación térmica de flujo latente congelado del PDF.
    while remaining > 1e-8:
        stiffness = thermal_crop.hc + thermal_crop.lambda_gamma_max*penman_saturation_slope(max(air,canopy))
        seconds = min(remaining, .5*thermal_crop.Cp/max(stiffness,1e-8))
        previous_canopy = canopy
        canopy = solve_edo1_step(canopy, air, radiation/.0864, humidity, water,
                                thermal_crop, dt_seconds=seconds).t_canopy_c
        remaining -= seconds
        if abs(canopy-previous_canopy) <= 1e-10:
            # Forzantes constantes: equilibrio térmico alcanzado a tolerancia.
            break
    temperatures = (*history, (air,canopy))[-7:]
    soil_temperature = sum(t[0] if isinstance(t,(tuple,list)) else t for t in temperatures)/len(temperatures)
    hyd = solve_edo2_step(water, rain, air, humidity, slope, crop,
                         irrigation_mm=irrigation, biomass_t_ha=biomass,
                         is_crop=growing, depth_mm=depth, canopy_temp_c=old_canopy, dt_days=dt_days,
                         is_daylight=radiation/.0864 > 5)
    erosion = solve_edo5_step(depth, rain, slope, biomass, is_transition=not growing, dt_days=dt_days)
    kdec = float(GLOBAL_CONSTANTS.get('k_dec_dia',.025))
    growth = solve_edo4_step(biomass, radiation, old_canopy, water, *npk, crop,
                            q_is_crop=growing, dt_days=dt_days, k_dec_daily=kdec)
    # Durante transición, integrar liberación de K con el rastrojo realmente
    # descompuesto; evita contar beta*kdec*B0*dt como si B no cambiara.
    chemical_biomass = biomass if growing or kdec == 0 else (biomass-growth.biomass_t_ha)/(kdec*dt_days)
    chemistry = solve_edo3_step(*npk, water, limits.w_cc, soil_temperature,
                                crop, soil=SoilChemicalProperties(om_pct=soil_om), biomass_t_ha=chemical_biomass,
                                erosion_rate_mm_day=erosion.erosion_loss_step_mm/dt_days, is_crop=growing, dt_days=dt_days)
    new_water = min(hyd.soil_water_mm, .30 * erosion.h_current_mm)
    new_limits = compute_soil_limits(crop, depth_mm=erosion.h_current_mm)
    psi = (thermal_comfort_index(canopy, crop.T_opt, crop.delta_T_tol)
           * relative_stomatal_conductance(new_water, new_limits) * chemistry.eta_nutrientes) if growing else 0
    return (
        (new_water, (chemistry.n_kg_ha, chemistry.p_kg_ha, chemistry.k_kg_ha),
         erosion.h_current_mm, growth.biomass_t_ha, temperatures),
        {"psi": psi, "canopy": canopy, "irrigation_needed": hyd.is_irrigation_needed,
         "suggested_irrigation_mm": hyd.suggested_irrigation_mm,
         "viable": not growing or crop.T_frost < canopy < crop.T_lethal,
         "capacity_runoff_mm": hyd.soil_water_mm-new_water,
         "water_infiltration_mm": hyd.infiltration_mm,
         "water_etc_mm": hyd.etc_mm,
         "water_drainage_mm": hyd.drainage_mm,
         "water_runoff_mm": hyd.runoff_mm + hyd.soil_water_mm-new_water,
         "water_stress": 1 - hyd.gamma_c_relative},
    )


def incorporate_residue(organic_matter_pct, residue_t_ha, depth_mm, bulk_density_t_m3=1.3):
    """Mix retained dry matter into the modeled soil horizon.

    Default bulk density is a reference assumption, not a measured property.
    A hectare of depth H mm has volume 10*H m3.
    """
    soil_mass = 10 * depth_mm * bulk_density_t_m3
    if soil_mass <= 0:
        return organic_matter_pct
    return min(100.0, organic_matter_pct + 100 * residue_t_ha / soil_mass)
