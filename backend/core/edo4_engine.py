"""
Agrophysical Solver Engine for ODE 4 (AgroPhasor).
Implements the differential equation for Biomass Growth and Stover Decomposition B_{i,j}(t) (t/ha),
its biophysical constitutive relations, hybrid discrete harvest and planting jumps,
and satellite remote-sensing projection/calibration (Landsat/MODIS/GEDI), per AgroPhasor.pdf (Sections 3.2.4, 3.3, 3.4, and 1.5).

Governing equations:
1. Active Crop Regime q(t) = Crop(c_k):
   dB/dt = k_p,c * f_rad(t) * eta_T(T) * f_W(W) * eta_N(N,P,K) * (1 - B / B_max) - k_m,c(T) * B
   where:
   - k_p,c: Photochemical radiation-conversion efficiency [t / (ha · (MJ/m² or W/m²))]
   - f_rad: Projected incident photosynthetically active radiation (NASA POWER + SRTM)
   - eta_T(T): Photosynthetic thermal comfort envelope (NASA POWER / ECOSTRESS / ODE 1)
   - f_W(W): Water limitation factor W / (W + K_W) (NASA SMAP / GPM / ODE 2)
   - eta_N: Liebig's Law of the Minimum min(N/(N+KN), P/(P+KP), K/(K+KK)) (USDA SSURGO / ODE 3)
   - (1 - B / B_max): Biological carrying capacity / logistic saturation brake (FAO GAEZ / GEDI)
   - k_m,c(T): Temperature-modulated maintenance respiration rate (Q10)

2. Transition / Stover Regime q(t) = Transition:
   dB/dt = - k_dec * B

3. Discrete Hybrid Transition Jumps:
   - Harvest: Commercial yield Y_k = HI * (1 - r_res) * B(t^-)
              Retained residual stover: B(t^+) = r_res * B(t^-)
   - Planting: Residual stover incorporation into organic matter delta_OM = xi_OM * B(t^-)
               Basal germination biomass initialization: B(t^+) = B0,c_k+1
"""

import math
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union

from backend.models.crop_parameters import CropParameters, get_crop_parameters


@dataclass
class EDO4StepOutput:
    """Agrophysical output of a single ODE 4 simulation step."""
    biomass_t_ha: float              # Resulting above-ground biomass B(t+dt) [t/ha]
    db_dt: float                     # Net rate of change dB/dt [t/(ha · day)]
    gross_growth_t_ha: float         # Gross accumulated photosynthesis in step [t/ha]
    maintenance_loss_t_ha: float     # Maintenance respiration loss [t/ha]
    eta_thermal: float               # Photosynthetic thermal efficiency eta_T [0, 1]
    eta_water: float                 # Water availability factor f_W [0, 1]
    eta_nutrients: float             # Liebig chemical efficiency eta_N [0, 1]
    limiting_nutrient: str           # Most limiting nutrient ('N', 'P', 'K', or 'None')
    logistic_brake: float            # Logistic saturation brake (1 - B/Bmax) [0, 1]
    canopy_cover_fraction: float     # Effective canopy cover fraction (1 - e^(-lambda_B * B)) [0, 1]
    simulated_ndvi: float            # Equivalent satellite NDVI (Landsat / MODIS proxy)
    is_growth_active: bool           # True when net photosynthesis is positive
    is_drought_arrest: bool          # Growth arrest alert due to extreme drought
    is_thermal_arrest: bool          # Photosynthesis arrest alert due to frost/heat stress
    is_nutrient_arrest: bool         # Growth arrest alert due to chemical depletion


@dataclass
class EDO4HarvestResult:
    """Result of a discrete harvest and transition event."""
    crop_name: str
    biomass_pre_harvest_t_ha: float  # B(t_s^-)
    harvest_index_hi: float          # HI
    residue_fraction_rres: float     # r_res
    commercial_yield_t_ha: float     # Y_k = HI * (1 - r_res) * B(t^-)
    residue_left_t_ha: float         # B(t_s^+) = r_res * B(t^-)
    market_price_usd_t: float        # Market price (USDA AMS)
    gross_revenue_usd_ha: float      # Y_k * Market price
    base_cost_usd_ha: float          # Input and labor cost
    net_margin_usd_ha: float         # Net margin per hectare


