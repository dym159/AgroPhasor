"""
AgroPhasor agrometeorological constitutive equations and closure relations.
Implements the official formulas from Sections 3.3 and 5 of the technical specification:
- Tetens saturation vapor pressure e_s(T)
- Penman saturation slope Delta = d(e_s)/dT
- Canopy vapor pressure deficit VPD(T, t)
- Stomatal conductance gamma_c(W)
"""

import math
from typing import Tuple


def saturation_vapor_pressure(temperature_c: float) -> float:
    """
    Tetens formula (Constitutive Eq. 3.3 and Eq. 5):
    e_s(T) = 0.6108 * exp(17.27 * T / (T + 237.3)) [kPa]
    """
    return 0.6108 * math.exp((17.27 * temperature_c) / (temperature_c + 237.3))


def penman_saturation_slope(temperature_c: float) -> float:
    """
    Derivative of the Tetens saturation curve d(e_s)/dT [kPa / °C]:
    Delta = (4098 * e_s(T)) / ((T + 237.3)^2)
    Used for unconditionally stable analytical Penman linearization in ODE 1.
    """
    es = saturation_vapor_pressure(temperature_c)
    return (4098.0 * es) / ((temperature_c + 237.3) ** 2)


def actual_vapor_pressure(temperature_air_c: float, relative_humidity_pct: float) -> float:
    """
    Actual air vapor pressure e_a [kPa]:
    e_a = e_s(T_air) * (RH / 100)
    """
    rh_clamped = max(0.0, min(100.0, relative_humidity_pct))
    es_air = saturation_vapor_pressure(temperature_air_c)
    return es_air * (rh_clamped / 100.0)


def vapor_pressure_deficit(surface_temp_c: float, ea_air_kpa: float) -> float:
    """
    Canopy vapor pressure deficit VPD [kPa]:
    VPD = max(0, e_s(T_canopy) - e_a)
    """
    es = saturation_vapor_pressure(surface_temp_c)
    return max(0.0, es - ea_air_kpa)


def stomatal_conductance_factor(
    soil_water_mm: float,
    w_pmp_mm: float,
    w_crit_mm: float,
    is_daylight: bool = True,
    epsilon: float = 1e-4
) -> float:
    """
    Bounded ramp function for stomatal conductance gamma_c(W) / gamma_max [0, 1] (Section 3.3).
    - If W <= W_pmp: 0.04 (closed stomata / minimal cuticular transpiration).
    - If W >= W_crit: 1.0 (maximum stomatal opening).
    - If W_pmp < W < W_crit: linear decay.
    - Nighttime (is_daylight=False): photoperiod stomatal closure (f_W <= 0.04).
    """
    if not is_daylight:
        return 0.04  # Natural nighttime stomatal closure
    
    if soil_water_mm <= w_pmp_mm:
        return 0.04  # Residual cuticular transpiration at wilting point
    elif soil_water_mm >= w_crit_mm:
        return 1.0
    else:
        denom = max(epsilon, w_crit_mm - w_pmp_mm)
        ratio = (soil_water_mm - w_pmp_mm) / denom
        return max(0.04, min(1.0, 0.04 + 0.96 * ratio))


def thermal_comfort_index(temperature_c: float, t_opt_c: float, delta_t_tol_c: float) -> float:
    """
    Photosynthetic and thermal comfort factor eta_T [0, 1] (Sections 2.6.1 and 3.3):
    eta_T = max(0, 1 - ((T - T_opt) / delta_T_tol)^2)
    """
    diff = (temperature_c - t_opt_c) / max(1e-3, delta_t_tol_c)
    return max(0.0, 1.0 - (diff ** 2))
