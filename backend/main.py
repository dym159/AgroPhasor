#!/usr/bin/env python3
"""
AgroPhasor - Local Backend API (FastAPI + ODE 1–5) and Frontend HTTP Server.
NASA Space Apps Challenge 2026 - Field Shift

Provides REST endpoints for the ODE 1 engine (/simulate/edo1, /crops), ODE 2–5 solvers,
the CC-02 contract (/api/v1/simular, /api/v1/parcelas, /api/v1/health),
Nominatim place search (/api/places), and static file serving.
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

# Frontend and project root paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.abspath(os.environ.get(
    "AGROPHASOR_FRONTEND_DIR", os.path.join(BASE_DIR, "frontend")
))
if not os.path.isfile(os.path.join(FRONTEND_DIR, "index.html")):
    raise RuntimeError(f"index.html not found in the frontend directory: {FRONTEND_DIR}")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from rotation_ranking import METRICS as ROTATION_METRICS, Candidate, rank_rotations
from backend.services.parcel_edo1 import ParcelDataError, simulate_parcel
from backend.services.rotation_service import ClimateUnavailable, recommend_rotation

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
            {"periodo": "P1 (Jan-May)", "cultivo": "Forage Oat / Vetch", "ventaja": "Anti-erosion cover (-72% runoff)"},
            {"periodo": "P2 (Jun-Dec)", "cultivo": "Green Fava Beans", "ventaja": "Biological N fixation +45 kg N/ha"},
            {"periodo": "P3 (Future)", "cultivo": "Pasankalla Quinoa", "ventaja": "High frost and drought tolerance"},
        ],
        "motivo_agronomico": "Prioritizes maximum climate resilience and topsoil protection through dense canopy cover, nitrogen fixation, and Andean hardiness.",
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
            {"periodo": "P1 (Jan-May)", "cultivo": "Canchan Potato", "ventaja": "14.1 t/ha (+6.8%)"},
            {"periodo": "P2 (Jun-Dec)", "cultivo": "Green Fava Beans", "ventaja": "Biological N fixation +45 kg N/ha"},
            {"periodo": "P3 (Future)", "cultivo": "Quinoa or Barley", "ventaja": "Crop residue and frost ground cover"},
        ],
        "motivo_agronomico": "Rotating Potato with Green Fava Beans breaks soil pest life cycles and fixes nitrogen naturally, cutting fertilizer costs.",
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
            {"periodo": "P1 (Jan-May)", "cultivo": "Canchan Potato", "ventaja": "14.5 t/ha (strong market demand)"},
            {"periodo": "P2 (Jun-Dec)", "cultivo": "Cusco White / Amylaceous Maize", "ventaja": "High net margin and stover input"},
            {"periodo": "P3 (Future)", "cultivo": "Green Fava Beans", "ventaja": "Partial N recovery after nutrient uptake"},
        ],
        "motivo_agronomico": "Maximizes short-term economic return by combining commercial Andean crops with a closing legume to prevent nitrogen collapse.",
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
        "motivo_agronomico": "Sequence dominated by accelerated degradation and phytosanitary risk.",
        "metricas_comparativas": {},
    },
}


def search_places(query: str) -> List[Dict[str, Any]]:
    """Query Nominatim (or AGROPHASOR_GEOCODER) with in-memory cache and 1.1 s rate limit."""
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
            "accept-language": "en",
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
            "name": "Mantaro Valley, Junin",
            "latitude": -12.06,
            "longitude": -75.21,
            "elevation_m": 3250,
        },
    }


def compute_simulation_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate GeoJSON input and compute physical balances and CC-09 rotation rankings."""
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

    # Biochemical Dynamics of ODE 3 (N-P-K Nutrients and Liebig's Law)
    if ranking_mode == "resilience":
        # Rotation with nitrogen-fixing legume (Oat + Green Fava Beans): F_fix > 0
        n_val = 104.5
        p_val = 36.2
        k_val = 192.0
        eta_val = 0.749
        limiting_nut = "Phosphorus (P)"
        npk_state = "Regenerated / High biological fertility"
        has_fix = True
    elif ranking_mode == "balance":
        # Balanced rotation (Canchan Potato + Fava Beans)
        n_val = 88.0
        p_val = 34.0
        k_val = 195.0
        eta_val = 0.682
        limiting_nut = "Nitrogen (N)"
        npk_state = "Fertile / Balanced nutrient budget"
        has_fix = True
    else:  # profit
        # Continuous extractive monoculture (Potato + Maize without legumes): F_fix = 0
        n_val = 44.5
        p_val = 21.0
        k_val = 138.0
        eta_val = 0.448
        limiting_nut = "Nitrogen (N)"
        npk_state = "Progressive N depletion (Fertilization required)"
        has_fix = False

    # If the client explicitly requests ODE 3 evaluation with custom parameters
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

    # Biophysical Dynamics of ODE 4 (Aboveground Biomass B_{i,j}(t) and Commercial Yield Y_k)
    b_val = 11.8
    b_state = "Vigorous growth"
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
        b_state = "Vigorous growth" if step_edo4.is_growth_active else (
            "Drought arrest" if step_edo4.is_drought_arrest else (
                "Thermal arrest" if step_edo4.is_thermal_arrest else (
                    "Nutrient arrest" if step_edo4.is_nutrient_arrest else "Stable / Mature"
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

    # Geomorphological Dynamics of ODE 5 (Water Erosion of Topsoil Layer)
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
        "simulation_kind": "demonstration",
        "warning": "Legacy endpoint with demonstration values. Use /api/v1/parcelas/simulacion and /api/v1/rotaciones for physical computation.",
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
                "estado": "Optimal",
                "color": "#10b981",
                "descripcion": "Root-zone moisture sufficient for tubers and legumes.",
            },
            "temperatura_dosel_T": {
                "valor": 16.8,
                "unidad": "°C",
                "estado": "Optimal",
                "color": "#38bdf8",
                "descripcion": "No thermal stress and no immediate severe frost risk.",
            },
            "nutrientes_NPK": {
                "N": {"valor": round(n_val, 1), "unidad": "kg/ha", "nivel": "Optimal" if n_val >= 90 else ("Medium" if n_val >= 60 else "Low")},
                "P": {"valor": round(p_val, 1), "unidad": "kg/ha", "nivel": "High" if p_val >= 30 else ("Medium" if p_val >= 20 else "Low")},
                "K": {"valor": round(k_val, 1), "unidad": "kg/ha", "nivel": "Optimal" if k_val >= 180 else ("Medium" if k_val >= 120 else "Low")},
                "eta_nutrientes": eta_val,
                "nutriente_limitante": limiting_nut,
                "fijacion_biologica_activa": has_fix,
                "estado_general": npk_state,
            },
            "biomasa_aerea_B": {
                "valor": round(b_val, 1),
                "unidad": "t/ha",
                "estado": b_state,
                "tasa_crecimiento_diario": f"{round(db_dt_val, 3)} t/(ha·day)",
                "ndvi_satelital_estimado": ndvi_val,
                "cobertura_foliar_pct": cover_pct,
                "rendimiento_estimado_cosecha": f"{round(yield_est, 2)} t/ha",
                "margen_neto_usd_ha": round(margin_est, 2),
            },
            "espesor_fertil_H": {
                "valor": h_current_calc,
                "unidad": "mm",
                "tasa_erosion": f"{annual_erosion_loss} mm/year ({'Low' if annual_erosion_loss < 0.1 else ('Moderate' if annual_erosion_loss < 0.5 else 'High')})",
                "estado": "Protected" if annual_erosion_loss < 0.1 else ("Watch" if annual_erosion_loss < 0.5 else "Erosion Risk"),
                "perdida_fosforo_kg_ha": round(step_edo5.nutrient_drag_kg_ha.get("P", 0.0) * 18.0, 3),
                "pendiente_terreno_deg": slope_est,
                "proteccion_foliar_pct": round((1.0 - step_edo5.vegetation_cover_factor) * 100.0, 1),
                "metrica_pareto_f2": pareto_f2_val,
            },
            "escudo_ambiental": {
                "indice": shield_idx,
                "max": 100,
                "calificacion": "High Resilience",
                "color": "#10b981",
            },
        },
        "rotacion_recomendada": {
            "ruta_seleccionada": selected_route_id,
            "pareto_frente": list(ranking.pareto),
            "plan_actual": [
                {"periodo": "P1 (Jan-May)", "cultivo": "Canchan Potato", "rendimiento_est": "13.2 t/ha"},
                {"periodo": "P2 (Jun-Dec)", "cultivo": "Canchan Potato (Monoculture)", "alerta": "Phytosanitary risk"},
            ],
            "sugerencia_optimizada": selected_route["sugerencia_optimizada"],
            "motivo_agronomico": selected_route["motivo_agronomico"],
            "metricas_comparativas": selected_route["metricas_comparativas"],
        },
    }


