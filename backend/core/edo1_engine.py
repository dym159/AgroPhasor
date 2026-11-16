"""
Analytical Solver Engine for ODE 1 (AgroPhasor).
Implements the exact solution with frozen latent heat flux (PDF Section 4.2).

Governing equations:
H_eff = hc
tau_eff = Cp / H_eff
T_eq = T_ext + (alpha * f_rad - lambda_max * f_W * VPD_air) / H_eff
T(t + dt) = T_eq + (T(t) - T_eq) * exp(-dt / tau_eff)
"""

import math
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from backend.models.crop_parameters import CropParameters
from backend.core.physics import (
    actual_vapor_pressure,
    saturation_vapor_pressure,
    penman_saturation_slope,
    stomatal_conductance_factor,
    thermal_comfort_index
)


@dataclass
class EDO1StepOutput:
    t_canopy_c: float        # Calculated canopy temperature [°C]
    t_air_c: float           # Local air temperature [°C]
    t_eq_c: float            # Steady-state equilibrium temperature [°C]
    delta_t_c: float         # Difference T_canopy - T_air [°C]
    comfort_index: float     # Thermal comfort eta_T [0, 1]
    is_fever: bool           # Foliar thermal stress alert (drought fever)
    is_frost_risk: bool      # Frost risk alert


def solve_edo1_step(
    t_current_c: float,
    t_ext_c: float,
    f_rad_wm2: float,
    rh_pct: float,
    soil_water_mm: float,
    crop: CropParameters,
    dt_seconds: float = 3600.0,
    sub_steps: int = 1
) -> EDO1StepOutput:
    """
    Solves a time step (dt) of ODE 1 for a crop cell.
    Freezes Q_lat at the initial temperature of the step (PDF Section 4.2).
    """
    if dt_seconds <= 0 or type(sub_steps) is not int or sub_steps < 1:
        raise ValueError("dt_seconds and sub_steps must be positive.")
    dt_sub = dt_seconds / float(sub_steps)
    T = t_current_c
    
    # Actual air vapor pressure [kPa]
    ea_air = actual_vapor_pressure(t_ext_c, rh_pct)
    es_air = saturation_vapor_pressure(t_ext_c)
    
    # Stomatal conductance factor based on soil moisture level
    is_daylight = f_rad_wm2 > 5.0
    fw = stomatal_conductance_factor(
        soil_water_mm=soil_water_mm,
        w_pmp_mm=crop.W_pmp,
        w_crit_mm=crop.W_crit,
        is_daylight=is_daylight
    )
    
    # Effective heat dissipation coefficient
    # Latent flux is treated as a constant source rather than dissipation.
    # PDF Section 4.2: Q_lat frozen at initial T, without Penman slope linearization.
    h_eff = crop.hc
    tau_eff = crop.Cp / max(1e-4, h_eff)
    
    # Theoretical equilibrium temperature (Eq. 17)
    radiative_gain = crop.alpha * f_rad_wm2
    latent_loss = crop.lambda_gamma_max * fw * max(0.0, saturation_vapor_pressure(t_current_c) - ea_air)
    t_eq = t_ext_c + (radiative_gain - latent_loss) / max(1e-4, h_eff)
    
    # Exact exponential integration over sub-steps (Eq. 18)
    decay_factor = math.exp(-dt_sub / max(1e-4, tau_eff))
    for _ in range(sub_steps):
        T = t_eq + (T - t_eq) * decay_factor
        
    delta_t = T - t_ext_c
    comfort = thermal_comfort_index(T, crop.T_opt, crop.delta_T_tol)
    is_fever = is_daylight and (delta_t >= 5.0)
    is_frost = T <= crop.T_frost
    
    return EDO1StepOutput(
        t_canopy_c=T,
        t_air_c=t_ext_c,
        t_eq_c=t_eq,
        delta_t_c=delta_t,
        comfort_index=comfort,
        is_fever=is_fever,
        is_frost_risk=is_frost
    )


def compute_lissajous_area(t_air_series: List[float], t_canopy_series: List[float]) -> float:
    """
    Computes the area of the closed trajectory in the phase plane (T_air(t), T_canopy(t)).
    Uses the Gauss / Shoelace polygon area formula (Section 2.6.1).
    """
    n = len(t_air_series)
    if n < 3 or len(t_canopy_series) < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += t_air_series[i] * t_canopy_series[j] - t_air_series[j] * t_canopy_series[i]
    return float(abs(area) * 0.5)


def simulate_canopy_diurnal_cycle(
    t_ext_hourly: List[float],
    f_rad_wm2_hourly: List[float],
    rh_pct_hourly: List[float],
    soil_water_mm: float,
    crop: CropParameters,
    t_initial_c: Optional[float] = None
) -> Dict[str, Any]:
    """
    Simulates a complete 24-hour cycle for a crop cell.
    Returns hourly time series and Thermal Shield metrics.
    """
    n_hours = len(t_ext_hourly)
    t_curr = t_initial_c if t_initial_c is not None else t_ext_hourly[0]
    
    canopy_temps = []
    delta_temps = []
    comfort_indices = []
    fever_alerts = []
    frost_alerts = []
    
    for h in range(n_hours):
        step_res = solve_edo1_step(
            t_current_c=t_curr,
            t_ext_c=t_ext_hourly[h],
            f_rad_wm2=f_rad_wm2_hourly[h],
            rh_pct=rh_pct_hourly[h],
            soil_water_mm=soil_water_mm,
            crop=crop,
            dt_seconds=3600.0,
            sub_steps=2
        )
        t_curr = step_res.t_canopy_c
        canopy_temps.append(round(step_res.t_canopy_c, 2))
        delta_temps.append(round(step_res.delta_t_c, 2))
        comfort_indices.append(round(step_res.comfort_index, 3))
        fever_alerts.append(step_res.is_fever)
        frost_alerts.append(step_res.is_frost_risk)
        
    al_area = compute_lissajous_area(t_ext_hourly, canopy_temps)
    
    mean_temp = sum(canopy_temps) / float(len(canopy_temps))
    max_temp = max(canopy_temps)
    min_temp = min(canopy_temps)
    
    return {
        "t_canopy_hourly": canopy_temps,
        "delta_t_hourly": delta_temps,
        "comfort_hourly": comfort_indices,
        "fever_alerts": fever_alerts,
        "frost_alerts": frost_alerts,
        "lissajous_area": round(al_area, 2),
        "mean_canopy_temp": round(mean_temp, 2),
        "max_canopy_temp": round(max_temp, 2),
        "min_canopy_temp": round(min_temp, 2)
    }
