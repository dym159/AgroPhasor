"""
Motor Analítico de Resolución de EDO 1 (AgroPhasor).
Implementa la solución analítica exacta paso a paso por factor integrante y linealización de Penman
derivada formalmente en las Secciones 6.1 a 6.4 del documento técnico.

Ecuaciones gobernantes:
H_eff = hc + lambda_max * f_W * Delta
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
    t_canopy_c: float        # Temperatura calculada del dosel [°C]
    t_air_c: float           # Temperatura local del aire [°C]
    t_eq_c: float            # Temperatura de equilibrio estacionario [°C]
    delta_t_c: float         # Diferencia T_dosel - T_aire [°C]
    comfort_index: float     # Confort térmico eta_T [0, 1]
    is_fever: bool           # Alerta de estrés térmico foliar (fiebre por sequía)
    is_frost_risk: bool      # Alerta de riesgo de helada


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
    Resuelve un paso de tiempo (dt) de EDO 1 para una celda de cultivo.
    Aplica la formulación analítica exacta con linealización de Penman (incondicionalmente estable).
    """
    dt_sub = dt_seconds / float(sub_steps)
    T = t_current_c
    
    # Presión de vapor actual del aire [kPa]
    ea_air = actual_vapor_pressure(t_ext_c, rh_pct)
    es_air = saturation_vapor_pressure(t_ext_c)
    vpd_air = max(0.0, es_air - ea_air)
    delta_penman = penman_saturation_slope(t_ext_c)
    
    # Factor estomático según nivel hídrico del suelo
    is_daylight = f_rad_wm2 > 5.0
    fw = stomatal_conductance_factor(
        soil_water_mm=soil_water_mm,
        w_pmp_mm=crop.W_pmp,
        w_crit_mm=crop.W_crit,
        is_daylight=is_daylight
    )
    
    # Coeficiente efectivo de disipación de calor
    # H_eff = h_c + lambda_ev * gamma_c * Delta (combina convección y pendiente evaporativa)
    h_eff = crop.hc + (crop.lambda_gamma_max * fw * delta_penman)
    tau_eff = crop.Cp / max(1e-4, h_eff)
    
    # Temperatura de equilibrio teórico (Ec. 17)
    radiative_gain = crop.alpha * f_rad_wm2
    latent_loss = crop.lambda_gamma_max * fw * vpd_air
    t_eq = t_ext_c + (radiative_gain - latent_loss) / max(1e-4, h_eff)
    
    # Integración exponencial exacta en los sub-pasos (Ec. 18)
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
    Calcula el área de la trayectoria cerrada en el plano de fase (T_air(t), T_dosel(t)).
    Fórmula de Gauss / Shoelace para el área del polígono (Sección 2.6.1).
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
    Simula un ciclo completo de 24 horas para una celda de cultivo.
    Devuelve las series horarias y las métricas del Escudo Térmico.
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
