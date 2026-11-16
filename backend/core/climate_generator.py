"""Stochastic climate generator for AgroPhasor multi-month forecasting.

Fits truncated Fourier harmonic series via ordinary least squares to historical
daily NASA POWER / GPM records and generates Monte Carlo future trajectories
using AR(1) autocorrelated residuals for continuous meteorological variables and
a seasonal Bernoulli-Gamma occurrence/intensity model for precipitation.
"""

from datetime import date
import math
from typing import Any, Dict, List, Sequence, Tuple
import numpy as np


def dewpoint_from_temp_rh(temp_c: float, rh_pct: float) -> float:
    """Invert the Tetens relation to estimate dew-point temperature [°C]."""
    rh = max(1e-3, min(100.0, float(rh_pct)))
    gamma = math.log(rh / 100.0) + (17.27 * float(temp_c)) / (float(temp_c) + 237.3)
    denom = max(1e-6, 17.27 - gamma)
    return (237.3 * gamma) / denom


def vapor_pressure_to_rh(temp_c: float, e_a_kpa: float) -> float:
    """Convert actual vapor pressure e_a [kPa] at temperature T [°C] to RH [%]."""
    es_kpa = 0.6108 * math.exp((17.27 * float(temp_c)) / (float(temp_c) + 237.3))
    if es_kpa <= 1e-9:
        return 0.0
    return max(0.0, min(100.0, 100.0 * float(e_a_kpa) / es_kpa))


def mc_day_to_weather(
    clima_dia: Dict[str, float],
    altitude_offset_c: float = 0.0,
) -> Tuple[float, float, float, float, float]:
    """Convert one Monte Carlo daily dict into coupled_model weather units.

    Returns ``(rain_mm, temp_c, rh_pct, radiation_mj_m2_day, t_soil_7d_c)``.
    """
    temp_c = float(clima_dia["T_NASA"]) + float(altitude_offset_c)
    t_soil_ref = float(clima_dia.get("T_soil_7d", clima_dia["T_NASA"]))
    t_soil_7d_c = t_soil_ref + float(altitude_offset_c)
    rh_pct = vapor_pressure_to_rh(temp_c, float(clima_dia["e_a_kPa"]))
    rad_mj_m2_day = max(0.0, float(clima_dia["f_rad_W_m2"]) * 0.0864)
    rain_mm = max(0.0, float(clima_dia["P0_mm"]))
    return rain_mm, temp_c, rh_pct, rad_mj_m2_day, t_soil_7d_c


