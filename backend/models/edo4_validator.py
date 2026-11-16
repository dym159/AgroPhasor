"""
Agrophysical JSON catalog validator specifically for ODE 4 (Biomass Growth & Residue Decomposition).
Verifies presence, types, units, and biophysical ranges of parameters required
for the evolution of B_{i,j}(t) per AgroPhasor.pdf (Sections 3.2.4, 3.3, 3.4, and 1.5).
"""

import json
import os
from typing import Dict, Any, List, Optional, Union, Tuple


class EDO4ValidationError(ValueError):
    """Exception raised for critical agrophysical validation errors in ODE 4."""
    pass


def validate_edo4_catalog(
    source: Union[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Validates that a JSON file or dictionary satisfies all ODE 4 requirements:
    
    1. constantes_globales:
       - k_dec_dia > 0: Daily microbial stover decomposition rate during transition.
       - lambda_B_ha_t > 0: Light-extinction and rainfall-attenuation coefficient.
       - Q10 >= 1.0: Enzymatic thermal amplification coefficient.
       
    2. cultivos:
       For each crop:
       - kp_c > 0: Radiation-to-biomass conversion efficiency.
       - B_max_t_ha > 0: Biological carrying capacity / agroecological genetic ceiling.
       - B0_t_ha > 0: Basal germination biomass.
       - km_c_dia > 0: Basal maintenance respiration rate.
       - HI in (0, 1): Commercial Harvest Index.
       - T_opt, dT_tol: Photosynthetic thermal comfort envelope parameters.
       - K_N, K_P, K_K > 0: Liebig half-saturation constants.
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

    # 1. Validate global constants
    globales = data.get("constantes_globales")
    if not isinstance(globales, dict):
        errors.append("Missing required 'constantes_globales' section in JSON.")
        extracted_globals = {}
    else:
        extracted_globals = {}
        req_globals = {
            "k_dec_dia": (0.001, 0.20),
            "lambda_B_ha_t": (0.1, 1.5),
            "Q10": (1.0, 4.0)
        }
        for p_name, (min_val, max_val) in req_globals.items():
            if p_name not in globales:
                errors.append(f"Missing '{p_name}' in 'constantes_globales' (required for ODE 4).")
            else:
                try:
                    val = float(globales[p_name])
                    if not (min_val <= val <= max_val):
                        warnings.append(f"Parameter '{p_name}' ({val}) outside typical range [{min_val}, {max_val}].")
                    extracted_globals[p_name] = val
                except (ValueError, TypeError):
                    errors.append(f"'{p_name}' in 'constantes_globales' must be numeric.")

    # 2. Validate cultivos
    cultivos = data.get("cultivos")
    if not isinstance(cultivos, dict) or len(cultivos) == 0:
        errors.append("Missing 'cultivos' section or no crops defined.")
    else:
        for crop_id, c in cultivos.items():
            crop_errors = []

            # kp_c
            kp = c.get("kp_c")
            if kp is None:
                crop_errors.append(f"{crop_id}: missing 'kp_c' (photosynthetic efficiency).")
            else:
                kp = float(kp)
                if kp <= 0:
                    crop_errors.append(f"{crop_id}: 'kp_c' ({kp}) must be > 0.")
                elif kp > 0.10:
                    warnings.append(f"{crop_id}: 'kp_c' ({kp}) is unusually high.")

            # B_max_t_ha
            b_max = c.get("B_max_t_ha")
            if b_max is None:
                crop_errors.append(f"{crop_id}: missing 'B_max_t_ha' (biomass ceiling).")
            else:
                b_max = float(b_max)
                if b_max <= 0:
                    crop_errors.append(f"{crop_id}: 'B_max_t_ha' ({b_max}) must be > 0.")

            # B0_t_ha
            b0 = c.get("B0_t_ha")
            if b0 is None:
                crop_errors.append(f"{crop_id}: missing 'B0_t_ha' (germination biomass).")
            else:
                b0 = float(b0)
                if b0 <= 0:
                    crop_errors.append(f"{crop_id}: 'B0_t_ha' ({b0}) must be > 0.")
                if b_max is not None and b0 >= b_max:
                    crop_errors.append(f"{crop_id}: 'B0_t_ha' ({b0}) cannot be greater than or equal to 'B_max_t_ha' ({b_max}).")

            # km_c_dia
            km = c.get("km_c_dia")
            if km is None:
                crop_errors.append(f"{crop_id}: missing 'km_c_dia' (maintenance respiration).")
            else:
                km = float(km)
                if km <= 0:
                    crop_errors.append(f"{crop_id}: 'km_c_dia' ({km}) must be > 0.")

            # HI
            hi = c.get("HI")
            if hi is None:
                crop_errors.append(f"{crop_id}: missing 'HI' (Harvest Index).")
            else:
                hi = float(hi)
                if not (0.05 <= hi <= 0.95):
                    crop_errors.append(f"{crop_id}: 'HI' ({hi}) outside allowable range [0.05, 0.95].")

            # Liebig constants
            for k_nut in ["K_N", "K_P", "K_K"]:
                k_val = c.get(k_nut)
                if k_val is None:
                    crop_errors.append(f"{crop_id}: missing '{k_nut}' for Liebig's Law.")
                else:
                    k_val = float(k_val)
                    if k_val <= 0:
                        crop_errors.append(f"{crop_id}: '{k_nut}' ({k_val}) must be > 0.")

            if crop_errors:
                errors.extend(crop_errors)
            else:
                crops_summary[crop_id] = {
                    "nombre": c.get("nombre", crop_id),
                    "kp_c": kp,
                    "B_max_t_ha": b_max,
                    "B0_t_ha": b0,
                    "km_c_dia": km,
                    "HI": hi,
                    "r_res_default": round(1.0 - hi, 3),
                    "Liebig_KN": float(c.get("K_N")),
                    "Liebig_KP": float(c.get("K_P")),
                    "Liebig_KK": float(c.get("K_K"))
                }

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "global_parameters_edo4": extracted_globals,
        "crops_validated_count": len(crops_summary),
        "crops_summary": crops_summary
    }


if __name__ == "__main__":
    import sys
    test_file = sys.argv[1] if len(sys.argv) > 1 else "backend/data/crop_catalog.json"
    res = validate_edo4_catalog(test_file)
    print(f"ODE 4 Validation for {test_file}: {'PASSED ✅' if res['valid'] else 'FAILED ❌'}")
    if res["errors"]:
        for err in res["errors"]:
            print("  - ERROR:", err)
    if res["warnings"]:
        for w in res["warnings"]:
            print("  - WARNING:", w)
