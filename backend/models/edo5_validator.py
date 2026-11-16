"""
Agrophysical JSON catalog validator specifically for ODE 5: Topsoil Water Erosion.
Verifies presence, types, units, biophysical ranges, and mathematical consistency of parameters
required for H_i,j(t) integration per AgroPhasor.pdf (Sections 3.2.5, 3.3, 1.5.1, 1.6.2, and 3.5).
"""

import json
import os
from typing import Dict, Any, List, Optional, Union, Tuple


class EDO5ValidationError(ValueError):
    """Exception raised for critical agrophysical validation errors in ODE 5."""
    pass


def validate_edo5_catalog(
    source: Union[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Validates that a JSON file or dictionary satisfies all biophysical requirements for ODE 5:
    
    1. constantes_globales:
       - k_er_cultivo > 0: Erodibility coefficient under living crop cover (mm / (mm_rain * day)).
         Typical range: [0.0001, 0.001]. AgroPhasor calibration value: 0.0004.
       - k_er_labranza > 0: Erodibility coefficient during transition/tillage (disturbed soil).
         Typical range: [0.001, 0.01]. AgroPhasor calibration value: 0.0035.
         Mandatory physical condition: k_er_labranza > k_er_cultivo (greater mechanical vulnerability).
       - lambda_B_ha_t > 0: Rainfall-impact attenuation coefficient per unit biomass (ha/t).
         Typical range: [0.2, 0.8]. AgroPhasor calibration value: 0.45.
       - xi_N, xi_P, xi_K > 0: Mechanical nutrient-drag coefficients with eroded soil.
         Calibration values: xi_N = 0.004, xi_P = 0.008, xi_K = 0.003.
         
    2. cultivos:
       For each crop in the catalog:
       - B_max_t_ha > 0: Biomass ceiling to compute peak canopy protection exp(-lambda_B * B_max).
       - B0_t_ha >= 0: Initial germination / transplant biomass.
       - duracion_dias > 0: Phenological cycle duration for cumulative erosion tracking.
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

    errors: List[str] = []
    warnings: List[str] = []
    crops_summary: Dict[str, Any] = {}

    # 1. Validate constantes_globales
    globales = data.get("constantes_globales")
    if not isinstance(globales, dict):
        errors.append("Missing required 'constantes_globales' section in JSON.")
        extracted_globals = {}
    else:
        extracted_globals = {}
        # Crop erodibility coefficient
        k_er_cultivo = globales.get("k_er_cultivo")
        if k_er_cultivo is None:
            errors.append("Missing 'k_er_cultivo' in constantes_globales.")
        elif not isinstance(k_er_cultivo, (int, float)) or k_er_cultivo <= 0.0:
            errors.append(f"'k_er_cultivo' must be a positive number, got: {k_er_cultivo}")
        elif not (0.00005 <= k_er_cultivo <= 0.005):
            warnings.append(f"'k_er_cultivo' ({k_er_cultivo}) outside standard biophysical range [0.00005, 0.005].")
        else:
            extracted_globals["k_er_cultivo"] = float(k_er_cultivo)

        # Tillage / transition erodibility coefficient
        k_er_labranza = globales.get("k_er_labranza")
        if k_er_labranza is None:
            errors.append("Missing 'k_er_labranza' in constantes_globales.")
        elif not isinstance(k_er_labranza, (int, float)) or k_er_labranza <= 0.0:
            errors.append(f"'k_er_labranza' must be a positive number, got: {k_er_labranza}")
        elif not (0.0005 <= k_er_labranza <= 0.05):
            warnings.append(f"'k_er_labranza' ({k_er_labranza}) outside standard biophysical range [0.0005, 0.05].")
        else:
            extracted_globals["k_er_labranza"] = float(k_er_labranza)

        # Relative physical consistency between tillage and active crop cover
        if "k_er_cultivo" in extracted_globals and "k_er_labranza" in extracted_globals:
            if extracted_globals["k_er_labranza"] <= extracted_globals["k_er_cultivo"]:
                errors.append(
                    f"Physical inconsistency: 'k_er_labranza' ({extracted_globals['k_er_labranza']}) "
                    f"must be strictly greater than 'k_er_cultivo' ({extracted_globals['k_er_cultivo']}). "
                    f"Disturbed bare soil must be more vulnerable to water erosion."
                )

        # Biomass extinction coefficient lambda_B
        lambda_b = globales.get("lambda_B_ha_t")
        if lambda_b is None:
            errors.append("Missing 'lambda_B_ha_t' in constantes_globales.")
        elif not isinstance(lambda_b, (int, float)) or lambda_b <= 0.0:
            errors.append(f"'lambda_B_ha_t' must be a positive number, got: {lambda_b}")
        elif not (0.1 <= lambda_b <= 1.5):
            warnings.append(f"'lambda_B_ha_t' ({lambda_b}) outside typical agronomic range [0.1, 1.5].")
        else:
            extracted_globals["lambda_B_ha_t"] = float(lambda_b)

        # Macronutrient drag coefficients (xi_N, xi_P, xi_K)
        for nut in ["xi_N", "xi_P", "xi_K"]:
            val = globales.get(nut)
            if val is None:
                errors.append(f"Missing '{nut}' (eroded-soil nutrient drag coefficient) in constantes_globales.")
            elif not isinstance(val, (int, float)) or val <= 0.0:
                errors.append(f"'{nut}' must be a positive number, got: {val}")
            else:
                extracted_globals[nut] = float(val)

    # 2. Validate cultivos
    cultivos = data.get("cultivos")
    if not isinstance(cultivos, dict) or len(cultivos) == 0:
        errors.append("Missing or empty required 'cultivos' section in JSON.")
    else:
        lambda_b_val = extracted_globals.get("lambda_B_ha_t", 0.45)
        for crop_id, crop_data in cultivos.items():
            if not isinstance(crop_data, dict):
                errors.append(f"Crop '{crop_id}' must be an object/dictionary.")
                continue

            crop_errors = []
            
            # Maximum biomass
            b_max = crop_data.get("B_max_t_ha")
            if b_max is None:
                crop_errors.append(f"Missing 'B_max_t_ha' in crop '{crop_id}'.")
                b_max_f = 10.0
            elif not isinstance(b_max, (int, float)) or b_max <= 0.0:
                crop_errors.append(f"'B_max_t_ha' must be positive in '{crop_id}', got: {b_max}")
                b_max_f = 10.0
            else:
                b_max_f = float(b_max)

            # Initial biomass
            b0 = crop_data.get("B0_t_ha")
            if b0 is None:
                crop_errors.append(f"Missing 'B0_t_ha' in crop '{crop_id}'.")
                b0_f = 0.2
            elif not isinstance(b0, (int, float)) or b0 < 0.0:
                crop_errors.append(f"'B0_t_ha' must be >= 0 in '{crop_id}', got: {b0}")
                b0_f = 0.2
            else:
                b0_f = float(b0)

            # Biological consistency
            if b0_f >= b_max_f:
                crop_errors.append(f"In '{crop_id}', B0_t_ha ({b0_f}) must be less than B_max_t_ha ({b_max_f}).")

            # Cycle duration
            dur = crop_data.get("duracion_dias")
            if dur is None or not isinstance(dur, (int, float)) or dur <= 0:
                crop_errors.append(f"Missing valid 'duracion_dias' in '{crop_id}'.")
                dur_days = 90
            else:
                dur_days = int(dur)

            # Canopy biomass protection factor: 1 - exp(-lambda_B * B)
            # Range: initial protection at B0 to peak mature protection at B_max
            protection_min = float(round(1.0 - (2.718281828459045 ** (-lambda_b_val * b0_f)), 4))
            protection_max = float(round(1.0 - (2.718281828459045 ** (-lambda_b_val * b_max_f)), 4))

            crops_summary[crop_id] = {
                "nombre": crop_data.get("nombre", crop_id),
                "familia_botanica": crop_data.get("familia_botanica", "Unknown"),
                "duracion_dias": dur_days,
                "B_max_t_ha": b_max_f,
                "B0_t_ha": b0_f,
                "soil_protection_initial_pct": round(protection_min * 100.0, 2),
                "soil_protection_peak_pct": round(protection_max * 100.0, 2)
            }

            errors.extend(crop_errors)

    is_valid = len(errors) == 0
    if not is_valid and isinstance(source, str):
        # Reported in returned dictionary
        pass

    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "global_parameters_edo5": extracted_globals,
        "crops_validated_count": len(crops_summary),
        "crops_summary": crops_summary
    }
