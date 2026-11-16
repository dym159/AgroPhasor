"""Evaluate an exploratory rotation from a fixed first planting."""

import csv
from copy import deepcopy
import json
from heapq import heappush, heappop
from itertools import count as counter
from dataclasses import replace
from datetime import date, timedelta
from functools import lru_cache
from math import isfinite
from pathlib import Path
import unicodedata
from urllib.parse import urlencode

from backend.core.climate_generator import mc_day_to_weather
from backend.core.edo2_engine import compute_soil_limits, solve_edo2_step
from backend.core.edo3_engine import solve_edo3_step, compute_liebig_factor
from backend.services.climate_service import (
    ClimateUnavailable,
    history_from_annual_climate,
    predict_climate_scenarios,
)
from backend.services.coupled_model import advance_day, incorporate_residue
from backend.core.edo4_engine import execute_harvest_event, solve_edo4_step
from backend.core.edo5_engine import solve_edo5_step
from backend.models.crop_parameters import CROP_CATALOG
from backend.services.parcel_edo1 import POWER_DAILY_URL, read_json
from rotation_ranking import Candidate, METRICS, rank_rotations

PRODUCTS = {"papa": "Native Potato", "maiz": "Amylaceous Maize", "frijol": "Dry Bean"}
CSV_CROP_NAMES = {"papa": "Papa", "maiz": "Maíz amiláceo", "frijol": "Frijol grano seco"}
BASE_WEIGHTS = {"resilience": (.50, .30, .10, .10), "balance": (.25,) * 4,
                "profit": (.05, .05, .85, .05)}
REFERENCE_YEAR = 2023
TRANSITION_DAYS = 14
DRY_RAIN_FACTOR = .7
INITIAL_SOIL = (.26, (100., 40., 120.), 400., 0.)


def normalize_name(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.strip().casefold())
                   if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def load_prices():
    path = Path(__file__).resolve().parents[1] / "data" / "precios_chacra_midagri_2025_2026.csv"
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {(normalize_name(row["region"]), row["nombre_cultivo"]): float(row["precio_soles_kg"])
                for row in csv.DictReader(source)}


@lru_cache(maxsize=64)
def load_climate(lat, lon):
    fields = ("PRECTOTCORR", "T2M", "RH2M", "ALLSKY_SFC_SW_DWN")
    params = {"parameters": ",".join(fields), "community": "AG", "format": "JSON",
              "latitude": lat, "longitude": lon,
              "start": f"{REFERENCE_YEAR}0101", "end": f"{REFERENCE_YEAR}1231"}
    try:
        response = read_json(f"{POWER_DAILY_URL}?{urlencode(params)}")
        series = response["properties"]["parameter"]
        units = response["parameters"][fields[-1]]["units"].lower().replace(" ", "")
        if units.startswith("mj"):
            radiation_scale = 1
        elif units.startswith("kw"):
            radiation_scale = 3.6
        else:
            raise ValueError("Unknown radiation unit")
        climate = {}
        for offset in range(365):
            day = date(REFERENCE_YEAR, 1, 1) + timedelta(days=offset)
            values = tuple(float(series[key][day.strftime("%Y%m%d")]) for key in fields)
            rain, temp, humidity, radiation = values
            if not all(map(isfinite, values)) or not (rain >= 0 and -90 <= temp <= 65
                                                       and 0 <= humidity <= 100 and radiation >= 0):
                raise ValueError("Incomplete daily weather data")
            climate[day.month, day.day] = (rain, temp, humidity, radiation * radiation_scale)
        return climate
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise ClimateUnavailable("NASA POWER did not return a complete daily series. Please try again.") from exc


_DEFAULT_LOAD_CLIMATE = load_climate


def _rotation_horizon_days(payload, start_day):
    """Estimate maximum date span in days needed to simulate all candidate routes."""
    count = payload.get("crop_count", 3)
    max_crop_days = max(CROP_CATALOG[k].duration_days for k in PRODUCTS)
    horizon = max(365, int(count) * (max_crop_days + TRANSITION_DAYS) + TRANSITION_DAYS)
    phases = payload.get("baseline_phases")
    if isinstance(phases, list) and phases:
        try:
            last_harvest = date.fromisoformat(phases[-1]["harvest"])
            horizon = max(horizon, (last_harvest - start_day).days + TRANSITION_DAYS)
        except (KeyError, TypeError, ValueError):
            pass
    return horizon


