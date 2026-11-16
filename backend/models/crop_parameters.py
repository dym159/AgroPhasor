"""
Official biophysical and physiological crop parameter catalog for AgroPhasor.
Automatically loads global constants and crop technical sheets from `backend/data/crop_catalog.json`.
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
    Cp: float = 35000.0              # Heat capacity [J / (m² · °C)]
    hc: float = 28.0                 # Convective heat transfer coefficient [W / (m² · °C)]
    alpha: float = 0.80              # Solar absorptivity [dimensionless]
    gamma_max: float = 0.00015       # Maximum stomatal conductance [kg / (m² · s · kPa)]
    lambda_gamma_max: float = 367.5  # Effective latent cooling capacity [W / (m² · kPa)]
    T_opt: float = 20.0              # Optimal comfort temperature [°C]
    delta_T_tol: float = 10.0        # Thermal tolerance [°C]
    T_frost: float = 1.0             # Frost threshold [°C]
    T_lethal: float = 40.0           # Lethal threshold [°C]
    Zr_mm: float = 800.0             # Root depth [mm]
    p_depletion: float = 0.50        # Allowable depletion fraction [0, 1]
    W_pmp: float = 20.0              # Permanent wilting point [mm]
    W_crit: float = 50.0             # Critical stress threshold [mm]
    W_fc: float = 75.0               # Field capacity [mm]
    # Parameters for ODE 3 and ODE 4 (Biomass and Nutrients)
    kp_c: float = 0.015              # Photosynthetic conversion efficiency
    B_max_t_ha: float = 15.0         # Maximum biomass ceiling
    B0_t_ha: float = 0.20            # Initial basal biomass
    km_c: float = 0.008              # Maintenance respiration rate
    HI: float = 0.45                 # Harvest Index
    F_fix: float = 0.0               # Biological Nitrogen fixation (legumes)
    F_sol: float = 0.02              # Root Phosphorus solubilization
    K_N: float = 30.0                # Liebig half-saturation constant for N
    K_P: float = 20.0                # Liebig half-saturation constant for P
    K_K: float = 40.0                # Liebig half-saturation constant for K
    # Economic parameters (Pareto front / A*)
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
    # Priority: Load official catalog gemini-code-1794737993920.json first
    for path in [GEMINI_CODE_PATH, CATALOG_PATH]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    if not data:
                        data = file_data
                    else:
                        # Merge constants and crops while respecting source priority
                        data.setdefault("constantes_globales", {}).update(file_data.get("constantes_globales", {}))
                        data.setdefault("cultivos", {}).update(file_data.get("cultivos", {}))
                        if "suelo_desnudo_transicion" in file_data:
                            data["suelo_desnudo_transicion"] = file_data["suelo_desnudo_transicion"]
            except Exception as e:
                print(f"Warning reading {path}: {e}")

    if data:
        try:
            global_consts.update(data.get("constantes_globales", {}))
            lambda_ev = global_consts.get("lambda_ev_J_kg", 2450000.0)
            
            # Load crops
            cultivos = data.get("cultivos", {})
            for raw_key, c in cultivos.items():
                g_max = float(c.get("gamma_max", 0.00015))
                # Effective latent conductance = lambda_ev * gamma_max
                l_g_max = lambda_ev * g_max
                
                zr = float(c.get("Zr_mm", 800.0))
                p_agot = float(c.get("p_agotamiento", 0.5))
                
                # Standard loam soil: theta_fc ≈ 0.12, theta_pmp ≈ 0.04
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
                
                # Store by canonical name and simplified alias
                catalog[raw_key.lower()] = param
                short_key = raw_key.split("_")[0].lower()
                catalog[short_key] = param
                
            # Load bare soil / transition
            suelo = data.get("suelo_desnudo_transicion", {})
            param_suelo = CropParameters(
                key="suelo_desnudo_transicion",
                name=suelo.get("nombre", "Bare Soil / Fallow"),
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
            print(f"Error loading official catalog: {e}")
            
    return global_consts, catalog


from backend.models.edo2_validator import validate_edo2_catalog

GLOBAL_CONSTANTS, CROP_CATALOG = _load_catalog()


def get_crop_parameters(crop_id: str) -> CropParameters:
    key = crop_id.strip().lower()
    if key in CROP_CATALOG:
        return CROP_CATALOG[key]
    # Partial-match lookup (e.g., 'maiz' in 'maiz_zea_mays')
    for k, param in CROP_CATALOG.items():
        if key in k:
            return param
    return CROP_CATALOG.get("maiz", list(CROP_CATALOG.values())[0])
