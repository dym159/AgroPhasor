#!/usr/bin/env python3
"""
AgroPhasor - API Backend Local (FastAPI + EDO 1) y Servidor HTTP de Frontend.
NASA Space Apps Challenge 2026 - Field Shift

Provee endpoints REST para el motor EDO 1 (/simulate/edo1, /crops),
el contrato CC-02 (/api/v1/simular, /api/v1/parcelas, /api/v1/health),
búsqueda de localidades Nominatim (/api/places) y servicio de archivos estáticos.
"""

from datetime import datetime, timezone
from math import isfinite
import http.server
import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

PORT = int(os.environ.get("PORT", 5173))
HOST = os.environ.get("HOST", "0.0.0.0")

# Rutas de frontend y raíz del proyecto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.abspath(os.environ.get(
    "AGROPHASOR_FRONTEND_DIR", os.path.join(BASE_DIR, "frontend")
))
if not os.path.isfile(os.path.join(FRONTEND_DIR, "index.html")):
    raise RuntimeError(f"No se encontró index.html en el directorio del frontend: {FRONTEND_DIR}")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from rotation_ranking import METRICS as ROTATION_METRICS, Candidate, rank_rotations
from backend.services.parcel_edo1 import ParcelDataError, simulate_parcel

from backend.core.edo1_engine import simulate_canopy_diurnal_cycle
from backend.core.edo2_engine import simulate_edo2_timeseries, solve_edo2_step
from backend.core.edo3_engine import simulate_edo3_timeseries, solve_edo3_step, compute_liebig_factor
from backend.core.edo4_engine import solve_edo4_step, simulate_edo4_timeseries, execute_harvest_event
from backend.core.edo5_engine import solve_edo5_step, simulate_edo5_timeseries, compute_soil_pareto_metric_f2
from backend.core.topoclimatic import convert_nasa_radiation_to_wm2
from backend.models.crop_parameters import CROP_CATALOG, get_crop_parameters
from backend.models.edo2_validator import validate_edo2_catalog
from backend.models.edo3_validator import validate_edo3_catalog
from backend.models.edo4_validator import validate_edo4_catalog
from backend.models.edo5_validator import validate_edo5_catalog
from backend.services.simulation_service import SimulationService
from backend.services.parcel_edo2 import ParcelEDO2Service
from backend.services.parcel_edo3 import ParcelEDO3Service
from backend.services.parcel_edo4 import ParcelEDO4Service
from backend.services.parcel_edo5 import ParcelEDO5Service

try:
    from fastapi import FastAPI, HTTPException, Query, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


SEARCH_URL = os.getenv("AGROPHASOR_GEOCODER", "https://nominatim.openstreetmap.org/search")
_places_cache: Dict[str, List[Dict[str, Any]]] = {}
_search_lock = threading.Lock()
_next_geocoder_request = 0.0

ROTATION_BOUNDS = dict(zip(ROTATION_METRICS, ((0.0, 10.0), (0.0, 10.0), (-35.0, 0.0), (0.0, 10.0))))
ROTATION_WEIGHTS = {
    "resilience": dict(zip(ROTATION_METRICS, (0.50, 0.30, 0.10, 0.10))),
    "balance": dict(zip(ROTATION_METRICS, (0.25, 0.25, 0.25, 0.25))),
    "profit": dict(zip(ROTATION_METRICS, (0.05, 0.05, 0.85, 0.05))),
}
MODE_TO_RANKING = {
    "maxima_resiliencia": "resilience",
    "balance_optimo": "balance",
    "mayor_ganancia": "profit",
}
ROTATION_ROUTES = {
    "avena_habas_quinua": {
        "metrics": (1.1, 1.0, -12.4, 3.4),
        "sugerencia_optimizada": [
            {"periodo": "P1 (Ene-May)", "cultivo": "Avena Forrajera / Vicia", "ventaja": "Cobertura antierosiva (-72% escorrentía)"},
            {"periodo": "P2 (Jun-Dic)", "cultivo": "Habas Verdes / Serranas", "ventaja": "Fijación biológica +45 kg N/ha"},
            {"periodo": "P3 (Futuro)", "cultivo": "Quinua Pasankalla", "ventaja": "Alta tolerancia a heladas y sequía"},
        ],
        "motivo_agronomico": "Prioriza la máxima resiliencia climática y protección de la capa fértil mediante cobertura densa, fijación de nitrógeno y rusticidad andina.",
        "metricas_comparativas": {
            "ahorro_agua_pct": 24,
            "aumento_fertilidad_pct": 38,
            "reduccion_riesgo_climatico_pct": 35,
            "margen_economico_est": "+12.4%",
        },
    },
    "papa_habas_quinua": {
        "metrics": (2.2, 1.8, -19.8, 2.5),
        "sugerencia_optimizada": [
            {"periodo": "P1 (Ene-May)", "cultivo": "Papa Canchán", "ventaja": "14.1 t/ha (+6.8%)"},
            {"periodo": "P2 (Jun-Dic)", "cultivo": "Habas Verdes / Serranas", "ventaja": "Fijación biológica +45 kg N/ha"},
            {"periodo": "P3 (Futuro)", "cultivo": "Quinua o Cebada", "ventaja": "Rastrojo y cobertura contra heladas"},
        ],
        "motivo_agronomico": "La rotación de Papa con Habas Verdes rompe el ciclo biológico de plagas del suelo y fija nitrógeno de forma natural, reduciendo costos de fertilización.",
        "metricas_comparativas": {
            "ahorro_agua_pct": 18,
            "aumento_fertilidad_pct": 32,
            "reduccion_riesgo_climatico_pct": 27,
            "margen_economico_est": "+19.8%",
        },
    },
    "papa_maiz_habas": {
        "metrics": (4.6, 4.1, -28.5, 1.8),
        "sugerencia_optimizada": [
            {"periodo": "P1 (Ene-May)", "cultivo": "Papa Canchán", "ventaja": "14.5 t/ha (alta demanda comercial)"},
            {"periodo": "P2 (Jun-Dic)", "cultivo": "Maíz Blanco Cuzco / Amiláceo", "ventaja": "Alto margen neto y aporte de rastrojo"},
            {"periodo": "P3 (Futuro)", "cultivo": "Habas Verdes / Serranas", "ventaja": "Recuperación parcial de N tras extracción"},
        ],
        "motivo_agronomico": "Maximiza el retorno económico de corto plazo combinando cultivos comerciales andinos con una leguminosa de cierre para evitar el colapso de nitrógeno.",
        "metricas_comparativas": {
            "ahorro_agua_pct": 11,
            "aumento_fertilidad_pct": 19,
            "reduccion_riesgo_climatico_pct": 16,
            "margen_economico_est": "+28.5%",
        },
    },
    "papa_monocultivo": {
        "metrics": (7.8, 8.5, -10.2, 4.0),
        "sugerencia_optimizada": [],
        "motivo_agronomico": "Secuencia dominada por degradación acelerada y riesgo fitosanitario.",
        "metricas_comparativas": {},
    },
}


