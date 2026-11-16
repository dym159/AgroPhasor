"""Exploración exacta o por capas con un límite de ramas prometedoras."""
from dataclasses import dataclass
from datetime import timedelta
from statistics import mean
from backend.core.edo3_engine import compute_liebig_factor
from backend.core.edo5_engine import compute_soil_pareto_metric_f2
from .graph import Node
from .pareto import Candidate, normalize
from .routes import PRESETS


@dataclass
class NoViableRotations:
    reasons: list
    status: str = "sin rotaciones viables"


def retain_prefixes(branches, limit=8):
    if len(branches) <= limit:
        return branches
    normalize([branch[0] for branch in branches])
    rankings = [
        iter(sorted(branches, key=lambda branch: (
            sum(weight * (value or 0) for weight, value in zip(weights, branch[0].f_hat)),
            branch[0].id,
        )))
        for weights in PRESETS.values()
    ]
    retained = {}
    while len(retained) < limit:
        for ranking in rankings:
            branch = next(item for item in ranking if item[0].id not in retained)
            retained[branch[0].id] = branch
            if len(retained) == limit:
                break
    return list(retained.values())


def search(graph, simulator, initial: tuple, start, scenarios: list[str],
           survival_threshold: float = 1., aggregation: str = "mean", mode: str = "exact"):
    """Propaga estados por escenario; frecuencia sobre todos los escenarios probados."""
    if mode not in ("exact", "adaptive"):
        raise ValueError("Modo de búsqueda desconocido. Usa exact o adaptive.")
    if not scenarios or len(set(scenarios)) != len(scenarios) or not 0 < survival_threshold <= 1 or aggregation not in ("mean", "worst"):
        raise ValueError("Escenarios, agregación o umbral inválidos.")
    candidates, reasons = [], []
    aggregate = mean if aggregation == "mean" else max

    def expand(node, states, totals, stages):
        if graph.period_dates and node.start != graph.period_dates[node.period]:
            expected = graph.period_dates[node.period]
            reasons.append({"sequence": [s["crop_id"] for s in stages],
                            "reason": f"El periodo {node.period + 1} pide sembrar el {expected}, pero la cosecha y la preparación permiten iniciar el {node.start}."})
            return
        edges = list(graph.successors(node))
        if not edges:
            reason = (graph.fixed_window_conflict(node.period, node.start)
                      or "Familia, ventana de siembra o cultivo fijado incompatible")
            reasons.append({"sequence": [s["crop_id"] for s in stages], "reason": reason})
        for key, crop in edges:
            next_states, next_totals = {}, {}
            for scenario, state in states.items():
                result = simulator(state, key, crop, node.start, scenario)
                if result.reason:
                    reasons.append({"sequence": [s["crop_id"] for s in stages]+[key], "scenario": scenario, "reason": result.reason})
                    continue
                next_states[scenario] = result.state
                next_totals[scenario] = tuple(None if a is None or b is None else a+b
                                              for a,b in zip(totals[scenario], result.g))
            frequency = len(next_states)/len(scenarios)
            if frequency < survival_threshold:
                continue
            end = node.start + timedelta(days=crop.duration_days + simulator.transition)
            stage = {"crop_id": key, "start": node.start.isoformat(),
                     "harvest": (node.start+timedelta(days=crop.duration_days)).isoformat(), "end": end.isoformat()}
            if partial_days := crop.partial_harvest_days():
                stage["partial_harvest_dates"] = [
                    (node.start + timedelta(days=day)).isoformat() for day in partial_days
                ]
            sequence = [*stages, stage]
            metrics = []
            for scenario, final in next_states.items():
                g = next_totals[scenario]
                eta = compute_liebig_factor(*final[1], crop.K_N, crop.K_P, crop.K_K)[0]
                metrics.append((g[0]/g[3], compute_soil_pareto_metric_f2(initial[2], final[2], eta),
                                None if g[2] is None else 365*g[2]/g[3], g[3]/len(sequence)))
            f = tuple(None if any(v[i] is None for v in metrics) else aggregate(v[i] for v in metrics) for i in range(4))
            yield (Candidate(">".join(s["crop_id"] for s in sequence), f, sequence,
                             list(next_states.values()), frequency),
                   Node(key, crop.botanical_family, tuple(next_states.items()), node.period+1, end),
                   next_states, next_totals, sequence)

    root = (Node(None, None, initial, 0, start), dict.fromkeys(scenarios, initial),
            dict.fromkeys(scenarios, (0.,0.,0.,0.)), [])

    def visit(node, states, totals, stages):
        for candidate, *branch in expand(node, states, totals, stages):
            if len(candidate.stages) == graph.m:
                candidates.append(candidate)
            else:
                visit(*branch)

    if mode == "exact" or len(graph.catalog) ** graph.m <= 300:
        visit(*root)
    else:
        layer = [(None, *root)]
        for period in range(graph.m):
            layer = [child for _, *branch in layer for child in expand(*branch)]
            if period + 1 < graph.m:
                continuing = [item for item in layer if any(graph.successors(item[1]))]
                layer = retain_prefixes(continuing or layer)
        candidates = [candidate for candidate, *_ in layer]
    return candidates if candidates else NoViableRotations(reasons)

# TODO NAMOA*: cotas inferiores optimistas por etapa (también para costos negativos).
# Podar por dominancia solo con estados heredados equivalentes y mismos escenarios;
# dominancia del costo acumulado por sí sola no garantiza dominancia futura.
