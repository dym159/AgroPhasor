"""Rotation API contract; physics cache independent of route presets and knobs."""
from dataclasses import asdict, replace
from datetime import date
from functools import lru_cache
import json
from math import isfinite
from backend.models.crop_parameters import CROP_CATALOG, normalize_region
from backend.services.rotation_service import load_climate, ClimateUnavailable, INITIAL_SOIL, TRANSITION_DAYS
from .costs import PeriodSimulator
from .graph import RotationGraph
from .search import search, NoViableRotations
from .pareto import normalize, pareto_front
from .regions import department_at, department_names
from .routes import PRESETS, effective_weights, select_route


def numeric(value, label, low=0, high=float("inf")):
    if type(value) not in (int, float) or not isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label}: finite number between {low} and {high} required.")
    return value


@lru_cache(maxsize=16)
def evaluate(serialized: str):
    p = json.loads(serialized)
    start = date.fromisoformat(p["start_date"])
    catalog = {key: c for key,c in CROP_CATALOG.items() if key == c.key.lower() and c.botanical_family != "None"}
    # Existing aliases are allowed when an explicit crop subset is requested.
    if "crop_ids" in p:
        if not p["crop_ids"] or any(k not in CROP_CATALOG or CROP_CATALOG[k].botanical_family == "None" for k in p["crop_ids"]):
            raise ValueError("Catalog has no valid crops.")
        catalog = {k:CROP_CATALOG[k] for k in p["crop_ids"]}
        if len({c.key for c in catalog.values()}) != len(catalog):
            raise ValueError("Duplicate crops provided via aliases.")
    period_dates = [date.fromisoformat(item["start"]) for item in p["periods"]] if "periods" in p else None
    if period_dates and (len(period_dates) != p["m"] or period_dates[0] != start or
                         any(b <= a for a,b in zip(period_dates, period_dates[1:]))):
        raise ValueError("Invalid period dates: they must be strictly increasing, start on start_date, and match m.")
    if "periods" in p and not period_dates:
        raise ValueError("periods cannot be empty.")
    region = normalize_region(p.get("region", ""))
    campaign = p.get("campaign", "").strip()
    fixed = {int(k): v for k, v in p.get("fixed", {}).items()}
    unavailable = {}
    if p.get("profile") == "reference" and region:
        # Reference varieties with documented regional coverage stay within it.
        unavailable = {key: crop for key, crop in catalog.items()
                       if crop.cycle_source and crop.calendars and region not in crop.calendars}
        if blocked := next((unavailable[key] for key in fixed.values() if key in unavailable), None):
            return NoViableRotations([{"sequence": [],
                                      "reason": f"{blocked.name} {blocked.variety} does not have a documented calendar for {p['region']}."}])
        catalog = {key: crop for key, crop in catalog.items() if key not in unavailable}
        if not catalog:
            return NoViableRotations([{"sequence": [],
                                      "reason": f"Selected crops do not have a documented calendar for {p['region']}."}])
    windows, prices, costs = {}, {}, {}
    for key, crop in catalog.items():
        calendar = crop.calendars.get(region)
        if calendar:
            catalog[key] = replace(crop, duration_days=calendar.duration_days)
            if calendar.planting_months:
                windows[key] = calendar.planting_months
        economics = crop.economics.get(region, {}).get(campaign)
        if economics:
            prices[key] = numeric(economics.price_usd_t, "precio USD/t")
            costs[key] = numeric(economics.cost_usd_ha, "costo USD/ha")
        elif p.get("profile") == "reference" and crop.has_base_economics:
            prices[key] = numeric(crop.price_usd_t, "reference price USD/t")
            costs[key] = numeric(crop.base_cost_usd_ha, "reference cost USD/ha")
    windows.update({key: months for key, months in (p.get("windows") or {}).items()
                    if key not in unavailable})
    graph = RotationGraph(catalog, p["m"], fixed, windows, period_dates)
    if p.get("profile") == "reference" and (conflict := graph.fixed_window_conflict(0, start)):
        return NoViableRotations([{"sequence": [], "reason": conflict}])
    initial = p["initial_state"]
    state = (numeric(initial["W"], "W"), tuple(numeric(initial[k], k) for k in ("N","P","K")),
             numeric(initial["H"], "H", .000001), numeric(initial["residue"], "residue"),
             tuple(tuple(numeric(v,"thermal history",-100,100) for v in t)
                   if isinstance(t,list) and len(t)==2 else numeric(t,"thermal history",-100,100)
                   for t in initial.get("history", [])), numeric(initial["OM"], "OM", 0, 100))
    transition = p["transition_days"]
    if type(transition) is not int or not 0 <= transition <= 365:
        raise ValueError("transition_days must be an integer between 0 and 365.")
    scenarios = {}
    for item in p.get("scenarios", []):
        sid = item["id"]
        if not isinstance(sid, str) or sid in scenarios:
            raise ValueError("Invalid or duplicate scenario identifiers.")
        climate = {}
        for day, values in item["daily"].items():
            month, day_number = map(int, day.split("-"))
            date(2000, month, day_number)
            if len(values) != 4:
                raise ValueError("Daily weather requires precipitation, temperature, humidity, and radiation.")
            climate[month,day_number] = tuple(numeric(x, "weather", lo, hi) for x,lo,hi in zip(values,(0,-90,0,0),(float("inf"),65,100,float("inf"))))
        scenarios[sid] = climate
    if not scenarios:
        scenarios["NASA_POWER"] = load_climate(numeric(p["latitude"], "latitude", -90,90), numeric(p["longitude"], "longitude", -180,180))
    prices.update({k:numeric(v, "price USD/t") for k,v in p.get("prices_usd_t", {}).items() if v is not None})
    costs.update({k:numeric(v, "cost USD/ha") for k,v in p.get("costs_usd_ha", {}).items() if v is not None})
    drought = p.get("drought_days")
    if drought is not None and (type(drought) is not int or drought < 1):
        raise ValueError("drought_days must be a positive integer.")
    simulator = PeriodSimulator(scenarios, transition, numeric(p["residue_fraction"], "residue fraction",0,1),
        numeric(p["slope_deg"], "slope",0,80), numeric(p["irrigation_mm_day"], "irrigation",0,30),
        prices, costs, numeric(p["irrigation_cost_usd_mm_ha"], "irrigation cost"), drought)
    result = search(graph, simulator, state, start, list(scenarios),
                    numeric(p.get("survival_threshold",1), "threshold",.000001,1), p.get("aggregation","mean"), p.get("mode","exact"))
    return result if isinstance(result, NoViableRotations) else pareto_front(normalize(result))


