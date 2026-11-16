"""
Catálogo oficial de parámetros biofísicos, fisiológicos, edáficos y de manejo de AgroPhasor.
Carga automáticamente la configuración jerárquica desde `gemini-code.json` (y sincroniza
`backend/data/crop_catalog.json`), manteniendo compatibilidad retroactiva con esquemas planos.
"""

import json
import os
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple

CATALOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "crop_catalog.json")
BASE_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GEMINI_CODE_PATH = os.path.join(BASE_PROJECT_DIR, "gemini-code.json")
LEGACY_GEMINI_CODE_PATH = os.path.join(BASE_PROJECT_DIR, "gemini-code-1794737993920.json")

DISPLAY_NAMES = {
    "maiz": "Maíz",
    "frijol": "Frijol",
    "fresa": "Fresa",
    "papa": "Papa",
}


def normalize_region(value: str) -> str:
    letters = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(c for c in letters if not unicodedata.combining(c)).split())


@dataclass(frozen=True)
class CropCalendar:
    duration_days: int
    planting_months: tuple[int, ...]
    source: str

    def __post_init__(self):
        if type(self.duration_days) is not int or self.duration_days < 1:
            raise ValueError("El calendario requiere una duración entera positiva.")
        if any(type(month) is not int or not 1 <= month <= 12 for month in self.planting_months):
            raise ValueError("Los meses de siembra deben estar entre 1 y 12.")


@dataclass(frozen=True)
class CropEconomics:
    price_usd_t: float
    cost_usd_ha: float
    source: str


@dataclass(frozen=True)
class PartialHarvest:
    first_day: int
    interval_days: int
    fraction: float

    def __post_init__(self):
        if type(self.first_day) is not int or self.first_day < 1:
            raise ValueError("El primer corte requiere un día entero positivo.")
        if type(self.interval_days) is not int or self.interval_days < 1:
            raise ValueError("El intervalo de corte requiere días enteros positivos.")
        if not 0 < self.fraction <= 1:
            raise ValueError("La fracción de corte debe ser mayor que cero y menor o igual que uno.")


@dataclass(frozen=True)
class CropParameters:
    key: str
    name: str
    botanical_family: str
    duration_days: int = 120
    Cp: float = 35000.0               # Capacidad calorífica [J / (m² · °C)]
    hc: float = 28.0                  # Coeficiente convectivo [W / (m² · °C)]
    alpha: float = 0.80               # Absortividad solar [adimensional]
    gamma_max: float = 0.00015        # Conductancia máxima estomática [kg / (m² · s · kPa)]
    gamma_max_daily_mm: float = 12.96 # Conductancia diaria [mm / (día · kPa)]
    lambda_gamma_max: float = 367.5   # Capacidad refrigerante efectiva [W / (m² · kPa)]
    T_opt: float = 20.0               # Temperatura óptima de confort [°C]
    delta_T_tol: float = 10.0         # Tolerancia térmica [°C]
    T_frost: float = 1.0              # Umbral de helada [°C]
    T_lethal: float = 40.0            # Umbral letal [°C]
    Zr_mm: float = 800.0              # Profundidad radicular [mm]
    p_depletion: float = 0.50         # Fracción de agotamiento permisible [0, 1]
    K_W_mm: float = 35.0              # Constante de semi-saturación hídrica EDO 4 [mm]
    W_pmp: float = 20.0               # Umbral de marchitez permanente [mm]
    W_crit: float = 50.0              # Umbral crítico de estrés [mm]
    W_fc: float = 75.0                # Capacidad de campo [mm]
    # Parámetros para EDO 3 y 4 (Biomasa, Cosecha y Nutrientes)
    kp_c: float = 0.015               # Eficiencia fotosintética [t / (ha · MJ/m²)]
    B_max_t_ha: float = 15.0          # Techo de biomasa [t/ha]
    B0_t_ha: float = 0.20             # Biomasa inicial [t/ha]
    km_c: float = 0.008               # Tasa de mantenimiento [1/día]
    HI: float = 0.45                  # Índice de cosecha final
    is_multiple_harvest: bool = False # True si admite cortes parciales (ej. Fresa)
    t_harvest_start_days: int = 120   # Inicio de cosecha [días]
    harvest_interval_days: int = 0    # Intervalo entre cortes parciales [días]
    partial_cut_fraction: float = 0.0 # Fracción de biomasa extraída en cada corte parcial
    F_fix: float = 0.0                # Fijación de Nitrógeno (leguminosas) [kg / (t · día)]
    F_sol: float = 0.02               # Solubilización de Fósforo [kg / (t · día)]
    ka_N: float = 0.00018             # Tasa de absorción radicular de N [1 / (mm · día)]
    ka_P: float = 0.00012             # Tasa de absorción radicular de P [1 / (mm · día)]
    ka_K: float = 0.00015             # Tasa de absorción radicular de K [1 / (mm · día)]
    K_N: float = 30.0                 # Constante Liebig N [kg/ha]
    K_P: float = 20.0                 # Constante Liebig P [kg/ha]
    K_K: float = 40.0                 # Constante Liebig K [kg/ha]
    # Parámetros económicos (Frente de Pareto / A*)
    price_usd_t: float = 300.0
    base_cost_usd_ha: float = 600.0
    has_base_economics: bool = False
    group: str = "Otros"
    variety: str = ""
    cycle_source: str = ""
    calendars: Dict[str, CropCalendar] = field(default_factory=dict)
    economics: Dict[str, Dict[str, CropEconomics]] = field(default_factory=dict)
    partial_harvest: Optional[PartialHarvest] = None

    def partial_harvest_days(self) -> range:
        schedule = self.partial_harvest
        if schedule is None:
            return range(0)
        return range(schedule.first_day, self.duration_days, schedule.interval_days)