def thermal_photosynthetic_efficiency(
    temp_canopy_c: float,
    t_opt_c: float,
    delta_t_tol_c: float,
    t_frost_c: float = 0.0,
    t_lethal_c: float = 45.0
) -> float:
    """
    Photosynthetic thermal efficiency bell curve eta_T(T) (PDF Sec. 3.3 and 1.3):
    eta_T = max(0, 1 - ((T - T_opt) / delta_T_tol)^2)
    Strictly zero outside survival boundaries: T <= T_frost or T >= T_lethal.
    """
    if temp_canopy_c <= t_frost_c or temp_canopy_c >= t_lethal_c:
        return 0.0
    diff = (temp_canopy_c - t_opt_c) / max(1e-3, delta_t_tol_c)
    val = 1.0 - (diff ** 2)
    return max(0.0, min(1.0, val))


def water_limitation_factor(
    soil_water_mm: float,
    w_pmp_mm: float,
    w_crit_mm: float,
    k_w_mm: Optional[float] = None,
    epsilon: float = 1e-4
) -> float:
    """
    Water limitation factor f_W(W) (PDF Sec. 3.2.4 and 3.3):
    Saturation f_W = W / (W + K_W). K_W is estimated from thresholds
    when the caller does not provide a calibrated value.
    """
    
    if k_w_mm is None:
        # Automatic biophysical calibration of K_W from root hydraulic limits
        k_w_mm = max(1.0, 0.5 * (w_crit_mm - w_pmp_mm))
        
    usable_water = max(0.0, soil_water_mm)
    factor = usable_water / (usable_water + k_w_mm)
    return max(0.0, min(1.0, factor))


def liebig_nutrient_efficiency(
    nitrogen_kg_ha: float,
    phosphorus_kg_ha: float,
    potassium_kg_ha: float,
    k_n: float,
    k_p: float,
    k_k: float,
    epsilon: float = 1e-4
) -> Tuple[float, str]:
    """
    Photosynthetic chemical factor under Liebig's Law of the Minimum (PDF Sec. 3.3 and 1.2):
    eta_N = min( N/(N+KN), P/(P+KP), K/(K+KK) )
    Returns (eta_N, limiting_nutrient).
    """
    f_n = max(0.0, nitrogen_kg_ha) / max(epsilon, max(0.0, nitrogen_kg_ha) + k_n)
    f_p = max(0.0, phosphorus_kg_ha) / max(epsilon, max(0.0, phosphorus_kg_ha) + k_p)
    f_k = max(0.0, potassium_kg_ha) / max(epsilon, max(0.0, potassium_kg_ha) + k_k)

    min_val = min(f_n, f_p, f_k)
    
    if min_val == f_n:
        limiting = "N"
    elif min_val == f_p:
        limiting = "P"
    else:
        limiting = "K"
        
    return min_val, limiting


def biomass_to_canopy_cover(biomass_t_ha: float, lambda_b: float = 0.45) -> float:
    """
    Canopy foliar cover fraction f_cover (PDF Sec. 3.3):
    f_cover = 1 - exp(-lambda_B * B)
    Controls soil shading, direct evaporation attenuation, and erosion shielding.
    """
    return max(0.0, min(1.0, 1.0 - math.exp(-lambda_b * max(0.0, biomass_t_ha))))


def biomass_to_satellite_ndvi(
    biomass_t_ha: float,
    ndvi_soil: float = 0.15,
    ndvi_max: float = 0.88,
    lambda_b: float = 0.45
) -> float:
    """
    Theoretical projection of simulated biomass onto satellite NDVI (Landsat / MODIS):
    NDVI = NDVI_soil + (NDVI_max - NDVI_soil) * (1 - exp(-lambda_B * B))
    Enables direct comparison between digital twin state and satellite overpasses.
    """
    cover = biomass_to_canopy_cover(biomass_t_ha, lambda_b)
    ndvi = ndvi_soil + (ndvi_max - ndvi_soil) * cover
    return round(max(ndvi_soil, min(ndvi_max, ndvi)), 3)


def satellite_ndvi_to_biomass(
    ndvi: float,
    ndvi_soil: float = 0.15,
    ndvi_max: float = 0.88,
    lambda_b: float = 0.45,
    b_max_t_ha: float = 20.0
) -> float:
    """
    Empirical remote-sensing inversion: estimates biomass [t/ha] from satellite NDVI.
    """
    if ndvi <= ndvi_soil:
        return 0.0
    clamped_ndvi = min(ndvi_max - 1e-4, max(ndvi_soil + 1e-4, ndvi))
    fraction = (clamped_ndvi - ndvi_soil) / (ndvi_max - ndvi_soil)
    fraction = min(0.999, max(0.0, fraction))
    b_est = -math.log(1.0 - fraction) / lambda_b
    return min(b_max_t_ha, max(0.0, b_est))


