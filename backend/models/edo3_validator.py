"""
Validador agrofísico del catálogo JSON específicamente para EDO 3 (Dinámica Vectorial de Macronutrientes).
Verifica la presencia, tipos, unidades y rangos biofísicos de los parámetros necesarios
para la evolución de N_i,j(t) = [N, P, K]^T según AgroPhasor.pdf (Secciones 3.2.3, 3.3, 1.2 y 2.5).
"""

import json
import os
from typing import Dict, Any, List, Optional, Union, Tuple

from backend.models.crop_parameters import normalize_catalog_dict


class EDO3ValidationError(ValueError):
    """Excepción para errores críticos de validación agrofísica en EDO 3."""
    pass


def validate_edo3_catalog(
    source: Union[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Valida que un archivo o diccionario JSON cumpla con todos los requisitos para EDO 3:
    
    1. constantes_globales:
       - k_min0_dia > 0: Mineralización microbiana basal de OM (1/día).
       - Q10 >= 1.0: Coeficiente térmico enzimático Q10 (típico 2.0).
       - k_lN > 0: Tasa de lixiviación vertical de Nitrógeno (1/día o dependiente de CIC).
       - k_lK > 0: Tasa de lixiviación vertical de Potasio (1/día o dependiente de CIC).
       - beta_K > 0: Contenido y factor de reciclaje de Potasio en rastrojos.
       - k_dec_dia > 0: Tasa de descomposición de rastrojo en transición (1/día).
       - xi_N, xi_P, xi_K > 0: Coeficientes de pérdida por arrastre de suelo erosionado (dH/dt).
       
    2. cultivos:
       Para cada cultivo:
       - F_fix >= 0: Fijación biológica de N (> 0 para Fabaceae / leguminosas).
       - F_sol >= 0: Solubilización radicular de P.
       - K_N, K_P, K_K > 0: Constantes de semi-saturación de la Ley de Liebig (kg/ha).
       - familia_botanica: Clasificación taxonómica (para ruptura de ciclos fitosanitarios).
       - B_max_t_ha > 0: Biomasa máxima para producción de rastrojo y fijación.
       - HI en (0, 1): Índice de cosecha para calcular residuo de biomasa post-cosecha.
    """
    if isinstance(source, str):
        if not os.path.exists(source):
            raise FileNotFoundError(f"No se encontró el archivo JSON: {source}")
        with open(source, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(source, dict):
        data = source
    else:
        raise TypeError("source debe ser una ruta de archivo (str) o un diccionario.")

    data = normalize_catalog_dict(data)

    errors: List[str] = []
    warnings: List[str] = []
    crops_summary: Dict[str, Any] = {}

    # 1. Validar constantes_globales
    globales = data.get("constantes_globales")
    if not isinstance(globales, dict):
        errors.append("Falta la sección obligatoria 'constantes_globales' en el JSON.")
        extracted_globals = {}
    else:
        extracted_globals = {}
        # Lista de parámetros requeridos para EDO 3
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
                errors.append(f"Falta '{p_name}' en 'constantes_globales' (requerido para cinéticas de EDO 3).")
            else:
                try:
                    val = float(globales[p_name])
                    if not (min_val <= val <= max_val):
                        warnings.append(f"Parámetro '{p_name}' ({val}) fuera del rango agrofísico típico [{min_val}, {max_val}].")
                    extracted_globals[p_name] = val
                except (ValueError, TypeError):
                    errors.append(f"'{p_name}' en 'constantes_globales' debe ser numérico.")

    # 2. Validar cultivos
    cultivos = data.get("cultivos")
    if not isinstance(cultivos, dict) or len(cultivos) == 0:
        errors.append("Falta la sección 'cultivos' o no contiene ninguna especie.")
    else:
        has_legume = False
        for crop_id, c in cultivos.items():
            crop_errors = []
            
            # Familia botánica
            familia = c.get("familia_botanica")
            if not familia:
                crop_errors.append(f"{crop_id}: falta 'familia_botanica' (requerido para restricciones A* de plagas).")
            
            # F_fix (Fijación de Nitrógeno)
            f_fix = c.get("F_fix")
            if f_fix is None:
                crop_errors.append(f"{crop_id}: falta 'F_fix' (fijación simbiótica de N).")
                f_fix = 0.0
            else:
                f_fix = float(f_fix)
                if f_fix < 0.0:
                    crop_errors.append(f"{crop_id}: 'F_fix' no puede ser negativo.")
                if f_fix > 0.0:
                    has_legume = True
                    if familia and "fab" not in familia.lower() and "legum" not in familia.lower():
                        warnings.append(f"{crop_id}: F_fix > 0 ({f_fix}) pero familia '{familia}' no es Fabaceae/Leguminosa.")

            # F_sol (Solubilización de Fósforo)
            f_sol = c.get("F_sol")
            if f_sol is None:
                crop_errors.append(f"{crop_id}: falta 'F_sol' (solubilización radicular de P).")
                f_sol = 0.0
            else:
                f_sol = float(f_sol)
                if f_sol < 0.0:
                    crop_errors.append(f"{crop_id}: 'F_sol' no puede ser negativo.")

            # Constantes de semi-saturación de Liebig K_N, K_P, K_K
            for k_nut in ["K_N", "K_P", "K_K"]:
                k_val = c.get(k_nut)
                if k_val is None:
                    crop_errors.append(f"{crop_id}: falta constante de Liebig '{k_nut}'.")
                else:
                    k_val = float(k_val)
                    if k_val <= 0.0:
                        crop_errors.append(f"{crop_id}: '{k_nut}' ({k_val}) debe ser estrictamente positivo.")

            # Tasas de absorción radicular ka_N, ka_P, ka_K (si están presentes en gemini-code.json)
            for ka_nut in ["ka_N_mm_inv_dia", "ka_P_mm_inv_dia", "ka_K_mm_inv_dia"]:
                ka_val = c.get(ka_nut)
                if ka_val is not None and float(ka_val) <= 0.0:
                    crop_errors.append(f"{crop_id}: '{ka_nut}' ({ka_val}) debe ser estrictamente positivo.")

            # B_max_t_ha y HI
            b_max = float(c.get("B_max_t_ha", 15.0))
            hi = float(c.get("HI", 0.45))
            if b_max <= 0:
                crop_errors.append(f"{crop_id}: 'B_max_t_ha' debe ser > 0.")
            if not (0.05 <= hi <= 0.90):
                crop_errors.append(f"{crop_id}: 'HI' ({hi}) fuera de rango agronómico [0.05, 0.90].")

            if crop_errors:
                errors.extend(crop_errors)
            else:
                # Fracción de residuo / rastrojo remanente en campo tras cosecha
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
            warnings.append("El catálogo no contiene ninguna especie fijadora de N (F_fix > 0). Las rutas de 'Hospital de Suelo' y 'Resiliencia' no podrán recargar nitrógeno biológicamente.")

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
    print("Resultado de Validación EDO 3 para:", test_file)
    print(f"Estado: {'VÁLIDO ✅' if result['valid'] else 'INVÁLIDO ❌'}")
    if result["errors"]:
        print("Errores encontrados:")
        for err in result["errors"]:
            print(f"  - {err}")
    if result["warnings"]:
        print("Advertencias:")
        for w in result["warnings"]:
            print(f"  - {w}")
    print("\nResumen de Cultivos:")
    for cid, info in result["crops_summary"].items():
        print(f"  [{cid}] Familia: {info['familia_botanica']} | Fijador N: {info['es_fijador_N']} (F_fix={info['F_fix']}) | Liebig: KN={info['Liebig_K_N']}, KP={info['Liebig_K_P']}, KK={info['Liebig_K_K']}")
