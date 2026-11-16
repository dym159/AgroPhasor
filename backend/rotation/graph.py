"""Implicit layered graph with chained planting dates."""
from dataclasses import dataclass
from datetime import date


MONTH_NAMES = ("January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December")


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
            raise ValueError("m must be between 2 and 6.")
        if not catalog:
            raise ValueError("Catalog has no valid crops.")
        self.catalog, self.m = catalog, m
        self.fixed, self.windows = fixed or {}, windows or {}
        self.period_dates = period_dates
        for k, key in self.fixed.items():
            if type(k) is not int or not 0 <= k < m or key not in catalog:
                raise ValueError("Invalid fixed crop or period (0-based indices).")
            if k-1 in self.fixed and catalog[key].botanical_family == catalog[self.fixed[k-1]].botanical_family:
                raise ValueError("Incompatible fixed crops: same consecutive botanical family.")
        for key, months in self.windows.items():
            if key not in catalog or not months or any(type(v) is not int or v not in range(1,13) for v in months):
                raise ValueError("Invalid planting window.")

    def successors(self, node: Node):
        """Create only edges compatible with botanical family, fixed crops, and planting month."""
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
            return (f"{self.catalog[key].name} is outside its regional planting window on {start}. "
                    f"Recorded planting months: {allowed}.")
        return None
