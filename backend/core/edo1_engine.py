"""
Motor Analítico de Resolución de EDO 1 (AgroPhasor).
Implementa la solución exacta con flujo latente congelado (PDF sección 4.2).

Ecuaciones gobernantes:
H_eff = hc
tau_eff = Cp / H_eff
T_eq = T_ext + (alpha * f_rad - lambda_max * f_W * VPD_air) / H_eff
T(t + dt) = T_eq + (T(t) - T_eq) * exp(-dt / tau_eff)
"""

import math
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

from backend.models.crop_parameters import CropParameters, GLOBAL_CONSTANTS
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
    Congela Qlat en la temperatura inicial del paso (PDF sección 4.2).
    """
    if dt_seconds <= 0 or type(sub_steps) is not int or sub_steps < 1:
        raise ValueError("dt_seconds y sub_steps deben ser positivos.")
    dt_sub = dt_seconds / float(sub_steps)
    T = t_current_c
    
    # Presión de vapor actual del aire [kPa]
    ea_air = actual_vapor_pressure(t_ext_c, rh_pct)
    es_air = saturation_vapor_pressure(t_ext_c)
    
    # Factor estomático según nivel hídrico del suelo
    is_daylight = f_rad_wm2 > 5.0
    fw = stomatal_conductance_factor(
        soil_water_mm=soil_water_mm,
        w_pmp_mm=crop.W_pmp,
        w_crit_mm=crop.W_crit,
        is_daylight=is_daylight
    )
    
    # Coeficiente efectivo de disipación de calor
    # El flujo latente se trata como fuente constante, no como disipación.
    # PDF sección 4.2: Qlat congelado en T inicial, sin pendiente de Penman.
    h_eff = crop.hc
    tau_eff = crop.Cp / max(1e-4, h_eff)
    
    # Temperatura de equilibrio teórico (Ec. 17) e integración exponencial en sub-pasos (Ec. 18)
    radiative_gain = crop.alpha * f_rad_wm2
    decay_factor = math.exp(-dt_sub / max(1e-4, tau_eff))
    t_eq = t_ext_c
    for _ in range(sub_steps):
        latent_loss = crop.lambda_gamma_max * fw * max(0.0, saturation_vapor_pressure(T) - ea_air)
        t_eq = t_ext_c + (radiative_gain - latent_loss) / max(1e-4, h_eff)
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


def compute_lissajous_shield_index(
    lissajous_area: float,
    a_l_ref: Optional[float] = None,
    a_l_max: Optional[float] = None,
) -> float:
    """
    Convierte el área de Lissajous A_L [°C²] en el índice normalizado de escudo eta_L in [0, 1].
    Curvas con mayor área poseen mayor capacidad amortiguadora del dosel (mejor escudo -> 1.0);
    curvas colapsadas o de área baja tienen escudo bajo (-> 0.0).
    """
    area = max(0.0, float(lissajous_area))
    if a_l_max is not None and a_l_max > 0:
        return round(max(0.0, min(1.0, area / float(a_l_max))), 4)
    ref = float(a_l_ref if a_l_ref is not None else GLOBAL_CONSTANTS.get("A_L_ref_C2", 0.9))
    ref = max(1e-4, ref)
    return round(max(0.0, min(1.0, area / (area + ref))), 4)


def compute_shield_state_and_color(
    lissajous_area: float,
    psi_environmental: Optional[float] = None,
    is_crop: bool = True,
    omega_lissajous: Optional[float] = None,
    a_l_ref: Optional[float] = None,
    psi_ref: Optional[float] = None,
    psi_exp: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Evalúa el estado del Escudo Ambiental y Térmico y su espectro cromático continuo
    entre ROJO [249, 64, 70] (área baja / estrés crítico) y AZUL [42, 155, 255]
    (área amplia / condición óptima) según la curva de Hill calibrada por biomas
    (Selva, Desiertos, Campos Andinos, Campos Templados y Heladas).
    """
    if not is_crop:
        return {
            "shield_enabled": False,
            "lissajous_area": 0.0,
            "eta_lissajous": 0.0,
            "shield_score": 0.0,
            "shield_state": "desactivado",
            "shield_label": "Desactivado (Suelo Desnudo)",
            "shield_color_rgb": (100, 116, 139),
            "shield_color_css": "rgb(100,116,139)",
        }

    eta_l = compute_lissajous_shield_index(lissajous_area, a_l_ref=a_l_ref)
    if psi_environmental is not None:
        omega_l = float(
            omega_lissajous
            if omega_lissajous is not None
            else GLOBAL_CONSTANTS.get("peso_lissajous_escudo_omega_L", 0.10)
        )
        omega_l = max(0.0, min(1.0, omega_l))
        p_ref = max(1e-4, float(psi_ref if psi_ref is not None else GLOBAL_CONSTANTS.get("escudo_psi_ref", 0.28)))
        p_exp = max(0.1, float(psi_exp if psi_exp is not None else GLOBAL_CONSTANTS.get("escudo_psi_exp", 2.0)))
        psi_clamped = max(0.0, min(1.0, float(psi_environmental)))
        if psi_clamped <= 0.0:
            score = 0.0
        else:
            f_psi = math.pow(psi_clamped, p_exp) / (math.pow(psi_clamped, p_exp) + math.pow(p_ref, p_exp))
            score = f_psi * ((1.0 - omega_l) + omega_l * eta_l)
    else:
        score = eta_l

    score = round(max(0.0, min(1.0, score)), 4)

    # Interpolación lineal continua (Lerp): ROJO (249, 64, 70) -> AZUL (42, 155, 255)
    c_red = (249.0, 64.0, 70.0)
    c_blue = (42.0, 155.0, 255.0)
    r = int(round(c_red[0] + (c_blue[0] - c_red[0]) * score))
    g = int(round(c_red[1] + (c_blue[1] - c_red[1]) * score))
    b = int(round(c_red[2] + (c_blue[2] - c_red[2]) * score))

    if score >= 0.70:
        state_key = "azul_cobalto"
        label = "Azul Cobalto (Óptimo)"
    elif score >= 0.38:
        state_key = "violeta_ambar"
        label = "Violeta / Ámbar (Estrés Moderado)"
    else:
        state_key = "rojo_intenso"
        label = "Rojo Intenso (Estrés Crítico)"

    return {
        "shield_enabled": True,
        "lissajous_area": round(max(0.0, float(lissajous_area)), 2),
        "eta_lissajous": eta_l,
        "shield_score": score,
        "shield_state": state_key,
        "shield_label": label,
        "shield_color_rgb": (r, g, b),
        "shield_color_css": f"rgb({r},{g},{b})",
    }


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
            sub_steps=12
        )
        t_curr = step_res.t_canopy_c
        canopy_temps.append(round(step_res.t_canopy_c, 2))
        delta_temps.append(round(step_res.delta_t_c, 2))
        comfort_indices.append(round(step_res.comfort_index, 3))
        fever_alerts.append(step_res.is_fever)
        frost_alerts.append(step_res.is_frost_risk)
        
    al_area = compute_lissajous_area(t_ext_hourly, canopy_temps)
    mean_comfort = sum(comfort_indices) / float(len(comfort_indices)) if comfort_indices else 0.0
    shield_info = compute_shield_state_and_color(al_area, psi_environmental=mean_comfort, is_crop=True)
    
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
        "eta_lissajous": shield_info["eta_lissajous"],
        "shield_score": shield_info["shield_score"],
        "shield_state": shield_info["shield_state"],
        "shield_color_rgb": shield_info["shield_color_rgb"],
        "mean_canopy_temp": round(mean_temp, 2),
        "max_canopy_temp": round(max_temp, 2),
        "min_canopy_temp": round(min_temp, 2)
    }