def solve_edo4_step(
    b_current_t_ha: float,
    f_rad_daily_mj_m2: float,
    temp_canopy_c: float,
    soil_water_mm: float,
    nitrogen_kg_ha: float,
    phosphorus_kg_ha: float,
    potassium_kg_ha: float,
    crop: CropParameters,
    q_is_crop: bool = True,
    k_dec_daily: float = 0.025,
    lambda_b: float = 0.45,
    q10: float = 2.0,
    dt_days: float = 1.0,
    epsilon: float = 1e-5
) -> EDO4StepOutput:
    """
    Solves one time step dt of ODE 4 for a grid cell (i, j).
    
    Applies an exact conditioned exponential integration:
    dB/dt = A * (1 - B / Bmax) - km * B
    rewritten linearly as:
    dB/dt + lambda_eff * B = A
    with lambda_eff = (A / Bmax) + km >= 0.
    
    This analytical formulation guarantees:
    1. Unconditional stability (does not blow up for large dt steps).
    2. Strict physical bounds 0 <= B(t) <= Bmax.
    3. Biomass conservation and exact monotonic decay in transition mode.
    """
    if not math.isfinite(dt_days) or dt_days <= 0 or crop.B_max_t_ha <= 0:
        raise ValueError("dt_days and B_max must be positive and finite.")
    b_curr = max(0.0, float(b_current_t_ha))
    if q_is_crop:
        b_curr = min(crop.B_max_t_ha, b_curr)

    if not q_is_crop:
        # Transition / Bare Soil / Stover Decomposition Mode:
        # dB/dt = - k_dec * B
        # Exact solution: B(t+dt) = B(t) * exp(-k_dec * dt)
        k_dec_eff = max(0.0, k_dec_daily)
        
        b_next = b_curr * math.exp(-k_dec_eff * dt_days)
        db_dt = (b_next - b_curr) / dt_days
        
        loss = b_curr - b_next
        cover = biomass_to_canopy_cover(b_next, lambda_b)
        ndvi = biomass_to_satellite_ndvi(b_next, lambda_b=lambda_b)

        return EDO4StepOutput(
            biomass_t_ha=b_next,
            db_dt=round(db_dt, 4),
            gross_growth_t_ha=0.0,
            maintenance_loss_t_ha=loss,
            eta_thermal=0.0,
            eta_water=0.0,
            eta_nutrients=0.0,
            limiting_nutrient="None",
            logistic_brake=1.0,
            canopy_cover_fraction=round(cover, 4),
            simulated_ndvi=ndvi,
            is_growth_active=False,
            is_drought_arrest=False,
            is_thermal_arrest=False,
            is_nutrient_arrest=False
        )

    # Active Crop Mode q(t) = Crop(c_k)
    # 1. Constitutive limiting factors
    eta_T = thermal_photosynthetic_efficiency(
        temp_canopy_c=temp_canopy_c,
        t_opt_c=crop.T_opt,
        delta_t_tol_c=crop.delta_T_tol,
        t_frost_c=crop.T_frost,
        t_lethal_c=crop.T_lethal
    )
    
    w_pmp = getattr(crop, "W_pmp", 20.0)
    w_crit = getattr(crop, "W_crit", 50.0)
    k_w = getattr(crop, "K_W_mm", None)
    eta_W = water_limitation_factor(
        soil_water_mm=soil_water_mm,
        w_pmp_mm=w_pmp,
        w_crit_mm=w_crit,
        k_w_mm=k_w
    )
    
    eta_N, limiting_nut = liebig_nutrient_efficiency(
        nitrogen_kg_ha=nitrogen_kg_ha,
        phosphorus_kg_ha=phosphorus_kg_ha,
        potassium_kg_ha=potassium_kg_ha,
        k_n=crop.K_N,
        k_p=crop.K_P,
        k_k=crop.K_K
    )

    # 2. Gross potential photosynthetic rate A [t / (ha · day)]
    # A = kp_c * f_rad * eta_T * eta_W * eta_N
    a_flux = crop.kp_c * max(0.0, f_rad_daily_mj_m2) * eta_T * eta_W * eta_N

    # 3. Thermally modulated maintenance respiration via Q10
    km_base = getattr(crop, "km_c", 0.008)
    temp_factor_q10 = q10 ** ((temp_canopy_c - 20.0) / 10.0)
    km_eff = max(0.0, km_base * temp_factor_q10)

    # 4. Unconditionally stable analytical integrator
    # dB/dt = A * (1 - B/Bmax) - km * B = A - (A/Bmax + km)*B
    b_max = crop.B_max_t_ha
    lambda_eff = (a_flux / b_max) + km_eff
    
    if lambda_eff > 0:
        # Asymptotic steady-state equilibrium
        b_inf = a_flux / lambda_eff
        # B(t+dt) = b_inf + (B(t) - b_inf) * exp(-lambda_eff * dt)
        exp_factor = math.exp(-lambda_eff * dt_days)
        b_next = b_curr * exp_factor + a_flux * (-math.expm1(-lambda_eff * dt_days)) / lambda_eff
    else:
        b_next = b_curr

    # Strict physical bounds
    b_next = max(0.0, min(b_max, b_next))
    db_dt = (b_next - b_curr) / dt_days

    # Diagnostics and components
    logistic_brake = max(0.0, 1.0 - (b_curr / b_max))
    z = lambda_eff * dt_days
    phi = -math.expm1(-z) / z if z else 1.0
    phi2 = (0.5 - z / 6 + z * z / 24) if abs(z) < 1e-5 else (1 - phi) / z
    integral_b = b_curr * dt_days * phi + a_flux * dt_days ** 2 * phi2
    gross_growth = a_flux * (dt_days - integral_b / b_max)
    maint_loss = km_eff * integral_b
    cover = biomass_to_canopy_cover(b_next, lambda_b)
    ndvi = biomass_to_satellite_ndvi(b_next, lambda_b=lambda_b)

    is_growth_active = (db_dt > 0.001)
    is_drought_arrest = (eta_W <= 0.05)
    is_thermal_arrest = (eta_T <= 0.05)
    is_nutrient_arrest = (eta_N <= 0.10)

    return EDO4StepOutput(
        biomass_t_ha=b_next,
        db_dt=round(db_dt, 4),
        gross_growth_t_ha=gross_growth,
        maintenance_loss_t_ha=maint_loss,
        eta_thermal=round(eta_T, 3),
        eta_water=round(eta_W, 3),
        eta_nutrients=round(eta_N, 3),
        limiting_nutrient=limiting_nut,
        logistic_brake=round(logistic_brake, 3),
        canopy_cover_fraction=round(cover, 4),
        simulated_ndvi=ndvi,
        is_growth_active=is_growth_active,
        is_drought_arrest=is_drought_arrest,
        is_thermal_arrest=is_thermal_arrest,
        is_nutrient_arrest=is_nutrient_arrest
    )