def _adapt_imported_crop(key: str, crop: dict) -> dict:
    cycle = crop["ciclo_y_cosecha"]
    thermal = crop["termodinamica_edo1"]
    water = crop["hidrologia_edo2_edo4"]
    nutrients = crop["nutrientes_edo3_edo4"]
    biomass = crop["biomasa_edo4"]
    economics = crop["economia_pareto_f3"]
    return {
        "nombre": key.split("_")[0],
        "familia_botanica": crop["familia_botanica"],
        "duracion_dias": cycle["duracion_vida_productiva_dias"],
        "HI": cycle["HI_indice_cosecha_final"],
        "cosecha_parcial": {
            "first_day": cycle["t_inicio_cosecha_dias"],
            "interval_days": cycle["intervalo_corte_dias"],
            "fraction": cycle["f_corte_parcial"],
        } if cycle["es_cosecha_multiple"] else None,
        "Cp_c": thermal["Cp_c_J_m2C"],
        "alpha_c": thermal["alpha_c"],
        "h_c": thermal["h_c_W_m2C"],
        "T_opt": thermal["T_opt_C"],
        "dT_tol": thermal["dT_tol_C"],
        "T_helada": thermal["T_helada_C"],
        "T_letal": thermal["T_letal_C"],
        "gamma_max": water["gamma_max_mm_dia_kPa"] / 86400,
        "Zr_mm": water["Zr_mm"],
        "p_agotamiento": water["p_agotamiento"],
        "F_fix": nutrients["F_fix_kg_t_dia"],
        "F_sol": nutrients["F_sol_kg_t_dia"],
        "K_N": nutrients["K_N_kg_ha"],
        "K_P": nutrients["K_P_kg_ha"],
        "K_K": nutrients["K_K_kg_ha"],
        "kp_c": biomass["kp_c_t_ha_MJ_m2"],
        "B_max_t_ha": biomass["B_max_t_ha"],
        "B0_t_ha": biomass["B0_t_ha"],
        "km_c_dia": biomass["km0_c_dia"],
        "precio_usd_t": economics["precio_mercado_usd_t"],
        "costo_base_usd_ha": economics["costo_insumos_usd_ha"],
    }


