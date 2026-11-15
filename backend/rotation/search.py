"""DFS exacta. NAMOA* queda pendiente hasta justificar sus cotas."""
from dataclasses import dataclass
from datetime import timedelta
from statistics import mean
from backend.core.edo3_engine import compute_liebig_factor
from backend.core.edo5_engine import compute_soil_pareto_metric_f2
from .graph import Node
from .pareto import Candidate


@dataclass
class NoViableRotations:
    reasons: list
    status: str = "sin rotaciones viables"


def search(graph, simulator, initial: tuple, start, scenarios: list[str],
           survival_threshold: float = 1., aggregation: str = "mean", mode: str = "exact"):
    """Propaga estados por escenario; frecuencia sobre todos los escenarios probados."""
    if mode != "exact":
        raise ValueError("astar pendiente: use exact.")
    if not scenarios or len(set(scenarios)) != len(scenarios) or not 0 < survival_threshold <= 1 or aggregation not in ("mean", "worst"):
        raise ValueError("Escenarios, agregación o umbral inválidos.")
    candidates, reasons = [], []
    aggregate = mean if aggregation == "mean" else max

    def visit(node, states, totals, stages):
        edges = list(graph.successors(node))
        if not edges:
            reasons.append({"sequence": [s["crop_id"] for s in stages], "reason": "Familia, ventana de siembra o cultivo fijado incompatible"})
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
            sequence = [*stages, {"crop_id": key, "start": node.start.isoformat(),
                        "harvest": (node.start+timedelta(days=crop.duration_days)).isoformat(), "end": end.isoformat()}]
            if node.period+1 < graph.m:
                visit(Node(key, crop.botanical_family, tuple(next_states.items()), node.period+1, end), next_states, next_totals, sequence)
                continue
            metrics = []
            for scenario, final in next_states.items():
                g = next_totals[scenario]
                eta = compute_liebig_factor(*final[1], crop.K_N, crop.K_P, crop.K_K)[0]
                metrics.append((g[0]/g[3], compute_soil_pareto_metric_f2(initial[2], final[2], eta),
                                None if g[2] is None else 365*g[2]/g[3], g[3]/graph.m))
            f = tuple(None if any(v[i] is None for v in metrics) else aggregate(v[i] for v in metrics) for i in range(4))
            candidates.append(Candidate(">".join(s["crop_id"] for s in sequence), f, sequence,
                                        list(next_states.values()), frequency))
    visit(Node(None, None, initial, 0, start), dict.fromkeys(scenarios, initial),
          dict.fromkeys(scenarios, (0.,0.,0.,0.)), [])
    return candidates if candidates else NoViableRotations(reasons)

# TODO NAMOA*: cotas inferiores optimistas por etapa (también para costos negativos).
# Podar por dominancia solo con estados heredados equivalentes y mismos escenarios;
# dominancia del costo acumulado por sí sola no garantiza dominancia futura.