class GeneradorClimaticoMontecarlo:
    """
    Fits Fourier harmonic series to historical data (NASA POWER / GPM) and generates
    N_MC stochastic future scenarios (AR(1) + Bernoulli-Gamma) compatible
    with the AgroPhasor analytical engine.
    """

    def __init__(self, n_armonicos: int = 2, periodo_dias: float = 365.25):
        if n_armonicos < 0:
            raise ValueError("n_armonicos must be non-negative.")
        if periodo_dias <= 0:
            raise ValueError("periodo_dias must be positive.")
        self.K = int(n_armonicos)
        self.periodo_dias = float(periodo_dias)
        self.omega0 = 2.0 * np.pi / self.periodo_dias
        self.modelos_continuos: Dict[str, Dict[str, Any]] = {}
        self.modelo_lluvia: Dict[str, Any] = {}
        self.historial_T_reciente: np.ndarray | None = None

    def _matriz_diseno_fourier(self, t: np.ndarray) -> np.ndarray:
        t_arr = np.asarray(t, dtype=float)
        cols = [np.ones_like(t_arr, dtype=float)]
        for k in range(1, self.K + 1):
            cols.append(np.cos(k * self.omega0 * t_arr))
            cols.append(np.sin(k * self.omega0 * t_arr))
        return np.column_stack(cols)

    def _ajustar_fourier_ols(self, t: np.ndarray, y: np.ndarray) -> np.ndarray:
        Phi = self._matriz_diseno_fourier(t)
        beta, _, _, _ = np.linalg.lstsq(Phi, y, rcond=None)
        return beta

    def entrenar(
        self,
        t_hist: np.ndarray,
        T_hist: np.ndarray,
        Tdew_hist: np.ndarray,
        rad_hist: np.ndarray,
        P_hist: np.ndarray,
    ) -> None:
        """
        Fits seasonal harmonics and residual statistical parameters.
        t_hist: array of days (e.g., 0, 1, ..., 1094)
        T_hist, Tdew_hist: °C | rad_hist: W/m2 | P_hist: mm/day
        """
        t_arr = np.asarray(t_hist, dtype=float)
        T_arr = np.asarray(T_hist, dtype=float)
        Tdew_arr = np.asarray(Tdew_hist, dtype=float)
        rad_arr = np.asarray(rad_hist, dtype=float)
        P_arr = np.asarray(P_hist, dtype=float)

        n = len(t_arr)
        if n == 0:
            raise ValueError("Historical climate arrays cannot be empty.")
        if not (len(T_arr) == len(Tdew_arr) == len(rad_arr) == len(P_arr) == n):
            raise ValueError("All historical climate arrays must have the same length.")

        if n >= 6:
            self.historial_T_reciente = T_arr[-6:].copy()
        else:
            # Pad short synthetic series on the left so the 7-day rolling splice always works.
            self.historial_T_reciente = np.pad(T_arr, (6 - n, 0), mode="edge")

        # 1. Fit continuous variables (T2M, T2MDEW, ALLSKY_SFC_SW_DWN)
        Phi_hist = self._matriz_diseno_fourier(t_arr)
        for nombre, serie in [("T_NASA", T_arr), ("T_dew", Tdew_arr), ("f_rad", rad_arr)]:
            beta = self._ajustar_fourier_ols(t_arr, serie)
            mu_fit = Phi_hist @ beta
            res = serie - mu_fit
            sigma = float(np.std(res, ddof=1)) if n > 1 else 0.0
            if len(res) > 2 and np.std(res[:-1]) > 1e-12 and np.std(res[1:]) > 1e-12:
                rho = float(np.corrcoef(res[:-1], res[1:])[0, 1])
                if not np.isfinite(rho):
                    rho = 0.0
            else:
                rho = 0.0
            rho = float(np.clip(rho, 0.0, 0.90))
            self.modelos_continuos[nombre] = {"beta": beta, "sigma": sigma, "rho": rho}

        # 2. Fit intermittent rainfall (seasonal Bernoulli-Gamma)
        es_dia_lluvia = (P_arr > 0.1).astype(float)
        beta_prob = self._ajustar_fourier_ols(t_arr, es_dia_lluvia)

        mask_humedo = P_arr > 0.1
        if int(np.sum(mask_humedo)) > 10:
            t_wet = t_arr[mask_humedo]
            P_wet = P_arr[mask_humedo]
            beta_int = self._ajustar_fourier_ols(t_wet, P_wet)
            mu_wet_fit = np.maximum(1.0, self._matriz_diseno_fourier(t_wet) @ beta_int)
            ratio_var = float(np.var(P_wet / mu_wet_fit, ddof=1))
            if not np.isfinite(ratio_var):
                ratio_var = 1.0
            alpha_gamma = float(np.clip(1.0 / max(ratio_var, 1e-3), 0.4, 5.0))
        else:
            beta_int = np.zeros(2 * self.K + 1, dtype=float)
            beta_int[0] = 5.0
            alpha_gamma = 1.0

        self.modelo_lluvia = {
            "beta_prob": beta_prob,
            "beta_int": beta_int,
            "alpha_gamma": alpha_gamma,
        }

    def generar_escenarios(
        self,
        t_futuro: np.ndarray,
        n_mc: int = 100,
        delta_T_whatif: float = 0.0,
        delta_P_pct_whatif: float = 0.0,
        seed: int = 42,
    ) -> list:
        """
        Generates n_mc future realizations. Each element of the returned list is a
        daily series of dictionaries ready to be passed to avanzar_un_dia_celda().
        """
        if not self.modelos_continuos or self.historial_T_reciente is None:
            raise RuntimeError("The generator must be trained before generating scenarios.")
        if n_mc < 1:
            raise ValueError("n_mc must be at least 1.")

        t_fut = np.asarray(t_futuro, dtype=float)
        N_dias = len(t_fut)
        if N_dias == 0:
            return [[] for _ in range(n_mc)]

        rng = np.random.default_rng(seed)
        Phi_fut = self._matriz_diseno_fourier(t_fut)

        mu_T = Phi_fut @ self.modelos_continuos["T_NASA"]["beta"]
        mu_Tdew = Phi_fut @ self.modelos_continuos["T_dew"]["beta"]
        mu_rad = Phi_fut @ self.modelos_continuos["f_rad"]["beta"]

        prob_lluvia = np.clip(Phi_fut @ self.modelo_lluvia["beta_prob"], 0.01, 0.95)
        mu_intensidad = np.maximum(0.5, Phi_fut @ self.modelo_lluvia["beta_int"])
        alpha_g = self.modelo_lluvia["alpha_gamma"]

        escenarios: List[List[Dict[str, float]]] = []
        for _ in range(n_mc):
            eta_T = np.zeros(N_dias, dtype=float)
            eta_Tdew = np.zeros(N_dias, dtype=float)
            eta_rad = np.zeros(N_dias, dtype=float)

            for m_key, eta_arr in [("T_NASA", eta_T), ("T_dew", eta_Tdew), ("f_rad", eta_rad)]:
                rho = self.modelos_continuos[m_key]["rho"]
                sig = self.modelos_continuos[m_key]["sigma"]
                innov = rng.normal(0.0, sig * np.sqrt(1.0 - rho**2), size=N_dias)
                for d in range(N_dias):
                    eta_arr[d] = (rho * eta_arr[d - 1] if d > 0 else 0.0) + innov[d]

            T_sim = mu_T + eta_T + delta_T_whatif
            Tdew_sim = np.minimum(T_sim, mu_Tdew + eta_Tdew + delta_T_whatif)
            ea_sim = 0.6108 * np.exp((17.27 * Tdew_sim) / (np.maximum(-200.0, Tdew_sim) + 237.3))
            rad_sim = np.maximum(0.0, mu_rad + eta_rad)

            llueve = rng.binomial(1, prob_lluvia)
            lamina = rng.gamma(shape=alpha_g, scale=mu_intensidad / alpha_g)
            P_sim = llueve * lamina * max(0.0, 1.0 + delta_P_pct_whatif / 100.0)

            # Seamless 7-day rolling splice for T_soil_7d(t)
            T_extendida = np.concatenate([self.historial_T_reciente, T_sim])
            T_soil_7d = np.array([np.mean(T_extendida[d : d + 7]) for d in range(N_dias)])

            serie_dias = [
                {
                    "T_NASA": float(T_sim[d]),
                    "e_a_kPa": float(ea_sim[d]),
                    "f_rad_W_m2": float(rad_sim[d]),
                    "P0_mm": float(P_sim[d]),
                    "T_soil_7d": float(T_soil_7d[d]),
                }
                for d in range(N_dias)
            ]
            escenarios.append(serie_dias)

        return escenarios