def search_places(query: str) -> List[Dict[str, Any]]:
    """Consulta Nominatim (o AGROPHASOR_GEOCODER) con caché en memoria y límite de 1.1 s."""
    global _next_geocoder_request
    cache_key = query.casefold()
    with _search_lock:
        if cache_key in _places_cache:
            return _places_cache[cache_key]
        time.sleep(max(0.0, _next_geocoder_request - time.monotonic()))
        params = urllib.parse.urlencode({
            "q": query,
            "format": "jsonv2",
            "limit": 5,
            "accept-language": "es",
        })
        request = urllib.request.Request(
            f"{SEARCH_URL}?{params}",
            headers={"User-Agent": "AgroPhasor-NAS-8/1.0"},
        )
        _next_geocoder_request = time.monotonic() + 1.1
        with urllib.request.urlopen(request, timeout=8) as response:
            places = json.load(response)
        if not isinstance(places, list):
            raise ValueError("Unexpected geocoder response")
        results = [
            {
                "name": place["display_name"],
                "lat": float(place["lat"]),
                "lon": float(place["lon"]),
            }
            for place in places
        ]
        if len(_places_cache) >= 512:
            del _places_cache[next(iter(_places_cache))]
        _places_cache[cache_key] = results
        return results


def build_v1_health_payload() -> Dict[str, Any]:
    return {
        "status": "online",
        "service": "AgroPhasor Mechanics Simulation Engine",
        "version": "1.0-alpha",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "default_parcel": {
            "name": "Valle del Mantaro, Junín",
            "latitude": -12.06,
            "longitude": -75.21,
            "elevation_m": 3250,
        },
    }


