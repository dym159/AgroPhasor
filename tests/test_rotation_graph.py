"""Valores sintéticos para probar lógica; no son resultados del modelo."""
from datetime import date, timedelta
from math import isfinite
from dataclasses import replace
from itertools import product
from unittest.mock import Mock
import pytest
from backend.models.crop_parameters import CROP_CATALOG
from backend.rotation.graph import RotationGraph
from backend.rotation.costs import PeriodSimulator, PeriodResult
from backend.rotation.search import search, NoViableRotations
from backend.rotation.pareto import Candidate, normalize, pareto_front
from backend.rotation.routes import PRESETS, select_route, rescale_weights
from backend.rotation.api import rotation_graph_response, evaluate

STATE = (100., (100.,40.,120.),400.,0.,(),3.)
CATALOG = {k:replace(CROP_CATALOG["papa"], key=k, botanical_family=f, duration_days=1)
           for k,f in zip(("papa","tomate","frijol","maiz"),("S","S","L","P"))}


def stub():
    simulator = Mock(side_effect=lambda state,key,crop,start,scenario: PeriodResult(state,(1.,0.,None,1.)))
    simulator.transition = 0
    return simulator


@pytest.mark.parametrize("m", [2,3])
def test_exact_enumeration_and_fixed(m):
    expected = [seq for seq in product(CATALOG, repeat=m) if all(CATALOG[a].botanical_family != CATALOG[b].botanical_family for a,b in zip(seq,seq[1:]))]
    result = search(RotationGraph(CATALOG,m),stub(),STATE,date(2026,1,1),["test"])
    assert {c.id for c in result} == {">".join(s) for s in expected}
    if m == 2:
        assert len(result) == 10
    fixed = search(RotationGraph(CATALOG,m,{1:"papa"}),stub(),STATE,date(2026,1,1),["test"])
    assert all(c.stages[1]["crop_id"] == "papa" for c in fixed)
    with pytest.raises(ValueError, match="misma familia"):
        RotationGraph(CATALOG,m,{0:"papa",1:"tomate"})


def test_pareto_and_routes_without_resimulation():
    vectors = [( .60,.30,.50,.55),(.55,.55,.35,.60),(.75,.35,.20,.40),(.70,.60,.15,.45),
               (.50,.10,.45,.60),(.65,.15,.10,.35),(.30,.05,.60,.80),(.55,.50,.45,.70),
               (.60,.55,.20,.40),(.25,.20,.65,.85)]
    candidates = [Candidate(str(i),v,f_hat=v) for i,v in enumerate(vectors,1)]
    front = pareto_front(candidates)
    assert {c.id for c in front} == {"1","2","5","6","7","9","10"}
    notes = {c.id:c.f_hat for c in front}
    assert [select_route(front,notes,w).id for w in PRESETS.values()] == ["10","7","7","6","6","6","6"]
    assert sum(a*b for a,b in zip(PRESETS["A1_menor_agua"], notes["10"])) == pytest.approx(.345)
    assert rescale_weights([.7,.1,.1,.1],2,.4) == pytest.approx([.466667,.066667,.4,.066667],abs=.001)
    assert sum(rescale_weights([1,0,0,0],0,.4)) == pytest.approx(1)


def test_normalization_missing_and_constant():
    candidates = normalize([Candidate("a",(1,2,None,4)), Candidate("b",(3,2,None,8))])
    assert candidates[0].f_hat == (0,0,None,0)
    assert candidates[1].f_hat == (1,0,None,1)


def test_no_viable_and_scenario_threshold():
    simulator = stub()
    simulator.side_effect = lambda state,key,crop,start,scenario: PeriodResult(state,(1,0,None,1), "letal" if scenario == "bad" else None)
    result = search(RotationGraph(CATALOG,2),simulator,STATE,date(2026,1,1),["bad"])
    assert isinstance(result,NoViableRotations) and result.reasons
    result = search(RotationGraph(CATALOG,2),simulator,STATE,date(2026,1,1),["bad","good"],.5)
    assert all(c.survival_frequency == .5 for c in result)


def test_real_simulator_state_and_cache():
    climate = {(m,d):(3.,16.,65.,18.) for m in range(1,13) for d in range(1,32)}
    simulator = PeriodSimulator({"test":climate},0,.5,0,0,{}, {},0)
    crop = replace(CROP_CATALOG["papa"], duration_days=1)
    first = simulator(STATE,"papa",crop,date(2026,1,1),"test")
    assert first.reason is None
    assert first is simulator(STATE,"papa",crop,date(2026,1,1),"test")
    from backend.rotation import costs
    original = costs.advance_day
    from unittest.mock import patch
    with patch.object(costs,"advance_day",wraps=original) as advance:
        simulator(first.state,"papa",crop,date(2026,1,2),"test")
        incoming = advance.call_args.args[0]
        assert incoming[:3] == first.state[:3]
        assert incoming[4] == first.state[4]
        assert advance.call_args.args[-1] >= first.state[-1]


