"""
Validador agrofísico del catálogo JSON específicamente para EDO 4 (Crecimiento de Biomasa y Rastrojo).
Verifica la presencia, tipos, unidades y rangos biofísicos de los parámetros necesarios
para la evolución de B_{i,j}(t) según AgroPhasor.pdf (Secciones 3.2.4, 3.3, 3.4 y 1.5).
"""

import json
import os
from typing import Dict, Any, List, Optional, Union, Tuple

from backend.models.crop_parameters import normalize_catalog_dict


class EDO4ValidationError(ValueError):
    """Excepción para errores críticos de validación agrofísica en EDO 4."""
    pass


def validate_edo4_catalog(
    source: Union[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Valida que un archivo o diccionario JSON cumpla con todos los requisitos para EDO 4:
    
    1. constantes_globales:
       - k_dec_dia > 0: Tasa diaria de descomposición microbiana de rastrojo en transición.
       - lambda_B_ha_t > 0: Coeficiente de extinción lumínica y atenuación de lluvia.
       - Q10 >= 1.0: Coeficiente de amplificación enzimática térmica.
       
    2. cultivos:
       Para cada cultivo:
       - kp_c > 0: Eficiencia de conversión de radiación a biomasa.
       - B_max_t_ha > 0: Capacidad de carga biológica / techo genético agroecológico.
       - B0_t_ha > 0: Biomasa basal germinativa.
       - km_c_dia > 0: Tasa de respiración de mantenimiento basal.
       - HI en (0, 1): Índice de cosecha comercial (Harvest Index).
       - T_opt, dT_tol: Parámetros de la campana térmica fotosintética.
       - K_N, K_P, K_K > 0: Constantes de semi-saturación de Liebig.
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

    # 1. Validar constantes globales
    globales = data.get("constantes_globales")
    if not isinstance(globales, dict):
        errors.append("Falta la sección obligatoria 'constantes_globales' en el JSON.")
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
                errors.append(f"Falta '{p_name}' en 'constantes_globales' (requerido para EDO 4).")
            else:
                try:
                    val = float(globales[p_name])
                    if not (min_val <= val <= max_val):
                        warnings.append(f"Parámetro '{p_name}' ({val}) fuera del rango típico [{min_val}, {max_val}].")
                    extracted_globals[p_name] = val
                except (ValueError, TypeError):
                    errors.append(f"'{p_name}' en 'constantes_globales' debe ser numérico.")

    # 2. Validar cultivos
    cultivos = data.get("cultivos")
    if not isinstance(cultivos, dict) or len(cultivos) == 0:
        errors.append("Falta la sección 'cultivos' o no contiene ninguna especie.")
    else:
        for crop_id, c in cultivos.items():
            crop_errors = []

            # kp_c
            kp = c.get("kp_c")
            if kp is None:
                crop_errors.append(f"{crop_id}: falta 'kp_c' (eficiencia fotosintética).")
            else:
                kp = float(kp)
                if kp <= 0:
                    crop_errors.append(f"{crop_id}: 'kp_c' ({kp}) debe ser > 0.")
                elif kp > 0.10:
                    warnings.append(f"{crop_id}: 'kp_c' ({kp}) es inusualmente alto.")

            # B_max_t_ha
            b_max = c.get("B_max_t_ha")
            if b_max is None:
                crop_errors.append(f"{crop_id}: falta 'B_max_t_ha' (techo de biomasa).")
            else:
                b_max = float(b_max)
                if b_max <= 0:
                    crop_errors.append(f"{crop_id}: 'B_max_t_ha' ({b_max}) debe ser > 0.")

            # B0_t_ha
            b0 = c.get("B0_t_ha")
            if b0 is None:
                crop_errors.append(f"{crop_id}: falta 'B0_t_ha' (biomasa germinativa).")
            else:
                b0 = float(b0)
                if b0 <= 0:
                    crop_errors.append(f"{crop_id}: 'B0_t_ha' ({b0}) debe ser > 0.")
                if b_max is not None and b0 >= b_max:
                    crop_errors.append(f"{crop_id}: 'B0_t_ha' ({b0}) no puede ser mayor o igual que 'B_max_t_ha' ({b_max}).")

            # km_c_dia
            km = c.get("km_c_dia")
            if km is None:
                crop_errors.append(f"{crop_id}: falta 'km_c_dia' (respiración de mantenimiento).")
            else:
                km = float(km)
                if km <= 0:
                    crop_errors.append(f"{crop_id}: 'km_c_dia' ({km}) debe ser > 0.")

            # HI
            hi = c.get("HI")
            if hi is None:
                crop_errors.append(f"{crop_id}: falta 'HI' (Harvest Index).")
            else:
                hi = float(hi)
                if not (0.05 <= hi <= 0.95):
                    crop_errors.append(f"{crop_id}: 'HI' ({hi}) fuera de rango admisible [0.05, 0.95].")

            # Liebig constants
            for k_nut in ["K_N", "K_P", "K_K"]:
                k_val = c.get(k_nut)
                if k_val is None:
                    crop_errors.append(f"{crop_id}: falta '{k_nut}' para Ley de Liebig.")
                else:
                    k_val = float(k_val)
                    if k_val <= 0:
                        crop_errors.append(f"{crop_id}: '{k_nut}' ({k_val}) debe ser > 0.")

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
                    "es_cosecha_multiple": bool(c.get("es_cosecha_multiple", False)),
                    "t_inicio_cosecha_dias": int(c.get("t_inicio_cosecha_dias", c.get("duracion_dias", 120))),
                    "intervalo_corte_dias": int(c.get("intervalo_corte_dias", 0)),
                    "f_corte_parcial": float(c.get("f_corte_parcial", 0.0)),
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
    print(f"Validación EDO 4 para {test_file}: {'EXITOSA ✅' if res['valid'] else 'FALLIDA ❌'}")
    if res["errors"]:
        for err in res["errors"]:
            print("  - ERROR:", err)
    if res["warnings"]:
        for w in res["warnings"]:
            print("  - ADVERTENCIA:", w)
