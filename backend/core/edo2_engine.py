"""
Motor Agrofísico de Resolución de EDO 2: Balance Hidrológico Radicular (AgroPhasor).
Implementa la dinámica diferencial de humedad del suelo, evaporación, transpiración del dosel,
drenaje topográfico y alertas de riego de acuerdo con AgroPhasor.pdf (Secciones 3.2.2, 3.3 y 2.6.2).

Ecuación gobernante:
dW/dt = P0(t)*cos(theta) + eta_riego*I(t) - ETc(T, W) - kd*sin(theta)*W
con acotamiento físico: 0 <= W(t) <= Wcc(H)
donde todo excedente hídrico sobre Wcc se convierte instantáneamente en escorrentía superficial.
"""

from dataclasses import dataclass, field
import math
from typing import List, Dict, Any, Optional, Tuple

from backend.core.physics import actual_vapor_pressure, saturation_vapor_pressure
from backend.models.crop_parameters import CropParameters, GLOBAL_CONSTANTS


@dataclass
class SoilHydraulicLimits:
    """Límites hídricos del perfil radicular útil según SSURGO/WSS y el cultivo."""
    theta_fc: float       # Contenido volumétrico a capacidad de campo [m³/m³]
    theta_wp: float       # Contenido volumétrico al punto de marchitez [m³/m³]
    zr_mm: float          # Profundidad radicular efectiva Zr [mm]
    w_cc: float           # Capacidad de campo útil Wcc [mm]
    w_pmp: float          # Punto de marchitez permanente Wpmp [mm]
    w_crit: float         # Umbral crítico de confort hídrico Wcrit [mm]
    raw: float            # Agua fácilmente disponible RAW = Wcc - Wcrit [mm]
    taw: float            # Agua total disponible TAW = Wcc - Wpmp [mm]


@dataclass
class EDO2StepOutput:
    """Resultados de un paso de integración dt de EDO 2."""
    soil_water_mm: float              # Humedad calculada en el paso W(t+dt) [mm]
    dw_dt: float                      # Tasa neta de cambio dW/dt [mm/día]
    etc_mm: float                     # Evapotranspiración total en el paso ETc [mm]
    transpiration_mm: float           # Transpiración foliar del dosel [mm]
    evaporation_soil_mm: float        # Evaporación directa del suelo sombreado [mm]
    drainage_mm: float                # Drenaje gravitacional de ladera kd*sin(θ)*W [mm]
    runoff_mm: float                  # Escorrentía superficial generada [mm]
    infiltration_mm: float            # Infiltración efectiva (lluvia + riego) [mm]
    gamma_c_relative: float           # Factor estomático relativo γc / γmax [0, 1]
    vpd_kpa: float                    # Déficit de presión de vapor del aire VPD [kPa]
    is_irrigation_needed: bool        # Alerta operativa: W <= Wcrit
    suggested_irrigation_mm: float    # Lámina sugerida de reposición Isugerido [mm]
    is_drying_warning: bool           # Alerta predictiva por tasa de secado
    is_wilting: bool                  # Alerta crítica: W <= Wpmp (Escudo Rojo)


def compute_soil_limits(
    crop: CropParameters,
    theta_fc: float = 0.30,
    theta_wp: float = 0.14,
    depth_mm: Optional[float] = None
) -> SoilHydraulicLimits:
    """Calcula los límites hídricos del suelo para una especie dada."""
    zr = max(0.0, depth_mm) if depth_mm is not None else max(50.0, crop.Zr_mm)
    w_cc = theta_fc * zr
    w_pmp = theta_wp * zr
    p_dep = max(0.05, min(0.95, crop.p_depletion))
    w_crit = w_cc - p_dep * (w_cc - w_pmp)
    return SoilHydraulicLimits(
        theta_fc=theta_fc,
        theta_wp=theta_wp,
        zr_mm=zr,
        w_cc=round(w_cc, 2),
        w_pmp=round(w_pmp, 2),
        w_crit=round(w_crit, 2),
        raw=round(w_cc - w_crit, 2),
        taw=round(w_cc - w_pmp, 2)
    )


