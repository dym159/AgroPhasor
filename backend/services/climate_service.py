"""Historical NASA POWER retrieval and Monte Carlo future climate forecasting."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import math
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
import numpy as np

from backend.core.climate_generator import (
    GeneradorClimaticoMontecarlo,
    dewpoint_from_temp_rh,
    select_representative_scenario_index,
    summarize_climate_scenarios,
)
from backend.services import parcel_edo1

DEFAULT_LOOKBACK_DAYS = 1095


class ClimateUnavailable(RuntimeError):
    """Raised when historical climate data cannot be retrieved or validated."""


@dataclass(frozen=True)
class HistoricalClimateSeries:
    """Contiguous daily historical meteorological series ready for Fourier fitting."""

    latitude: float
    longitude: float
    start_date: date
    end_date: date
    dates: Tuple[date, ...]
    t_hist: np.ndarray
    T_hist: np.ndarray
    Tdew_hist: np.ndarray
    rh_hist: np.ndarray
    rad_wm2_hist: np.ndarray
    rad_mj_hist: np.ndarray
    P_hist: np.ndarray
    source: str
    imputed_days: int = 0


def _radiation_scales(units_raw: str) -> Tuple[float, float]:
    """Return ``(to_mj_m2_day, to_w_m2)`` conversion factors from NASA POWER units."""
    units = units_raw.lower().replace(" ", "").replace("^", "").replace("²", "2")
    if units.startswith("mj"):
        return 1.0, 1.0 / 0.0864
    if units.startswith("kw"):
        return 3.6, 3.6 / 0.0864
    if units in {"w/m2", "wm-2", "w/m^2"}:
        return 0.0864, 1.0
    raise ValueError(f"Unknown radiation unit: {units_raw}")


def _is_valid_value(value: Any, fill_value: float, low: float, high: float) -> Optional[float]:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num) or num == fill_value or not (low <= num <= high):
        return None
    return num


def _interpolate_series(values: List[Optional[float]]) -> np.ndarray:
    """Linearly interpolate isolated None gaps inside a daily series."""
    idx = np.arange(len(values), dtype=float)
    valid = [i for i, v in enumerate(values) if v is not None]
    if not valid:
        raise ValueError("No valid observations available for interpolation.")
    xp = np.array(valid, dtype=float)
    fp = np.array([values[i] for i in valid], dtype=float)
    return np.interp(idx, xp, fp)


def load_historical_climate(
    lat: float,
    lon: float,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    end_date: Optional[date] = None,
) -> HistoricalClimateSeries:
    """Fetch a ~3-year daily NASA POWER series for Fourier + Monte Carlo training."""
    ref_end = end_date or datetime.now(timezone.utc).date()
    return _cached_historical_climate(round(float(lat), 3), round(float(lon), 3), int(lookback_days), ref_end.isoformat())


@lru_cache(maxsize=64)
def _cached_historical_climate(
    lat: float,
    lon: float,
    lookback_days: int,
    ref_end_iso: str,
) -> HistoricalClimateSeries:
    ref_end = date.fromisoformat(ref_end_iso)
    # Include extra buffer days to absorb NASA POWER's multi-day publication lag.
    query_start = ref_end - timedelta(days=lookback_days + 21)
    fields = ("PRECTOTCORR", "T2M", "T2MDEW", "RH2M", "ALLSKY_SFC_SW_DWN")
    params = {
        "parameters": ",".join(fields),
        "community": "AG",
        "format": "JSON",
        "latitude": lat,
        "longitude": lon,
        "start": query_start.strftime("%Y%m%d"),
        "end": ref_end.strftime("%Y%m%d"),
    }
    try:
        response = parcel_edo1.read_json(f"{parcel_edo1.POWER_DAILY_URL}?{urlencode(params)}")
        series = response["properties"]["parameter"]
        fill_value = float(response.get("header", {}).get("fill_value", -999.0))
        rad_units = response["parameters"]["ALLSKY_SFC_SW_DWN"]["units"]
        to_mj, to_wm2 = _radiation_scales(rad_units)

        total_span = (ref_end - query_start).days + 1
        all_days = [query_start + timedelta(days=offset) for offset in range(total_span)]

        parsed_rows: List[Optional[Tuple[date, float, float, float, float, float, float]]] = []
        for day in all_days:
            key = day.strftime("%Y%m%d")
            rain = _is_valid_value(series.get("PRECTOTCORR", {}).get(key), fill_value, 0.0, 2000.0)
            temp = _is_valid_value(series.get("T2M", {}).get(key), fill_value, -90.0, 65.0)
            rad_raw = _is_valid_value(series.get("ALLSKY_SFC_SW_DWN", {}).get(key), fill_value, 0.0, 2000.0)
            rh = _is_valid_value(series.get("RH2M", {}).get(key), fill_value, 0.0, 100.0)
            tdew = _is_valid_value(series.get("T2MDEW", {}).get(key), fill_value, -95.0, 65.0)
            if tdew is None and temp is not None and rh is not None:
                tdew = dewpoint_from_temp_rh(temp, rh)
            if rh is None and temp is not None and tdew is not None:
                es = 0.6108 * math.exp((17.27 * temp) / (temp + 237.3))
                ea = 0.6108 * math.exp((17.27 * min(temp, tdew)) / (min(temp, tdew) + 237.3))
                rh = max(0.0, min(100.0, 100.0 * ea / max(1e-6, es)))

            if None in (rain, temp, rad_raw, tdew, rh):
                parsed_rows.append(None)
            else:
                parsed_rows.append((day, rain, temp, tdew, rh, rad_raw * to_wm2, rad_raw * to_mj))

        valid_indices = [idx for idx, row in enumerate(parsed_rows) if row is not None]
        if len(valid_indices) < 30:
            raise ValueError("Insufficient valid historical climate records.")

        first_idx, last_idx = valid_indices[0], valid_indices[-1]
        trimmed_start = max(first_idx, last_idx - lookback_days + 1)
        window_days = all_days[trimmed_start : last_idx + 1]
        window_rows = parsed_rows[trimmed_start : last_idx + 1]
        missing_count = sum(1 for row in window_rows if row is None)
        if missing_count > 0.20 * len(window_rows):
            raise ValueError("Historical climate window has too many missing days.")

        T_arr = _interpolate_series([row[2] if row else None for row in window_rows])
        Tdew_arr = _interpolate_series([row[3] if row else None for row in window_rows])
        rh_arr = _interpolate_series([row[4] if row else None for row in window_rows])
        rad_wm2_arr = _interpolate_series([row[5] if row else None for row in window_rows])
        rad_mj_arr = _interpolate_series([row[6] if row else None for row in window_rows])
        P_arr = np.array([row[1] if row else 0.0 for row in window_rows], dtype=float)

        return HistoricalClimateSeries(
            latitude=lat,
            longitude=lon,
            start_date=window_days[0],
            end_date=window_days[-1],
            dates=tuple(window_days),
            t_hist=np.arange(len(window_days), dtype=float),
            T_hist=T_arr,
            Tdew_hist=Tdew_arr,
            rh_hist=rh_arr,
            rad_wm2_hist=rad_wm2_arr,
            rad_mj_hist=rad_mj_arr,
            P_hist=P_arr,
            source="NASA POWER Daily AG",
            imputed_days=missing_count,
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise ClimateUnavailable(
            "NASA POWER did not return sufficient historical daily series for climate forecasting."
        ) from exc


def history_from_annual_climate(
    climate_dict: Dict[Tuple[int, int], Tuple[float, ...]],
    lat: float = 0.0,
    lon: float = 0.0,
    ref_year: int = 2023,
    years: int = 3,
) -> HistoricalClimateSeries:
    """Expand a ``(month, day) -> (rain, temp, rh, rad_mj)`` dict into a multi-year training series."""
    start = date(ref_year - years + 1, 1, 1)
    end = date(ref_year, 12, 31)
    total = (end - start).days + 1
    dates: List[date] = []
    rains: List[float] = []
    temps: List[float] = []
    tdews: List[float] = []
    rhs: List[float] = []
    rads_wm2: List[float] = []
    rads_mj: List[float] = []
    for offset in range(total):
        day = start + timedelta(days=offset)
        key = (2, 28) if (day.month, day.day) == (2, 29) else (day.month, day.day)
        rain, temp, rh, rad_mj = climate_dict[key][:4]
        dates.append(day)
        rains.append(float(rain))
        temps.append(float(temp))
        rhs.append(float(rh))
        tdews.append(dewpoint_from_temp_rh(float(temp), float(rh)))
        rads_mj.append(float(rad_mj))
        rads_wm2.append(float(rad_mj) / 0.0864)

    return HistoricalClimateSeries(
        latitude=lat,
        longitude=lon,
        start_date=dates[0],
        end_date=dates[-1],
        dates=tuple(dates),
        t_hist=np.arange(len(dates), dtype=float),
        T_hist=np.array(temps, dtype=float),
        Tdew_hist=np.array(tdews, dtype=float),
        rh_hist=np.array(rhs, dtype=float),
        rad_wm2_hist=np.array(rads_wm2, dtype=float),
        rad_mj_hist=np.array(rads_mj, dtype=float),
        P_hist=np.array(rains, dtype=float),
        source="Annual climatology expansion",
        imputed_days=0,
    )


def predict_climate_scenarios(
    lat: float,
    lon: float,
    start_date: date,
    end_date: date,
    *,
    n_mc: int = 50,
    delta_T_whatif: float = 0.0,
    delta_P_pct_whatif: float = 0.0,
    seed: int = 42,
    n_armonicos: int = 2,
    history_override: Optional[HistoricalClimateSeries] = None,
) -> Dict[str, Any]:
    """Train ``GeneradorClimaticoMontecarlo`` on historical data and project future scenarios."""
    if end_date < start_date:
        raise ValueError("end_date must not precede start_date.")
    history = history_override or load_historical_climate(lat, lon)
    generator = GeneradorClimaticoMontecarlo(n_armonicos=n_armonicos)
    generator.entrenar(
        history.t_hist,
        history.T_hist,
        history.Tdew_hist,
        history.rad_wm2_hist,
        history.P_hist,
    )

    n_days = (end_date - start_date).days + 1
    dates = [start_date + timedelta(days=offset) for offset in range(n_days)]
    t_offset = (start_date - history.start_date).days
    t_futuro = np.arange(t_offset, t_offset + n_days, dtype=float)

    escenarios = generator.generar_escenarios(
        t_futuro,
        n_mc=n_mc,
        delta_T_whatif=delta_T_whatif,
        delta_P_pct_whatif=delta_P_pct_whatif,
        seed=seed,
    )
    rep_index = select_representative_scenario_index(escenarios)
    summary = summarize_climate_scenarios(escenarios, dates)

    return {
        "generator": generator,
        "history": history,
        "dates": dates,
        "t_futuro": t_futuro,
        "escenarios": escenarios,
        "representative_index": rep_index,
        "representative_scenario": escenarios[rep_index],
        "summary": summary,
        "metadata": {
            "model": "GeneradorClimaticoMontecarlo",
            "components": "Fourier OLS + AR(1) residuals + Bernoulli-Gamma precipitation",
            "source": history.source,
            "fitting_window": {
                "start": history.start_date.isoformat(),
                "end": history.end_date.isoformat(),
                "days": len(history.dates),
                "imputed_days": history.imputed_days,
            },
            "forecast_window": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": n_days,
            },
            "n_armonicos": n_armonicos,
            "mc_scenarios": n_mc,
            "representative_scenario_index": rep_index,
            "seed": seed,
            "delta_T_whatif": float(delta_T_whatif),
            "delta_P_pct_whatif": float(delta_P_pct_whatif),
        },
    }
