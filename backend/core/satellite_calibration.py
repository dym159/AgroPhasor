"""
Motor de Calibración Satelital en Tiempo Real de AgroPhasor.
Implementa en código los tres métodos numéricos definidos en `guia_calibracion_satelital`
de `gemini-code.json`:

1. `edo1_termica`:
   - Parámetros ajustables: `h_c_W_m2C`, `Cp_c_J_m2C`, `h_suelo_W_m2C`
   - Fuente: ECOSTRESS (LST) y NASA POWER (TS)
   - Método: Mínimos cuadrados no lineales (Levenberg-Marquardt acotado) sobre ventana de 30-60 días.

2. `edo2_hidrologica`:
   - Parámetros ajustables: `hidrologia_por_clase_drenaje_ssurgo` (`kd`), `E_suelo0_mm_dia`
   - Fuente: SMAP (GWETTOP / GWETROOT) y OpenET (ET real)
   - Método: Ajuste de tasa de secado post-lluvia tras eventos GPM/IMERG.

3. `edo4_biomasa`:
   - Parámetros ajustables: `kp_c_t_ha_MJ_m2`
   - Fuente: Sentinel-2 y Landsat (series temporales NDVI/EVI)
   - Método: Escalamiento de curva normalizada B(t)/B_max frente a vigor satelital.
"""

from dataclasses import dataclass, replace
from datetime import date, timedelta
from functools import lru_cache
import json
import math
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.models.crop_parameters import (
    CropParameters,
    GLOBAL_CONSTANTS,
    CATALOG_METADATA,
    get_crop_parameters,
)
from backend.core.edo1_engine import solve_edo1_step
from backend.core.edo2_engine import compute_soil_limits, relative_stomatal_conductance, solve_edo2_step
from backend.core.edo4_engine import (
    solve_edo4_step,
    biomass_to_satellite_ndvi,
    satellite_ndvi_to_biomass,
)
from backend.core.physics import actual_vapor_pressure, saturation_vapor_pressure

POWER_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


@dataclass(frozen=True)
class ThermalCalibrationResult:
    """Resultado de la calibración térmica en tiempo real (EDO 1)."""
    h_c_W_m2C: float
    Cp_c_J_m2C: float
    h_suelo_W_m2C: float
    h_c_prior: float
    Cp_c_prior: float
    h_suelo_prior: float
    rmse_before_c: float
    rmse_after_c: float
    samples_used: int
    iterations: int
    converged: bool
    observation_source: str
    calibrated_crop: CropParameters


@dataclass(frozen=True)
class HydrologyCalibrationResult:
    """Resultado de la calibración hidrológica post-lluvia en tiempo real (EDO 2)."""
    kd_calibrated: float
    e_suelo0_mm_dia: float
    kd_prior: float
    e_suelo0_prior: float
    closest_ssurgo_class: str
    hidrologia_por_clase_drenaje_ssurgo: Dict[str, float]
    drydown_steps_used: int
    rain_events_detected: int
    rmse_before_mm: float
    rmse_after_mm: float
    observation_source: str


@dataclass(frozen=True)
class BiomassCalibrationResult:
    """Resultado de la calibración fotosintética en tiempo real (EDO 4)."""
    kp_c_t_ha_MJ_m2: float
    kp_c_prior: float
    scale_factor: float
    rmse_ndvi_before: float
    rmse_ndvi_after: float
    rmse_norm_biomass_after: float
    observations_used: int
    iterations: int
    converged: bool
    observation_source: str
    calibrated_crop: CropParameters


def _clamp(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))


def _rmse(residuals: List[float]) -> float:
    if not residuals:
        return 0.0
    return math.sqrt(sum(r * r for r in residuals) / len(residuals))


# ==============================================================================
# 1. EDO 1 TÉRMICA: Mínimos Cuadrados No Lineales (ECOSTRESS LST / NASA POWER TS)
# ==============================================================================

