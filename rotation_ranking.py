"""Select CC-09 routes from candidates already evaluated by a simulator."""

from dataclasses import dataclass
from math import isclose, isfinite


ECONOMIC_LOSS = "economic_loss"
METRICS = ("environmental_risk", "soil_degradation", ECONOMIC_LOSS, "payback_time")
MODES = ("resilience", "balance", "profit")


@dataclass(frozen=True)
class Candidate:
    route_id: str
    # All objectives are minimized. Economic loss is the negative net margin.
    metrics: dict[str, float | None]


@dataclass(frozen=True)
class Ranking:
    compared_metrics: tuple[str, ...]
    pareto: tuple[str, ...]
    # Candidates ordered by score for each mode. None means unavailable.
    by_mode: dict[str, tuple[str, ...] | None]


def dominates(left, right, metrics):
    return (
        all(left.metrics[key] <= right.metrics[key] for key in metrics)
        and any(left.metrics[key] < right.metrics[key] for key in metrics)
    )


def normalize(value, low, high):
    if low == high:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def rank_rotations(
    candidates: list[Candidate],
    bounds: dict[str, tuple[float, float]],
    weights: dict[str, dict[str, float]],
) -> Ranking:
    """Rank feasible rotations using scenario-independent bounds and weights."""
    route_ids = set()
    for candidate in candidates:
        if not candidate.route_id or candidate.route_id in route_ids:
            raise ValueError("Each candidate needs a unique route ID.")
        route_ids.add(candidate.route_id)
        for key in METRICS:
            value = candidate.metrics.get(key)
            if value is None and key == ECONOMIC_LOSS:
                continue
            if value is None or not isfinite(value):
                raise ValueError(f"{candidate.route_id}: invalid metric {key}.")

    for key in METRICS:
        low, high = bounds[key]
        if not isfinite(low) or not isfinite(high) or low > high:
            raise ValueError(f"Invalid normalization bounds for {key}.")

    modes = dict.fromkeys((*MODES, *weights))
    for mode in modes:
        mode_weights = weights[mode]
        if (
            set(mode_weights) != set(METRICS)
            or any(not isfinite(value) or value < 0 for value in mode_weights.values())
            or not isclose(sum(mode_weights.values()), 1.0)
        ):
            raise ValueError(f"Weights for {mode} must be nonnegative and sum to one.")

    has_economics = bool(candidates) and all(
        candidate.metrics.get(ECONOMIC_LOSS) is not None for candidate in candidates
    )
    compared_metrics = tuple(key for key in METRICS if has_economics or key != ECONOMIC_LOSS)
    front = [
        candidate for candidate in candidates
        if not any(dominates(other, candidate, compared_metrics) for other in candidates)
    ]
    normalized = {
        candidate.route_id: {
            key: normalize(candidate.metrics[key], *bounds[key]) for key in compared_metrics
        }
        for candidate in front
    }

    by_mode = {}
    for mode in modes:
        active_weight = sum(weights[mode][key] for key in compared_metrics)
        if (mode == "profit" and not has_economics) or active_weight == 0:
            by_mode[mode] = None
            continue

        scores = {
            route_id: sum(weights[mode][key] * values[key] for key in compared_metrics)
            / active_weight
            for route_id, values in normalized.items()
        }
        by_mode[mode] = tuple(sorted(scores, key=lambda route_id: (scores[route_id], route_id)))

    return Ranking(compared_metrics, tuple(sorted(normalized)), by_mode)
