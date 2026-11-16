"""
Agrophysical JSON catalog validator specifically for ODE 3 (Macronutrient Vector Dynamics).
Verifies presence, types, units, and biophysical ranges of parameters required
for the evolution of N_i,j(t) = [N, P, K]^T per AgroPhasor.pdf (Sections 3.2.3, 3.3, 1.2, and 2.5).
"""

import json
import os
from typing import Dict, Any, List, Optional, Union, Tuple

from backend.models.crop_parameters import normalize_catalog_dict


class EDO3ValidationError(ValueError):
    """Exception raised for critical agrophysical validation errors in ODE 3."""
    pass


def validate_edo3_catalog(
    source: Union[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Validates that a JSON file or dictionary satisfies all ODE 3 requirements:
    
    1. constantes_globales:
       - k_min0_dia > 0: Basal microbial OM mineralization rate (1/day).
       - Q10 >= 1.0: Enzymatic thermal coefficient Q10 (typical 2.0).
       - k_lN > 0: Vertical Nitrogen leaching rate (1/day or CEC-dependent).
       - k_lK > 0: Vertical Potassium leaching rate (1/day or CEC-dependent).
       - beta_K > 0: Stover Potassium content and recycling factor.
       - k_dec_dia > 0: Transition stover decomposition rate (1/day).
       - xi_N, xi_P, xi_K > 0: Erosion-driven nutrient drag coefficients (dH/dt).
       
    2. cultivos:
       For each crop:
       - F_fix >= 0: Biological N fixation (> 0 for Fabaceae / legumes).
       - F_sol >= 0: Root P solubilization.
       - K_N, K_P, K_K > 0: Liebig's Law half-saturation constants (kg/ha).
       - familia_botanica: Taxonomic family (for pest-cycle breaking constraints).
       - B_max_t_ha > 0: Maximum biomass for stover production and N fixation.
       - HI in (0, 1): Harvest Index for computing post-harvest biomass residue.
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
        extracted_globals = {}
    else:
        extracted_globals = {}
        # Required parameters for ODE 3
        req_globals = {
            "k_min0_dia": (0.0001, 0.1),
            "Q10": (1.0, 4.0),
            "k_lN": (0.0001, 0.5),
            "k_lK": (0.0001, 0.5),
            "beta_K": (0.01, 50.0),
            "k_dec_dia": (0.001, 0.2),
            "xi_N": (0.0001, 0.5),
            "xi_P": (0.0001, 0.5),
            "xi_K": (0.0001, 0.5)
        }
        
        for p_name, (min_val, max_val) in req_globals.items():
            if p_name not in globales:
                errors.append(f"Missing '{p_name}' in 'constantes_globales' (required for ODE 3 kinetics).")
            else:
                try:
                    val = float(globales[p_name])
                    if not (min_val <= val <= max_val):
                        warnings.append(f"Parameter '{p_name}' ({val}) outside typical agrophysical range [{min_val}, {max_val}].")
                    extracted_globals[p_name] = val
                except (ValueError, TypeError):
                    errors.append(f"'{p_name}' in 'constantes_globales' must be numeric.")

    # 2. Validate cultivos
    cultivos = data.get("cultivos")
    if not isinstance(cultivos, dict) or len(cultivos) == 0:
        errors.append("Missing 'cultivos' section or no crops defined.")
    else:
        has_legume = False
        for crop_id, c in cultivos.items():
            crop_errors = []
            
            # Botanical family
            familia = c.get("familia_botanica")
            if not familia:
                crop_errors.append(f"{crop_id}: missing 'familia_botanica' (required for A* pest-rotation constraints).")
            
            # F_fix (Nitrogen fixation)
            f_fix = c.get("F_fix")
            if f_fix is None:
                crop_errors.append(f"{crop_id}: missing 'F_fix' (symbiotic N fixation).")
                f_fix = 0.0
            else:
                f_fix = float(f_fix)
                if f_fix < 0.0:
                    crop_errors.append(f"{crop_id}: 'F_fix' cannot be negative.")
                if f_fix > 0.0:
                    has_legume = True
                    if familia and "fab" not in familia.lower() and "legum" not in familia.lower():
                        warnings.append(f"{crop_id}: F_fix > 0 ({f_fix}) but family '{familia}' is not Fabaceae/Legume.")

            # F_sol (Phosphorus solubilization)
            f_sol = c.get("F_sol")
            if f_sol is None:
                crop_errors.append(f"{crop_id}: missing 'F_sol' (root P solubilization).")
                f_sol = 0.0
            else:
                f_sol = float(f_sol)
                if f_sol < 0.0:
                    crop_errors.append(f"{crop_id}: 'F_sol' cannot be negative.")

            # Liebig half-saturation constants K_N, K_P, K_K
            for k_nut in ["K_N", "K_P", "K_K"]:
                k_val = c.get(k_nut)
                if k_val is None:
                    crop_errors.append(f"{crop_id}: missing Liebig constant '{k_nut}'.")
                else:
                    k_val = float(k_val)
                    if k_val <= 0.0:
                        crop_errors.append(f"{crop_id}: '{k_nut}' ({k_val}) must be strictly positive.")

            # Root nutrient uptake rates ka_N, ka_P, ka_K (when present in gemini-code.json)
            for ka_nut in ["ka_N_mm_inv_dia", "ka_P_mm_inv_dia", "ka_K_mm_inv_dia"]:
                ka_val = c.get(ka_nut)
                if ka_val is not None and float(ka_val) <= 0.0:
                    crop_errors.append(f"{crop_id}: '{ka_nut}' ({ka_val}) must be strictly positive.")

            # B_max_t_ha and HI
            b_max = float(c.get("B_max_t_ha", 15.0))
            hi = float(c.get("HI", 0.45))
            if b_max <= 0:
                crop_errors.append(f"{crop_id}: 'B_max_t_ha' must be > 0.")
            if not (0.05 <= hi <= 0.90):
                crop_errors.append(f"{crop_id}: 'HI' ({hi}) outside agronomic range [0.05, 0.90].")

            if crop_errors:
                errors.extend(crop_errors)
            else:
                # Fraction of post-harvest residue / stover remaining in the field
                r_res = round(1.0 - hi, 3)
                k_n = float(c.get("K_N", 30.0))
                k_p = float(c.get("K_P", 20.0))
                k_k = float(c.get("K_K", 40.0))

                crops_summary[crop_id] = {
                    "familia_botanica": familia,
                    "es_fijador_N": f_fix > 0.0,
                    "F_fix": f_fix,
                    "F_sol": f_sol,
                    "ka_N_mm_inv_dia": float(c.get("ka_N_mm_inv_dia", 0.00018)),
                    "ka_P_mm_inv_dia": float(c.get("ka_P_mm_inv_dia", 0.00012)),
                    "ka_K_mm_inv_dia": float(c.get("ka_K_mm_inv_dia", 0.00015)),
                    "Liebig_K_N": k_n,
                    "Liebig_K_P": k_p,
                    "Liebig_K_K": k_k,
                    "B_max_t_ha": b_max,
                    "HI": hi,
                    "fraccion_rastrojo_remanente": r_res
                }

        if not has_legume:
            warnings.append("Catalog contains no N-fixing species (F_fix > 0). Soil recovery and resilience rotations will lack biological nitrogen recharge.")

    is_valid = len(errors) == 0

    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "global_parameters_edo3": extracted_globals,
        "crops_validated_count": len(crops_summary),
        "crops_summary": crops_summary
    }


if __name__ == "__main__":
    import sys
    test_file = sys.argv[1] if len(sys.argv) > 1 else "gemini-code.json"
    result = validate_edo3_catalog(test_file)
    print("ODE 3 Validation Result for:", test_file)
    print(f"Status: {'VALID ✅' if result['valid'] else 'INVALID ❌'}")
    if result["errors"]:
        print("Errors found:")
        for err in result["errors"]:
            print(f"  - {err}")
    if result["warnings"]:
        print("Warnings:")
        for w in result["warnings"]:
            print(f"  - {w}")
    print("\nCrop Summary:")
    for cid, info in result["crops_summary"].items():
        print(f"  [{cid}] Family: {info['familia_botanica']} | N-fixer: {info['es_fijador_N']} (F_fix={info['F_fix']}) | Liebig: KN={info['Liebig_K_N']}, KP={info['Liebig_K_P']}, KK={info['Liebig_K_K']}")