def calibrate_edo1_thermal(
    crop: CropParameters,
    t_air_series_c: List[float],
    f_rad_series_wm2: List[float],
    rh_series_pct: List[float],
    soil_water_series_mm: List[float],
    observed_lst_or_ts_c: List[float],
    is_crop_series: Optional[List[bool]] = None,
    dt_seconds: float = 3600.0,
    max_rel_deviation: float = 0.35,
    reg_weight: float = 0.08,
    max_iter: int = 25,
    observation_source: str = "ECOSTRESS (LST) y NASA POWER (TS)",
) -> ThermalCalibrationResult:
    """
    Ajusta `h_c_W_m2C`, `Cp_c_J_m2C` y `h_suelo_W_m2C` mediante mínimos cuadrados
    no lineales (Levenberg-Marquardt con restricción de caja física y regularización L2)
    sobre una ventana histórica de 30-60 días/observaciones.
    """
    n = min(
        len(t_air_series_c),
        len(f_rad_series_wm2),
        len(rh_series_pct),
        len(soil_water_series_mm),
        len(observed_lst_or_ts_c),
    )
    suelo_defaults = (
        CATALOG_METADATA.get("parametros_terreno_y_suelo", {}).get("transicion_suelo_desnudo", {})
    )
    h_suelo_0 = float(suelo_defaults.get("h_suelo_W_m2C", 24.0))
    cp_suelo_0 = float(suelo_defaults.get("Cp_suelo_J_m2C", 18000.0))
    alpha_suelo_0 = float(suelo_defaults.get("alpha_suelo", 0.72))

    hc_0 = float(crop.hc)
    cp_0 = float(crop.Cp)

    if is_crop_series is None:
        is_crop_series = [True] * n
    else:
        is_crop_series = list(is_crop_series[:n]) + [True] * max(0, n - len(is_crop_series))

    # Filtrar muestras válidas (finitas)
    valid_indices = [
        i for i in range(n)
        if all(
            math.isfinite(x)
            for x in (
                t_air_series_c[i],
                f_rad_series_wm2[i],
                rh_series_pct[i],
                soil_water_series_mm[i],
                observed_lst_or_ts_c[i],
            )
        )
    ]

    if len(valid_indices) < 3:
        return ThermalCalibrationResult(
            h_c_W_m2C=hc_0,
            Cp_c_J_m2C=cp_0,
            h_suelo_W_m2C=h_suelo_0,
            h_c_prior=hc_0,
            Cp_c_prior=cp_0,
            h_suelo_prior=h_suelo_0,
            rmse_before_c=0.0,
            rmse_after_c=0.0,
            samples_used=len(valid_indices),
            iterations=0,
            converged=False,
            observation_source=observation_source,
            calibrated_crop=crop,
        )

    bounds = [
        (hc_0 * (1.0 - max_rel_deviation), hc_0 * (1.0 + max_rel_deviation)),
        (cp_0 * (1.0 - max_rel_deviation), cp_0 * (1.0 + max_rel_deviation)),
        (h_suelo_0 * (1.0 - max_rel_deviation), h_suelo_0 * (1.0 + max_rel_deviation)),
    ]

    def simulate_residuals(params: List[float]) -> Tuple[List[float], List[float]]:
        hc_val, cp_val, h_soil_val = params
        crop_cand = replace(crop, hc=hc_val, Cp=cp_val)
        soil_cand = replace(
            crop,
            hc=h_soil_val,
            Cp=cp_suelo_0,
            alpha=alpha_suelo_0,
            gamma_max=0.0,
            gamma_max_daily_mm=0.0,
            lambda_gamma_max=0.0,
        )
        data_res: List[float] = []
        for k_pos, idx in enumerate(valid_indices):
            t_start = observed_lst_or_ts_c[valid_indices[k_pos - 1]] if k_pos > 0 else t_air_series_c[idx]
            active_model = crop_cand if is_crop_series[idx] else soil_cand
            step = solve_edo1_step(
                t_current_c=t_start,
                t_ext_c=t_air_series_c[idx],
                f_rad_wm2=f_rad_series_wm2[idx],
                rh_pct=rh_series_pct[idx],
                soil_water_mm=soil_water_series_mm[idx],
                crop=active_model,
                dt_seconds=dt_seconds,
            )
            t_sim = step.t_canopy_c
            data_res.append(t_sim - observed_lst_or_ts_c[idx])

        # Términos de regularización de Tikhonov hacia el prior del catálogo
        scale_reg = math.sqrt(reg_weight * len(valid_indices))
        reg_res = [
            scale_reg * (hc_val - hc_0) / hc_0,
            scale_reg * (cp_val - cp_0) / cp_0,
            scale_reg * (h_soil_val - h_suelo_0) / h_suelo_0,
        ]
        return data_res, data_res + reg_res

    p_curr = [hc_0, cp_0, h_suelo_0]
    data_res_0, full_res_curr = simulate_residuals(p_curr)
    rmse_before = _rmse(data_res_0)
    cost_curr = sum(r * r for r in full_res_curr)

    damping = 1e-2
    converged = False
    iters = 0

    for it in range(1, max_iter + 1):
        iters = it
        m = len(full_res_curr)
        # Jacobiano numérico por diferencias finitas relativas
        jac: List[List[float]] = [[0.0, 0.0, 0.0] for _ in range(m)]
        for j in range(3):
            step_h = max(1e-4, abs(p_curr[j]) * 1e-4)
            p_pert = list(p_curr)
            p_pert[j] += step_h
            _, res_pert = simulate_residuals(p_pert)
            for i in range(m):
                jac[i][j] = (res_pert[i] - full_res_curr[i]) / step_h

        # Resolver (J^T J + damping * diag(J^T J)) delta = - J^T r
        jtj = [[0.0] * 3 for _ in range(3)]
        jtr = [0.0] * 3
        for i in range(m):
            for r_idx in range(3):
                jtr[r_idx] += jac[i][r_idx] * full_res_curr[i]
                for c_idx in range(3):
                    jtj[r_idx][c_idx] += jac[i][r_idx] * jac[i][c_idx]

        for d_idx in range(3):
            jtj[d_idx][d_idx] += damping * max(1e-3, jtj[d_idx][d_idx])

        delta = _solve_3x3(jtj, [-x for x in jtr])
        p_cand = [
            _clamp(p_curr[j] + delta[j], bounds[j][0], bounds[j][1])
            for j in range(3)
        ]

        data_res_cand, full_res_cand = simulate_residuals(p_cand)
        cost_cand = sum(r * r for r in full_res_cand)

        if cost_cand < cost_curr:
            rel_change = max(abs(p_cand[j] - p_curr[j]) / max(1e-6, abs(p_curr[j])) for j in range(3))
            p_curr = p_cand
            full_res_curr = full_res_cand
            data_res_0 = data_res_cand
            cost_curr = cost_cand
            damping = max(1e-5, damping * 0.5)
            if rel_change < 1e-4:
                converged = True
                break
        else:
            damping *= 4.0
            if damping > 1e6:
                break

    hc_cal, cp_cal, h_suelo_cal = (
        round(p_curr[0], 3),
        round(p_curr[1], 1),
        round(p_curr[2], 3),
    )
    rmse_after = _rmse(data_res_0)
    calibrated_crop = replace(crop, hc=hc_cal, Cp=cp_cal)

    return ThermalCalibrationResult(
        h_c_W_m2C=hc_cal,
        Cp_c_J_m2C=cp_cal,
        h_suelo_W_m2C=h_suelo_cal,
        h_c_prior=hc_0,
        Cp_c_prior=cp_0,
        h_suelo_prior=h_suelo_0,
        rmse_before_c=round(rmse_before, 4),
        rmse_after_c=round(rmse_after, 4),
        samples_used=len(valid_indices),
        iterations=iters,
        converged=converged or (rmse_after <= rmse_before),
        observation_source=observation_source,
        calibrated_crop=calibrated_crop,
    )


