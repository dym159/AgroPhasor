"""
Catálogo oficial de parámetros biofísicos y fisiológicos de cultivos de AgroPhasor.
Carga automáticamente las constantes globales y fichas técnicas desde `backend/data/crop_catalog.json`.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple

CATALOG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "crop_catalog.json")
BASE_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GEMINI_CODE_PATH = os.path.join(BASE_PROJECT_DIR, "gemini-code-1794737993920.json")


@dataclass(frozen=True)
class CropParameters:
    key: str
    name: str
    botanical_family: str
    duration_days: int = 120
    Cp: float = 35000.0              # Capacidad calorífica [J / (m² · °C)]
    hc: float = 28.0                 # Coeficiente convectivo [W / (m² · °C)]
    alpha: float = 0.80              # Absortividad solar [adimensional]
    gamma_max: float = 0.00015       # Conductancia máxima estomática [kg / (m² · s · kPa)]
    lambda_gamma_max: float = 367.5  # Capacidad refrigerante efectiva [W / (m² · kPa)]
    T_opt: float = 20.0              # Temperatura óptima de confort [°C]
    delta_T_tol: float = 10.0        # Tolerancia térmica [°C]
    T_frost: float = 1.0             # Umbral de helada [°C]
    T_lethal: float = 40.0           # Umbral letal [°C]
    Zr_mm: float = 800.0             # Profundidad radicular [mm]
    p_depletion: float = 0.50        # Fracción de agotamiento permisible [0, 1]
    W_pmp: float = 20.0              # Umbral de marchitez permanente [mm]
    W_crit: float = 50.0             # Umbral crítico de estrés [mm]
    W_fc: float = 75.0               # Capacidad de campo [mm]
    # Parámetros para EDO 3 y 4 (Biomasa y Nutrientes)
    kp_c: float = 0.015              # Eficiencia fotosintética
    B_max_t_ha: float = 15.0         # Techo de biomasa
    B0_t_ha: float = 0.20            # Biomasa inicial
    km_c: float = 0.008              # Tasa de mantenimiento
    HI: float = 0.45                 # Índice de cosecha
    F_fix: float = 0.0               # Fijación de Nitrógeno (leguminosas)
    F_sol: float = 0.02              # Solubilización de Fósforo
    K_N: float = 30.0                # Constante Liebig N
    K_P: float = 20.0                # Constante Liebig P
    K_K: float = 40.0                # Constante Liebig K
    # Parámetros económicos (Frente de Pareto / A*)
    price_usd_t: float = 300.0
    base_cost_usd_ha: float = 600.0


def _load_catalog() -> Tuple[Dict[str, float], Dict[str, CropParameters]]:
    global_consts: Dict[str, float] = {
        "lambda_ev_J_kg": 2450000.0,
        "Gamma_C_m": 0.0065,
        "Q10": 2.0,
        "k_er_cultivo": 0.0004,
        "k_er_labranza": 0.0035
    }
    catalog: Dict[str, CropParameters] = {}
    
    data = {}
    # Prioridad: Cargar catálogo oficial gemini-code-1794737993920.json
    for path in [GEMINI_CODE_PATH, CATALOG_PATH]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    if not data:
                        data = file_data
                    else:
                        # Combinar constantes y cultivos respetando prioridades
                        data.setdefault("constantes_globales", {}).update(file_data.get("constantes_globales", {}))
                        data.setdefault("cultivos", {}).update(file_data.get("cultivos", {}))
                        if "suelo_desnudo_transicion" in file_data:
                            data["suelo_desnudo_transicion"] = file_data["suelo_desnudo_transicion"]
            except Exception as e:
                print(f"Advertencia leyendo {path}: {e}")

    if data:
        try:
            global_consts.update(data.get("constantes_globales", {}))
            lambda_ev = global_consts.get("lambda_ev_J_kg", 2450000.0)
            
            # Cargar cultivos
            cultivos = data.get("cultivos", {})
            for raw_key, c in cultivos.items():
                g_max = float(c.get("gamma_max", 0.00015))
                # Conductancia latente efectiva = lambda_ev * gamma_max
                l_g_max = lambda_ev * g_max
                
                zr = float(c.get("Zr_mm", 800.0))
                p_agot = float(c.get("p_agotamiento", 0.5))
                
                # Suelo franco estándar: theta_fc ≈ 0.12, theta_pmp ≈ 0.04
                w_fc = round(0.12 * zr, 1)
                w_pmp = round(0.04 * zr, 1)
                w_crit = round(w_fc - p_agot * (w_fc - w_pmp), 1)
                
                param = CropParameters(
                    key=raw_key,
                    name=c.get("nombre", raw_key.split("_")[0]),
                    botanical_family=c.get("familia_botanica", "Unknown"),
                    duration_days=int(c.get("duracion_dias", 120)),
                    Cp=float(c.get("Cp_c", 35000.0)),
                    hc=float(c.get("h_c", 28.0)),
                    alpha=float(c.get("alpha_c", 0.80)),
                    gamma_max=g_max,
                    lambda_gamma_max=l_g_max,
                    T_opt=float(c.get("T_opt", 20.0)),
                    delta_T_tol=float(c.get("dT_tol", 10.0)),
                    T_frost=float(c.get("T_helada", 1.0)),
                    T_lethal=float(c.get("T_letal", 40.0)),
                    Zr_mm=zr,
                    p_depletion=p_agot,
                    W_pmp=w_pmp,
                    W_crit=w_crit,
                    W_fc=w_fc,
                    kp_c=float(c.get("kp_c", 0.015)),
                    B_max_t_ha=float(c.get("B_max_t_ha", 15.0)),
                    B0_t_ha=float(c.get("B0_t_ha", 0.20)),
                    km_c=float(c.get("km_c_dia", 0.008)),
                    HI=float(c.get("HI", 0.45)),
                    F_fix=float(c.get("F_fix", 0.0)),
                    F_sol=float(c.get("F_sol", 0.02)),
                    K_N=float(c.get("K_N", 30.0)),
                    K_P=float(c.get("K_P", 20.0)),
                    K_K=float(c.get("K_K", 40.0)),
                    price_usd_t=float(c.get("precio_usd_t", 300.0)),
                    base_cost_usd_ha=float(c.get("costo_base_usd_ha", 600.0))
                )
                
                # Guardamos por nombre canónico y alias simplificado
                catalog[raw_key.lower()] = param
                short_key = raw_key.split("_")[0].lower()
                catalog[short_key] = param
                
            # Cargar suelo desnudo / transición
            suelo = data.get("suelo_desnudo_transicion", {})
            param_suelo = CropParameters(
                key="suelo_desnudo_transicion",
                name=suelo.get("nombre", "Suelo Desnudo / Barbecho"),
                botanical_family="None",
                duration_days=30,
                Cp=float(suelo.get("Cp_suelo", 18000.0)),
                hc=float(suelo.get("h_suelo", 24.0)),
                alpha=float(suelo.get("alpha_suelo", 0.72)),
                gamma_max=0.0,
                lambda_gamma_max=0.0,
                T_opt=float(suelo.get("T_opt", 20.0)),
                delta_T_tol=float(suelo.get("dT_tol", 15.0)),
                T_frost=float(suelo.get("T_helada", -5.0)),
                T_lethal=float(suelo.get("T_letal", 50.0)),
                Zr_mm=0.0,
                W_pmp=0.0,
                W_crit=0.0,
                W_fc=50.0,
                HI=0.0,
                F_fix=0.0,
                price_usd_t=0.0,
                base_cost_usd_ha=100.0
            )
            catalog["suelo_desnudo_transicion"] = param_suelo
            catalog["barbecho"] = param_suelo
            catalog["transicion"] = param_suelo
        except Exception as e:
            print(f"Error cargando catálogo oficial: {e}")
            
    return global_consts, catalog


from backend.models.edo2_validator import validate_edo2_catalog

GLOBAL_CONSTANTS, CROP_CATALOG = _load_catalog()


def get_crop_parameters(crop_id: str) -> CropParameters:
    key = crop_id.strip().lower()
    if key in CROP_CATALOG:
        return CROP_CATALOG[key]
    # Búsqueda por coincidencia parcial (ej: 'maiz' en 'maiz_zea_mays')
    for k, param in CROP_CATALOG.items():
        if key in k:
            return param
    return CROP_CATALOG.get("maiz", list(CROP_CATALOG.values())[0])
