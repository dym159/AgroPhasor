"""
Motor Agrofísico de Resolución de EDO 4 (AgroPhasor).
Implementa la ecuación diferencial de Crecimiento de Biomasa y Descomposición de Rastrojo B_{i,j}(t) (t/ha),
sus relaciones constitutivas biofísicas, saltos discretos híbridos de cosecha y siembra,
y calibración con teledetección satelital (Landsat/MODIS/GEDI), conforme a AgroPhasor.pdf (Secciones 3.2.4, 3.3, 3.4 y 1.5).

Ecuaciones gobernantes:
1. Régimen de Cultivo Activo q(t) = Cultivo(c_k):
   dB/dt = k_p,c * f_rad(t) * eta_T(T) * f_W(W) * eta_N(N,P,K) * (1 - B / B_max) - k_m,c(T) * B
   donde:
   - k_p,c: Eficiencia de conversión fotoquímica [t / (ha · (MJ/m² o W/m²))]
   - f_rad: Radiación fotosintéticamente activa incidente proyectada (NASA POWER + SRTM)
   - eta_T(T): Campana de confort térmico fotosintético (NASA POWER / ECOSTRESS / EDO 1)
   - f_W(W): Factor de limitación hídrica W / (W + K_W) (NASA SMAP / GPM / EDO 2)
   - eta_N: Ley del Mínimo de Liebig min(N/(N+KN), P/(P+KP), K/(K+KK)) (USDA SSURGO / EDO 3)
   - (1 - B / B_max): Freno biológico / saturación logística de capacidad de carga (FAO GAEZ / GEDI)
   - k_m,c(T): Tasa de respiración de mantenimiento modulada por temperatura (Q10)

2. Régimen de Transición / Rastrojo q(t) = Transición:
   dB/dt = - k_dec * B

3. Saltos Discretos de Transición Híbrida:
   - Cosecha: Rendimiento comercial Y_k = HI * (1 - r_res) * B(t^-)
              Biomasa residual retenida: B(t^+) = r_res * B(t^-)
   - Siembra: Incorporación de rastrojo remanente a materia orgánica delta_OM = xi_OM * B(t^-)
              Inicialización de biomasa basal germinativa: B(t^+) = B0,c_k+1
"""

import math
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union

from backend.models.crop_parameters import CropParameters, get_crop_parameters


@dataclass
class EDO4StepOutput:
    """Resultado agrofísico de un paso de simulación de EDO 4."""
    biomass_t_ha: float              # Biomasa aérea resultante B(t+dt) [t/ha]
    db_dt: float                     # Tasa neta de cambio dB/dt [t/(ha · día)]
    gross_growth_t_ha: float         # Fotosíntesis neta bruta acumulada en el paso [t/ha]
    maintenance_loss_t_ha: float     # Pérdida respiratoria de mantenimiento [t/ha]
    eta_thermal: float               # Eficiencia térmica fotosintética eta_T [0, 1]
    eta_water: float                 # Factor de disponibilidad hídrica f_W [0, 1]
    eta_nutrients: float             # Eficiencia química por Ley del Mínimo eta_N [0, 1]
    limiting_nutrient: str           # Nutriente más limitante ('N', 'P', 'K' o 'None')
    logistic_brake: float            # Factor de freno logístico (1 - B/Bmax) [0, 1]
    canopy_cover_fraction: float     # Fracción de cobertura vegetal efectiva (1 - e^(-lambda_B * B)) [0, 1]
    simulated_ndvi: float            # NDVI satelital equivalente (Landsat / MODIS proxy)
    is_growth_active: bool           # True si está en fotosíntesis neta positiva
    is_drought_arrest: bool          # Alerta de paro de crecimiento por sequía extrema
    is_thermal_arrest: bool          # Alerta de paro de fotosíntesis por estrés térmico/helada
    is_nutrient_arrest: bool         # Alerta de bloqueo por agotamiento químico


@dataclass
class EDO4HarvestResult:
    """Resultado del evento discreto de cosecha y transición."""
    crop_name: str
    biomass_pre_harvest_t_ha: float  # B(t_s^-)
    harvest_index_hi: float          # HI
    residue_fraction_rres: float     # r_res
    commercial_yield_t_ha: float     # Y_k = HI * (1 - r_res) * B(t^-)
    residue_left_t_ha: float         # B(t_s^+) = r_res * B(t^-)
    market_price_usd_t: float        # P_mercado (USDA AMS)
    gross_revenue_usd_ha: float      # Y_k * P_mercado
    base_cost_usd_ha: float          # Costo de insumos y labor
    net_margin_usd_ha: float         # Margen neto por hectárea