def normalize_catalog_dict(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza un diccionario de catálogo (ya sea en el formato jerárquico de `gemini-code.json`
    o en el formato plano anterior) para que exponga tanto las secciones modulares como las
    claves canónicas requeridas por los motores EDO 1-5 y sus validadores.
    """
    if not isinstance(raw_data, dict):
        return {}

    is_hierarchical = any(
        k in raw_data
        for k in (
            "configuracion_y_constantes_globales",
            "parametros_terreno_y_suelo",
            "catalogo_cultivos",
        )
    )
    if not is_hierarchical:
        return raw_data

    normalized: Dict[str, Any] = dict(raw_data)

    # 1. Unificar constantes globales (físicas, numéricas, edáficas y de manejo)
    cfg_global = raw_data.get("configuracion_y_constantes_globales", {})
    numericos = cfg_global.get("numericos", {}) if isinstance(cfg_global, dict) else {}
    fisicos = cfg_global.get("fisicos_universales", {}) if isinstance(cfg_global, dict) else {}

    terreno = raw_data.get("parametros_terreno_y_suelo", {})
    cinetica = terreno.get("cinetica_edafica_global", {}) if isinstance(terreno, dict) else {}
    umbrales_q = terreno.get("umbrales_quimicos_phi_pH_EC", {}) if isinstance(terreno, dict) else {}

    manejo = raw_data.get("manejo_y_pareto_default", {})
    if not isinstance(manejo, dict):
        manejo = {}

    globales: Dict[str, Any] = {}
    if isinstance(raw_data.get("constantes_globales"), dict):
        globales.update(raw_data["constantes_globales"])

    for section in (numericos, fisicos, cinetica, umbrales_q):
        if isinstance(section, dict):
            globales.update(section)

    # Mapear alias canónicos usados en los motores EDO 1-5
    alias_pairs = [
        ("Gamma_C_m", "Gamma_adiabatico_C_m"),
        ("Q10", "Q10_enzimatico"),
        ("k_er_cultivo", "k_er_cultivo_base"),
        ("k_er_labranza", "k_er_labranza_base"),
        ("k_lN", "k_lN_cmolc_kg_mm"),
        ("k_lK", "k_lK_cmolc_kg_mm"),
        ("beta_K", "beta_K_rastrojo"),
        ("k_dec_dia", "k_dec_rastrojo_dia"),
        ("xi_N", "xi_N_mm_inv"),
        ("xi_P", "xi_P_mm_inv"),
        ("xi_K", "xi_K_mm_inv"),
    ]
    for canonical_key, hierarchical_key in alias_pairs:
        if hierarchical_key in globales and canonical_key not in globales:
            globales[canonical_key] = globales[hierarchical_key]

    for m_key in (
        "r_res_rastrojo_default",
        "costo_riego_usd_mm_ha",
        "pareto_f2_peso_suelo_omega_H",
        "pareto_f2_peso_nutrientes_omega_N",
    ):
        if m_key in manejo:
            globales[m_key] = manejo[m_key]

    normalized["constantes_globales"] = globales

    # 2. Normalizar suelo desnudo / transición
    trans_src = terreno.get("transicion_suelo_desnudo") if isinstance(terreno, dict) else None
    if isinstance(trans_src, dict):
        normalized["suelo_desnudo_transicion"] = {
            "nombre": trans_src.get("nombre", "Suelo Desnudo / Transición"),
            "familia_botanica": "None",
            "dt_trans_dias": trans_src.get("dt_trans_dias", 15),
            "Cp_suelo": trans_src.get("Cp_suelo_J_m2C", trans_src.get("Cp_suelo", 18000.0)),
            "alpha_suelo": trans_src.get("alpha_suelo", 0.72),
            "h_suelo": trans_src.get("h_suelo_W_m2C", trans_src.get("h_suelo", 24.0)),
            "gamma_max": trans_src.get("gamma_max_mm_dia_kPa", trans_src.get("gamma_max", 0.0)),
            "T_opt": trans_src.get("T_opt", 20.0),
            "dT_tol": trans_src.get("dT_tol", 15.0),
            "T_helada": trans_src.get("T_helada", -5.0),
            "T_letal": trans_src.get("T_letal", 50.0),
        }

    # 3. Normalizar catálogo de cultivos
    cat_src = raw_data.get("catalogo_cultivos")
    if isinstance(cat_src, dict):
        dt_seg = float(globales.get("dt_simulacion_seg", 86400.0))
        cultivos_norm: Dict[str, Any] = {}
        for raw_key, c in cat_src.items():
            if not isinstance(c, dict):
                cultivos_norm[raw_key] = c
                continue

            ciclo = c.get("ciclo_y_cosecha", {})
            termo = c.get("termodinamica_edo1", {})
            hidro = c.get("hidrologia_edo2_edo4", {})
            nutr = c.get("nutrientes_edo3_edo4", {})
            bio = c.get("biomasa_edo4", {})
            econ = c.get("economia_pareto_f3", {})

            short_prefix = raw_key.split("_")[0].lower()
            default_name = DISPLAY_NAMES.get(short_prefix, raw_key.split("_")[0])

            g_daily = hidro.get("gamma_max_mm_dia_kPa", c.get("gamma_max_mm_dia_kPa"))
            if g_daily is not None:
                g_sec = float(g_daily) / dt_seg
                g_daily_val = float(g_daily)
            else:
                g_raw = float(c.get("gamma_max", 0.00015))
                g_sec = g_raw if g_raw < 0.1 else g_raw / dt_seg
                g_daily_val = g_raw * dt_seg if g_raw < 0.1 else g_raw

            duracion = ciclo.get("duracion_vida_productiva_dias", c.get("duracion_dias"))

            flat_crop: Dict[str, Any] = {
                "nombre": c.get("nombre", default_name),
                "familia_botanica": c.get("familia_botanica"),
                "duracion_dias": duracion,
                "es_cosecha_multiple": bool(ciclo.get("es_cosecha_multiple", c.get("es_cosecha_multiple", False))),
                "t_inicio_cosecha_dias": ciclo.get("t_inicio_cosecha_dias", duracion),
                "intervalo_corte_dias": ciclo.get("intervalo_corte_dias", 0),
                "f_corte_parcial": ciclo.get("f_corte_parcial", 0.0),
                "Cp_c": termo.get("Cp_c_J_m2C", c.get("Cp_c")),
                "alpha_c": termo.get("alpha_c", c.get("alpha_c")),
                "h_c": termo.get("h_c_W_m2C", c.get("h_c")),
                "gamma_max": g_sec,
                "gamma_max_mm_dia_kPa": g_daily_val,
                "Zr_mm": hidro.get("Zr_mm", c.get("Zr_mm")),
                "p_agotamiento": hidro.get("p_agotamiento", c.get("p_agotamiento")),
                "K_W_mm": hidro.get("K_W_mm", c.get("K_W_mm")),
                "T_opt": termo.get("T_opt_C", c.get("T_opt")),
                "dT_tol": termo.get("dT_tol_C", c.get("dT_tol")),
                "T_helada": termo.get("T_helada_C", c.get("T_helada")),
                "T_letal": termo.get("T_letal_C", c.get("T_letal")),
                "kp_c": bio.get("kp_c_t_ha_MJ_m2", c.get("kp_c")),
                "B_max_t_ha": bio.get("B_max_t_ha", c.get("B_max_t_ha")),
                "B0_t_ha": bio.get("B0_t_ha", c.get("B0_t_ha")),
                "km_c_dia": bio.get("km0_c_dia", c.get("km_c_dia")),
                "HI": ciclo.get("HI_indice_cosecha_final", c.get("HI")),
                "F_fix": nutr.get("F_fix_kg_t_dia", c.get("F_fix")),
                "F_sol": nutr.get("F_sol_kg_t_dia", c.get("F_sol")),
                "ka_N_mm_inv_dia": nutr.get("ka_N_mm_inv_dia", c.get("ka_N_mm_inv_dia")),
                "ka_P_mm_inv_dia": nutr.get("ka_P_mm_inv_dia", c.get("ka_P_mm_inv_dia")),
                "ka_K_mm_inv_dia": nutr.get("ka_K_mm_inv_dia", c.get("ka_K_mm_inv_dia")),
                "K_N": nutr.get("K_N_kg_ha", c.get("K_N")),
                "K_P": nutr.get("K_P_kg_ha", c.get("K_P")),
                "K_K": nutr.get("K_K_kg_ha", c.get("K_K")),
                "precio_usd_t": econ.get("precio_mercado_usd_t", c.get("precio_usd_t")),
                "costo_base_usd_ha": econ.get("costo_insumos_usd_ha", c.get("costo_base_usd_ha")),
            }
            for meta_key in ("grupo", "variedad", "fuente_ciclo", "calendarios", "economia", "cosecha_parcial"):
                if meta_key in c:
                    flat_crop[meta_key] = c[meta_key]
            cultivos_norm[raw_key] = flat_crop
        normalized["cultivos"] = cultivos_norm

    return normalized


def _load_catalog() -> Tuple[Dict[str, Any], Dict[str, CropParameters], Dict[str, Any]]:
    global_consts: Dict[str, Any] = {
        "lambda_ev_J_kg": 2450000.0,
        "Gamma_C_m": 0.0065,
        "Q10": 2.0,
        "k_er_cultivo": 0.0004,
        "k_er_labranza": 0.0035,
    }
    catalog: Dict[str, CropParameters] = {}
    raw_metadata: Dict[str, Any] = {}

    data: Dict[str, Any] = {}
    # Prioridad: Cargar catálogo oficial gemini-code.json -> crop_catalog.json -> legacy
    for path in [GEMINI_CODE_PATH, CATALOG_PATH, LEGACY_GEMINI_CODE_PATH]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    file_data = normalize_catalog_dict(json.load(f))
                    if not data:
                        data = file_data
                    else:
                        # Prioridad EDO: mantener constantes y parámetros calibrados de gemini-code.json,
                        # complementando metadatos regionales y cultivos de referencia.
                        for k, v in file_data.get("constantes_globales", {}).items():
                            data.setdefault("constantes_globales", {}).setdefault(k, v)
                        target_crops = data.setdefault("cultivos", {})
                        for k, v in file_data.get("cultivos", {}).items():
                            if k not in target_crops:
                                target_crops[k] = v
                            elif isinstance(v, dict) and isinstance(target_crops[k], dict):
                                for meta_key in ("nombre", "grupo", "variedad", "fuente_ciclo", "calendarios", "economia", "cosecha_parcial"):
                                    if meta_key in v:
                                        target_crops[k].setdefault(meta_key, v[meta_key])
                        for k, v in file_data.get("cultivos_referencia", {}).items():
                            data.setdefault("cultivos_referencia", {}).setdefault(k, v)
                        if "suelo_desnudo_transicion" not in data and "suelo_desnudo_transicion" in file_data:
                            data["suelo_desnudo_transicion"] = file_data["suelo_desnudo_transicion"]
            except Exception as e:
                print(f"Advertencia leyendo {path}: {e}")

    if data:
        try:
            global_consts.update(data.get("constantes_globales", {}))
            raw_metadata = {
                "parametros_terreno_y_suelo": data.get("parametros_terreno_y_suelo", {}),
                "manejo_y_pareto_default": data.get("manejo_y_pareto_default", {}),
                "guia_calibracion_satelital": data.get("guia_calibracion_satelital", {}),
            }
            lambda_ev = float(global_consts.get("lambda_ev_J_kg", 2450000.0))
            dt_seg = float(global_consts.get("dt_simulacion_seg", 86400.0))

            # Cargar cultivos (calibrados primero, luego referencia regional)
            cultivos = {**data.get("cultivos", {}), **data.get("cultivos_referencia", {})}
            for raw_key, c in cultivos.items():
                g_max = float(c.get("gamma_max", 0.00015))
                if g_max >= 0.1:
                    g_daily_mm = g_max
                    g_max = g_daily_mm / dt_seg
                else:
                    g_daily_mm = float(c.get("gamma_max_mm_dia_kPa", round(g_max * dt_seg, 4)))

                # Conductancia latente efectiva = lambda_ev * gamma_max [W / (m² · kPa)]
                l_g_max = lambda_ev * g_max

                zr = float(c.get("Zr_mm", 800.0))
                p_agot = float(c.get("p_agotamiento", 0.5))

                # Suelo franco de referencia para límites basales en CropParameters
                w_fc = round(0.12 * zr, 1)
                w_pmp = round(0.04 * zr, 1)
                w_crit = round(w_fc - p_agot * (w_fc - w_pmp), 1)
                k_w = float(c.get("K_W_mm") if c.get("K_W_mm") is not None else max(1.0, 0.5 * (w_crit - w_pmp)))

                dur_days = int(c.get("duracion_dias", 120))
                short_prefix = raw_key.split("_")[0].lower()
                crop_name = c.get("nombre") or DISPLAY_NAMES.get(short_prefix, raw_key.split("_")[0])

                param = CropParameters(
                    key=raw_key,
                    name=crop_name,
                    botanical_family=c.get("familia_botanica", "Unknown"),
                    duration_days=dur_days,
                    group=c.get("grupo", "Otros"),
                    variety=c.get("variedad", ""),
                    cycle_source=c.get("fuente_ciclo", ""),
                    partial_harvest=PartialHarvest(**c["cosecha_parcial"]) if c.get("cosecha_parcial") else None,
                    calendars={
                        normalize_region(region): CropCalendar(
                            profile["duracion_dias"], tuple(profile["meses_siembra"]), profile["fuente"]
                        )
                        for region, profile in c.get("calendarios", {}).items()
                    },
                    economics={
                        normalize_region(region): {
                            campaign: CropEconomics(
                                profile["precio_usd_t"], profile["costo_usd_ha"], profile["fuente"]
                            )
                            for campaign, profile in campaigns.items()
                        }
                        for region, campaigns in c.get("economia", {}).items()
                    },
                    Cp=float(c.get("Cp_c", 35000.0)),
                    hc=float(c.get("h_c", 28.0)),
                    alpha=float(c.get("alpha_c", 0.80)),
                    gamma_max=g_max,
                    gamma_max_daily_mm=g_daily_mm,
                    lambda_gamma_max=l_g_max,
                    T_opt=float(c.get("T_opt", 20.0)),
                    delta_T_tol=float(c.get("dT_tol", 10.0)),
                    T_frost=float(c.get("T_helada", 1.0)),
                    T_lethal=float(c.get("T_letal", 40.0)),
                    Zr_mm=zr,
                    p_depletion=p_agot,
                    K_W_mm=k_w,
                    W_pmp=w_pmp,
                    W_crit=w_crit,
                    W_fc=w_fc,
                    kp_c=float(c.get("kp_c", 0.015)),
                    B_max_t_ha=float(c.get("B_max_t_ha", 15.0)),
                    B0_t_ha=float(c.get("B0_t_ha", 0.20)),
                    km_c=float(c.get("km_c_dia", 0.008)),
                    HI=float(c.get("HI", 0.45)),
                    is_multiple_harvest=bool(c.get("es_cosecha_multiple", False)),
                    t_harvest_start_days=int(c.get("t_inicio_cosecha_dias", dur_days)),
                    harvest_interval_days=int(c.get("intervalo_corte_dias", 0)),
                    partial_cut_fraction=float(c.get("f_corte_parcial", 0.0)),
                    F_fix=float(c.get("F_fix", 0.0)),
                    F_sol=float(c.get("F_sol", 0.02)),
                    ka_N=float(c.get("ka_N_mm_inv_dia") if c.get("ka_N_mm_inv_dia") is not None else 0.00018),
                    ka_P=float(c.get("ka_P_mm_inv_dia") if c.get("ka_P_mm_inv_dia") is not None else 0.00012),
                    ka_K=float(c.get("ka_K_mm_inv_dia") if c.get("ka_K_mm_inv_dia") is not None else 0.00015),
                    K_N=float(c.get("K_N", 30.0)),
                    K_P=float(c.get("K_P", 20.0)),
                    K_K=float(c.get("K_K", 40.0)),
                    price_usd_t=float(c.get("precio_usd_t", 300.0)),
                    base_cost_usd_ha=float(c.get("costo_base_usd_ha", 600.0)),
                    has_base_economics="precio_usd_t" in c and "costo_base_usd_ha" in c,
                )

                # Guardamos por nombre canónico y alias simplificado
                catalog[raw_key.lower()] = param
                catalog.setdefault(short_prefix, param)
            # Cargar suelo desnudo / transición
            suelo = data.get("suelo_desnudo_transicion", {})
            param_suelo = CropParameters(
                key="suelo_desnudo_transicion",
                name=suelo.get("nombre", "Suelo Desnudo / Transición"),
                botanical_family="None",
                duration_days=int(suelo.get("dt_trans_dias", 15)),
                Cp=float(suelo.get("Cp_suelo", 18000.0)),
                hc=float(suelo.get("h_suelo", 24.0)),
                alpha=float(suelo.get("alpha_suelo", 0.72)),
                gamma_max=0.0,
                gamma_max_daily_mm=0.0,
                lambda_gamma_max=0.0,
                T_opt=float(suelo.get("T_opt", 20.0)),
                delta_T_tol=float(suelo.get("dT_tol", 15.0)),
                T_frost=float(suelo.get("T_helada", -5.0)),
                T_lethal=float(suelo.get("T_letal", 50.0)),
                Zr_mm=0.0,
                K_W_mm=1.0,
                W_pmp=0.0,
                W_crit=0.0,
                W_fc=50.0,
                HI=0.0,
                F_fix=0.0,
                ka_N=0.0,
                ka_P=0.0,
                ka_K=0.0,
                price_usd_t=0.0,
                base_cost_usd_ha=100.0,
            )
            catalog["suelo_desnudo_transicion"] = param_suelo
            catalog["barbecho"] = param_suelo
            catalog["transicion"] = param_suelo
        except Exception as e:
            print(f"Error cargando catálogo oficial: {e}")

    return global_consts, catalog, raw_metadata


GLOBAL_CONSTANTS, CROP_CATALOG, CATALOG_METADATA = _load_catalog()


def get_crop_parameters(crop_id: str) -> CropParameters:
    key = crop_id.strip().lower()
    if key in CROP_CATALOG:
        return CROP_CATALOG[key]
    # Búsqueda por coincidencia parcial (ej: 'maiz' en 'maiz_zea_mays')
    for k, param in CROP_CATALOG.items():
        if key in k:
            return param
    return CROP_CATALOG.get("maiz", list(CROP_CATALOG.values())[0])
