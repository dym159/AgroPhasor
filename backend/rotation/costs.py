"""Adapter for the real simulator; no new physical parameters."""
from dataclasses import dataclass
from datetime import timedelta
from backend.services.coupled_model import advance_day, incorporate_residue
from backend.core.edo4_engine import execute_harvest_event, execute_partial_cut
from backend.core.edo2_engine import compute_soil_limits
from backend.core.edo3_engine import compute_liebig_factor
from backend.core.edo5_engine import compute_soil_pareto_metric_f2


@dataclass(frozen=True)
class PeriodResult:
    state: tuple
    g: tuple
    reason: str | None = None


class PeriodSimulator:
    def __init__(self, scenarios, transition_days, residue_fraction, slope,
                 irrigation, prices, costs, irrigation_cost, drought_days=None):
        self.scenarios = scenarios
        self.transition = transition_days
        self.residue = residue_fraction
        self.slope, self.irrigation = slope, irrigation
        self.prices, self.costs = prices, costs
        self.irrigation_cost, self.drought_days = irrigation_cost, drought_days
        self.cache = {}

    def __call__(self, state: tuple, key: str, crop, start, scenario: str) -> PeriodResult:
        """Memoize by full state, crop, start date, and scenario id."""
        cache_key = (state, key, start, scenario)
        if cache_key not in self.cache:
            self.cache[cache_key] = self._simulate(state, key, crop, start, scenario)
        return self.cache[cache_key]

    def _simulate(self, inherited, key, crop, start, scenario):
        water, npk, depth, residue, history, om = inherited
        om = incorporate_residue(om, residue, depth)
        state = (water, npk, depth, crop.B0_t_ha, history)
        stress, dry = 0., 0
        duration = crop.duration_days
        partial_days = crop.partial_harvest_days()
        harvest = None
        partial_yield = 0.0
        is_multi = getattr(crop, "is_multiple_harvest", False)
        t_start_cut = getattr(crop, "t_harvest_start_days", duration)
        cut_interval = getattr(crop, "harvest_interval_days", 0)
        for offset in range(duration + self.transition):
            growing = offset < duration
            if growing and is_multi and cut_interval > 0 and offset >= t_start_cut and (offset - t_start_cut) % cut_interval == 0:
                cut_y, rem_b = execute_partial_cut(state[3], crop)
                partial_yield += cut_y
                state = (*state[:3], rem_b, state[4])
            elif offset in partial_days:
                cut_mass = state[3] * crop.partial_harvest.fraction
                partial_yield += cut_mass
                state = (*state[:3], state[3] - cut_mass, state[4])
            if offset == duration:
                harvest = execute_harvest_event(state[3], crop, self.residue, partial_yield_accumulated_t_ha=partial_yield)
                state = (*state[:3], harvest.residue_left_t_ha, state[4])
            day = start + timedelta(days=offset)
            weather_key = (2,28) if (day.month,day.day) == (2,29) else (day.month,day.day)
            weather = self.scenarios[scenario].get(weather_key)
            if weather is None:
                month, day_number = weather_key
                raise ValueError(f"Climate scenario '{scenario}' is missing day {month:02d}-{day_number:02d}, required to simulate date {day}.")
            state, diagnostics = advance_day(state, crop, weather, self.slope,
                self.irrigation if growing else 0, growing, om)
            stress += 1-diagnostics["psi"]
            dry = dry+1 if growing and state[0] < compute_soil_limits(crop, depth_mm=state[2]).w_pmp else 0
            reason = ("Lethal thermal threshold" if not diagnostics["viable"] else
                      "Depleted fertile topsoil" if state[2] <= 0 else
                      "Prolonged wilting" if self.drought_days is not None and dry >= self.drought_days else None)
            if reason:
                return PeriodResult((*state, om), (0,0,None,0), reason)
        if harvest is None:
            harvest = execute_harvest_event(state[3], crop, self.residue, partial_yield_accumulated_t_ha=partial_yield)
            state = (*state[:3], harvest.residue_left_t_ha, state[4])
        price, cost = self.prices.get(key), self.costs.get(key)
        economic = None if price is None or cost is None else (
            cost + self.irrigation_cost*self.irrigation*duration
            - (partial_yield + harvest.commercial_yield_t_ha)*price)
        eta = compute_liebig_factor(*state[1], crop.K_N, crop.K_P, crop.K_K)[0]
        soil = compute_soil_pareto_metric_f2(depth, state[2], eta)
        return PeriodResult((*state, om), (stress, soil, economic, duration+self.transition))