def _solve_3x3(a: List[List[float]], b: List[float]) -> List[float]:
    """Eliminación gaussiana con pivoteo parcial para sistema 3x3 en Python puro."""
    m = [list(row) + [b[i]] for i, row in enumerate(a)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            return [0.0, 0.0, 0.0]
        m[col], m[pivot] = m[pivot], m[col]
        for row in range(col + 1, 3):
            factor = m[row][col] / m[col][col]
            for k in range(col, 4):
                m[row][k] -= factor * m[col][k]
    x = [0.0, 0.0, 0.0]
    for row in range(2, -1, -1):
        s = m[row][3] - sum(m[row][k] * x[k] for k in range(row + 1, 3))
        x[row] = s / m[row][row]
    return x


def _solve_2x2(a: List[List[float]], b: List[float]) -> List[float]:
    det = a[0][0] * a[1][1] - a[0][1] * a[1][0]
    if abs(det) < 1e-12:
        return [0.0, 0.0]
    return [
        (b[0] * a[1][1] - b[1] * a[0][1]) / det,
        (a[0][0] * b[1] - a[1][0] * b[0]) / det,
    ]


# ==============================================================================
# 2. EDO 2 HIDROLÓGICA: Ajuste de Tasa de Secado Post-Lluvia (SMAP + OpenET)
# ==============================================================================

def calibrate_edo2_hydrology(
    crop: CropParameters,
    precip_series_mm: List[float],
    t_air_series_c: List[float],
    rh_series_pct: List[float],
    smap_soil_water_series_mm: List[float],
    slope_deg: float = 8.0,
    biomass_series_t_ha: Optional[List[float]] = None,
    openet_series_mm_day: Optional[List[float]] = None,
    theta_fc: float = 0.30,
    theta_wp: float = 0.14,
    is_crop: bool = True,
    kd_prior: Optional[float] = None,
    e_suelo0_prior: Optional[float] = None,
    max_rel_deviation: float = 0.40,
    reg_weight: float = 0.10,
    observation_source: str = "SMAP (humedad superficial) y OpenET (ET real)",
) -> HydrologyCalibrationResult:
    """
    Ajusta el coeficiente de drenaje `kd` (y su tabla `hidrologia_por_clase_drenaje_ssurgo`)
    y `E_suelo0_mm_dia` analizando las ventanas de secado post-lluvia tras eventos GPM/IMERG.
    """
    terreno_meta = CATALOG_METADATA.get("parametros_terreno_y_suelo", {})
    ssurgo_table: Dict[str, float] = dict(
        terreno_meta.get(
            "hidrologia_por_clase_drenaje_ssurgo",
            {
                "excessively_drained": 0.16,
                "well_drained": 0.09,
                "moderately_well_drained": 0.06,
                "somewhat_poorly_drained": 0.03,
                "poorly_drained": 0.01,
                "default": 0.08,
            },
        )
    )
    kd_0 = float(kd_prior if kd_prior is not None else ssurgo_table.get("default", 0.08))
    e_suelo_0 = float(
        e_suelo0_prior
        if e_suelo0_prior is not None
        else GLOBAL_CONSTANTS.get("E_suelo0_mm_dia", 4.2)
    )
    lambda_b = float(GLOBAL_CONSTANTS.get("lambda_B_ha_t", 0.45))

    n = min(
        len(precip_series_mm),
        len(t_air_series_c),
        len(rh_series_pct),
        len(smap_soil_water_series_mm),
    )
    if biomass_series_t_ha is None:
        default_b = crop.B_max_t_ha * 0.35 if is_crop else crop.B0_t_ha
        biomass_series_t_ha = [default_b] * n

    limits = compute_soil_limits(crop, theta_fc=theta_fc, theta_wp=theta_wp)
    w_cc = max(1.0, limits.w_cc)
    sin_theta = math.sin(math.radians(_clamp(slope_deg, 0.5, 80.0)))

    # 1. Identificar eventos de lluvia GPM/IMERG y pasos de secado post-lluvia (precip <= 0.5 mm)
    rain_events = sum(1 for p in precip_series_mm[:n] if p >= 2.0)
    drydown_indices: List[int] = []
    for k in range(n - 1):
        if precip_series_mm[k + 1] <= 0.5 and smap_soil_water_series_mm[k + 1] <= smap_soil_water_series_mm[k] + 0.5:
            drydown_indices.append(k)

    # Si no hay suficientes días secos puros, usar todos los pasos subsaturados
    if len(drydown_indices) < 3:
        drydown_indices = [k for k in range(n - 1) if smap_soil_water_series_mm[k] < w_cc]

    def eval_drydown_residuals(kd_val: float, es0_val: float) -> List[float]:
        res: List[float] = []
        for k in drydown_indices:
            step = solve_edo2_step(
                w_current_mm=smap_soil_water_series_mm[k],
                precip_mm=precip_series_mm[k + 1],
                t_air_c=t_air_series_c[k + 1],
                rh_pct=rh_series_pct[k + 1],
                slope_deg=slope_deg,
                crop=crop,
                theta_fc=theta_fc,
                theta_wp=theta_wp,
                kd=kd_val,
                e_suelo0=es0_val,
                lambda_b=lambda_b,
                biomass_t_ha=biomass_series_t_ha[min(k + 1, len(biomass_series_t_ha) - 1)],
                is_crop=is_crop,
            )
            res.append(step.soil_water_mm - smap_soil_water_series_mm[k + 1])
            if openet_series_mm_day is not None and k + 1 < len(openet_series_mm_day):
                et_obs = openet_series_mm_day[k + 1]
                if et_obs is not None and math.isfinite(et_obs):
                    res.append(step.etc_mm - float(et_obs))
        return res

    res_before = eval_drydown_residuals(kd_0, e_suelo_0)
    rmse_before = _rmse(res_before)

    if not drydown_indices:
        closest_cls = min(
            (k for k in ssurgo_table if k != "default"),
            key=lambda k: abs(ssurgo_table[k] - kd_0),
        )
        return HydrologyCalibrationResult(
            kd_calibrated=kd_0,
            e_suelo0_mm_dia=e_suelo_0,
            kd_prior=kd_0,
            e_suelo0_prior=e_suelo_0,
            closest_ssurgo_class=closest_cls,
            hidrologia_por_clase_drenaje_ssurgo=ssurgo_table,
            drydown_steps_used=0,
            rain_events_detected=rain_events,
            rmse_before_mm=0.0,
            rmse_after_mm=0.0,
            observation_source=observation_source,
        )

    # 2. Ajuste linealizado con refinamiento de Gauss-Newton acotado sobre (kd, E_suelo0)
    kd_bounds = (
        max(0.005, kd_0 * (1.0 - max_rel_deviation)),
        min(0.25, kd_0 * (1.0 + max_rel_deviation)),
    )
    es0_bounds = (
        max(1.0, e_suelo_0 * (1.0 - max_rel_deviation)),
        min(12.0, e_suelo_0 * (1.0 + max_rel_deviation)),
    )

    p_curr = [kd_0, e_suelo_0]
    scale_reg = math.sqrt(reg_weight * max(1, len(drydown_indices)))

    def full_residuals(p: List[float]) -> List[float]:
        d_res = eval_drydown_residuals(p[0], p[1])
        r_res = [
            scale_reg * (p[0] - kd_0) / max(1e-4, kd_0),
            scale_reg * (p[1] - e_suelo_0) / max(1e-4, e_suelo_0),
        ]
        return d_res + r_res

    f_curr = full_residuals(p_curr)
    cost_curr = sum(r * r for r in f_curr)
    damping = 1e-2

    for _ in range(20):
        m = len(f_curr)
        jac = [[0.0, 0.0] for _ in range(m)]
        for j in range(2):
            h_step = max(1e-5, abs(p_curr[j]) * 1e-4)
            p_pert = list(p_curr)
            p_pert[j] += h_step
            f_pert = full_residuals(p_pert)
            for i in range(m):
                jac[i][j] = (f_pert[i] - f_curr[i]) / h_step

        jtj = [[0.0, 0.0], [0.0, 0.0]]
        jtr = [0.0, 0.0]
        for i in range(m):
            for r_idx in range(2):
                jtr[r_idx] += jac[i][r_idx] * f_curr[i]
                for c_idx in range(2):
                    jtj[r_idx][c_idx] += jac[i][r_idx] * jac[i][c_idx]

        jtj[0][0] += damping * max(1e-3, jtj[0][0])
        jtj[1][1] += damping * max(1e-3, jtj[1][1])

        delta = _solve_2x2(jtj, [-jtr[0], -jtr[1]])
        p_cand = [
            _clamp(p_curr[0] + delta[0], kd_bounds[0], kd_bounds[1]),
            _clamp(p_curr[1] + delta[1], es0_bounds[0], es0_bounds[1]),
        ]
        f_cand = full_residuals(p_cand)
        cost_cand = sum(r * r for r in f_cand)
        if cost_cand < cost_curr:
            rel_step = max(
                abs(p_cand[0] - p_curr[0]) / max(1e-5, p_curr[0]),
                abs(p_cand[1] - p_curr[1]) / max(1e-5, p_curr[1]),
            )
            p_curr = p_cand
            f_curr = f_cand
            cost_curr = cost_cand
            damping = max(1e-5, damping * 0.5)
            if rel_step < 1e-4:
                break
        else:
            damping *= 4.0

    kd_cal = round(p_curr[0], 4)
    es0_cal = round(p_curr[1], 3)
    rmse_after = _rmse(eval_drydown_residuals(kd_cal, es0_cal))

    # Escalar tabla SSURGO proporcionalmente y determinar la clase más cercana
    ratio_kd = kd_cal / max(1e-5, kd_0)
    calibrated_ssurgo = {
        k: round(v * ratio_kd, 4) for k, v in ssurgo_table.items()
    }
    calibrated_ssurgo["default"] = kd_cal
    closest_cls = min(
        (k for k in ssurgo_table if k != "default"),
        key=lambda k: abs(ssurgo_table[k] - kd_cal),
    )

    return HydrologyCalibrationResult(
        kd_calibrated=kd_cal,
        e_suelo0_mm_dia=es0_cal,
        kd_prior=kd_0,
        e_suelo0_prior=e_suelo_0,
        closest_ssurgo_class=closest_cls,
        hidrologia_por_clase_drenaje_ssurgo=calibrated_ssurgo,
        drydown_steps_used=len(drydown_indices),
        rain_events_detected=rain_events,
        rmse_before_mm=round(rmse_before, 4),
        rmse_after_mm=round(rmse_after, 4),
        observation_source=observation_source,
    )


# ==============================================================================
# 3. EDO 4 BIOMASA: Escalamiento de B(t)/B_max frente a NDVI/EVI (Sentinel-2/Landsat)
# ==============================================================================

def calibrate_edo4_biomass(
    crop: CropParameters,
    f_rad_series_mj_m2: List[float],
    t_canopy_series_c: List[float],
    soil_water_series_mm: List[float],
    nitrogen_series_kg_ha: List[float],
    phosphorus_series_kg_ha: List[float],
    potassium_series_kg_ha: List[float],
    observed_ndvi_series: List[Optional[float]],
    b0_t_ha: Optional[float] = None,
    ndvi_soil: float = 0.15,
    ndvi_max: float = 0.88,
    max_rel_deviation: float = 0.40,
    reg_weight: float = 0.05,
    max_iter: int = 25,
    observation_source: str = "Sentinel-2 y Landsat (series temporales NDVI/EVI)",
) -> BiomassCalibrationResult:
    """
    Ajusta `kp_c_t_ha_MJ_m2` escalando la curva normalizada B(t)/B_max frente
    a las observaciones satelitales de NDVI/EVI (Sentinel-2 / Landsat).
    """
    n = min(
        len(f_rad_series_mj_m2),
        len(t_canopy_series_c),
        len(soil_water_series_mm),
        len(nitrogen_series_kg_ha),
        len(phosphorus_series_kg_ha),
        len(potassium_series_kg_ha),
        len(observed_ndvi_series),
    )
    kp_0 = float(crop.kp_c)
    b_max = max(0.1, float(crop.B_max_t_ha))
    b_init = float(b0_t_ha if b0_t_ha is not None else crop.B0_t_ha)
    lambda_b = float(GLOBAL_CONSTANTS.get("lambda_B_ha_t", 0.45))

    obs_indices = [
        i for i in range(n)
        if observed_ndvi_series[i] is not None and math.isfinite(float(observed_ndvi_series[i]))
    ]

    if not obs_indices:
        return BiomassCalibrationResult(
            kp_c_t_ha_MJ_m2=kp_0,
            kp_c_prior=kp_0,
            scale_factor=1.0,
            rmse_ndvi_before=0.0,
            rmse_ndvi_after=0.0,
            rmse_norm_biomass_after=0.0,
            observations_used=0,
            iterations=0,
            converged=False,
            observation_source=observation_source,
            calibrated_crop=crop,
        )

    # Invertir NDVI observado a fracción normalizada B_obs(t) / B_max
    obs_norm_b = {
        i: satellite_ndvi_to_biomass(
            float(observed_ndvi_series[i]),
            ndvi_soil=ndvi_soil,
            ndvi_max=ndvi_max,
            lambda_b=lambda_b,
            b_max_t_ha=b_max,
        ) / b_max
        for i in obs_indices
    }

    def simulate_trajectory(kp_val: float) -> Tuple[List[float], List[float]]:
        cand_crop = replace(crop, kp_c=kp_val)
        b_curr = b_init
        norm_b_res: List[float] = []
        ndvi_res: List[float] = []
        for i in range(n):
            step = solve_edo4_step(
                b_current_t_ha=b_curr,
                f_rad_daily_mj_m2=f_rad_series_mj_m2[i],
                temp_canopy_c=t_canopy_series_c[i],
                soil_water_mm=soil_water_series_mm[i],
                nitrogen_kg_ha=nitrogen_series_kg_ha[i],
                phosphorus_kg_ha=phosphorus_series_kg_ha[i],
                potassium_kg_ha=potassium_series_kg_ha[i],
                crop=cand_crop,
                q_is_crop=True,
                lambda_b=lambda_b,
            )
            b_curr = step.biomass_t_ha
            if i in obs_norm_b:
                norm_b_res.append((b_curr / b_max) - obs_norm_b[i])
                ndvi_sim = biomass_to_satellite_ndvi(
                    b_curr, ndvi_soil=ndvi_soil, ndvi_max=ndvi_max, lambda_b=lambda_b
                )
                ndvi_res.append(ndvi_sim - float(observed_ndvi_series[i]))
        return norm_b_res, ndvi_res

    norm_res_0, ndvi_res_0 = simulate_trajectory(kp_0)
    rmse_ndvi_before = _rmse(ndvi_res_0)

    kp_low = max(0.002, kp_0 * (1.0 - max_rel_deviation))
    kp_high = min(0.060, kp_0 * (1.0 + max_rel_deviation))
    scale_reg = math.sqrt(reg_weight * len(obs_indices))

    def full_res(kp_val: float) -> List[float]:
        nb_res, _ = simulate_trajectory(kp_val)
        return nb_res + [scale_reg * (kp_val - kp_0) / kp_0]

    kp_curr = kp_0
    r_curr = full_res(kp_curr)
    cost_curr = sum(r * r for r in r_curr)
    damping = 1e-2
    converged = False
    iters = 0

    for it in range(1, max_iter + 1):
        iters = it
        h_step = max(1e-6, kp_curr * 1e-3)
        r_pert = full_res(kp_curr + h_step)
        jac = [(r_pert[i] - r_curr[i]) / h_step for i in range(len(r_curr))]
        jtj = sum(j * j for j in jac)
        jtr = sum(j * r for j, r in zip(jac, r_curr))
        if jtj < 1e-12:
            break
        delta = -jtr / (jtj + damping * jtj)
        kp_cand = _clamp(kp_curr + delta, kp_low, kp_high)
        r_cand = full_res(kp_cand)
        cost_cand = sum(r * r for r in r_cand)
        if cost_cand < cost_curr:
            rel_change = abs(kp_cand - kp_curr) / max(1e-6, kp_curr)
            kp_curr = kp_cand
            r_curr = r_cand
            cost_curr = cost_cand
            damping = max(1e-5, damping * 0.5)
            if rel_change < 1e-4:
                converged = True
                break
        else:
            damping *= 4.0

    kp_cal = round(kp_curr, 5)
    norm_res_after, ndvi_res_after = simulate_trajectory(kp_cal)
    calibrated_crop = replace(crop, kp_c=kp_cal)

    return BiomassCalibrationResult(
        kp_c_t_ha_MJ_m2=kp_cal,
        kp_c_prior=kp_0,
        scale_factor=round(kp_cal / max(1e-6, kp_0), 4),
        rmse_ndvi_before=round(rmse_ndvi_before, 4),
        rmse_ndvi_after=round(_rmse(ndvi_res_after), 4),
        rmse_norm_biomass_after=round(_rmse(norm_res_after), 4),
        observations_used=len(obs_indices),
        iterations=iters,
        converged=converged or (_rmse(ndvi_res_after) <= rmse_ndvi_before),
        observation_source=observation_source,
        calibrated_crop=calibrated_crop,
    )


# ==============================================================================
# 4. PIPELINE UNIFICADO EN TIEMPO REAL (NASA POWER 30-60 DÍAS + SATÉLITES)
# ==============================================================================

@lru_cache(maxsize=32)
def fetch_nasa_power_calibration_window(
    latitude: float,
    longitude: float,
    window_days: int = 45,
    end_date_iso: str = "2023-11-15",
) -> Dict[str, List[float]]:
    """
    Descarga de NASA POWER (en una sola petición HTTP con caché) la ventana histórica
    de 30-60 días con forzantes y observaciones satelitales (`TS`, `GWETROOT`, `GWETTOP`).
    """
    window = int(_clamp(window_days, 30, 60))
    end_dt = date.fromisoformat(end_date_iso)
    start_dt = end_dt - timedelta(days=window - 1)
    fields = (
        "T2M",
        "TS",
        "RH2M",
        "ALLSKY_SFC_SW_DWN",
        "PRECTOTCORR",
        "GWETROOT",
        "GWETTOP",
    )
    params = {
        "parameters": ",".join(fields),
        "community": "AG",
        "format": "JSON",
        "latitude": round(latitude, 4),
        "longitude": round(longitude, 4),
        "start": start_dt.strftime("%Y%m%d"),
        "end": end_dt.strftime("%Y%m%d"),
    }
    req = Request(
        f"{POWER_DAILY_URL}?{urlencode(params)}",
        headers={"User-Agent": "AgroPhasor/1.0"},
    )
    with urlopen(req, timeout=12) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    series = payload["properties"]["parameter"]
    rad_units = (
        payload.get("parameters", {})
        .get("ALLSKY_SFC_SW_DWN", {})
        .get("units", "MJ/m^2/day")
        .lower()
        .replace(" ", "")
    )
    rad_scale = 3.6 if rad_units.startswith("kw") else 1.0

    out: Dict[str, List[float]] = {k: [] for k in fields}
    for offset in range(window):
        d_key = (start_dt + timedelta(days=offset)).strftime("%Y%m%d")
        vals = [float(series[f].get(d_key, -999.0)) for f in fields]
        if any(v <= -900.0 or not math.isfinite(v) for v in vals):
            continue
        for f_name, v in zip(fields, vals):
            if f_name == "ALLSKY_SFC_SW_DWN":
                out[f_name].append(max(0.0, v * rad_scale))
            elif f_name in ("GWETROOT", "GWETTOP"):
                out[f_name].append(_clamp(v, 0.0, 1.0))
            else:
                out[f_name].append(v)
    return out


def calibrate_parcel_realtime(
    crop_id: str = "maiz",
    window_data: Optional[Dict[str, List[Any]]] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    window_days: int = 45,
    slope_deg: float = 8.0,
    theta_fc: float = 0.27,
    theta_wp: float = 0.12,
    nitrogen_kg_ha: float = 80.0,
    phosphorus_kg_ha: float = 35.0,
    potassium_kg_ha: float = 120.0,
) -> Dict[str, Any]:
    """
    Orquesta en tiempo real los 3 algoritmos de `guia_calibracion_satelital`
    sobre una ventana de 30-60 días y devuelve los parámetros calibrados y métricas de ajuste.
    """
    crop = get_crop_parameters(crop_id)
    if window_data is None:
        if latitude is not None and longitude is not None:
            window_data = fetch_nasa_power_calibration_window(
                float(latitude), float(longitude), window_days=window_days
            )
        else:
            raise ValueError("Proporciona `window_data` o coordenadas (`latitude`, `longitude`).")

    t_air = [float(x) for x in window_data.get("T2M", window_data.get("t_air_series", []))]
    n = len(t_air)
    if n == 0:
        raise ValueError("La ventana de calibración no contiene observaciones térmicas (`T2M`).")

    f_rad_mj = [
        float(x) for x in window_data.get("ALLSKY_SFC_SW_DWN", window_data.get("f_rad_series_mj_m2", [18.0] * n))
    ]
    # Conversión de radiación diaria media MJ/(m²·día) a W/m² diurno efectivo para EDO 1
    f_rad_wm2 = [
        float(x) for x in window_data.get("f_rad_series_wm2", [mj / 0.0864 for mj in f_rad_mj])
    ]
    rh = [float(x) for x in window_data.get("RH2M", window_data.get("rh_series", [60.0] * n))]
    precip = [
        float(x) for x in window_data.get("PRECTOTCORR", window_data.get("precip_series", [0.0] * n))
    ]
    ts_obs = [
        float(x) for x in window_data.get("TS", window_data.get("observed_lst_series", t_air))
    ]

    limits = compute_soil_limits(crop, theta_fc=theta_fc, theta_wp=theta_wp)
    if "soil_water_series_mm" in window_data:
        w_series = [float(x) for x in window_data["soil_water_series_mm"]]
    elif "GWETROOT" in window_data:
        w_series = [
            limits.w_pmp + _clamp(float(g), 0.0, 1.0) * (limits.w_cc - limits.w_pmp)
            for g in window_data["GWETROOT"]
        ]
    else:
        w_series = [limits.w_crit] * n

    openet = window_data.get("openet_series_mm_day")
    ndvi_obs = window_data.get("observed_ndvi_series", [])

    # 1. Calibración Térmica EDO 1
    edo1_res = calibrate_edo1_thermal(
        crop=crop,
        t_air_series_c=t_air,
        f_rad_series_wm2=f_rad_wm2,
        rh_series_pct=rh,
        soil_water_series_mm=w_series,
        observed_lst_or_ts_c=ts_obs,
        dt_seconds=float(GLOBAL_CONSTANTS.get("dt_lissajous_seg", 3600.0)),
    )
    crop = edo1_res.calibrated_crop

    # 2. Calibración Hidrológica EDO 2
    edo2_res = calibrate_edo2_hydrology(
        crop=crop,
        precip_series_mm=precip,
        t_air_series_c=t_air,
        rh_series_pct=rh,
        smap_soil_water_series_mm=w_series,
        slope_deg=slope_deg,
        openet_series_mm_day=openet,
        theta_fc=theta_fc,
        theta_wp=theta_wp,
    )

    # 3. Calibración Fotosintética de Biomasa EDO 4 (si hay serie NDVI/EVI disponible)
    if ndvi_obs:
        edo4_res = calibrate_edo4_biomass(
            crop=crop,
            f_rad_series_mj_m2=f_rad_mj,
            t_canopy_series_c=ts_obs,
            soil_water_series_mm=w_series,
            nitrogen_series_kg_ha=[nitrogen_kg_ha] * n,
            phosphorus_series_kg_ha=[phosphorus_kg_ha] * n,
            potassium_series_kg_ha=[potassium_kg_ha] * n,
            observed_ndvi_series=ndvi_obs,
        )
        crop = edo4_res.calibrated_crop
    else:
        edo4_res = BiomassCalibrationResult(
            kp_c_t_ha_MJ_m2=crop.kp_c,
            kp_c_prior=crop.kp_c,
            scale_factor=1.0,
            rmse_ndvi_before=0.0,
            rmse_ndvi_after=0.0,
            rmse_norm_biomass_after=0.0,
            observations_used=0,
            iterations=0,
            converged=True,
            observation_source="Catálogo oficial (sin serie NDVI en la petición)",
            calibrated_crop=crop,
        )

    return {
        "status": "calibrated",
        "crop_id": crop.key,
        "crop_name": crop.name,
        "window_days_evaluated": n,
        "edo1_termica": {
            "parametros_ajustables": {
                "h_c_W_m2C": edo1_res.h_c_W_m2C,
                "Cp_c_J_m2C": edo1_res.Cp_c_J_m2C,
                "h_suelo_W_m2C": edo1_res.h_suelo_W_m2C,
            },
            "priors_catalogo": {
                "h_c_W_m2C": edo1_res.h_c_prior,
                "Cp_c_J_m2C": edo1_res.Cp_c_prior,
                "h_suelo_W_m2C": edo1_res.h_suelo_prior,
            },
            "rmse_before_c": edo1_res.rmse_before_c,
            "rmse_after_c": edo1_res.rmse_after_c,
            "samples_used": edo1_res.samples_used,
            "converged": edo1_res.converged,
            "fuente_observacion": edo1_res.observation_source,
        },
        "edo2_hidrologica": {
            "parametros_ajustables": {
                "kd_calibrated": edo2_res.kd_calibrated,
                "E_suelo0_mm_dia": edo2_res.e_suelo0_mm_dia,
                "clase_drenaje_ssurgo": edo2_res.closest_ssurgo_class,
                "hidrologia_por_clase_drenaje_ssurgo": edo2_res.hidrologia_por_clase_drenaje_ssurgo,
            },
            "priors_catalogo": {
                "kd_prior": edo2_res.kd_prior,
                "E_suelo0_mm_dia": edo2_res.e_suelo0_prior,
            },
            "drydown_steps_used": edo2_res.drydown_steps_used,
            "rain_events_detected": edo2_res.rain_events_detected,
            "rmse_before_mm": edo2_res.rmse_before_mm,
            "rmse_after_mm": edo2_res.rmse_after_mm,
            "fuente_observacion": edo2_res.observation_source,
        },
        "edo4_biomasa": {
            "parametros_ajustables": {
                "kp_c_t_ha_MJ_m2": edo4_res.kp_c_t_ha_MJ_m2,
                "scale_factor": edo4_res.scale_factor,
            },
            "priors_catalogo": {
                "kp_c_t_ha_MJ_m2": edo4_res.kp_c_prior,
            },
            "rmse_ndvi_before": edo4_res.rmse_ndvi_before,
            "rmse_ndvi_after": edo4_res.rmse_ndvi_after,
            "observations_used": edo4_res.observations_used,
            "converged": edo4_res.converged,
            "fuente_observacion": edo4_res.observation_source,
        },
        "calibrated_crop": crop,
    }
