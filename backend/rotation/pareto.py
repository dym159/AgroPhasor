"""Objetivos a minimizar; economía ausente se excluye globalmente."""
from dataclasses import dataclass, field


@dataclass
class Candidate:
    id: str
    f: tuple[float | None, ...]
    stages: list = field(default_factory=list)
    final_states: list = field(default_factory=list)
    survival_frequency: float = 1.0
    f_hat: tuple = ()


def normalize(candidates: list[Candidate]) -> list[Candidate]:
    """Min-max por columna; constantes a cero y ausentes a None."""
    active = [all(c.f[i] is not None for c in candidates) for i in range(4)]
    bounds = [(min(c.f[i] for c in candidates), max(c.f[i] for c in candidates))
              if active[i] and candidates else (0, 0) for i in range(4)]
    for c in candidates:
        c.f_hat = tuple(None if not active[i] else
                        (c.f[i] - lo) / (hi - lo) if hi != lo else 0.
                        for i, (lo, hi) in enumerate(bounds))
    return candidates


def pareto_front(candidates: list[Candidate]) -> list[Candidate]:
    """Dominancia estricta en al menos un objetivo activo; orden por id."""
    active = [i for i in range(4) if all(c.f[i] is not None for c in candidates)]
    def dominates(a, b):
        return (all(a.f[i] <= b.f[i] for i in active)
                and any(a.f[i] < b.f[i] for i in active))
    return sorted([c for c in candidates if not any(dominates(d, c) for d in candidates)],
                  key=lambda c: c.id)
