"""
Validador agrofísico del catálogo JSON específicamente para EDO 5: Erosión Hídrica de la Capa Fértil.
Verifica la presencia, tipos, unidades, rangos biofísicos y consistencia matemática de los parámetros
necesarios para la integración de H_i,j(t) según AgroPhasor.pdf (Secciones 3.2.5, 3.3, 1.5.1, 1.6.2 y 3.5).
"""

import json
import os
from typing import Dict, Any, List, Optional, Union, Tuple

from backend.models.crop_parameters import normalize_catalog_dict


class EDO5ValidationError(ValueError):
    """Excepción para errores críticos de validación agrofísica en EDO 5."""
    pass


def validate_edo5_catalog(
    source: Union[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Valida que un archivo o diccionario JSON cumpla con todos los requisitos biofísicos para EDO 5:
    
    1. constantes_globales:
       - k_er_cultivo > 0: Coeficiente de erodibilidad en presencia de cultivo vivo (mm / (mm_lluvia * día)).
         Rango típico: [0.0001, 0.001]. Valor de calibración AgroPhasor: 0.0004.
       - k_er_labranza > 0: Coeficiente de erodibilidad durante transición/labranza (suelo removido).
         Rango típico: [0.001, 0.01]. Valor de calibración AgroPhasor: 0.0035.
         Condición física obligatoria: k_er_labranza > k_er_cultivo (mayor desprotección mecánica).
       - lambda_B_ha_t > 0: Coeficiente de extinción / atenuación del impacto de lluvia por biomasa (ha/t).
         Rango típico: [0.2, 0.8]. Valor de calibración AgroPhasor: 0.45.
       - xi_N, xi_P, xi_K > 0: Coeficientes de arrastre mecánico de nutrientes con el suelo erosionado.
         Valores de calibración: xi_N = 0.004, xi_P = 0.008, xi_K = 0.003.
         
    2. cultivos:
       Para cada cultivo en el catálogo:
       - B_max_t_ha > 0: Techo de biomasa para calcular protección foliar máxima exp(-lambda_B * B_max).
       - B0_t_ha >= 0: Biomasa inicial de germinación / trasplante.
       - duracion_dias > 0: Duración del ciclo fenológico para acumulación temporal de erosión.
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
        # Coeficiente erodibilidad cultivo
        k_er_cultivo = globales.get("k_er_cultivo")
        if k_er_cultivo is None:
            errors.append("Falta 'k_er_cultivo' en constantes_globales.")
        elif not isinstance(k_er_cultivo, (int, float)) or k_er_cultivo <= 0.0:
            errors.append(f"'k_er_cultivo' debe ser un número positivo, recibido: {k_er_cultivo}")
        elif not (0.00005 <= k_er_cultivo <= 0.005):
            warnings.append(f"'k_er_cultivo' ({k_er_cultivo}) fuera del rango biofísico estándar [0.00005, 0.005].")
        else:
            extracted_globals["k_er_cultivo"] = float(k_er_cultivo)

        # Coeficiente erodibilidad labranza / transición
        k_er_labranza = globales.get("k_er_labranza")
        if k_er_labranza is None:
            errors.append("Falta 'k_er_labranza' en constantes_globales.")
        elif not isinstance(k_er_labranza, (int, float)) or k_er_labranza <= 0.0:
            errors.append(f"'k_er_labranza' debe ser un número positivo, recibido: {k_er_labranza}")
        elif not (0.0005 <= k_er_labranza <= 0.05):
            warnings.append(f"'k_er_labranza' ({k_er_labranza}) fuera del rango biofísico estándar [0.0005, 0.05].")
        else:
            extracted_globals["k_er_labranza"] = float(k_er_labranza)

        # Consistencia física relativa entre labranza y cultivo
        if "k_er_cultivo" in extracted_globals and "k_er_labranza" in extracted_globals:
            if extracted_globals["k_er_labranza"] <= extracted_globals["k_er_cultivo"]:
                errors.append(
                    f"Inconsistencia física: 'k_er_labranza' ({extracted_globals['k_er_labranza']}) "
                    f"debe ser estrictamente mayor que 'k_er_cultivo' ({extracted_globals['k_er_cultivo']}). "
                    f"El suelo removido sin cobertura vegetal debe ser más vulnerable a la erosión hídrica."
                )

        # Coeficiente de extinción por biomasa lambda_B
        lambda_b = globales.get("lambda_B_ha_t")
        if lambda_b is None:
            errors.append("Falta 'lambda_B_ha_t' en constantes_globales.")
        elif not isinstance(lambda_b, (int, float)) or lambda_b <= 0.0:
            errors.append(f"'lambda_B_ha_t' debe ser un número positivo, recibido: {lambda_b}")
        elif not (0.1 <= lambda_b <= 1.5):
            warnings.append(f"'lambda_B_ha_t' ({lambda_b}) fuera del rango agronómico típico [0.1, 1.5].")
        else:
            extracted_globals["lambda_B_ha_t"] = float(lambda_b)

        # Coeficientes de arrastre de macronutrientes (xi_N, xi_P, xi_K)
        for nut in ["xi_N", "xi_P", "xi_K"]:
            val = globales.get(nut)
            if val is None:
                errors.append(f"Falta '{nut}' (coeficiente de arrastre con suelo erosionado) en constantes_globales.")
            elif not isinstance(val, (int, float)) or val <= 0.0:
                errors.append(f"'{nut}' debe ser un número positivo, recibido: {val}")
            else:
                extracted_globals[nut] = float(val)

    # 2. Validar cultivos
    cultivos = data.get("cultivos")
    if not isinstance(cultivos, dict) or len(cultivos) == 0:
        errors.append("Falta la sección obligatoria 'cultivos' o está vacía en el JSON.")
    else:
        lambda_b_val = extracted_globals.get("lambda_B_ha_t", 0.45)
        for crop_id, crop_data in cultivos.items():
            if not isinstance(crop_data, dict):
                errors.append(f"El cultivo '{crop_id}' debe ser un objeto/diccionario.")
                continue

            crop_errors = []
            
            # Biomasa máxima
            b_max = crop_data.get("B_max_t_ha")
            if b_max is None:
                crop_errors.append(f"Falta 'B_max_t_ha' en el cultivo '{crop_id}'.")
                b_max_f = 10.0
            elif not isinstance(b_max, (int, float)) or b_max <= 0.0:
                crop_errors.append(f"'B_max_t_ha' debe ser positivo en '{crop_id}', recibido: {b_max}")
                b_max_f = 10.0
            else:
                b_max_f = float(b_max)

            # Biomasa inicial
            b0 = crop_data.get("B0_t_ha")
            if b0 is None:
                crop_errors.append(f"Falta 'B0_t_ha' en el cultivo '{crop_id}'.")
                b0_f = 0.2
            elif not isinstance(b0, (int, float)) or b0 < 0.0:
                crop_errors.append(f"'B0_t_ha' debe ser >= 0 en '{crop_id}', recibido: {b0}")
                b0_f = 0.2
            else:
                b0_f = float(b0)

            # Consistencia biológica
            if b0_f >= b_max_f:
                crop_errors.append(f"En '{crop_id}', B0_t_ha ({b0_f}) debe ser menor que B_max_t_ha ({b_max_f}).")

            # Duración del ciclo
            dur = crop_data.get("duracion_dias")
            if dur is None or not isinstance(dur, (int, float)) or dur <= 0:
                crop_errors.append(f"Falta 'duracion_dias' válido en '{crop_id}'.")
                dur_days = 90
            else:
                dur_days = int(dur)

            # Factor de protección foliar de la biomasa: exp(-lambda_B * B)
            # Rango: exp(-lambda_B * B0) (mínima protección inicial) a exp(-lambda_B * B_max) (máxima protección madura)
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
        # Reportar en el diccionario devuelto
        pass

    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "global_parameters_edo5": extracted_globals,
        "crops_validated_count": len(crops_summary),
        "crops_summary": crops_summary
    }