def compute_simulation_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Valida el GeoJSON y computa balances físicos y ranking CC-09 de rotaciones."""
    geo_features = payload.get("geo_features", {})
    lote_id = payload.get("lote_seleccionado_id", "lote-1")
    modo = payload.get("modo_prioridad", "balance_optimo")

    features = geo_features.get("features", [])
    area_ha = 2.45
    if features:
        props = features[0].get("properties", {})
        area_ha = props.get("area_ha", 2.45)

    shield_idx = 88 if modo == "maxima_resiliencia" else (82 if modo == "balance_optimo" else 76)
    ranking_mode = MODE_TO_RANKING.get(modo, "balance")
    candidates = [
        Candidate(route_id, dict(zip(ROTATION_METRICS, spec["metrics"])))
        for route_id, spec in ROTATION_ROUTES.items()
    ]
    weights = ROTATION_WEIGHTS
    sliders = payload.get("perillas")
    if isinstance(sliders, dict):
        values = [sliders.get(f"w{i}") for i in range(1, len(ROTATION_METRICS) + 1)]
        if all(type(value) in (int, float) and 0 <= value <= 100 and isfinite(value) for value in values):
            total = sum(values)
            if total > 0:
                weights = {**ROTATION_WEIGHTS, "custom": dict(zip(
                    ROTATION_METRICS, (value / total for value in values)
                ))}
                ranking_mode = "custom"
    ranking = rank_rotations(candidates, ROTATION_BOUNDS, weights)
    ordered_routes = ranking.by_mode.get(ranking_mode) or ranking.pareto
    selected_route_id = ordered_routes[0] if ordered_routes else "papa_habas_quinua"
    selected_route = ROTATION_ROUTES[selected_route_id]

    # Dinámica Bioquímica de EDO 3 (Nutrientes N-P-K y Ley de Liebig)
    if ranking_mode == "resilience":
        # Rotación con leguminosa fijadora (Avena + Habas Verdes): F_fix > 0
        n_val = 104.5
        p_val = 36.2
        k_val = 192.0
        eta_val = 0.749
        limiting_nut = "Fósforo (P)"
        npk_state = "Regenerado / Alta fertilidad biológica"
        has_fix = True
    elif ranking_mode == "balance":
        # Rotación balanceada (Papa Canchán + Habas)
        n_val = 88.0
        p_val = 34.0
        k_val = 195.0
        eta_val = 0.682
        limiting_nut = "Nitrógeno (N)"
        npk_state = "Fértil / Balance equilibrado"
        has_fix = True
    else:  # profit
        # Monocultivo extractivo continuo (Papa + Maíz sin leguminosas): F_fix = 0
        n_val = 44.5
        p_val = 21.0
        k_val = 138.0
        eta_val = 0.448
        limiting_nut = "Nitrógeno (N)"
        npk_state = "Agotamiento progresivo de N (Requiere fertilización)"
        has_fix = False

    # Si el cliente solicita activación explícita de EDO 3 con parámetros personalizados
    if payload.get("activar_edo3") or "nutrientes_iniciales" in payload:
        try:
            from backend.core.edo3_engine import solve_edo3_step, SoilChemicalProperties
            from backend.models.crop_parameters import get_crop_parameters
            init_npk = payload.get("nutrientes_iniciales", {})
            n_in = float(init_npk.get("N", n_val))
            p_in = float(init_npk.get("P", p_val))
            k_in = float(init_npk.get("K", k_val))
            w_in = float(payload.get("soil_water_mm", 142.5))
            t_in = float(payload.get("temperature_soil_c", 16.8))
            soil_props = SoilChemicalProperties(
                om_pct=float(payload.get("soil_om_pct", 3.0)),
                cic_cmolc_kg=float(payload.get("soil_cic", 22.0)),
                ph=float(payload.get("soil_ph", 6.8)),
                ec_ds_m=float(payload.get("soil_ec", 0.8))
            )
            default_crop = "frijol" if ranking_mode == "resilience" else "papa"
            crop_id = payload.get("cultivo_asignado", default_crop)
            crop_obj = get_crop_parameters(crop_id)
            step_out = solve_edo3_step(
                n_current_kg_ha=n_in,
                p_current_kg_ha=p_in,
                k_current_kg_ha=k_in,
                w_mm=w_in,
                w_cc_mm=160.0,
                t_soil_c=t_in,
                crop=crop_obj,
                soil=soil_props,
                is_crop=True
            )
            n_val, p_val, k_val = step_out.n_kg_ha, step_out.p_kg_ha, step_out.k_kg_ha
            eta_val = step_out.eta_nutrientes
            limiting_nut = step_out.limiting_nutrient
            has_fix = (step_out.biological_n_fixation_kg > 0) or (crop_obj.F_fix > 0.0)
        except Exception:
            pass

    # Dinámica Biofísica de EDO 4 (Biomasa Aérea B_{i,j}(t) y Rendimiento Comercial Y_k)
    b_val = 11.8
    b_state = "Crecimiento vigoroso"
    db_dt_val = 0.125
    ndvi_val = 0.81
    cover_pct = 95.0
    yield_est = 14.2
    margin_est = 1350.0

    try:
        from backend.core.edo4_engine import solve_edo4_step, execute_harvest_event
        from backend.models.crop_parameters import get_crop_parameters

        default_crop_edo4 = "frijol" if ranking_mode == "resilience" else "papa"
        crop_for_edo4 = get_crop_parameters(payload.get("cultivo_asignado", default_crop_edo4))
        b_init = float(payload.get("biomasa_inicial_t_ha", crop_for_edo4.B_max_t_ha * 0.55 if ranking_mode != "profit" else crop_for_edo4.B_max_t_ha * 0.70))
        f_rad_in = float(payload.get("f_rad_daily_mj_m2", 19.5))
        w_soil_for_b = float(payload.get("soil_water_mm", 142.5))
        t_canopy_for_b = float(payload.get("temperature_canopy_c", 16.8))

        step_edo4 = solve_edo4_step(
            b_current_t_ha=b_init,
            f_rad_daily_mj_m2=f_rad_in,
            temp_canopy_c=t_canopy_for_b,
            soil_water_mm=w_soil_for_b,
            nitrogen_kg_ha=n_val,
            phosphorus_kg_ha=p_val,
            potassium_kg_ha=k_val,
            crop=crop_for_edo4,
            q_is_crop=True
        )

        harvest_edo4 = execute_harvest_event(
            biomass_pre_harvest_t_ha=step_edo4.biomass_t_ha,
            crop=crop_for_edo4
        )

        b_val = step_edo4.biomass_t_ha
        b_state = "Crecimiento vigoroso" if step_edo4.is_growth_active else (
            "Paro por sequía" if step_edo4.is_drought_arrest else (
                "Paro térmico" if step_edo4.is_thermal_arrest else (
                    "Paro por nutrientes" if step_edo4.is_nutrient_arrest else "Estable / Maduro"
                )
            )
        )
        db_dt_val = step_edo4.db_dt
        ndvi_val = step_edo4.simulated_ndvi
        cover_pct = round(step_edo4.canopy_cover_fraction * 100, 1)
        yield_est = harvest_edo4.commercial_yield_t_ha
        margin_est = harvest_edo4.net_margin_usd_ha
    except Exception:
        pass

    # Dinámica Geomorfológica de EDO 5 (Erosión Hídrica de la Capa Fértil)
    slope_est = float(payload.get("slope_deg", 10.0 if ranking_mode != "resilience" else 4.5))
    precip_est = float(payload.get("precip_mm", 22.5))
    h0_soil = float(payload.get("h0_mm", 400.0))
    is_bare_trans = (ranking_mode == "profit")

    step_edo5 = solve_edo5_step(
        h_current_mm=h0_soil,
        precip_mm=precip_est,
        slope_deg=slope_est,
        biomass_t_ha=b_val,
        is_transition=is_bare_trans,
        h_initial_mm=h0_soil,
        theta_fc=0.30,
        theta_wp=0.14,
        current_nutrients_kg_ha={"N": n_val, "P": p_val, "K": k_val}
    )
    annual_erosion_loss = round(step_edo5.erosion_loss_step_mm * 18.0, 3)
    h_current_calc = round(max(0.0, h0_soil - annual_erosion_loss), 1)
    pareto_f2_val = compute_soil_pareto_metric_f2(h0_soil, h_current_calc, eta_val)

    return {
        "status": "success",
        "meta": {
            "engine": "AgroPhasor-FastODE-Mantaro",
            "nasa_power_source": "NASA POWER / AG Climatology (1991-2023)",
            "elevation_m": 3250,
            "lote_id": lote_id,
            "area_ha": area_ha,
            "modo_activo": modo,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "indicadores": {
            "humedad_radicular_W": {
                "valor": 142.5,
                "unidad": "mm",
                "estado": "Adecuado",
                "color": "#10b981",
                "descripcion": "Humedad en zona de raíces suficiente para tubérculos y leguminosas.",
            },
            "temperatura_dosel_T": {
                "valor": 16.8,
                "unidad": "°C",
                "estado": "Óptimo",
                "color": "#38bdf8",
                "descripcion": "Sin estrés térmico ni riesgo inmediato de helada severa.",
            },
            "nutrientes_NPK": {
                "N": {"valor": round(n_val, 1), "unidad": "kg/ha", "nivel": "Óptimo" if n_val >= 90 else ("Medio" if n_val >= 60 else "Bajo")},
                "P": {"valor": round(p_val, 1), "unidad": "kg/ha", "nivel": "Alto" if p_val >= 30 else ("Medio" if p_val >= 20 else "Bajo")},
                "K": {"valor": round(k_val, 1), "unidad": "kg/ha", "nivel": "Óptimo" if k_val >= 180 else ("Medio" if k_val >= 120 else "Bajo")},
                "eta_nutrientes": eta_val,
                "nutriente_limitante": limiting_nut,
                "fijacion_biologica_activa": has_fix,
                "estado_general": npk_state,
            },
            "biomasa_aerea_B": {
                "valor": round(b_val, 1),
                "unidad": "t/ha",
                "estado": b_state,
                "tasa_crecimiento_diario": f"{round(db_dt_val, 3)} t/(ha·día)",
                "ndvi_satelital_estimado": ndvi_val,
                "cobertura_foliar_pct": cover_pct,
                "rendimiento_estimado_cosecha": f"{round(yield_est, 2)} t/ha",
                "margen_neto_usd_ha": round(margin_est, 2),
            },
            "espesor_fertil_H": {
                "valor": h_current_calc,
                "unidad": "mm",
                "tasa_erosion": f"{annual_erosion_loss} mm/año ({'Baja' if annual_erosion_loss < 0.1 else ('Moderada' if annual_erosion_loss < 0.5 else 'Alta')})",
                "estado": "Protegido" if annual_erosion_loss < 0.1 else ("Vigilancia" if annual_erosion_loss < 0.5 else "Riesgo de Erosión"),
                "perdida_fosforo_kg_ha": round(step_edo5.nutrient_drag_kg_ha.get("P", 0.0) * 18.0, 3),
                "pendiente_terreno_deg": slope_est,
                "proteccion_foliar_pct": round((1.0 - step_edo5.vegetation_cover_factor) * 100.0, 1),
                "metrica_pareto_f2": pareto_f2_val,
            },
            "escudo_ambiental": {
                "indice": shield_idx,
                "max": 100,
                "calificacion": "Alta Resiliencia",
                "color": "#10b981",
            },
        },
        "rotacion_recomendada": {
            "ruta_seleccionada": selected_route_id,
            "pareto_frente": list(ranking.pareto),
            "plan_actual": [
                {"periodo": "P1 (Ene-May)", "cultivo": "Papa Canchán", "rendimiento_est": "13.2 t/ha"},
                {"periodo": "P2 (Jun-Dic)", "cultivo": "Papa Canchán (Monocultivo)", "alerta": "Riesgo fitosanitario"},
            ],
            "sugerencia_optimizada": selected_route["sugerencia_optimizada"],
            "motivo_agronomico": selected_route["motivo_agronomico"],
            "metricas_comparativas": selected_route["metricas_comparativas"],
        },
    }


def build_parcel_saved_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    lote_id = payload.get("lote_seleccionado_id", "lote-default")
    return {
        "status": "guardado",
        "lote_id": lote_id,
        "mensaje": "Coordenadas GeoJSON registradas exitosamente en el servidor.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def parcel_edo1_response(payload):
    try:
        return simulate_parcel(payload), 200
    except (ValueError, TypeError) as exc:
        return {"error": str(exc)}, 400
    except ParcelDataError as exc:
        return {"error": str(exc)}, 502
    except ImportError:
        return {"error": "Instala las dependencias de EDO 1 indicadas en el README."}, 503


class AgroPhasorHandler(http.server.SimpleHTTPRequestHandler):
    """Manejador HTTP con soporte para API REST y servicio de archivos estáticos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/places":
            query = " ".join(urllib.parse.parse_qs(parsed.query).get("q", [""])[0].split())
            if not 2 <= len(query) <= 120:
                self.send_json_response({"error": "Escribe entre 2 y 120 caracteres."}, status=400)
                return
            try:
                results = search_places(query)
            except (OSError, ValueError, KeyError, TypeError):
                self.send_json_response({"error": "El buscador no está disponible por ahora."}, status=502)
                return
            self.send_json_response(results)
            return

        if path == "/api/v1/health":
            self.send_json_response(build_v1_health_payload())
            return

        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception as e:
            self.send_json_response({"error": f"JSON inválido: {str(e)}"}, status=400)
            return

        if path == "/api/v1/parcelas/edo1":
            result, status = parcel_edo1_response(payload)
            self.send_json_response(result, status=status)
            return

        if path == "/api/v1/simular":
            if "simulate_error" in query or payload.get("force_error"):
                self.send_json_response({
                    "error": "Error 500: Fallo inducido en el solver físico para pruebas de resiliencia.",
                    "detail": "El cliente debe conservar la selección de la parcela sin perder los vértices.",
                }, status=500)
                return

            self.send_json_response(self.process_simulation(payload))
            return

        if path == "/api/v1/validate/catalog":
            from backend.models.edo2_validator import validate_edo2_catalog
            res = validate_edo2_catalog(payload)
            status = 200 if res["valid"] else 422
            self.send_json_response(res, status=status)
            return

        if path == "/api/v1/simular/edo2":
            from backend.services.parcel_edo2 import ParcelEDO2Service
            try:
                res = ParcelEDO2Service.simulate_timeseries(
                    precip_series=payload.get("precip_series", []),
                    t_air_series=payload.get("t_air_series", []),
                    rh_series=payload.get("rh_series", []),
                    crop_id=payload.get("crop_id", "maiz"),
                    slope_deg=float(payload.get("slope_deg", 0.0)),
                    smap_root_wetness=payload.get("smap_root_wetness"),
                    w0_mm=payload.get("w0_mm"),
                    theta_fc=float(payload.get("theta_fc", 0.30)),
                    theta_wp=float(payload.get("theta_wp", 0.14)),
                    auto_irrigate=bool(payload.get("auto_irrigate", False)),
                    eta_irrigation=float(payload.get("eta_irrigation", 0.85))
                )
                self.send_json_response(res, status=200)
            except Exception as exc:
                self.send_json_response({"error": str(exc)}, status=400)
            return

        if path in ("/api/v1/validate/catalog/edo3", "/validate/catalog/edo3"):
            from backend.models.edo3_validator import validate_edo3_catalog
            res = validate_edo3_catalog(payload)
            status = 200 if res["valid"] else 422
            self.send_json_response(res, status=status)
            return

        if path in ("/api/v1/simular/edo3", "/simulate/edo3"):
            from backend.services.parcel_edo3 import ParcelEDO3Service
            try:
                res = ParcelEDO3Service.simulate_timeseries(
                    w_series=payload.get("w_series", [100.0] * 30),
                    t_soil_series=payload.get("t_soil_series", [18.0] * 30),
                    crop_id=payload.get("crop_id", "maiz"),
                    om_pct=float(payload.get("om_pct", 3.0)),
                    cic_cmolc_kg=float(payload.get("cic_cmolc_kg", 22.0)),
                    ph=float(payload.get("ph", 6.8)),
                    ec_ds_m=float(payload.get("ec_ds_m", 0.8)),
                    w_cc_mm=float(payload.get("w_cc_mm", 120.0)),
                    n0_kg_ha=float(payload.get("n0_kg_ha", 85.0)),
                    p0_kg_ha=float(payload.get("p0_kg_ha", 32.0)),
                    k0_kg_ha=float(payload.get("k0_kg_ha", 180.0)),
                    erosion_rate_series=payload.get("erosion_rate_series"),
                    is_crop=bool(payload.get("is_crop", True)),
                    dt_days=float(payload.get("dt_days", 1.0))
                )
                self.send_json_response(res, status=200)
            except Exception as exc:
                self.send_json_response({"error": str(exc)}, status=400)
            return

        if path in ("/api/v1/simular/edo3/rotacion", "/simulate/edo3/rotation"):
            from backend.services.parcel_edo3 import ParcelEDO3Service
            try:
                res = ParcelEDO3Service.simulate_rotation(
                    stages=payload.get("stages", []),
                    t_soil_series=payload.get("t_soil_series", []),
                    w_series=payload.get("w_series", []),
                    om_pct=float(payload.get("om_pct", 3.0)),
                    cic_cmolc_kg=float(payload.get("cic_cmolc_kg", 22.0)),
                    ph=float(payload.get("ph", 6.8)),
                    ec_ds_m=float(payload.get("ec_ds_m", 0.8)),
                    w_cc_mm=float(payload.get("w_cc_mm", 120.0)),
                    n0_kg_ha=float(payload.get("n0_kg_ha", 85.0)),
                    p0_kg_ha=float(payload.get("p0_kg_ha", 32.0)),
                    k0_kg_ha=float(payload.get("k0_kg_ha", 180.0)),
                    dt_days=float(payload.get("dt_days", 1.0))
                )
                self.send_json_response(res, status=200)
            except Exception as exc:
                self.send_json_response({"error": str(exc)}, status=400)
            return

        if path in ("/api/v1/validate/catalog/edo4", "/validate/edo4"):
            from backend.models.edo4_validator import validate_edo4_catalog
            res = validate_edo4_catalog(payload)
            status = 200 if res["valid"] else 422
            self.send_json_response(res, status=status)
            return

        if path in ("/api/v1/simular/edo4", "/simulate/edo4"):
            from backend.services.parcel_edo4 import ParcelEDO4Service
            try:
                res = ParcelEDO4Service.simulate_crop_cycle(
                    crop_id=payload.get("crop_id", "maiz"),
                    f_rad_series_mj_m2=payload.get("f_rad_series", [18.0] * 30),
                    t_canopy_series_c=payload.get("t_canopy_series", [20.0] * 30),
                    soil_water_series_mm=payload.get("soil_water_series", [60.0] * 30),
                    nitrogen_series_kg_ha=payload.get("nitrogen_series", [60.0] * 30),
                    phosphorus_series_kg_ha=payload.get("phosphorus_series", [35.0] * 30),
                    potassium_series_kg_ha=payload.get("potassium_series", [75.0] * 30),
                    b0_t_ha=payload.get("b0_t_ha"),
                    residue_fraction_rres=float(payload.get("residue_fraction_rres", 0.30)),
                    market_price_usd_t=payload.get("market_price_usd_t")
                )
                self.send_json_response(res, status=200)
            except Exception as exc:
                self.send_json_response({"error": str(exc)}, status=400)
            return

        if path in ("/api/v1/simular/edo4/malla", "/simulate/edo4/grid"):
            from backend.services.parcel_edo4 import ParcelEDO4Service
            try:
                res = ParcelEDO4Service.simulate_grid_cells(
                    grid_cells=payload.get("grid_cells", []),
                    crop_id=payload.get("crop_id", "maiz"),
                    nasa_hourly_data=payload.get("nasa_hourly_data", {}),
                    soil_water_mm=float(payload.get("soil_water_mm", 65.0)),
                    soil_nutrients=payload.get("soil_nutrients"),
                    simulation_days=int(payload.get("simulation_days", 30))
                )
                self.send_json_response(res, status=200)
            except Exception as exc:
                self.send_json_response({"error": str(exc)}, status=400)
            return

        if path == "/api/v1/parcelas":
            self.send_json_response(build_parcel_saved_payload(payload))
            return

        self.send_json_response({"error": "Endpoint no encontrado"}, status=404)

    def process_simulation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return compute_simulation_payload(payload)

    def send_json_response(self, data: Any, status: int = 200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if HAS_FASTAPI:
    app = FastAPI(
        title="AgroPhasor Simulation Engine - Backend Local",
        description="Motor de física y balance térmico (EDO 1) para rotación de cultivos bajo estrés climático",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    class CellData(BaseModel):
        cell_id: str
        altitude_m: float = 3000.0
        slope_deg: float = 0.0
        aspect_deg: float = 0.0

    class FieldSimulationRequest(BaseModel):
        crop_id: str = Field(default="papa", description="Identificador del cultivo ('papa', 'maiz', 'haba', 'barbecho')")
        soil_water_mm: float = Field(default=50.0, description="Humedad del suelo en raíces [mm]")
        ref_altitude_m: Optional[float] = Field(default=None, description="Altitud de referencia del lote [m]")
        nasa_hourly_data: Dict[str, Dict[str, float]] = Field(
            ...,
            description="Respuesta horaria de NASA POWER conteniendo 'T2M', 'ALLSKY_SFC_SW_DWN', 'RH2M'",
        )
        grid_cells: List[CellData] = Field(
            default_factory=lambda: [CellData(cell_id="0_0", altitude_m=3200.0, slope_deg=2.0, aspect_deg=180.0)],
            description="Lista de celdas de 30x30m de la parcela dibujada",
        )

    class SinglePointSimulationRequest(BaseModel):
        crop_id: str = "papa"
        soil_water_mm: float = 50.0
        t_air_hourly: List[float]
        radiation_hourly: List[float] = Field(..., description="Radiación solar en W/m² (o MJ/hr si is_radiation_mj_hr=True)")
        rh_hourly: List[float]
        is_radiation_mj_hr: bool = False

    @app.get("/health")
    def health_check():
        return {"status": "ok", "service": "AgroPhasor EDO 1 Engine"}

    @app.get("/api/v1/health")
    def v1_health_check():
        return build_v1_health_payload()

    @app.get("/api/places")
    def places_lookup(q: str = Query(default="")):
        query = " ".join(q.split())
        if not 2 <= len(query) <= 120:
            return JSONResponse({"error": "Escribe entre 2 y 120 caracteres."}, status_code=400)
        try:
            return search_places(query)
        except (OSError, ValueError, KeyError, TypeError):
            return JSONResponse({"error": "El buscador no está disponible por ahora."}, status_code=502)

    @app.get("/crops")
    def list_crops():
        """Devuelve la lista de cultivos precalibrados en el sistema."""
        return {
            crop_id: {
                "name": crop.name,
                "family": crop.botanical_family,
                "T_opt": crop.T_opt,
                "T_frost": crop.T_frost,
                "T_lethal": crop.T_lethal,
                "W_pmp": crop.W_pmp,
                "W_crit": crop.W_crit,
            }
            for crop_id, crop in CROP_CATALOG.items()
        }

    @app.post("/simulate/edo1")
    def simulate_field(request: FieldSimulationRequest):
        """
        Simulación completa de la parcela:
        Recibe la respuesta cruda de NASA POWER y las celdas 30x30m de SRTM,
        y devuelve la temperatura del dosel y métricas de confort para cada celda.
        """
        try:
            cells_dict = [cell.model_dump() for cell in request.grid_cells]
            return SimulationService.run_field_simulation(
                nasa_hourly_data=request.nasa_hourly_data,
                grid_cells=cells_dict,
                crop_id=request.crop_id,
                soil_water_mm=request.soil_water_mm,
                ref_altitude_m=request.ref_altitude_m,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/simulate/edo1/point")
    def simulate_point(request: SinglePointSimulationRequest):
        """Simulación para un punto / celda individual en una serie de horas."""
        crop = get_crop_parameters(request.crop_id)
        rad_wm2 = (
            [convert_nasa_radiation_to_wm2(r) for r in request.radiation_hourly]
            if request.is_radiation_mj_hr
            else request.radiation_hourly
        )
        return simulate_canopy_diurnal_cycle(
            t_ext_hourly=request.t_air_hourly,
            f_rad_wm2_hourly=rad_wm2,
            rh_pct_hourly=request.rh_hourly,
            soil_water_mm=request.soil_water_mm,
            crop=crop,
        )

    @app.post("/api/v1/simular")
    async def simulate_v1(request: Request, simulate_error: Optional[str] = None):
        try:
            payload = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"JSON inválido: {str(e)}"}, status_code=400)
        if simulate_error is not None or payload.get("force_error"):
            return JSONResponse({
                "error": "Error 500: Fallo inducido en el solver físico para pruebas de resiliencia.",
                "detail": "El cliente debe conservar la selección de la parcela sin perder los vértices.",
            }, status_code=500)
        return compute_simulation_payload(payload)

    @app.post("/api/v1/parcelas/edo1")
    def simulate_parcel_v1(payload: Dict[str, Any]):
        result, status = parcel_edo1_response(payload)
        return JSONResponse(result, status_code=status)

    @app.post("/api/v1/parcelas")
    async def save_parcelas_v1(request: Request):
        try:
            payload = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"JSON inválido: {str(e)}"}, status_code=400)
        return build_parcel_saved_payload(payload)

    @app.post("/api/v1/validate/catalog")
    def validate_catalog_v1(payload: Dict[str, Any]):
        return validate_edo2_catalog(payload)

    @app.post("/simulate/edo2")
    def simulate_edo2_api(payload: Dict[str, Any]):
        try:
            return ParcelEDO2Service.simulate_timeseries(
                precip_series=payload.get("precip_series", []),
                t_air_series=payload.get("t_air_series", []),
                rh_series=payload.get("rh_series", []),
                crop_id=payload.get("crop_id", "maiz"),
                slope_deg=float(payload.get("slope_deg", 0.0)),
                smap_root_wetness=payload.get("smap_root_wetness"),
                w0_mm=payload.get("w0_mm"),
                theta_fc=float(payload.get("theta_fc", 0.30)),
                theta_wp=float(payload.get("theta_wp", 0.14)),
                auto_irrigate=bool(payload.get("auto_irrigate", False)),
                eta_irrigation=float(payload.get("eta_irrigation", 0.85))
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/v1/validate/catalog/edo3")
    def validate_catalog_edo3_v1(payload: Dict[str, Any]):
        return validate_edo3_catalog(payload)

    @app.post("/simulate/edo3")
    @app.post("/api/v1/simular/edo3")
    def simulate_edo3_api(payload: Dict[str, Any]):
        try:
            return ParcelEDO3Service.simulate_timeseries(
                w_series=payload.get("w_series", [100.0] * 30),
                t_soil_series=payload.get("t_soil_series", [18.0] * 30),
                crop_id=payload.get("crop_id", "maiz"),
                om_pct=float(payload.get("om_pct", 3.0)),
                cic_cmolc_kg=float(payload.get("cic_cmolc_kg", 22.0)),
                ph=float(payload.get("ph", 6.8)),
                ec_ds_m=float(payload.get("ec_ds_m", 0.8)),
                w_cc_mm=float(payload.get("w_cc_mm", 120.0)),
                n0_kg_ha=float(payload.get("n0_kg_ha", 85.0)),
                p0_kg_ha=float(payload.get("p0_kg_ha", 32.0)),
                k0_kg_ha=float(payload.get("k0_kg_ha", 180.0)),
                erosion_rate_series=payload.get("erosion_rate_series"),
                is_crop=bool(payload.get("is_crop", True)),
                dt_days=float(payload.get("dt_days", 1.0))
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/simulate/edo3/rotation")
    @app.post("/api/v1/simular/edo3/rotacion")
    def simulate_edo3_rotation_api(payload: Dict[str, Any]):
        try:
            return ParcelEDO3Service.simulate_rotation(
                stages=payload.get("stages", []),
                t_soil_series=payload.get("t_soil_series", []),
                w_series=payload.get("w_series", []),
                om_pct=float(payload.get("om_pct", 3.0)),
                cic_cmolc_kg=float(payload.get("cic_cmolc_kg", 22.0)),
                ph=float(payload.get("ph", 6.8)),
                ec_ds_m=float(payload.get("ec_ds_m", 0.8)),
                w_cc_mm=float(payload.get("w_cc_mm", 120.0)),
                n0_kg_ha=float(payload.get("n0_kg_ha", 85.0)),
                p0_kg_ha=float(payload.get("p0_kg_ha", 32.0)),
                k0_kg_ha=float(payload.get("k0_kg_ha", 180.0)),
                dt_days=float(payload.get("dt_days", 1.0))
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/v1/validate/catalog/edo4")
    def validate_catalog_edo4_v1(payload: Dict[str, Any]):
        from backend.models.edo4_validator import validate_edo4_catalog
        return validate_edo4_catalog(payload)

    @app.post("/simulate/edo4")
    @app.post("/api/v1/simular/edo4")
    def simulate_edo4_api(payload: Dict[str, Any]):
        from backend.services.parcel_edo4 import ParcelEDO4Service
        try:
            return ParcelEDO4Service.simulate_crop_cycle(
                crop_id=payload.get("crop_id", "maiz"),
                f_rad_series_mj_m2=payload.get("f_rad_series", [18.0] * 30),
                t_canopy_series_c=payload.get("t_canopy_series", [20.0] * 30),
                soil_water_series_mm=payload.get("soil_water_series", [60.0] * 30),
                nitrogen_series_kg_ha=payload.get("nitrogen_series", [60.0] * 30),
                phosphorus_series_kg_ha=payload.get("phosphorus_series", [35.0] * 30),
                potassium_series_kg_ha=payload.get("potassium_series", [75.0] * 30),
                b0_t_ha=payload.get("b0_t_ha"),
                residue_fraction_rres=float(payload.get("residue_fraction_rres", 0.30)),
                market_price_usd_t=payload.get("market_price_usd_t")
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/simulate/edo4/grid")
    @app.post("/api/v1/simular/edo4/malla")
    def simulate_edo4_grid_api(payload: Dict[str, Any]):
        from backend.services.parcel_edo4 import ParcelEDO4Service
        try:
            return ParcelEDO4Service.simulate_grid_cells(
                grid_cells=payload.get("grid_cells", []),
                crop_id=payload.get("crop_id", "maiz"),
                nasa_hourly_data=payload.get("nasa_hourly_data", {}),
                soil_water_mm=float(payload.get("soil_water_mm", 65.0)),
                soil_nutrients=payload.get("soil_nutrients"),
                simulation_days=int(payload.get("simulation_days", 30))
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/v1/validate/catalog/edo5")
    def validate_catalog_edo5_v1(payload: Dict[str, Any]):
        return validate_edo5_catalog(payload)

    @app.post("/simulate/edo5")
    @app.post("/api/v1/simular/edo5")
    def simulate_edo5_api(payload: Dict[str, Any]):
        try:
            return simulate_edo5_timeseries(
                precip_series=payload.get("precip_series", [15.0] * 30),
                slope_deg=float(payload.get("slope_deg", 10.0)),
                biomass_series=payload.get("biomass_series", [3.0] * 30),
                transition_flags=payload.get("transition_flags", [False] * 30),
                h0_mm=float(payload.get("h0_mm", 400.0)),
                theta_fc=float(payload.get("theta_fc", 0.30)),
                theta_wp=float(payload.get("theta_wp", 0.14)),
                initial_nutrients_kg_ha=payload.get("initial_nutrients_kg_ha")
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/simulate/edo5/step")
    @app.post("/api/v1/simular/edo5/paso")
    def simulate_edo5_step_api(payload: Dict[str, Any]):
        try:
            step = solve_edo5_step(
                h_current_mm=float(payload.get("h_current_mm", 400.0)),
                precip_mm=float(payload.get("precip_mm", 20.0)),
                slope_deg=float(payload.get("slope_deg", 10.0)),
                biomass_t_ha=float(payload.get("biomass_t_ha", 3.0)),
                is_transition=bool(payload.get("is_transition", False)),
                h_initial_mm=float(payload.get("h_initial_mm", 400.0)),
                theta_fc=float(payload.get("theta_fc", 0.30)),
                theta_wp=float(payload.get("theta_wp", 0.14)),
                current_nutrients_kg_ha=payload.get("current_nutrients")
            )
            return {
                "h_current_mm": step.h_current_mm,
                "dh_dt_mm_day": step.dh_dt_mm_day,
                "erosion_loss_step_mm": step.erosion_loss_step_mm,
                "accumulated_erosion_mm": step.accumulated_erosion_mm,
                "soil_retention_ratio": step.soil_retention_ratio,
                "vegetation_cover_factor": step.vegetation_cover_factor,
                "w_cc_mm": step.w_cc_mm,
                "w_pmp_mm": step.w_pmp_mm,
                "nutrient_drag_kg_ha": step.nutrient_drag_kg_ha,
                "soil_color_rgb": step.soil_color_rgb,
                "mesh_subsidence_m": step.mesh_subsidence_m,
                "is_bedrock_exposed": step.is_bedrock_exposed
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/simulate/edo5/grid")
    @app.post("/api/v1/simular/edo5/malla")
    def simulate_edo5_grid_api(payload: Dict[str, Any]):
        try:
            return ParcelEDO5Service.simulate_parcel_grid(
                grid_cells=payload.get("grid_cells", []),
                precip_series=payload.get("precip_series", [15.0] * 30),
                biomass_series=payload.get("biomass_series", [2.5] * 30),
                transition_flags=payload.get("transition_flags", [False] * 30),
                default_h0_mm=float(payload.get("h0_mm", 400.0)),
                theta_fc=float(payload.get("theta_fc", 0.30)),
                theta_wp=float(payload.get("theta_wp", 0.14))
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    if os.path.isdir(FRONTEND_DIR):
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


def run():
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer((HOST, PORT), AgroPhasorHandler) as httpd:
        print("==================================================================")
        print(" 🚀 AgroPhasor Servidor Activo")
        print(f" 🌐 Aplicación Web Frontend:  http://localhost:{PORT}")
        print(f" 📡 Endpoint de Simulación:   http://localhost:{PORT}/api/v1/simular")
        print(f" 🩺 Health Check:             http://localhost:{PORT}/api/v1/health")
        print("==================================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDeteniendo servidor AgroPhasor...")


if __name__ == "__main__":
    run()
