"""Contrato de rotación; caché física independiente de rutas y perillas."""
from dataclasses import asdict
from datetime import date
from functools import lru_cache
import json
from math import isfinite
from backend.models.crop_parameters import CROP_CATALOG
from backend.services.rotation_service import load_climate, ClimateUnavailable
from .costs import PeriodSimulator
from .graph import RotationGraph
from .search import search, NoViableRotations
from .pareto import normalize, pareto_front
from .routes import PRESETS, effective_weights, select_route


def numeric(value, label, low=0, high=float("inf")):
    if type(value) not in (int, float) or not isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label}: número finito entre {low} y {high} requerido.")
    return value


@lru_cache(maxsize=16)
def evaluate(serialized: str):
    p = json.loads(serialized)
    start = date.fromisoformat(p["start_date"])
    catalog = {key: c for key,c in CROP_CATALOG.items() if key == c.key and c.botanical_family != "None"}
    # Los alias existentes se admiten cuando se solicita un subconjunto explícito.
    if "crop_ids" in p:
        if not p["crop_ids"] or any(k not in CROP_CATALOG or CROP_CATALOG[k].botanical_family == "None" for k in p["crop_ids"]):
            raise ValueError("Catálogo sin cultivos válidos.")
        catalog = {k:CROP_CATALOG[k] for k in p["crop_ids"]}
        if len({c.key for c in catalog.values()}) != len(catalog):
            raise ValueError("Cultivos duplicados mediante alias.")
    period_dates = [date.fromisoformat(item["start"]) for item in p["periods"]] if "periods" in p else None
    if period_dates and (len(period_dates) != p["m"] or period_dates[0] != start or
                         any(b <= a for a,b in zip(period_dates, period_dates[1:]))):
        raise ValueError("Fechas de periodos inválidas: deben ser crecientes, empezar en start_date y coincidir con m.")
    if "periods" in p and not period_dates:
        raise ValueError("periods no puede estar vacío.")
    graph = RotationGraph(catalog, p["m"], {int(k):v for k,v in p.get("fixed", {}).items()}, p.get("windows"), period_dates)
    initial = p["initial_state"]
    state = (numeric(initial["W"], "W"), tuple(numeric(initial[k], k) for k in ("N","P","K")),
             numeric(initial["H"], "H", .000001), numeric(initial["residue"], "rastrojo"),
             tuple(numeric(t, "historial térmico", -100, 100) for t in initial.get("history", [])), numeric(initial["OM"], "OM", 0, 100))
    transition = p["transition_days"]
    if type(transition) is not int or not 0 <= transition <= 365:
        raise ValueError("transition_days debe ser entero entre 0 y 365.")
    scenarios = {}
    for item in p.get("scenarios", []):
        sid = item["id"]
        if not isinstance(sid, str) or sid in scenarios:
            raise ValueError("Identificadores de escenario inválidos o duplicados.")
        climate = {}
        for day, values in item["daily"].items():
            month, day_number = map(int, day.split("-"))
            date(2000, month, day_number)
            if len(values) != 4:
                raise ValueError("Clima diario requiere lluvia, temperatura, humedad y radiación.")
            climate[month,day_number] = tuple(numeric(x, "clima", lo, hi) for x,lo,hi in zip(values,(0,-90,0,0),(float("inf"),65,100,float("inf"))))
        scenarios[sid] = climate
    if not scenarios:
        scenarios["NASA_POWER"] = load_climate(numeric(p["latitude"], "latitud", -90,90), numeric(p["longitude"], "longitud", -180,180))
    prices = {k:numeric(v, "precio USD/t") for k,v in p.get("prices_usd_t", {}).items() if v is not None}
    costs = {k:numeric(v, "costo USD/ha") for k,v in p.get("costs_usd_ha", {}).items() if v is not None}
    drought = p.get("drought_days")
    if drought is not None and (type(drought) is not int or drought < 1):
        raise ValueError("drought_days debe ser un entero positivo.")
    simulator = PeriodSimulator(scenarios, transition, numeric(p["residue_fraction"], "fracción rastrojo",0,1),
        numeric(p["slope_deg"], "pendiente",0,80), numeric(p["irrigation_mm_day"], "riego",0,30),
        prices, costs, numeric(p["irrigation_cost_usd_mm_ha"], "costo riego"), drought)
    result = search(graph, simulator, state, start, list(scenarios),
                    numeric(p.get("survival_threshold",1), "umbral",.000001,1), p.get("aggregation","mean"), p.get("mode","exact"))
    return result if isinstance(result, NoViableRotations) else pareto_front(normalize(result))


