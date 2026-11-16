"""Grafo implícito por capas con fechas encadenadas."""
from dataclasses import dataclass
from datetime import date


MONTH_NAMES = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
               "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


@dataclass(frozen=True)
class Node:
    crop: str | None
    family: str | None
    inherited_state: tuple
    period: int
    start: date


class RotationGraph:
    def __init__(self, catalog: dict, m: int, fixed=None, windows=None, period_dates=None):
        if type(m) is not int or not 2 <= m <= 6:
            raise ValueError("m debe estar entre 2 y 6.")
        if not catalog:
            raise ValueError("Catálogo sin cultivos válidos.")
        self.catalog, self.m = catalog, m
        self.fixed, self.windows = fixed or {}, windows or {}
        self.period_dates = period_dates
        for k, key in self.fixed.items():
            if type(k) is not int or not 0 <= k < m or key not in catalog:
                raise ValueError("Cultivo fijado o periodo inválido (índices desde cero).")
            if k-1 in self.fixed and catalog[key].botanical_family == catalog[self.fixed[k-1]].botanical_family:
                raise ValueError("Cultivos fijados incompatibles: misma familia consecutiva.")
        for key, months in self.windows.items():
            if key not in catalog or not months or any(type(v) is not int or v not in range(1,13) for v in months):
                raise ValueError("Ventana de siembra inválida.")

    def successors(self, node: Node):
        """Solo crea aristas compatibles con familia, fijación y mes."""
        if self.period_dates and node.start != self.period_dates[node.period]:
            return
        keys = [self.fixed[node.period]] if node.period in self.fixed else sorted(self.catalog)
        for key in keys:
            crop = self.catalog[key]
            if crop.botanical_family != node.family and (key not in self.windows or node.start.month in self.windows[key]):
                yield key, crop

    def fixed_window_conflict(self, period, start):
        key = self.fixed.get(period)
        months = self.windows.get(key)
        if months and start.month not in months:
            allowed = ", ".join(MONTH_NAMES[month - 1] for month in months)
            return (f"{self.catalog[key].name} está fuera de su ventana regional de siembra el {start}. "
                    f"Meses de siembra registrados: {allowed}.")
        return None