def number(value, minimum, maximum, label):
    if type(value) not in (int, float) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")
    return float(value)


def simulate_segment(crop, start, days, soil, climate, slope, irrigation, rain_factor, growing):
    moisture, npk, depth, residue, *memory = soil
    history, organic_matter = memory if memory else ((), 3.0)
    if growing:
        organic_matter = incorporate_residue(organic_matter, residue, depth)
    state = (moisture * depth, npk, depth, crop.B0_t_ha if growing else residue, history)
    stress_days = 0
    deficit = 0.0
    for offset in range(days):
        day = start + timedelta(days=offset)
        key = (2, 28) if (day.month, day.day) == (2, 29) else (day.month, day.day)
        rain, temp, humidity, radiation, *rest = climate[day] if day in climate else climate[key]
        state, diagnostics = advance_day(state, crop, (rain * rain_factor, temp, humidity, radiation, *rest),
                                          slope, irrigation if growing else 0, growing, organic_matter)
        if growing and not diagnostics["viable"]:
            raise ValueError("Route exceeds the crop's thermal limits.")
        stress_days += growing and diagnostics["water_stress"] > 0
        deficit += 1 - diagnostics["psi"]
    water, npk, depth, biomass, history = state
    return (water / depth if depth else 0, npk, depth, biomass, history, organic_matter), stress_days, deficit


def _resolve_rotation_climate(payload, start, lat, lon):
    delta_t = number(payload.get("delta_T_whatif", 0), -10, 15, "Temperature delta")
    delta_p = number(payload.get("delta_P_pct_whatif", 0), -90, 200, "Precipitation delta (%)")
    seed = int(payload.get("climate_seed", 42))
    use_forecast = bool(payload.get("use_climate_forecast", True))
    if load_climate is not _DEFAULT_LOAD_CLIMATE or not use_forecast:
        climate = load_climate(round(lat, 3), round(lon, 3))
        if delta_t or delta_p:
            rain_mult = max(0.0, 1.0 + delta_p / 100.0)
            climate = {
                k: (w[0] * rain_mult, w[1] + delta_t, w[2], w[3], *(([w[4] + delta_t] if len(w) > 4 else [])))
                for k, w in climate.items()
            }
        return climate, {
            "climate_source": f"NASA POWER {REFERENCE_YEAR} · historical repeat",
            "climate_window": None,
        }

    horizon = _rotation_horizon_days(payload, start)
    n_mc = int(number(payload.get("mc_samples", 30), 1, 200, "Monte Carlo samples"))
    forecast = predict_climate_scenarios(
        lat,
        lon,
        start,
        start + timedelta(days=horizon),
        n_mc=n_mc,
        delta_T_whatif=delta_t,
        delta_P_pct_whatif=delta_p,
        seed=seed,
    )
    climate = {
        day: mc_day_to_weather(sc_day)
        for day, sc_day in zip(forecast["dates"], forecast["representative_scenario"])
    }
    return climate, {
        "climate_source": "NASA POWER + Fourier/AR(1)-Gamma Monte Carlo",
        "climate_window": forecast["metadata"]["fitting_window"],
        "climate_forecast_meta": forecast["metadata"],
    }