def test_windows_and_explicit_dates():
    graph = RotationGraph(CATALOG,2,windows={"papa":[2],"tomate":[2],"frijol":[2],"maiz":[2]})
    assert isinstance(search(graph,stub(),STATE,date(2026,1,1),["test"]),NoViableRotations)
    graph = RotationGraph(CATALOG,2,period_dates=[date(2026,1,1),date(2026,1,3)])
    assert isinstance(search(graph,stub(),STATE,date(2026,1,1),["test"]),NoViableRotations)


def test_reference_column_performance(record_property):
    """Clima sintético, catálogo real: mide columna, no malla espacial."""
    from time import perf_counter
    catalog = {k:CROP_CATALOG[k] for k in ("papa","maiz","frijol")}
    climate = {(m,d):(3.,16.,65.,18.) for m in range(1,13) for d in range(1,32)}
    simulator = PeriodSimulator({"test":climate},14,.5,0,0,{}, {},0)
    started = perf_counter()
    result = search(RotationGraph(catalog,3),simulator,STATE,date(2026,1,1),["test"])
    elapsed = perf_counter()-started
    record_property("m3_reference_column_seconds",elapsed)
    print(f"m=3, catálogo real, una columna, clima sintético: {elapsed:.3f} s")
    assert not isinstance(result, NoViableRotations)


def test_endpoint_validation_and_weights_cache():
    assert rotation_graph_response({})[1] == 422
    assert rotation_graph_response({"geometry":{"type":"Point","coordinates":[0,0]}})[1] == 422
    payload = dict(m=2, crop_ids=["papa","frijol"], start_date="2026-01-01",
                   initial_state=dict(W=100,N=100,P=40,K=120,H=400,residue=0,OM=3),
                   transition_days=0,residue_fraction=.5,slope_deg=0,irrigation_mm_day=0,
                   irrigation_cost_usd_mm_ha=0, scenarios=[{"id":"test", "daily":{
                       f"{m:02d}-{d:02d}":[3,16,65,18] for m in range(1,13) for d in range(1,29)}}])
    # Stub únicamente en tests: evita clima incompleto y no utiliza red.
    from unittest.mock import patch
    evaluate.cache_clear()
    with patch("backend.rotation.api.PeriodSimulator", return_value=stub()) as factory:
        first,status = rotation_graph_response(payload)
        assert status == 200 and first["pareto"]
        assert first["recomendada_por_ruta"]["C2_mayor_ganancia"] is None
        second,status = rotation_graph_response({**payload,"weights":[.7,.1,.1,.1]})
        assert status == 200 and factory.call_count == 1
        assert second["pareto"] == first["pareto"]
    evaluate.cache_clear()


def test_incomplete_economics_stays_disabled_after_pareto_filtering():
    complete = Candidate("papa>frijol", (.4, .2, -300, 100))
    incomplete = Candidate("papa>maiz", (.5, .3, None, 120))
    front = pareto_front(normalize([complete, incomplete]))
    assert front == [complete]
    from unittest.mock import patch
    with patch("backend.rotation.api.evaluate", return_value=front):
        response, status = rotation_graph_response({"route": "C2_mayor_ganancia"})
    assert status == 200
    assert response["pareto"][0]["f_hat"][2] is None
    assert response["recommended"] is None
    assert response["recomendada_por_ruta"]["C2_mayor_ganancia"] is None


def test_calendar_and_annualized_cost_with_real_solver():
    daily = {}
    day = date(2024, 1, 1)
    while day.year == 2024:
        daily[day.strftime("%m-%d")] = [3, 16, 65, 18]
        day += timedelta(days=1)
    payload = dict(
        periods=[{"start": "2026-11-01"}, {"start": "2027-03-05"}],
        crop_ids=["papa", "frijol"], fixed={"0": "papa", "1": "frijol"},
        initial_state=dict(W=104, N=100, P=40, K=120, H=400, residue=0, OM=3),
        transition_days=14, residue_fraction=.5, slope_deg=0, irrigation_mm_day=10,
        irrigation_cost_usd_mm_ha=0, prices_usd_t={"papa": 400, "frijol": 500},
        costs_usd_ha={"papa": 100, "frijol": 200}, scenarios=[{"id": "control", "daily": daily}],
    )
    result, status = rotation_graph_response(payload)
    assert status == 200 and result["recommended"] == "papa>frijol"
    route = result["pareto"][0]
    assert route["stages"][0]["harvest"] == "2027-02-19"
    assert route["stages"][1]["harvest"] == "2027-06-03"
    assert route["stages"][1]["end"] == "2027-06-17"
    assert route["f"][3] == 114
    assert all(isfinite(value) for value in route["f"])
    assert all(0 <= value <= 1 for value in route["f"][:2])

    mismatched_dates = [{"start": "2026-11-01"}, {"start": "2027-04-01"}]
    incompatible, status = rotation_graph_response({**payload, "periods": mismatched_dates})
    assert status == 200 and not incompatible["pareto"]
    assert any("2027-04-01" in item["reason"] and "2027-03-05" in item["reason"]
               for item in incompatible["reasons"])

    automatic = {key: value for key, value in payload.items() if key != "periods"}
    suggested, status = rotation_graph_response({**automatic, "start_date": "2026-11-01", "m": 2})
    assert status == 200
    assert suggested["pareto"][0]["stages"] == route["stages"]

    cost_result, status = rotation_graph_response({**payload, "irrigation_cost_usd_mm_ha": .1})
    assert status == 200
    new_f = cost_result["pareto"][0]["f"]
    # El riego aplica a los 200 días de cultivo. El año se escala sobre los 228 días del plan.
    assert new_f[2] - route["f"][2] == pytest.approx(365 * .1 * 10 * 200 / 228)
    assert new_f[:2] == route["f"][:2]


