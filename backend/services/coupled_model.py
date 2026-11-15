"""Coupled daily column model used by rotation trajectories."""
from dataclasses import replace
from backend.core.edo1_engine import solve_edo1_step
from backend.core.edo2_engine import compute_soil_limits, solve_edo2_step, relative_stomatal_conductance
from backend.core.edo3_engine import solve_edo3_step, SoilChemicalProperties
from backend.core.edo4_engine import solve_edo4_step
from backend.core.edo5_engine import solve_edo5_step
from backend.core.physics import thermal_comfort_index


def advance_day(state, crop, weather, slope, irrigation=0, growing=True, soil_om=3.0):
    """State holds water in mm independently of crop root depth."""
    water, npk, depth, biomass, history = state
    rain, air, humidity, radiation = weather
    limits = compute_soil_limits(crop, depth_mm=depth)
    crop = replace(crop, W_fc=limits.w_cc, W_pmp=limits.w_pmp, W_crit=limits.w_crit)
    thermal_crop = crop if growing else replace(crop, gamma_max=0, lambda_gamma_max=0,
                                                Cp=18000, alpha=.72, hc=24)
    canopy = solve_edo1_step(air, air, radiation / .0864, humidity, water,
                             thermal_crop, dt_seconds=86400).t_canopy_c
    temperatures = (*history, air)[-7:]
    hyd = solve_edo2_step(water, rain, air, humidity, slope, crop,
                         irrigation_mm=irrigation, biomass_t_ha=biomass,
                         is_crop=growing, depth_mm=depth, canopy_temp_c=canopy)
    erosion = solve_edo5_step(depth, rain, slope, biomass, is_transition=not growing)
    chemistry = solve_edo3_step(*npk, water, limits.w_cc, sum(temperatures)/len(temperatures),
                                crop, soil=SoilChemicalProperties(om_pct=soil_om), biomass_t_ha=biomass,
                                erosion_rate_mm_day=erosion.erosion_loss_step_mm, is_crop=growing)
    growth = solve_edo4_step(biomass, radiation, canopy, water, *npk, crop, q_is_crop=growing)
    new_water = min(hyd.soil_water_mm, .30 * erosion.h_current_mm)
    psi = (thermal_comfort_index(canopy, crop.T_opt, crop.delta_T_tol)
           * relative_stomatal_conductance(new_water, limits) * chemistry.eta_nutrientes) if growing else 0
    return (
        (new_water, (chemistry.n_kg_ha, chemistry.p_kg_ha, chemistry.k_kg_ha),
         erosion.h_current_mm, growth.biomass_t_ha, temperatures),
        {"psi": psi, "canopy": canopy, "irrigation_needed": hyd.is_irrigation_needed,
         "suggested_irrigation_mm": hyd.suggested_irrigation_mm,
         "viable": not growing or crop.T_frost < canopy < crop.T_lethal,
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