def recommend_rotation(payload):
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    physical = {key: value for key, value in payload.items() if key not in ("weights", "strategy")}
    data = json.loads(_cached_rotation(json.dumps(physical, sort_keys=True)))
    candidates = [Candidate(route["id"], route["metrics"]) for route in data["candidates"]]
    weights = dict(zip(METRICS, (.25,) * 4))
    if "weights" in payload:
        if not isinstance(payload["weights"], dict):
            raise ValueError("Weights must be a JSON object.")
        values = [number(payload["weights"].get(f"w{i}"), 0, 100, "Each knob weight") for i in range(1, 5)]
        total = sum(values)
        if total <= 0:
            raise ValueError("Assign weight to at least one knob.")
        weights = dict(zip(METRICS, (value / total for value in values)))
    else:
        mode = payload.get("strategy", "balance")
        if mode not in BASE_WEIGHTS:
            raise ValueError("Unknown strategy mode.")
        weights = dict(zip(METRICS, BASE_WEIGHTS[mode]))
    modes = {key: dict(zip(METRICS, values)) for key, values in BASE_WEIGHTS.items()}
    ranking = rank_rotations(candidates, data["bounds"], {**modes, "custom": weights})
    by_id = {route["id"]: route for route in data["candidates"]}
    data["routes"] = [by_id[key] for key in ranking.by_mode["custom"] or ()]
    return data


@lru_cache(maxsize=32)
def _cached_rotation(serialized):
    payload = json.loads(serialized)
    result = _evaluate_spatial(payload)
    phases = payload.get("baseline_phases")
    if phases:
        if not isinstance(phases, list) or not 2 <= len(phases) <= 6:
            raise ValueError("Baseline comparison supports between two and six complete phases.")
        baseline = _evaluate_spatial({**payload, "_baseline": True, "crop_id": phases[0]["cropId"],
                                     "crop_count": len(phases), "start_date": phases[0]["start"]})
        result["baseline"] = baseline["candidates"][0] if baseline["candidates"] else None
        result["baseline_rejected"] = not bool(baseline["candidates"])
    if payload.get("evaluate_uncertainty"):
        start_dt = date.fromisoformat(payload["start_date"])
        horizon = _rotation_horizon_days(payload, start_dt)
        samples = int(number(payload.get("uncertainty_samples", 20), 1, 200, "Uncertainty samples"))
        delta_t = number(payload.get("delta_T_whatif", 0), -10, 15, "Temperature delta")
        delta_p = number(payload.get("delta_P_pct_whatif", 0), -90, 200, "Precipitation delta (%)")
        seed = int(payload.get("climate_seed", 42))
        history_override = None
        if load_climate is not _DEFAULT_LOAD_CLIMATE:
            annual = load_climate(round(payload["latitude"], 3), round(payload["longitude"], 3))
            history_override = history_from_annual_climate(
                annual, lat=payload["latitude"], lon=payload["longitude"]
            )
        mc_forecast = predict_climate_scenarios(
            payload["latitude"],
            payload["longitude"],
            start_dt,
            start_dt + timedelta(days=horizon),
            n_mc=samples,
            delta_T_whatif=delta_t,
            delta_P_pct_whatif=delta_p,
            seed=seed,
            history_override=history_override,
        )
        survived = {route["id"]: 0 for route in result["candidates"]}
        for sc in mc_forecast["escenarios"]:
            scenario = {day: mc_day_to_weather(sc_day) for day, sc_day in zip(mc_forecast["dates"], sc)}
            tested = _evaluate_spatial(payload, scenario)
            for route in tested["candidates"]:
                if route["id"] in survived:
                    survived[route["id"]] += 1
        for route in result["candidates"]:
            route["uncertainty"] = {
                "samples": samples,
                "viable_samples": survived[route["id"]],
                "confidence_pct": round(100.0 * survived[route["id"]] / samples, 1),
            }
        fit_win = mc_forecast["metadata"]["fitting_window"]
        result["uncertainty_assumptions"] = (
            f"{samples} Fourier (K=2) + AR(1) + Bernoulli-Gamma Monte Carlo scenarios "
            f"calibrated on {fit_win['start']}..{fit_win['end']} ({fit_win['days']} days, seed={seed})."
        )
    return json.dumps(result)