def thermal_photosynthetic_efficiency(
    temp_canopy_c: float,
    t_opt_c: float,
    delta_t_tol_c: float,
    t_frost_c: float = 0.0,
    t_lethal_c: float = 45.0
) -> float:
    """
    Campana de eficiencia térmica fotosintética eta_T(T) (PDF Sec. 3.3 y 1.3):
    eta_T = max(0, 1 - ((T - T_opt) / delta_T_tol)^2)
    Anulación estricta fuera de fronteras de supervivencia: T <= T_helada o T >= T_letal.
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
    Factor de limitación hídrica f_W(W) (PDF Sec. 3.2.4 y 3.3):
    Saturación f_W = W / (W + K_W). K_W se estima de los umbrales
    cuando el llamador no proporciona un valor calibrado.
    """
    
    if k_w_mm is None:
        # Calibración biofísica automática de K_W a partir de los límites radiculares
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
    Factor químico fotosintético bajo la Ley del Mínimo de Liebig (PDF Sec. 3.3 y 1.2):
    eta_N = min( N/(N+KN), P/(P+KP), K/(K+KK) )
    Retorna (eta_N, limiting_nutrient).
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
    Fracción de cobertura foliar del dosel f_cover (PDF Sec. 3.3):
    f_cover = 1 - exp(-lambda_B * B)
    Controla el sombreo del suelo, la atenuación de la evaporación directa y el escudo contra erosión.
    """
    return max(0.0, min(1.0, 1.0 - math.exp(-lambda_b * max(0.0, biomass_t_ha))))


def biomass_to_satellite_ndvi(
    biomass_t_ha: float,
    ndvi_soil: float = 0.15,
    ndvi_max: float = 0.88,
    lambda_b: float = 0.45
) -> float:
    """
    Proyección teórica de biomasa simulada a índice de vegetación satelital NDVI (Landsat / MODIS):
    NDVI = NDVI_suelo + (NDVI_max - NDVI_suelo) * (1 - exp(-lambda_B * B))
    Permite el contraste directo del estado del gemelo digital con las pasadas de satélite.
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
    Inversión empírica de teledetección: estima biomasa [t/ha] a partir de NDVI satelital.
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
    Resuelve un paso temporal dt de EDO 4 para una celda (i, j).
    
    Aplica una integración exacta exponencial condicionada:
    dB/dt = A * (1 - B / Bmax) - km * B
    que se reescribe linealmente como:
    dB/dt + lambda_eff * B = A
    con lambda_eff = (A / Bmax) + km >= 0.
    
    Esta formulación analítica garantiza:
    1. Estabilidad incondicional (no explota ante pasos dt grandes).
    2. Acotamiento físico estricto 0 <= B(t) <= Bmax.
    3. Conservación de biomasa y decaimiento monótono exacto en modo transición.
    """
    if not math.isfinite(dt_days) or dt_days <= 0 or crop.B_max_t_ha <= 0:
        raise ValueError("dt_days y B_max deben ser positivos y finitos.")
    b_curr = max(0.0, float(b_current_t_ha))
    if q_is_crop:
        b_curr = min(crop.B_max_t_ha, b_curr)

    if not q_is_crop:
        # Modo Transición / Suelo Desnudo / Descomposición de Rastrojo:
        # dB/dt = - k_dec * B
        # Solución exacta: B(t+dt) = B(t) * exp(-k_dec * dt)
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

    # Modo Cultivo Activo q(t) = Cultivo(c_k)
    # 1. Factores constitutivos de limitación
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

    # 2. Tasa fotosintética potencial bruta A [t / (ha · día)]
    # A = kp_c * f_rad * eta_T * eta_W * eta_N
    a_flux = crop.kp_c * max(0.0, f_rad_daily_mj_m2) * eta_T * eta_W * eta_N

    # 3. Respiración de mantenimiento modulada térmicamente por Q10
    km_base = getattr(crop, "km_c", 0.008)
    temp_factor_q10 = q10 ** ((temp_canopy_c - 20.0) / 10.0)
    km_eff = max(0.0, km_base * temp_factor_q10)

    # 4. Integrador analítico incondicionalmente estable
    # dB/dt = A * (1 - B/Bmax) - km * B = A - (A/Bmax + km)*B
    b_max = crop.B_max_t_ha
    lambda_eff = (a_flux / b_max) + km_eff
    
    if lambda_eff > 0:
        # Estado asintótico estacionario de equilibrio
        b_inf = a_flux / lambda_eff
        # B(t+dt) = b_inf + (B(t) - b_inf) * exp(-lambda_eff * dt)
        exp_factor = math.exp(-lambda_eff * dt_days)
        b_next = b_curr * exp_factor + a_flux * (-math.expm1(-lambda_eff*dt_days))/lambda_eff
    else:
        b_next = b_curr

    # Acotamiento físico estricto
    b_next = max(0.0, min(b_max, b_next))
    db_dt = (b_next - b_curr) / dt_days

    # Diagnósticos y componentes
    logistic_brake = max(0.0, 1.0 - (b_curr / b_max))
    z = lambda_eff*dt_days
    phi = -math.expm1(-z)/z if z else 1.0
    phi2 = (0.5-z/6+z*z/24) if abs(z)<1e-5 else (1-phi)/z
    integral_b = b_curr*dt_days*phi + a_flux*dt_days**2*phi2
    gross_growth = a_flux*(dt_days-integral_b/b_max)
    maint_loss = km_eff*integral_b
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
    Ejecuta un corte parcial intermedio en cultivos de cosecha múltiple (ej. Fresa).
    Retorna (rendimiento_corte_t_ha, biomasa_remanente_t_ha).
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
    Ejecuta el salto discreto de cosecha (PDF Sec. 3.4 y 1.1):
    1. Rendimiento comercial cosechable: Y_k = Y_parcial_acum + HI * (1 - r_res) * B(t_s^-)
    2. Rastrojo protector remanente en campo: B(t_s^+) = r_res * B(t_s^-)
    3. Valoración económica basada en precios USDA AMS Market News.
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
    Ejecuta una serie temporal completa de EDO 4 para una celda a lo largo de n días.
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