def recommend(payload):
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    p = dict(payload)
    reference = p.get("profile") == "reference"
    if "profile" in p and not reference:
        raise ValueError("Unknown rotation profile.")
    if reference:
        water_fraction, (nitrogen, phosphorus, potassium), depth, residue = INITIAL_SOIL
        defaults = {
            "initial_state": {"W": water_fraction * depth, "N": nitrogen, "P": phosphorus,
                              "K": potassium, "H": depth, "residue": residue, "OM": 3.0},
            "transition_days": TRANSITION_DAYS, "residue_fraction": .5,
            "slope_deg": 0, "irrigation_mm_day": 0, "irrigation_cost_usd_mm_ha": 0,
        }
        for key, value in defaults.items():
            p.setdefault(key, value)
    if p.get("periods"):
        p.setdefault("m", len(p["periods"]))
        p.setdefault("start_date", p["periods"][0]["start"])
    geometry = p.pop("geometry", None)
    region_point = None
    if geometry is not None:
        from shapely.geometry import shape
        polygon = shape(geometry)
        if polygon.geom_type not in ("Polygon", "MultiPolygon") or polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            raise ValueError("Invalid geometry.")
        p.setdefault("latitude", polygon.centroid.y)
        p.setdefault("longitude", polygon.centroid.x)
        region_point = polygon.centroid if polygon.covers(polygon.centroid) else polygon.representative_point()
    if reference and "latitude" in p and "longitude" in p:
        latitude = numeric(p["latitude"], "latitude", -90, 90)
        longitude = numeric(p["longitude"], "longitude", -180, 180)
        point = (region_point.x, region_point.y) if region_point is not None else (longitude, latitude)
        region = department_at(*point)
        if not region and p.get("region"):
            names = {normalize_region(name): name for name in department_names()}
            region = names.get(normalize_region(p["region"]))
            if not region:
                raise ValueError("Select a valid department of Peru.")
        if not region:
            return {"status": "region_required", "pareto": [], "region": None,
                    "available_regions": department_names()}
        p["region"] = region
    route, weights = p.pop("route", "B_balance"), p.pop("weights", None)
    if route not in PRESETS:
        raise ValueError("Unknown rotation route.")
    result = evaluate(json.dumps(p, sort_keys=True, allow_nan=False))
    warnings = ["Model estimate; parameters inherited from catalog without local validation.",
                "Metrics aggregated across surviving scenarios only."]
    if not p.get("windows") and not p.get("region"):
        warnings.append("No planting windows provided: monthly constraint not evaluated.")
    if p.get("region"):
        warnings.append("Available regional calendars applied. Remaining crops keep their baseline cycle and explicit windows.")
    if p.get("drought_days") is None:
        warnings.append("No prolonged wilting threshold: criterion not evaluated.")
    if isinstance(result, NoViableRotations):
        return {"label":"estimate", "status":result.status, "reasons":result.reasons,
                "pareto":[], "recomendada_por_ruta":{}, "avisos":warnings, "region":p.get("region")}
    f_hat = {c.id:c.f_hat for c in result}
    # Comparability was determined across all feasible routes, before Pareto filtering.
    economic = all(c.f_hat[2] is not None for c in result)
    if not economic:
        warnings.append("Explicit prices or costs missing: f3 and C2 disabled; remaining weights renormalized.")
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
    return {"label":"estimate", "status":"ok", "pareto":[asdict(c) for c in result],
            "region":p.get("region"),
            "recomendada_por_ruta":routes, "recommended":selected.id if selected else None,
            "weights":w, "avisos":warnings, "motivo":"Minimum weighted sum over the Pareto front; tie-break by id.",
            "scenario_count":len(p.get("scenarios") or ["NASA_POWER"]),
            "survival_label":"survival frequency across tested scenarios",
            "origins":{"initial_state":"fallback: reference profile" if reference and "initial_state" not in payload
                       else "observed: provided by requester", "catalog":"fallback: existing catalog",
                       "climate":"provided by requester" if p.get("scenarios") else "observed: NASA POWER, existing reference year",
                       "results":"estimado"}}


def rotation_graph_response(payload):
    try:
        return recommend(payload), 200
    except ClimateUnavailable as exc:
        return {"error":str(exc)}, 503
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
        return {"error":f"Invalid or missing rotation data: {exc}"}, 422