def relative_stomatal_conductance(w_mm: float, limits: SoilHydraulicLimits) -> float:
    """Fracción de apertura estomática usada en el balance diario de EDO 2."""
    if limits.w_cc <= 0:
        return 0.0
    if w_mm >= limits.w_crit:
        return 1.0
    span = max(1e-4, limits.w_crit - limits.w_pmp)
    return max(0.0, min(1.0, (w_mm - limits.w_pmp) / span))


def solve_edo2_step(
    w_current_mm: float,
    precip_mm: float,
    t_air_c: float,
    rh_pct: float,
    slope_deg: float,
    crop: CropParameters,
    irrigation_mm: float = 0.0,
    theta_fc: float = 0.30,
    theta_wp: float = 0.14,
    kd: float = 0.03,
    eta_irrigation: float = 0.85,
    e_suelo0: Optional[float] = None,
    lambda_b: Optional[float] = None,
    biomass_t_ha: Optional[float] = None,
    dt_days: float = 1.0,
    tau_warning_days: float = 2.0,
    is_crop: bool = True,
    depth_mm: Optional[float] = None,
    canopy_temp_c: Optional[float] = None
) -> EDO2StepOutput:
    """
    Integra un paso de tiempo dt de EDO 2 (Balance Hidrológico Radicular).
    
    Parámetros:
    - w_current_mm: Humedad en la zona de raíces al inicio del paso [mm].
    - precip_mm: Precipitación incidente P0(t) [mm/día].
    - t_air_c: Temperatura media del aire [°C].
    - rh_pct: Humedad relativa del aire [%].
    - slope_deg: Inclinación del terreno θ [grados] (SRTM).
    - crop: Ficha técnica del cultivo o cobertura vegetal.
    - irrigation_mm: Lámina externa de riego I(t) [mm/día].
    - theta_fc: Contenido volumétrico a capacidad de campo (SSURGO/WSS).
    - theta_wp: Contenido volumétrico a punto de marchitez (SSURGO/WSS).
    - kd: Coeficiente de drenaje gravitacional dependiente de pendiente.
    - eta_irrigation: Eficiencia del sistema de riego (goteo/aspersión).
    - e_suelo0: Evaporación de suelo desnudo (mm/día). Si None, toma de constantes globales.
    - lambda_b: Atenuación lumínica foliar. Si None, toma de constantes globales.
    - biomass_t_ha: Biomasa del lote para sombreo. Si None, usa B_max o B0.
    - dt_days: Paso de tiempo de integración [días].
    - tau_warning_days: Ventana de anticipación para alerta de secado rápido [días].
    - is_crop: True si q(t)=Cultivo, False si q(t)=Transición (sin transpiración).
    """
    if e_suelo0 is None:
        e_suelo0 = float(GLOBAL_CONSTANTS.get("E_suelo0_mm_dia", 4.2))
    if lambda_b is None:
        lambda_b = float(GLOBAL_CONSTANTS.get("lambda_B_ha_t", 0.45))
    if biomass_t_ha is None:
        biomass_t_ha = crop.B_max_t_ha if is_crop else crop.B0_t_ha

    limits = compute_soil_limits(crop, theta_fc, theta_wp, depth_mm)
    w_cc = limits.w_cc
    w_pmp = limits.w_pmp
    w_crit = limits.w_crit

    # 1. Trigonometría de pendiente (SRTM)
    slope_rad = math.radians(max(0.0, min(80.0, slope_deg)))
    cos_theta = math.cos(slope_rad)
    sin_theta = math.sin(slope_rad)

    # 2. Déficit de presión de vapor atmosférico VPD [kPa]
    ea_air = actual_vapor_pressure(t_air_c, rh_pct)
    es_air = saturation_vapor_pressure(t_air_c if canopy_temp_c is None else canopy_temp_c)
    vpd = max(0.0, es_air - ea_air)

    # 3. Factor de conductancia estomática gamma_c(W) (AgroPhasor.pdf Sec. 3.3)
    eps = 1e-4
    gamma_rel = relative_stomatal_conductance(w_current_mm, limits) if is_crop and crop.gamma_max > 0 else 0.0

    # Conductancia efectiva diaria: gamma_max_daily [mm / (kPa · día)]
    # Si gamma_max está en kg/(m²·s·kPa), multiplicamos por 86400 s/día
    gamma_daily_max = crop.gamma_max * 86400.0 if crop.gamma_max < 0.1 else crop.gamma_max
    gamma_effective = gamma_daily_max * gamma_rel
    transpiration = gamma_effective * vpd

    # 4. Evaporación directa de suelo sombreado por biomasa (Sec. 3.3)
    soil_wetness_ratio = max(0.0, min(1.0, w_current_mm / max(eps, w_cc)))
    canopy_shading = math.exp(-lambda_b * max(0.0, biomass_t_ha))
    evap_soil = e_suelo0 * soil_wetness_ratio * canopy_shading

    etc = transpiration + evap_soil

    # 5. Drenaje gravitacional y balance de flujos
    drainage = kd * sin_theta * max(0.0, w_current_mm)
    infil_precip = precip_mm * cos_theta
    infil_riego = eta_irrigation * max(0.0, irrigation_mm)
    total_infil = infil_precip + infil_riego

    dw_dt = total_infil - etc - drainage
    # Freeze stomatal conductance and biomass within the step. Evaporation
    # and drainage are linear in W, allowing an exponential update.
    loss_rate = kd * sin_theta + e_suelo0 * canopy_shading / max(eps, w_cc)
    source = total_infil - transpiration
    decay = math.exp(-loss_rate * dt_days)
    w_tentative = (w_current_mm * decay + source * (-math.expm1(-loss_rate * dt_days)) / loss_rate
                   if loss_rate > 0 else w_current_mm + source * dt_days)

    # 6. Frontera física de saturación: corte Wcc y escorrentía superficial
    runoff = 0.0
    if w_tentative > w_cc:
        runoff = w_tentative - w_cc
        w_next = w_cc
    elif w_tentative < 0.0:
        w_next = 0.0
    else:
        w_next = w_tentative

    active_time = dt_days
    if w_tentative < 0 and source < 0 and loss_rate > 0:
        equilibrium = source / loss_rate
        active_time = math.log((w_current_mm - equilibrium) / -equilibrium) / loss_rate
    if loss_rate > 0:
        equilibrium = source / loss_rate
        water_integral = equilibrium * active_time + (w_current_mm - equilibrium) * (-math.expm1(-loss_rate * active_time)) / loss_rate
    else:
        water_integral = w_current_mm * active_time + .5 * source * active_time ** 2
    water_integral = max(0.0, water_integral)
    evaporation_total = e_suelo0 * canopy_shading / max(eps, w_cc) * water_integral
    drainage_total = kd * sin_theta * water_integral
    transpiration_total = transpiration * active_time
    # Water entering after exhaustion is consumed immediately by unmet demand.
    if active_time < dt_days:
        transpiration_total += total_infil * (dt_days - active_time)

    # 7. Capa de Diagnóstico y Alertas Operativas (Sec. 2.6.2)
    is_irrigation = w_next <= w_crit
    is_wilting = w_next <= w_pmp
    suggested_irrigation = round(max(0.0, (w_cc - w_next) / max(eps, eta_irrigation)), 2) if is_irrigation else 0.0
    
    # Alerta anticipada por secado rápido: W + tau * (dW/dt) <= Wcrit
    projected_w = w_next + tau_warning_days * dw_dt
    is_drying_alert = projected_w <= w_crit

    return EDO2StepOutput(
        soil_water_mm=round(w_next, 2),
        dw_dt=round(dw_dt, 3),
        etc_mm=round(transpiration_total + evaporation_total, 3),
        transpiration_mm=round(transpiration_total, 3),
        evaporation_soil_mm=round(evaporation_total, 3),
        drainage_mm=round(drainage_total, 3),
        runoff_mm=round(runoff, 3),
        infiltration_mm=round(total_infil * dt_days, 3),
        gamma_c_relative=round(gamma_rel, 3),
        vpd_kpa=round(vpd, 3),
        is_irrigation_needed=is_irrigation,
        suggested_irrigation_mm=suggested_irrigation,
        is_drying_warning=is_drying_alert,
        is_wilting=is_wilting
    )


