"""
Validador agrofísico del catálogo JSON específicamente para EDO 2 (Balance Hidrológico Radicular).
Verifica la presencia, tipos, rangos físicos y consistencia matemática de los parámetros
necesarios para la integración de EDO 2 según AgroPhasor.pdf (Secciones 3.2.2, 3.3 y 2.6.2).
"""

import json
import os
from typing import Dict, Any, List, Optional, Union, Tuple


class EDO2ValidationError(ValueError):
    """Excepción para errores críticos de validación agrofísica en EDO 2."""
    pass


def validate_edo2_catalog(
    source: Union[str, Dict[str, Any]],
    default_theta_fc: float = 0.30,
    default_theta_wp: float = 0.14
) -> Dict[str, Any]:
    """
    Valida que un archivo o diccionario JSON cumpla con todos los requisitos para EDO 2:
    
    1. constantes_globales:
       - E_suelo0_mm_dia > 0 (Evaporación basal de suelo desnudo, mm/día)
       - lambda_B_ha_t > 0 (Factor de extinción lumínica por biomasa, ha/t)
    2. suelo_desnudo_transicion:
       - gamma_max == 0.0 (Sin transpiración activa de cultivo en transición/barbecho)
    3. cultivos:
       Para cada cultivo:
       - Zr_mm > 0 (Profundidad radicular efectiva, mm)
       - p_agotamiento en (0, 1) (Factor de agotamiento hídrico admisible de FAO 56)
       - gamma_max > 0 (Conductancia estomática máxima)
       - B_max_t_ha > 0 (Techo de biomasa para sombreo del suelo)
       - B0_t_ha > 0 (Biomasa inicial / rastrojo)
    
    Calcula además el resumen hidrológico derivado (Wcc, Wpmp, Wcrit, RAW).
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

    errors: List[str] = []
    warnings: List[str] = []
    crops_summary: Dict[str, Any] = {}

    # 1. Validar constantes_globales
    globales = data.get("constantes_globales")
    if not isinstance(globales, dict):
        errors.append("Falta la sección obligatoria 'constantes_globales' en el JSON.")
        e_suelo0 = 4.2
        lambda_b = 0.45
    else:
        # E_suelo0_mm_dia
        if "E_suelo0_mm_dia" not in globales:
            errors.append("Falta 'E_suelo0_mm_dia' en 'constantes_globales' (requerido para evaporación de EDO 2).")
            e_suelo0 = 4.2
        else:
            e_suelo0 = float(globales["E_suelo0_mm_dia"])
            if e_suelo0 <= 0 or e_suelo0 > 25.0:
                errors.append(f"Valor no físico de E_suelo0_mm_dia: {e_suelo0}. Debe estar en (0, 25] mm/día.")

        # lambda_B_ha_t
        if "lambda_B_ha_t" not in globales:
            errors.append("Falta 'lambda_B_ha_t' en 'constantes_globales' (requerido para atenuación de radiación en EDO 2).")
            lambda_b = 0.45
        else:
            lambda_b = float(globales["lambda_B_ha_t"])
            if lambda_b <= 0 or lambda_b > 5.0:
                errors.append(f"Valor no físico de lambda_B_ha_t: {lambda_b}. Debe estar en (0, 5] ha/t.")

    # 2. Validar suelo_desnudo_transicion
    transicion = data.get("suelo_desnudo_transicion")
    if not isinstance(transicion, dict):
        warnings.append("Falta la sección 'suelo_desnudo_transicion'. Se asumirá gamma_max = 0.0.")
    else:
        g_max_trans = float(transicion.get("gamma_max", 0.0))
        if g_max_trans != 0.0:
            errors.append(f"gamma_max en 'suelo_desnudo_transicion' debe ser 0.0 (detectado: {g_max_trans}).")

    # 3. Validar cultivos
    cultivos = data.get("cultivos")
    if not isinstance(cultivos, dict) or len(cultivos) == 0:
        errors.append("Falta la sección 'cultivos' o no contiene ninguna especie.")
    else:
        for crop_id, c in cultivos.items():
            crop_errors = []
            
            # Zr_mm (Profundidad radicular)
            zr = c.get("Zr_mm")
            if zr is None:
                crop_errors.append(f"{crop_id}: falta 'Zr_mm'.")
                zr = 600.0
            else:
                zr = float(zr)
                if zr < 50.0 or zr > 4000.0:
                    crop_errors.append(f"{crop_id}: 'Zr_mm' ({zr}) fuera del rango agronómico razonable [50, 4000] mm.")

            # p_agotamiento (Fracción de agotamiento FAO 56)
            p_agot = c.get("p_agotamiento")
            if p_agot is None:
                crop_errors.append(f"{crop_id}: falta 'p_agotamiento'.")
                p_agot = 0.50
            else:
                p_agot = float(p_agot)
                if not (0.05 <= p_agot <= 0.95):
                    crop_errors.append(f"{crop_id}: 'p_agotamiento' ({p_agot}) debe estar en el rango (0.05, 0.95).")

            # gamma_max
            g_max = c.get("gamma_max")
            if g_max is None:
                crop_errors.append(f"{crop_id}: falta 'gamma_max'.")
                g_max = 0.00015
            else:
                g_max = float(g_max)
                if g_max <= 0.0:
                    crop_errors.append(f"{crop_id}: 'gamma_max' ({g_max}) debe ser estrictamente positivo.")

            # B_max_t_ha y B0_t_ha
            b_max = float(c.get("B_max_t_ha", 15.0))
            b_0 = float(c.get("B0_t_ha", 0.20))
            if b_max <= 0:
                crop_errors.append(f"{crop_id}: 'B_max_t_ha' debe ser > 0.")
            if b_0 <= 0 or b_0 > b_max:
                crop_errors.append(f"{crop_id}: 'B0_t_ha' ({b_0}) debe ser > 0 y <= B_max_t_ha ({b_max}).")

            if crop_errors:
                errors.extend(crop_errors)
            else:
                # Calcular propiedades hidrológicas derivadas con suelo de referencia
                w_cc = round(default_theta_fc * zr, 2)
                w_pmp = round(default_theta_wp * zr, 2)
                w_crit = round(w_cc - p_agot * (w_cc - w_pmp), 2)
                raw = round(w_cc - w_crit, 2)
                taw = round(w_cc - w_pmp, 2)
                
                # Conversión de conductancia diaria: kg/(m2*s*kPa) -> mm/(kPa*dia)
                gamma_daily_mm = round(g_max * 86400.0, 3)

                crops_summary[crop_id] = {
                    "nombre": c.get("nombre", crop_id),
                    "familia_botanica": c.get("familia_botanica", "Desconocida"),
                    "Zr_mm": zr,
                    "p_agotamiento": p_agot,
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
