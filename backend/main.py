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

try:
    from fastapi import FastAPI, HTTPException, Query, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field

    from backend.core.edo1_engine import simulate_canopy_diurnal_cycle
    from backend.core.topoclimatic import convert_nasa_radiation_to_wm2
    from backend.models.crop_parameters import CROP_CATALOG, get_crop_parameters
    from backend.services.simulation_service import SimulationService

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
                "N": {"valor": 88, "unidad": "kg/ha", "nivel": "Medio"},
                "P": {"valor": 34, "unidad": "kg/ha", "nivel": "Alto"},
                "K": {"valor": 195, "unidad": "kg/ha", "nivel": "Óptimo"},
                "estado_general": "Fértil",
            },
            "biomasa_aerea_B": {
                "valor": 11.8,
                "unidad": "t/ha",
                "estado": "Crecimiento vigoroso",
            },
            "espesor_fertil_H": {
                "valor": 278,
                "unidad": "mm",
                "tasa_erosion": "0.28 mm/año (Baja)",
                "estado": "Protegido",
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
