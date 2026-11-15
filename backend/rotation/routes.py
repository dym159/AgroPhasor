"""Selección pura sin simulación."""
from math import isfinite

PRESETS = dict(zip(("A1_menor_agua", "A2_mejor_suelo", "A3_equilibrio_agua_suelo",
                    "B_balance", "C1_ganancia_rapida", "C2_mayor_ganancia",
                    "C3_equilibrio_rapidez_ganancia"),
                   ((.7,.1,.1,.1), (.1,.7,.1,.1), (.4,.4,.1,.1), (.25,)*4,
                    (.1,.1,.1,.7), (.1,.1,.7,.1), (.1,.1,.4,.4))))


def validate_weights(w):
    """Pesos finitos, no negativos y suma uno."""
    if len(w) != 4 or any(type(x) not in (int, float) or not isfinite(x) or x < 0 for x in w) or abs(sum(w)-1) > 1e-8:
        raise ValueError("Los cuatro pesos deben ser no negativos y sumar 1.")


def rescale_weights(w, i: int, nuevo: float) -> list[float]:
    """w'_j = w_j (1-nuevo)/(1-w_i); vértice reparte uniformemente."""
    validate_weights(w)
    if type(i) is not int or i not in range(4) or not isfinite(nuevo) or not 0 <= nuevo <= 1:
        raise ValueError("Perilla o valor inválido.")
    return [nuevo if j == i else (1-nuevo)/3 if w[i] == 1 else
            x*(1-nuevo)/(1-w[i]) for j, x in enumerate(w)]


def effective_weights(w, f_hat):
    validate_weights(w)
    active = [all(v[i] is not None for v in f_hat.values()) for i in range(4)]
    weights = [x if active[i] else 0 for i, x in enumerate(w)]
    total = sum(weights)
    if not total:
        return [1/sum(active) if a else 0 for a in active]
    return [x/total for x in weights]


def select_route(pareto, f_hat, w):
    """Argmin de w·f_hat con desempate por identificador."""
    weights = effective_weights(w, f_hat)
    return min(pareto, key=lambda c: (sum(weights[i]*(f_hat[c.id][i] or 0)
                                          for i in range(4)), c.id), default=None)