def recommend(payload):
    if not isinstance(payload, dict):
        raise ValueError("Se esperaba un objeto JSON.")
    p = dict(payload)
    if p.get("periods"):
        p.setdefault("m", len(p["periods"]))
        p.setdefault("start_date", p["periods"][0]["start"])
    geometry = p.pop("geometry", None)
    if geometry is not None:
        from shapely.geometry import shape
        polygon = shape(geometry)
        if polygon.geom_type not in ("Polygon", "MultiPolygon") or polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            raise ValueError("Geometría inválida.")
        p.setdefault("latitude", polygon.centroid.y)
        p.setdefault("longitude", polygon.centroid.x)
    route, weights = p.pop("route", "B_balance"), p.pop("weights", None)
    if route not in PRESETS:
        raise ValueError("Ruta desconocida.")
    result = evaluate(json.dumps(p, sort_keys=True, allow_nan=False))
    warnings = ["Estimación del motor; parámetros heredados del catálogo sin validación local.",
                "Métricas agregadas únicamente entre escenarios supervivientes."]
    if not p.get("windows"):
        warnings.append("Sin ventanas de siembra: restricción mensual no evaluada.")
    if p.get("drought_days") is None:
        warnings.append("Sin umbral de marchitez prolongada: criterio no evaluado.")
    if isinstance(result, NoViableRotations):
        return {"label":"estimación", "status":result.status, "reasons":result.reasons,
                "pareto":[], "recomendada_por_ruta":{}, "avisos":warnings}
    f_hat = {c.id:c.f_hat for c in result}
    economic = all(c.f[2] is not None for c in result)
    if not economic:
        warnings.append("Faltan precios o costos explícitos: f3 y C2 deshabilitados; pesos restantes renormalizados.")
    routes = {}
    for name, w in PRESETS.items():
        if not economic and name == "C2_mayor_ganancia":
            routes[name] = None
            continue
        selected = select_route(result, f_hat, w)
        routes[name] = {"id":selected.id, "weights":effective_weights(w, f_hat)}
    for name, entry in routes.items():
        if entry:
            entry["coincide_con"] = [n for n,e in routes.items() if n != name and e and e["id"] == entry["id"]]
    w = effective_weights(weights if weights is not None else PRESETS[route], f_hat)
    selected = None if not economic and route == "C2_mayor_ganancia" and weights is None else select_route(result, f_hat, w)
    return {"label":"estimación", "status":"ok", "pareto":[asdict(c) for c in result],
            "recomendada_por_ruta":routes, "recommended":selected.id if selected else None,
            "weights":w, "avisos":warnings, "motivo":"Mínima suma ponderada sobre el frente de Pareto; desempate por id.",
            "survival_label":"frecuencia de supervivencia dentro de los escenarios probados",
            "origins":{"initial_state":"observado: aportado por solicitante", "catalog":"respaldo: catálogo existente",
                       "climate":"aportado por solicitante" if p.get("scenarios") else "observado: NASA POWER, año de referencia existente",
                       "results":"estimado"}}


def rotation_graph_response(payload):
    try:
        return recommend(payload), 200
    except ClimateUnavailable as exc:
        return {"error":str(exc)}, 503
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
        return {"error":f"Datos de rotación inválidos o faltantes: {exc}"}, 422
