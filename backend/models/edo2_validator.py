"""
Agrophysical JSON catalog validator specifically for ODE 2 (Root-Zone Water Balance).
Verifies presence, types, physical ranges, and mathematical consistency of parameters
required for ODE 2 integration per AgroPhasor.pdf (Sections 3.2.2, 3.3, and 2.6.2).
"""

import json
import os
from typing import Dict, Any, List, Optional, Union, Tuple

from backend.models.crop_parameters import normalize_catalog_dict


class EDO2ValidationError(ValueError):
    """Exception raised for critical agrophysical validation errors in ODE 2."""
    pass


def validate_edo2_catalog(
    source: Union[str, Dict[str, Any]],
    default_theta_fc: float = 0.30,
    default_theta_wp: float = 0.14
) -> Dict[str, Any]:
    """
    Validates that a JSON file or dictionary satisfies all ODE 2 requirements:
    
    1. constantes_globales:
       - E_suelo0_mm_dia > 0 (Bare-soil basal evaporation, mm/day)
       - lambda_B_ha_t > 0 (Biomass light-extinction factor, ha/t)
    2. suelo_desnudo_transicion:
       - gamma_max == 0.0 (No active crop transpiration in transition/fallow)
    3. cultivos:
       For each crop:
       - Zr_mm > 0 (Effective rooting depth, mm)
       - p_agotamiento in (0, 1) (FAO 56 allowable water depletion fraction)
       - gamma_max > 0 (Maximum stomatal conductance)
       - B_max_t_ha > 0 (Biomass ceiling for soil shading)
       - B0_t_ha > 0 (Initial / stover biomass)
    
    Also computes the derived hydrological summary (Wcc, Wpmp, Wcrit, RAW).
    """
    if isinstance(source, str):
        if not os.path.exists(source):
            raise FileNotFoundError(f"JSON file not found: {source}")
        with open(source, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(source, dict):
        data = source
    else:
        raise TypeError("source must be a file path (str) or a dictionary.")

    data = normalize_catalog_dict(data)

    errors: List[str] = []
    warnings: List[str] = []
    crops_summary: Dict[str, Any] = {}

    # 1. Validate constantes_globales
    globales = data.get("constantes_globales")
    if not isinstance(globales, dict):
        errors.append("Missing required 'constantes_globales' section in JSON.")
        e_suelo0 = 4.2
        lambda_b = 0.45
    else:
        # E_suelo0_mm_dia
        if "E_suelo0_mm_dia" not in globales:
            errors.append("Missing 'E_suelo0_mm_dia' in 'constantes_globales' (required for ODE 2 evaporation).")
            e_suelo0 = 4.2
        else:
            e_suelo0 = float(globales["E_suelo0_mm_dia"])
            if e_suelo0 <= 0 or e_suelo0 > 25.0:
                errors.append(f"Non-physical value for E_suelo0_mm_dia: {e_suelo0}. Must be in (0, 25] mm/day.")

        # lambda_B_ha_t
        if "lambda_B_ha_t" not in globales:
            errors.append("Missing 'lambda_B_ha_t' in 'constantes_globales' (required for ODE 2 radiation attenuation).")
            lambda_b = 0.45
        else:
            lambda_b = float(globales["lambda_B_ha_t"])
            if lambda_b <= 0 or lambda_b > 5.0:
                errors.append(f"Non-physical value for lambda_B_ha_t: {lambda_b}. Must be in (0, 5] ha/t.")

    # 2. Validate suelo_desnudo_transicion
    transicion = data.get("suelo_desnudo_transicion")
    if not isinstance(transicion, dict):
        warnings.append("Missing 'suelo_desnudo_transicion' section. Defaulting gamma_max = 0.0.")
    else:
        g_max_trans = float(transicion.get("gamma_max", 0.0))
        if g_max_trans != 0.0:
            errors.append(f"gamma_max in 'suelo_desnudo_transicion' must be 0.0 (detected: {g_max_trans}).")

    # 3. Validate cultivos
    cultivos = data.get("cultivos")
    if not isinstance(cultivos, dict) or len(cultivos) == 0:
        errors.append("Missing 'cultivos' section or no crops defined.")
    else:
        for crop_id, c in cultivos.items():
            crop_errors = []
            
            # Zr_mm (Rooting depth)
            zr = c.get("Zr_mm")
            if zr is None:
                crop_errors.append(f"{crop_id}: missing 'Zr_mm'.")
                zr = 600.0
            else:
                zr = float(zr)
                if zr < 50.0 or zr > 4000.0:
                    crop_errors.append(f"{crop_id}: 'Zr_mm' ({zr}) outside reasonable agronomic range [50, 4000] mm.")

            # p_agotamiento (FAO 56 depletion fraction)
            p_agot = c.get("p_agotamiento")
            if p_agot is None:
                crop_errors.append(f"{crop_id}: missing 'p_agotamiento'.")
                p_agot = 0.50
            else:
                p_agot = float(p_agot)
                if not (0.05 <= p_agot <= 0.95):
                    crop_errors.append(f"{crop_id}: 'p_agotamiento' ({p_agot}) must be in range (0.05, 0.95).")

            # gamma_max
            g_max = c.get("gamma_max")
            if g_max is None:
                crop_errors.append(f"{crop_id}: missing 'gamma_max'.")
                g_max = 0.00015
            else:
                g_max = float(g_max)
                if g_max <= 0.0:
                    crop_errors.append(f"{crop_id}: 'gamma_max' ({g_max}) must be strictly positive.")

            # B_max_t_ha and B0_t_ha
            b_max = float(c.get("B_max_t_ha", 15.0))
            b_0 = float(c.get("B0_t_ha", 0.20))
            if b_max <= 0:
                crop_errors.append(f"{crop_id}: 'B_max_t_ha' must be > 0.")
            if b_0 <= 0 or b_0 > b_max:
                crop_errors.append(f"{crop_id}: 'B0_t_ha' ({b_0}) must be > 0 and <= B_max_t_ha ({b_max}).")

            k_w = c.get("K_W_mm")
            if k_w is not None:
                k_w = float(k_w)
                if k_w <= 0:
                    crop_errors.append(f"{crop_id}: 'K_W_mm' ({k_w}) must be > 0.")

            if crop_errors:
                errors.extend(crop_errors)
            else:
                # Compute derived hydraulic properties using reference soil
                w_cc = round(default_theta_fc * zr, 2)
                w_pmp = round(default_theta_wp * zr, 2)
                w_crit = round(w_cc - p_agot * (w_cc - w_pmp), 2)
                raw = round(w_cc - w_crit, 2)
                taw = round(w_cc - w_pmp, 2)
                
                # Daily conductance conversion: kg/(m2*s*kPa) -> mm/(kPa*day)
                gamma_daily_mm = round(float(c.get("gamma_max_mm_dia_kPa", g_max * 86400.0)), 3)

                crops_summary[crop_id] = {
                    "nombre": c.get("nombre", crop_id),
                    "familia_botanica": c.get("familia_botanica", "Unknown"),
                    "Zr_mm": zr,
                    "p_agotamiento": p_agot,
                    "K_W_mm": k_w if k_w is not None else round(0.5 * (w_crit - w_pmp), 2),
                    "gamma_max_raw": g_max,
                    "gamma_max_mm_per_kpa_day": gamma_daily_mm,
                    "W_cc_mm": w_cc,
                    "W_pmp_mm": w_pmp,
                    "W_crit_mm": w_crit,
                    "TAW_mm": taw,
                    "RAW_mm": raw,
                    "B_max_t_ha": b_max,
                    "B0_t_ha": b_0
                }

    is_valid = len(errors) == 0

    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "global_parameters_edo2": {
            "E_suelo0_mm_dia": e_suelo0,
            "lambda_B_ha_t": lambda_b,
        },
        "crops_validated_count": len(crops_summary),
        "crops_summary": crops_summary
    }