def execute_partial_cut(
    biomass_current_t_ha: float,
    crop: CropParameters
) -> Tuple[float, float]:
    """
    Executes an intermediate partial cut for multi-harvest crops (e.g., Strawberry).
    Returns (cut_yield_t_ha, remaining_biomass_t_ha).
    """
    b_curr = max(0.0, float(biomass_current_t_ha))
    if not getattr(crop, "is_multiple_harvest", False):
        return 0.0, b_curr
    f_cut = max(0.0, min(1.0, float(getattr(crop, "partial_cut_fraction", 0.0))))
    cut_yield = f_cut * b_curr
    return cut_yield, b_curr - cut_yield


def execute_harvest_event(
    biomass_pre_harvest_t_ha: float,
    crop: CropParameters,
    residue_fraction_rres: Optional[float] = None,
    market_price_usd_t: Optional[float] = None,
    partial_yield_accumulated_t_ha: float = 0.0
) -> EDO4HarvestResult:
    """
    Executes the discrete harvest jump (PDF Sec. 3.4 and 1.1):
    1. Commercial harvestable yield: Y_k = Y_partial_acc + HI * (1 - r_res) * B(t_s^-)
    2. Protective stover residue retained in field: B(t_s^+) = r_res * B(t_s^-)
    3. Economic valuation based on USDA AMS Market News prices.
    """
    hi = getattr(crop, "HI", 0.45)
    if residue_fraction_rres is None:
        residue_fraction_rres = round(1.0 - hi, 3)
    r_res = max(0.0, min(1.0, residue_fraction_rres))
    
    price = market_price_usd_t if market_price_usd_t is not None else getattr(crop, "price_usd_t", 250.0)
    base_cost = getattr(crop, "base_cost_usd_ha", 600.0)

    b_pre = max(0.0, biomass_pre_harvest_t_ha)
    commercial_yield = max(0.0, partial_yield_accumulated_t_ha) + hi * (1.0 - r_res) * b_pre
    residue_left = r_res * b_pre
    
    gross_revenue = commercial_yield * price
    net_margin = gross_revenue - base_cost

    return EDO4HarvestResult(
        crop_name=crop.name,
        biomass_pre_harvest_t_ha=b_pre,
        harvest_index_hi=round(hi, 3),
        residue_fraction_rres=round(r_res, 3),
        commercial_yield_t_ha=commercial_yield,
        residue_left_t_ha=residue_left,
        market_price_usd_t=round(price, 2),
        gross_revenue_usd_ha=round(gross_revenue, 2),
        base_cost_usd_ha=round(base_cost, 2),
        net_margin_usd_ha=round(net_margin, 2)
    )