def _evaluate_spatial(payload, climate_override=None):
    cells = payload.get("terrain_cells")
    if not cells:
        return _evaluate_rotation(payload, climate_override)
    if not isinstance(cells, list) or len(cells) > 2500:
        raise ValueError("The terrain grid must contain at most 2,500 cells.")
    validated = []
    for cell in cells:
        validated.append((
            number(cell.get("area_m2"), .001, 1e8, "Cell area"),
            number(cell.get("altitude_m"), -500, 9000, "Altitude"),
            number(cell.get("slope_deg"), 0, 80, "Slope"),
        ))
    base_climate = climate_override
    base_meta = {}
    if base_climate is None:
        start_dt = date.fromisoformat(payload.get("start_date", ""))
        lat = number(payload.get("latitude"), -90, 90, "Latitude")
        lon = number(payload.get("longitude"), -180, 180, "Longitude")
        base_climate, base_meta = _resolve_rotation_climate(payload, start_dt, lat, lon)
    area = sum(cell[0] for cell in validated)
    altitude = sum(a*z for a,z,_ in validated) / area
    results = []
    for cell_area, elevation, slope in validated:
        cell_payload = {**payload, "slope_deg": slope,
                        "temperature_offset_c": -.0065 * (elevation-altitude)}
        result = _evaluate_rotation(cell_payload, base_climate)
        if base_meta:
            result.update(base_meta)
        results.append((cell_area / area, result))
    result = deepcopy(results[0][1])
    common = set(route["id"] for route in result["candidates"])
    for _, cell_result in results[1:]:
        common.intersection_update(route["id"] for route in cell_result["candidates"])
    routes = []
    for route_id in sorted(common):
        members = [(weight, next(route for route in item["candidates"] if route["id"] == route_id))
                   for weight, item in results]
        route = deepcopy(members[0][1])
        for field in ("dry_stress", "soil_loss_mm", "final_nutrient_index", "final_water_pct",
                      "irrigation_mm", "revenue_pen_ha", "margin_pen_ha"):
            route[field] = (sum(w*r[field] for w,r in members)
                            if all(r[field] is not None for _,r in members) else None)
        for metric in METRICS:
            route["metrics"][metric] = (sum(w*r["metrics"][metric] for w,r in members)
                                       if all(r["metrics"][metric] is not None for _,r in members) else None)
        for index, stage in enumerate(route["stages"]):
            for field in ("yield_t_ha", "dry_yield_t_ha", "revenue_pen_ha"):
                stage[field] = (sum(w*r["stages"][index][field] for w,r in members)
                                if all(r["stages"][index][field] is not None for _,r in members) else None)
        routes.append(route)
    result["candidates"] = routes
    result["rejected"] = [entry for _,item in results for entry in item["rejected"]]
    result["cells_count"] = len(cells)
    result["slope_assumed"] = False
    for metric in METRICS:
        values = [r["metrics"][metric] for r in routes if r["metrics"][metric] is not None]
        result["bounds"][metric] = (min(values),max(values)) if values else (0.,0.)
    return result