def simulate_edo2_timeseries(
    precip_series: List[float],
    t_air_series: List[float],
    rh_series: List[float],
    crop: CropParameters,
    slope_deg: float = 0.0,
    w0_mm: Optional[float] = None,
    smap_root_wetness: Optional[float] = None,
    theta_fc: float = 0.30,
    theta_wp: float = 0.14,
    auto_irrigate: bool = False,
    eta_irrigation: float = 0.85,
    dt_days: float = 1.0,
    is_crop: bool = True
) -> Dict[str, Any]:
    """
    Ejecuta una simulación temporal completa de EDO 2 a lo largo de una serie climática.
    
    Permite comparar secano (auto_irrigate=False) frente a riego inteligente automatizado
    (auto_irrigate=True), registrando todas las trayectorias de estado y balances hídricos.
    """
    n_steps = len(precip_series)
    if not (len(t_air_series) == n_steps and len(rh_series) == n_steps):
        raise ValueError("Las series meteorológicas (precip, t_air, rh) deben tener la misma longitud.")

    limits = compute_soil_limits(crop, theta_fc, theta_wp)
    w_cc = limits.w_cc
    w_pmp = limits.w_pmp
    w_crit = limits.w_crit

    # Inicialización de W(0)
    if w0_mm is not None:
        current_w = max(0.0, min(w_cc, float(w0_mm)))
    elif smap_root_wetness is not None:
        wetness = max(0.0, min(1.0, float(smap_root_wetness)))
        current_w = w_pmp + wetness * (w_cc - w_pmp)
    else:
        # Por defecto al umbral crítico de confort
        current_w = w_crit

    w_series = [round(current_w, 2)]
    etc_series = []
    transp_series = []
    evap_series = []
    drainage_series = []
    runoff_series = []
    irrigation_series = []
    irrigation_events: List[Dict[str, Any]] = []
    gamma_rel_series = []
    stress_days = 0
    wilting_days = 0

    for step in range(n_steps):
        p0 = precip_series[step]
        t_air = t_air_series[step]
        rh = rh_series[step]

        applied_irrigation = 0.0
        if auto_irrigate and current_w <= w_crit:
            applied_irrigation = (w_cc - current_w) / eta_irrigation
            irrigation_events.append({
                "step": step,
                "w_before_mm": round(current_w, 2),
                "irrigation_applied_mm": round(applied_irrigation, 2)
            })

        step_res = solve_edo2_step(
            w_current_mm=current_w,
            precip_mm=p0,
            t_air_c=t_air,
            rh_pct=rh,
            slope_deg=slope_deg,
            crop=crop,
            irrigation_mm=applied_irrigation,
            theta_fc=theta_fc,
            theta_wp=theta_wp,
            eta_irrigation=eta_irrigation,
            dt_days=dt_days,
            is_crop=is_crop
        )

        current_w = step_res.soil_water_mm
        w_series.append(current_w)
        etc_series.append(step_res.etc_mm)
        transp_series.append(step_res.transpiration_mm)
        evap_series.append(step_res.evaporation_soil_mm)
        drainage_series.append(step_res.drainage_mm)
        runoff_series.append(step_res.runoff_mm)
        irrigation_series.append(round(applied_irrigation, 2))
        gamma_rel_series.append(step_res.gamma_c_relative)

        if current_w <= w_crit:
            stress_days += 1
        if current_w <= w_pmp:
            wilting_days += 1

    return {
        "crop": crop.name,
        "limits": {
            "W_cc_mm": w_cc,
            "W_pmp_mm": w_pmp,
            "W_crit_mm": w_crit,
            "RAW_mm": limits.raw,
            "TAW_mm": limits.taw
        },
        "soil_water_series": w_series,
        "etc_series": etc_series,
        "transpiration_series": transp_series,
        "soil_evaporation_series": evap_series,
        "drainage_series": drainage_series,
        "runoff_series": runoff_series,
        "irrigation_applied_series": irrigation_series,
        "gamma_c_relative_series": gamma_rel_series,
        "summary": {
            "total_precip_mm": round(sum(precip_series), 2),
            "total_irrigation_mm": round(sum(irrigation_series), 2),
            "total_etc_mm": round(sum(etc_series), 2),
            "total_drainage_mm": round(sum(drainage_series), 2),
            "total_runoff_mm": round(sum(runoff_series), 2),
            "final_soil_water_mm": current_w,
            "min_soil_water_mm": min(w_series),
            "max_soil_water_mm": max(w_series),
            "stress_days": stress_days,
            "wilting_days": wilting_days,
            "irrigation_events_count": len(irrigation_events),
            "irrigation_events": irrigation_events
        }
    }