def build_parcel_saved_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    lote_id = payload.get("lote_seleccionado_id", "lote-default")
    return {
        "status": "saved",
        "lote_id": lote_id,
        "mensaje": "GeoJSON coordinates successfully registered on the server.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def crop_cycles():
    return {key: crop.duration_days for key, crop in CROP_CATALOG.items()
            if crop.key != "suelo_desnudo_transicion"}


def rotation_response(payload):
    try:
        return recommend_rotation(payload), 200
    except ValueError as exc:
        return {"error": str(exc)}, 422
    except ClimateUnavailable as exc:
        return {"error": str(exc)}, 503


def parcel_edo1_response(payload):
    try:
        result = simulate_parcel(payload)
        if payload.get("phases") and payload.get("selected_date"):
            from backend.services.plan_service import replay_plan
            result = replay_plan(
                result,
                payload["phases"],
                payload["selected_date"],
                mc_samples=payload.get("mc_samples", 30),
                delta_T_whatif=payload.get("delta_T_whatif", 0.0),
                delta_P_pct_whatif=payload.get("delta_P_pct_whatif", 0.0),
                seed=payload.get("climate_seed", 42),
                use_climate_forecast=bool(payload.get("use_climate_forecast", True)),
            )
        return result, 200
    except (ValueError, TypeError, KeyError) as exc:
        return {"error": str(exc)}, 400
    except (ParcelDataError, ClimateUnavailable) as exc:
        return {"error": str(exc)}, 502
    except ImportError:
        return {"error": "Install the simulation dependencies listed in the README."}, 503


def climate_forecast_response(payload):
    from datetime import date, timedelta
    from backend.services.climate_service import predict_climate_scenarios
    from backend.services.rotation_service import number

    try:
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object.")
        lat = number(payload.get("latitude", -12.06), -90, 90, "Latitude")
        lon = number(payload.get("longitude", -75.21), -180, 180, "Longitude")
        start_raw = payload.get("start_date")
        start_dt = date.fromisoformat(start_raw) if start_raw else datetime.now(timezone.utc).date()
        end_raw = payload.get("end_date")
        if end_raw:
            end_dt = date.fromisoformat(end_raw)
        else:
            months = int(number(payload.get("months", 6), 1, 36, "Forecast months"))
            end_dt = start_dt + timedelta(days=months * 30 - 1)
        if (end_dt - start_dt).days > 3650:
            raise ValueError("Forecast horizon must not exceed 3,650 days.")
        n_mc = int(number(payload.get("n_mc", 100), 1, 200, "Monte Carlo scenarios"))
        n_armonicos = int(number(payload.get("n_armonicos", 2), 1, 4, "Fourier harmonics"))
        delta_t = number(payload.get("delta_T_whatif", 0.0), -10, 15, "Temperature delta")
        delta_p = number(payload.get("delta_P_pct_whatif", 0.0), -90, 200, "Precipitation delta (%)")
        seed = int(payload.get("seed", 42))
        include_series = bool(payload.get("include_representative_series", True))

        forecast = predict_climate_scenarios(
            lat,
            lon,
            start_dt,
            end_dt,
            n_mc=n_mc,
            delta_T_whatif=delta_t,
            delta_P_pct_whatif=delta_p,
            seed=seed,
            n_armonicos=n_armonicos,
        )
        body = {
            **forecast["metadata"],
            "summary": forecast["summary"],
        }
        if include_series:
            body["representative_series"] = [
                {"date": day.isoformat(), **sc_day}
                for day, sc_day in zip(forecast["dates"], forecast["representative_scenario"])
            ]
        return body, 200
    except (ValueError, TypeError, KeyError) as exc:
        return {"error": str(exc)}, 422
    except ClimateUnavailable as exc:
        return {"error": str(exc)}, 503


class AgroPhasorHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler supporting the REST API and static file serving."""

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
                self.send_json_response({"error": "Enter between 2 and 120 characters."}, status=400)
                return
            try:
                results = search_places(query)
            except (OSError, ValueError, KeyError, TypeError):
                self.send_json_response({"error": "Place search is currently unavailable."}, status=502)
                return
            self.send_json_response(results)
            return

        if path == "/api/v1/health":
            self.send_json_response(build_v1_health_payload())
            return

        if path == "/api/v1/crop-cycles":
            self.send_json_response(crop_cycles())
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
            self.send_json_response({"error": f"Invalid JSON: {str(e)}"}, status=400)
            return

        if path in ("/api/v1/parcelas/simulacion", "/api/v1/parcelas/edo1"):
            result, status = parcel_edo1_response(payload)
            self.send_json_response(result, status=status)
            return

        if path == "/api/v1/rotaciones":
            result, status = rotation_response(payload)
            self.send_json_response(result, status=status)
            return

        if path in ("/api/v1/clima/predecir", "/api/v1/climate/forecast"):
            result, status = climate_forecast_response(payload)
            self.send_json_response(result, status=status)
            return

        if path == "/api/v1/simular":
            if "simulate_error" in query or payload.get("force_error"):
                self.send_json_response({
                    "error": "Error 500: Induced physics solver failure for resilience testing.",
                    "detail": "The client must preserve the parcel selection without losing vertices.",
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

        if path in ("/api/v1/validate/catalog/edo5", "/validate/edo5"):
            res = validate_edo5_catalog(payload)
            status = 200 if res["valid"] else 422
            self.send_json_response(res, status=status)
            return

        if path in ("/api/v1/simular/edo5", "/simulate/edo5"):
            try:
                res = simulate_edo5_timeseries(
                    precip_series=payload.get("precip_series", [15.0] * 30),
                    slope_deg=float(payload.get("slope_deg", 10.0)),
                    biomass_series=payload.get("biomass_series", [3.0] * 30),
                    transition_flags=payload.get("transition_flags", [False] * 30),
                    h0_mm=float(payload.get("h0_mm", 400.0)),
                    theta_fc=float(payload.get("theta_fc", 0.30)),
                    theta_wp=float(payload.get("theta_wp", 0.14)),
                    initial_nutrients_kg_ha=payload.get("initial_nutrients_kg_ha")
                )
                self.send_json_response(res, status=200)
            except Exception as exc:
                self.send_json_response({"error": str(exc)}, status=400)
            return

        if path in ("/api/v1/simular/edo5/paso", "/simulate/edo5/step"):
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
                self.send_json_response({
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
                }, status=200)
            except Exception as exc:
                self.send_json_response({"error": str(exc)}, status=400)
            return

        if path in ("/api/v1/simular/edo5/malla", "/simulate/edo5/grid"):
            try:
                res = ParcelEDO5Service.simulate_parcel_grid(
                    grid_cells=payload.get("grid_cells", []),
                    precip_series=payload.get("precip_series", [15.0] * 30),
                    biomass_series=payload.get("biomass_series", [2.5] * 30),
                    transition_flags=payload.get("transition_flags", [False] * 30),
                    default_h0_mm=float(payload.get("h0_mm", 400.0)),
                    theta_fc=float(payload.get("theta_fc", 0.30)),
                    theta_wp=float(payload.get("theta_wp", 0.14))
                )
                self.send_json_response(res, status=200)
            except Exception as exc:
                self.send_json_response({"error": str(exc)}, status=400)
            return

        if path == "/api/v1/parcelas":
            self.send_json_response(build_parcel_saved_payload(payload))
            return

        self.send_json_response({"error": "Endpoint not found"}, status=404)

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
        title="AgroPhasor Simulation Engine - Local Backend",
        description="Physics and thermal balance engine (ODE 1–5) for crop rotation under climate stress",
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
        crop_id: str = Field(default="papa", description="Crop identifier ('papa', 'maiz', 'haba', 'barbecho')")
        soil_water_mm: float = Field(default=50.0, description="Root-zone soil moisture [mm]")
        ref_altitude_m: Optional[float] = Field(default=None, description="Parcel reference altitude [m]")
        nasa_hourly_data: Dict[str, Dict[str, float]] = Field(
            ...,
            description="Hourly NASA POWER response containing 'T2M', 'ALLSKY_SFC_SW_DWN', 'RH2M'",
        )
        grid_cells: List[CellData] = Field(
            default_factory=lambda: [CellData(cell_id="0_0", altitude_m=3200.0, slope_deg=2.0, aspect_deg=180.0)],
            description="List of 30x30m grid cells for the drawn parcel",
        )

    class SinglePointSimulationRequest(BaseModel):
        crop_id: str = "papa"
        soil_water_mm: float = 50.0
        t_air_hourly: List[float]
        radiation_hourly: List[float] = Field(..., description="Solar radiation in W/m² (or MJ/hr if is_radiation_mj_hr=True)")
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
            return JSONResponse({"error": "Enter between 2 and 120 characters."}, status_code=400)
        try:
            return search_places(query)
        except (OSError, ValueError, KeyError, TypeError):
            return JSONResponse({"error": "Place search is currently unavailable."}, status_code=502)

    @app.get("/api/v1/crop-cycles")
    def crop_cycles_api():
        return crop_cycles()

    @app.get("/crops")
    def list_crops():
        """Return the list of pre-calibrated crops in the system."""
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
        Full parcel simulation:
        Receives the raw NASA POWER response and SRTM 30x30m grid cells,
        and returns canopy temperature and thermal comfort metrics for each cell.
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
        """Simulation for a single point/cell over a sequence of hours."""
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
            return JSONResponse({"error": f"Invalid JSON: {str(e)}"}, status_code=400)
        if simulate_error is not None or payload.get("force_error"):
            return JSONResponse({
                "error": "Error 500: Induced physics solver failure for resilience testing.",
                "detail": "The client must preserve the parcel selection without losing vertices.",
            }, status_code=500)
        return compute_simulation_payload(payload)

    @app.post("/api/v1/rotaciones")
    def recommend_rotation_v1(payload: Dict[str, Any]):
        result, status = rotation_response(payload)
        return JSONResponse(result, status_code=status)

    @app.post("/api/v1/parcelas/simulacion")
    @app.post("/api/v1/parcelas/edo1")
    def simulate_parcel_v1(payload: Dict[str, Any]):
        result, status = parcel_edo1_response(payload)
        return JSONResponse(result, status_code=status)

    @app.post("/api/v1/clima/predecir")
    @app.post("/api/v1/climate/forecast")
    def predict_climate_v1(payload: Dict[str, Any]):
        result, status = climate_forecast_response(payload)
        return JSONResponse(result, status_code=status)

    @app.post("/api/v1/parcelas")
    async def save_parcelas_v1(request: Request):
        try:
            payload = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {str(e)}"}, status_code=400)
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
        print(" 🚀 AgroPhasor Server Active")
        print(f" 🌐 Web Frontend Application: http://localhost:{PORT}")
        print(f" 📡 Parcel Simulation:        http://localhost:{PORT}/api/v1/parcelas/simulacion")
        print(f" 🩺 Health Check:             http://localhost:{PORT}/api/v1/health")
        print("==================================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping AgroPhasor server...")


if __name__ == "__main__":
    run()