def select_representative_scenario_index(escenarios: List[List[Dict[str, float]]]) -> int:
    """Select the Monte Carlo realization closest to ensemble medians.

    Using a single medoid realization preserves realistic dry/wet rainfall
    intermittency and AR(1) persistence instead of flattening rain into daily drizzle.
    """
    if not escenarios or not escenarios[0]:
        return 0
    if len(escenarios) == 1:
        return 0

    temps = np.array([np.mean([d["T_NASA"] for d in sc]) for sc in escenarios], dtype=float)
    rains = np.array([np.sum([d["P0_mm"] for d in sc]) for sc in escenarios], dtype=float)
    rads = np.array([np.mean([d["f_rad_W_m2"] for d in sc]) for sc in escenarios], dtype=float)

    distance = np.zeros(len(escenarios), dtype=float)
    for vec in (temps, rains, rads):
        med = float(np.median(vec))
        scale = float(np.std(vec))
        if scale > 1e-9:
            distance += ((vec - med) / scale) ** 2
    return int(np.argmin(distance))


def summarize_climate_scenarios(
    escenarios: List[List[Dict[str, float]]],
    dates: Sequence[date],
) -> Dict[str, Any]:
    """Summarize daily Monte Carlo scenarios into overall and monthly p10/p50/p90 bands."""
    if not escenarios or not dates:
        return {"overall": {}, "monthly": []}

    n_mc = len(escenarios)
    n_days = len(dates)
    T_mat = np.array([[sc[d]["T_NASA"] for d in range(n_days)] for sc in escenarios], dtype=float)
    P_mat = np.array([[sc[d]["P0_mm"] for d in range(n_days)] for sc in escenarios], dtype=float)
    R_mat = np.array([[sc[d]["f_rad_W_m2"] for d in range(n_days)] for sc in escenarios], dtype=float)

    sc_temp_means = np.mean(T_mat, axis=1)
    sc_precip_totals = np.sum(P_mat, axis=1)
    sc_rad_means = np.mean(R_mat, axis=1)
    sc_rainy_days = np.sum(P_mat > 0.1, axis=1)

    overall = {
        "days": n_days,
        "mc_scenarios": n_mc,
        "temp_p10_c": round(float(np.percentile(sc_temp_means, 10)), 2),
        "temp_p50_c": round(float(np.percentile(sc_temp_means, 50)), 2),
        "temp_p90_c": round(float(np.percentile(sc_temp_means, 90)), 2),
        "precip_total_p10_mm": round(float(np.percentile(sc_precip_totals, 10)), 1),
        "precip_total_p50_mm": round(float(np.percentile(sc_precip_totals, 50)), 1),
        "precip_total_p90_mm": round(float(np.percentile(sc_precip_totals, 90)), 1),
        "rad_p50_wm2": round(float(np.percentile(sc_rad_means, 50)), 1),
        "rainy_days_mean": round(float(np.mean(sc_rainy_days)), 1),
    }

    month_buckets: Dict[str, List[int]] = {}
    for idx, day in enumerate(dates):
        month_buckets.setdefault(f"{day.year:04d}-{day.month:02d}", []).append(idx)

    monthly: List[Dict[str, Any]] = []
    for month_key, indices in month_buckets.items():
        m_T = np.mean(T_mat[:, indices], axis=1)
        m_P = np.sum(P_mat[:, indices], axis=1)
        m_R = np.mean(R_mat[:, indices], axis=1)
        m_wet = np.sum(P_mat[:, indices] > 0.1, axis=1)
        monthly.append({
            "month": month_key,
            "days": len(indices),
            "temp_p10_c": round(float(np.percentile(m_T, 10)), 2),
            "temp_p50_c": round(float(np.percentile(m_T, 50)), 2),
            "temp_p90_c": round(float(np.percentile(m_T, 90)), 2),
            "precip_p10_mm": round(float(np.percentile(m_P, 10)), 1),
            "precip_p50_mm": round(float(np.percentile(m_P, 50)), 1),
            "precip_p90_mm": round(float(np.percentile(m_P, 90)), 1),
            "rad_p50_wm2": round(float(np.percentile(m_R, 50)), 1),
            "rainy_days_mean": round(float(np.mean(m_wet)), 1),
        })

    return {"overall": overall, "monthly": monthly}