def _evaluate_rotation(payload, climate_override=None):
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    first = payload.get("crop_id")
    if not isinstance(first, str) or first not in PRODUCTS:
        raise ValueError("Choose Native Potato (papa), Amylaceous Maize (maiz), or Dry Bean (frijol).")
    count = payload.get("crop_count", 3)
    if type(count) is not int or not 2 <= count <= 6:
        raise ValueError("The crop rotation must contain between two and six crops.")
    try:
        start = date.fromisoformat(payload.get("start_date", ""))
        if not 1900 <= start.year <= 9990:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ValueError("Provide a valid planting start date.") from exc

    lat = number(payload.get("latitude"), -90, 90, "Latitude")
    lon = number(payload.get("longitude"), -180, 180, "Longitude")
    slope = number(payload.get("slope_deg", 0), 0, 80, "Slope")
    irrigation = number(payload.get("irrigation_mm_day", 0), 0, 30, "Daily irrigation")
    region = payload.get("region", "")
    if not isinstance(region, str) or len(region) > 100:
        raise ValueError("Provide a valid region.")
    costs = payload.get("costs_pen_ha", {})
    if not isinstance(costs, dict) or costs.keys() - PRODUCTS.keys():
        raise ValueError("Costs must correspond to the pilot crop catalog.")
    costs = {key: number(value, 0, 1_000_000, "Cost per hectare")
             for key, value in costs.items()}

    mode = payload.get("strategy", "balance")
    if not isinstance(mode, str) or mode not in BASE_WEIGHTS:
        raise ValueError("Unknown strategy mode.")
    weights = {key: dict(zip(METRICS, values)) for key, values in BASE_WEIGHTS.items()}
    sliders = payload.get("weights")
    if sliders is not None:
        if not isinstance(sliders, dict):
            raise ValueError("Weights must be a JSON object.")
        values = [number(sliders.get(f"w{i}"), 0, 100, "Each knob weight") for i in range(1, 5)]
        total = sum(values)
        if not total:
            raise ValueError("Assign weight to at least one knob.")
        weights["custom"] = dict(zip(METRICS, (value / total for value in values)))
        mode = "custom"

    residue_fraction = number(payload.get("residue_fraction", .5), 0, 1, "Residue fraction")
    irrigation_cost = number(payload.get("irrigation_cost_pen_mm_ha", 0), 0, 10000, "Irrigation cost")
    if climate_override is not None:
        climate = climate_override
        climate_meta = {}
    else:
        climate, climate_meta = _resolve_rotation_climate(payload, start, lat, lon)
    temperature_offset = number(payload.get("temperature_offset_c", 0), -70, 70, "Temperature offset")
    if temperature_offset:
        adjusted = {}
        for key, weather in climate.items():
            rain, temp, humidity, radiation, *rest = weather
            t_soil = (rest[0] + temperature_offset,) if rest else ()
            adjusted[key] = (rain, temp + temperature_offset, humidity, radiation, *t_soil)
        climate = adjusted
    prices = {key: load_prices().get((normalize_name(region), product))
              for key, product in CSV_CROP_NAMES.items()}
    manual = payload.get("baseline_phases") if payload.get("_baseline") else None
    if manual:
        previous_end = None
        for phase in manual:
            phase_start = date.fromisoformat(phase["start"])
            phase_end = date.fromisoformat(phase["harvest"])
            if phase.get("cropId") not in PRODUCTS or phase_end <= phase_start or (previous_end and phase_start < previous_end):
                raise ValueError("The current rotation contains invalid crops or dates.")
            previous_end = phase_end
    routes = {}
    rejected = []
    frontier = []
    serial = counter()

    def visit(key, planting, wet, dry, stages, stress_sum, crop_days):
        crop = CROP_CATALOG[key]
        duration = ((date.fromisoformat(manual[len(stages)]["harvest"]) - planting).days
                    if manual else crop.duration_days)
        if not 1 <= duration <= 1095:
            raise ValueError("Each crop cycle must last between 1 and 1,095 days.")
        try:
            wet, _, _ = simulate_segment(crop, planting, duration, wet, climate, slope, irrigation, 1, True)
            dry, stress_days, deficit = simulate_segment(
                crop, planting, duration, dry, climate, slope, irrigation, DRY_RAIN_FACTOR, True)
        except ValueError as exc:
            rejected.append({"crops": [s["crop_id"] for s in stages] + [key], "reason": str(exc)})
            return
        harvest = planting + timedelta(days=duration)
        regular = execute_harvest_event(wet[3], crop, residue_fraction)
        drought = execute_harvest_event(dry[3], crop, residue_fraction)
        price = prices[key]
        revenue = None if price is None else regular.commercial_yield_t_ha * 1000 * price
        stages = [*stages, {
            "crop_id": key, "crop": PRODUCTS[key], "start": planting.isoformat(),
            "residue_fraction": residue_fraction, "irrigation_mm_day": irrigation,
            "harvest": harvest.isoformat(), "duration_days": duration, "root_depth_mm": crop.Zr_mm,
            "depletion_fraction": crop.p_depletion, "dry_stress_days": stress_days,
            "yield_t_ha": regular.commercial_yield_t_ha, "dry_yield_t_ha": drought.commercial_yield_t_ha,
            "price_pen_kg": price, "revenue_pen_ha": revenue,
        }]
        crop_days += duration
        stress_sum += deficit
        if len(stages) == count:
            wet, _, _ = simulate_segment(crop, harvest, TRANSITION_DAYS, (*wet[:3], regular.residue_left_t_ha, *wet[4:]),
                                         climate, slope, 0, 1, False)
            dry, _, transition_deficit = simulate_segment(crop, harvest, TRANSITION_DAYS, (*dry[:3], drought.residue_left_t_ha, *dry[4:]),
                                                          climate, slope, 0, DRY_RAIN_FACTOR, False)
            stress_sum += transition_deficit
            total_days = (harvest - start).days + TRANSITION_DAYS
            ids = tuple(stage["crop_id"] for stage in stages)
            routes[">".join(ids)] = {
                "stages": stages, "days": total_days,
                "dry_stress": stress_sum / total_days, "soil_loss_mm": INITIAL_SOIL[2] - wet[2],
                "final_nutrient_index": compute_liebig_factor(*wet[1], crop.K_N, crop.K_P, crop.K_K)[0],
                "final_water_pct": wet[0] * 100, "irrigation_mm": irrigation * crop_days,
                "revenue_pen_ha": (sum(stage["revenue_pen_ha"] for stage in stages)
                                   if all(prices[k] is not None for k in ids) else None),
            }
            return

        next_start = date.fromisoformat(manual[len(stages)]["start"]) if manual else harvest + timedelta(days=TRANSITION_DAYS)
        gap = (next_start - harvest).days
        wet, _, _ = simulate_segment(crop, harvest, gap, (*wet[:3], regular.residue_left_t_ha, *wet[4:]),
                                     climate, slope, 0, 1, False)
        dry, _, transition_deficit = simulate_segment(crop, harvest, gap, (*dry[:3], drought.residue_left_t_ha, *dry[4:]),
                                     climate, slope, 0, DRY_RAIN_FACTOR, False)
        for next_key in ([manual[len(stages)]["cropId"]] if manual else PRODUCTS):
            if CROP_CATALOG[next_key].botanical_family != crop.botanical_family:
                cost = stress_sum + transition_deficit
                # A* with admissible h=0 on accumulated environmental deficit.
                # Exhaust the finite graph to retain candidates for every Pareto objective.
                heappush(frontier, (cost, next(serial), next_key,
                                    next_start,
                                    wet, dry, stages, cost, crop_days))

    heappush(frontier, (0., next(serial), first, start, INITIAL_SOIL, INITIAL_SOIL, [], 0., 0))
    while frontier:
        _, _, key, planting, wet, dry, stages, stress_sum, crop_days = heappop(frontier)
        visit(key, planting, wet, dry, stages, stress_sum, crop_days)
    use_margin = all(k in costs for r in routes.values() for k in (s["crop_id"] for s in r["stages"]))
    candidates = []
    for key, route in routes.items():
        revenue = route["revenue_pen_ha"]
        route["margin_pen_ha"] = (revenue - sum(costs[s["crop_id"]] for s in route["stages"]) - irrigation_cost * route["irrigation_mm"]
                                  if use_margin and revenue is not None else None)
        economic = route["margin_pen_ha"] if use_margin else revenue
        candidates.append(Candidate(key, dict(zip(METRICS, (
            route["dry_stress"], .5 * route["soil_loss_mm"] / INITIAL_SOIL[2] + .5 * (1 - route["final_nutrient_index"]),
            None if economic is None else -economic * 365 / route["days"], route["days"] / count,
        )))))
    for candidate in candidates:
        routes[candidate.route_id]["id"] = candidate.route_id
        routes[candidate.route_id]["metrics"] = candidate.metrics
    bounds = {}
    for metric in METRICS:
        values = [c.metrics[metric] for c in candidates if c.metrics[metric] is not None]
        bounds[metric] = (min(values), max(values)) if values else (0., 0.)
    ranking = rank_rotations(candidates, bounds, weights)
    ordered = ranking.by_mode[mode]
    return {
        "routes": [routes[key] for key in ordered or ()],
        "candidates": list(routes.values()), "bounds": bounds,
        "rejected": rejected,
        "economic_metric": ("unavailable" if "economic_loss" not in ranking.compared_metrics
                            else "margin" if use_margin else "revenue"),
        "climate_year": REFERENCE_YEAR, "dry_rain_factor": DRY_RAIN_FACTOR,
        "transition_days": TRANSITION_DAYS,
        "slope_assumed": "slope_deg" not in payload,
        **climate_meta,
    }