def simulate_edo4_timeseries(
    f_rad_series_mj_m2: List[float],
    t_canopy_series_c: List[float],
    soil_water_series_mm: List[float],
    nitrogen_series_kg_ha: List[float],
    phosphorus_series_kg_ha: List[float],
    potassium_series_kg_ha: List[float],
    crop: CropParameters,
    b0_t_ha: Optional[float] = None,
    q_is_crop: bool = True,
    k_dec_daily: float = 0.025,
    lambda_b: float = 0.45,
    dt_days: float = 1.0
) -> Dict[str, Any]:
    """
    Runs a complete ODE 4 time-series simulation for one cell over n days.
    """
    n_steps = len(f_rad_series_mj_m2)
    current_b = crop.B0_t_ha if b0_t_ha is None else b0_t_ha
    
    biomass_traj = [round(current_b, 4)]
    ndvi_traj = [biomass_to_satellite_ndvi(current_b, lambda_b=lambda_b)]
    cover_traj = [biomass_to_canopy_cover(current_b, lambda_b=lambda_b)]
    db_dt_traj = []
    eta_t_traj = []
    eta_w_traj = []
    eta_n_traj = []
    limiting_nuts = []

    active_growth_days = 0
    drought_stress_days = 0
    thermal_stress_days = 0
    nutrient_stress_days = 0

    for i in range(n_steps):
        step_out = solve_edo4_step(
            b_current_t_ha=current_b,
            f_rad_daily_mj_m2=f_rad_series_mj_m2[i],
            temp_canopy_c=t_canopy_series_c[i],
            soil_water_mm=soil_water_series_mm[i],
            nitrogen_kg_ha=nitrogen_series_kg_ha[i],
            phosphorus_kg_ha=phosphorus_series_kg_ha[i],
            potassium_kg_ha=potassium_series_kg_ha[i],
            crop=crop,
            q_is_crop=q_is_crop,
            k_dec_daily=k_dec_daily,
            lambda_b=lambda_b,
            dt_days=dt_days
        )
        current_b = step_out.biomass_t_ha
        biomass_traj.append(current_b)
        ndvi_traj.append(step_out.simulated_ndvi)
        cover_traj.append(step_out.canopy_cover_fraction)
        db_dt_traj.append(step_out.db_dt)
        eta_t_traj.append(step_out.eta_thermal)
        eta_w_traj.append(step_out.eta_water)
        eta_n_traj.append(step_out.eta_nutrients)
        limiting_nuts.append(step_out.limiting_nutrient)

        if step_out.is_growth_active:
            active_growth_days += 1
        if step_out.is_drought_arrest:
            drought_stress_days += 1
        if step_out.is_thermal_arrest:
            thermal_stress_days += 1
        if step_out.is_nutrient_arrest:
            nutrient_stress_days += 1

    return {
        "crop": crop.name,
        "days": n_steps,
        "initial_biomass_t_ha": round(biomass_traj[0], 3),
        "final_biomass_t_ha": round(biomass_traj[-1], 3),
        "peak_biomass_t_ha": round(max(biomass_traj), 3),
        "biomass_series": biomass_traj,
        "ndvi_series": ndvi_traj,
        "cover_fraction_series": cover_traj,
        "growth_rate_series": db_dt_traj,
        "summary": {
            "active_growth_days": active_growth_days,
            "drought_stress_days": drought_stress_days,
            "thermal_stress_days": thermal_stress_days,
            "nutrient_stress_days": nutrient_stress_days,
            "final_ndvi": ndvi_traj[-1],
            "final_cover": cover_traj[-1]
        }
    }