def test_reference_profile_recommends_without_manual_inputs():
    daily = {(date(2024, 1, 1) + timedelta(days=i)).strftime("%m-%d"): [3, 16, 65, 18]
             for i in range(366)}
    result, status = rotation_graph_response({
        "profile": "reference", "m": 2, "start_date": "2026-11-01",
        "crop_ids": ["papa", "frijol"], "scenarios": [{"id": "control", "daily": daily}],
        "weights": [0, 0, 1, 0],
    })
    assert status == 200 and len(result["pareto"][0]["stages"]) == 2
    assert result["weights"] == [0, 0, 1, 0]
    assert result["pareto"][0]["f"][2] is not None
    assert result["origins"]["initial_state"] == "respaldo: perfil de referencia"


def test_documented_cultivars_are_available_to_the_rotation_dashboard():
    from backend.main import crop_catalog

    catalog = crop_catalog()
    assert len(catalog) >= 27
    assert catalog["haba"]["duration_days"] == 158
    assert catalog["quinua"]["variety"] == "Atipaq"
    daily = {(date(2024, 1, 1) + timedelta(days=i)).strftime("%m-%d"): [3, 16, 65, 18]
             for i in range(366)}
    result, status = rotation_graph_response({
        "profile": "reference", "m": 2, "start_date": "2026-11-01",
        "crop_ids": ["haba", "quinua"], "scenarios": [{"id": "control", "daily": daily}],
    })
    assert status == 200
    assert set(result["recommended"].split(">")) == {"haba", "quinua"}


def test_dashboard_applies_detected_calendar_and_supports_six_stages():
    daily = {(date(2024, 1, 1) + timedelta(days=i)).strftime("%m-%d"): [3, 16, 65, 18]
             for i in range(366)}
    payload = {
        "profile": "reference", "m": 3, "mode": "adaptive", "start_date": "2026-11-01",
        "geometry": {"type": "Polygon", "coordinates": [[[-70.15, -15.49], [-70.14, -15.49],
                     [-70.14, -15.48], [-70.15, -15.49]]]},
        "crop_ids": ["haba", "papa", "maiz"], "fixed": {"0": "haba"},
        "scenarios": [{"id": "control", "daily": daily}],
    }
    result, status = rotation_graph_response(payload)
    assert status == 200 and result["region"] == "Puno" and not result["pareto"]
    assert "fuera de su ventana regional" in result["reasons"][0]["reason"]

    result, status = rotation_graph_response({**payload, "start_date": "2026-10-01", "m": 6})
    assert status == 200 and result["pareto"]
    assert all(len(candidate["stages"]) == 6 for candidate in result["pareto"])
    assert all(candidate["stages"][0]["crop_id"] == "haba" for candidate in result["pareto"])


def test_dashboard_requires_region_and_filters_crops_documented_elsewhere():
    payload = {"profile": "reference", "mode": "adaptive", "m": 3,
               "start_date": "2026-11-01", "longitude": 0, "latitude": 0,
               "crop_ids": ["haba", "zanahoria", "caupi"], "fixed": {"0": "haba"}}
    result, status = rotation_graph_response(payload)
    assert status == 200 and result["status"] == "region_required"
    assert "Puno" in result["available_regions"] and not result["pareto"]

    result, status = rotation_graph_response({**payload, "region": "Puno"})
    assert status == 200 and result["region"] == "Puno" and not result["pareto"]
    assert "fuera de su ventana regional" in result["reasons"][0]["reason"]

    result, status = rotation_graph_response({**payload, "region": "Junín", "fixed": {"0": "caupi"}})
    assert status == 200 and result["region"] == "Junín" and not result["pareto"]
    assert "Caupí Vaina Verde no tiene un calendario documentado para Junín" in result["reasons"][0]["reason"]
