from datetime import date, timedelta
import io
import json
import math
from unittest import TestCase
from unittest.mock import patch
import numpy as np

from backend.core.climate_generator import (
    GeneradorClimaticoMontecarlo,
    mc_day_to_weather,
    select_representative_scenario_index,
)
from backend.core.physics import saturation_vapor_pressure
from backend.main import AgroPhasorHandler
from backend.models.crop_parameters import CROP_CATALOG
from backend.services import climate_service, parcel_edo1, rotation_service
from backend.services.coupled_model import advance_day, avanzar_un_dia_celda
from backend.services.plan_service import replay_plan


def _build_mock_nasa_daily_payload(start: date, end: date, *, base_temp: float = 14.0, lag_days: int = 3):
    """Build a realistic 3-year NASA POWER daily JSON payload with seasonal harmonics and trailing lag."""
    rng = np.random.default_rng(123)
    total = (end - start).days + 1
    t2m, t2mdew, rh2m, rad, precip = {}, {}, {}, {}, {}
    for offset in range(total):
        day = start + timedelta(days=offset)
        key = day.strftime("%Y%m%d")
        if offset >= total - lag_days:
            t2m[key] = -999.0
            t2mdew[key] = -999.0
            rh2m[key] = -999.0
            rad[key] = -999.0
            precip[key] = -999.0
            continue
        phase = 2.0 * math.pi * offset / 365.25
        temp = base_temp + 3.0 * math.cos(phase) + float(rng.normal(0.0, 0.8))
        dew = temp - 4.0 - 1.5 * math.sin(phase)
        es = saturation_vapor_pressure(temp)
        ea = saturation_vapor_pressure(min(temp, dew))
        rh = max(15.0, min(98.0, 100.0 * ea / es))
        solar_mj = max(8.0, 19.0 + 3.5 * math.cos(phase) + float(rng.normal(0.0, 1.5)))
        wet_prob = 0.55 + 0.30 * math.cos(phase)
        rain = float(rng.gamma(1.6, 3.0)) if rng.random() < wet_prob else 0.0
        t2m[key] = round(temp, 2)
        t2mdew[key] = round(dew, 2)
        rh2m[key] = round(rh, 2)
        rad[key] = round(solar_mj, 2)
        precip[key] = round(rain, 2)
    return {
        "header": {"fill_value": -999.0},
        "parameters": {"ALLSKY_SFC_SW_DWN": {"units": "MJ/m^2/day"}},
        "properties": {
            "parameter": {
                "T2M": t2m,
                "T2MDEW": t2mdew,
                "RH2M": rh2m,
                "ALLSKY_SFC_SW_DWN": rad,
                "PRECTOTCORR": precip,
            }
        },
    }


class TestGeneradorClimaticoMontecarlo(TestCase):
    def test_seasonal_fit_splice_and_whatif_perturbations(self):
        rng = np.random.default_rng(7)
        t_hist = np.arange(1095, dtype=float)
        omega = 2.0 * np.pi / 365.25
        T_hist = 15.0 + 4.0 * np.cos(omega * t_hist) + rng.normal(0.0, 0.7, size=len(t_hist))
        Tdew_hist = T_hist - 4.0
        rad_hist = 220.0 + 50.0 * np.cos(omega * t_hist)
        prob_rain = 0.45 + 0.35 * np.cos(omega * t_hist)
        P_hist = (rng.random(len(t_hist)) < prob_rain) * rng.gamma(2.0, 3.5, size=len(t_hist))

        gen = GeneradorClimaticoMontecarlo(n_armonicos=2)
        gen.entrenar(t_hist, T_hist, Tdew_hist, rad_hist, P_hist)

        t_fut = np.arange(1095, 1095 + 180, dtype=float)
        base_a = gen.generar_escenarios(t_fut, n_mc=15, seed=99)
        base_b = gen.generar_escenarios(t_fut, n_mc=15, seed=99)
        self.assertEqual(base_a, base_b)
        self.assertEqual(len(base_a), 15)
        self.assertEqual(len(base_a[0]), 180)

        # Verify 7-day seamless splice on day 0 and day 10
        sc0 = base_a[0]
        expected_day0_tsoil = float(np.mean(np.concatenate([T_hist[-6:], [sc0[0]["T_NASA"]]])))
        expected_day10_tsoil = float(np.mean([sc0[i]["T_NASA"] for i in range(4, 11)]))
        self.assertAlmostEqual(sc0[0]["T_soil_7d"], expected_day0_tsoil, places=6)
        self.assertAlmostEqual(sc0[10]["T_soil_7d"], expected_day10_tsoil, places=6)

        # Verify physical bounds (e_a <= e_s(T), f_rad >= 0, P0 >= 0)
        for day in sc0:
            self.assertLessEqual(day["e_a_kPa"], saturation_vapor_pressure(day["T_NASA"]) + 1e-9)
            self.assertGreaterEqual(day["f_rad_W_m2"], 0.0)
            self.assertGreaterEqual(day["P0_mm"], 0.0)

        # Verify what-if shifts
        warmer_dry = gen.generar_escenarios(t_fut, n_mc=15, delta_T_whatif=3.0, delta_P_pct_whatif=-100.0, seed=99)
        for d_base, d_mod in zip(base_a[0], warmer_dry[0]):
            self.assertAlmostEqual(d_mod["T_NASA"], d_base["T_NASA"] + 3.0, places=6)
            self.assertEqual(d_mod["P0_mm"], 0.0)

        # Verify direct compatibility with avanzar_un_dia_celda & advance_day
        crop = CROP_CATALOG["papa"]
        init_state = (104.0, (100.0, 40.0, 120.0), 400.0, crop.B0_t_ha, ())
        s1, diag1 = avanzar_un_dia_celda(init_state, crop, sc0[0], slope=8.0)
        s2, diag2 = advance_day(init_state, crop, sc0[0], slope=8.0)
        self.assertAlmostEqual(s1[0], s2[0], places=6)
        self.assertAlmostEqual(diag1["canopy"], diag2["canopy"], places=6)

    def test_edge_cases_constant_arid_short_and_untrained(self):
        gen = GeneradorClimaticoMontecarlo()
        with self.assertRaises(RuntimeError):
            gen.generar_escenarios(np.arange(10))

        # Short constant dry series (< 6 days, 0 wet days, zero residual variance)
        t_short = np.array([0.0, 1.0, 2.0, 3.0])
        gen.entrenar(
            t_short,
            np.full(4, 15.0),
            np.full(4, 10.0),
            np.full(4, 200.0),
            np.zeros(4),
        )
        empty = gen.generar_escenarios(np.array([]), n_mc=3)
        self.assertEqual(empty, [[], [], []])

        out = gen.generar_escenarios(np.array([4.0, 5.0]), n_mc=5, seed=1)
        self.assertEqual(len(out), 5)
        for day in out[0]:
            self.assertTrue(all(math.isfinite(v) for v in day.values()))
        self.assertEqual(select_representative_scenario_index(out) in range(5), True)


class TestPhaseAndMonthlyIntegration(TestCase):
    def setUp(self):
        climate_service._cached_historical_climate.cache_clear()
        rotation_service._cached_rotation.cache_clear()

    def test_historical_loader_handles_lag_and_missing_tdew(self):
        today = date(2026, 11, 15)
        payload = _build_mock_nasa_daily_payload(today - timedelta(days=1116), today, lag_days=4)
        # Drop T2MDEW for 5 days so RH2M inversion fallback is exercised
        for day_key in list(payload["properties"]["parameter"]["T2MDEW"].keys())[:5]:
            payload["properties"]["parameter"]["T2MDEW"][day_key] = -999.0

        with patch.object(parcel_edo1, "read_json", return_value=payload):
            hist = climate_service.load_historical_climate(-12.06, -75.21, lookback_days=1095, end_date=today)

        self.assertEqual(hist.end_date, date(2026, 11, 11))
        self.assertEqual(len(hist.dates), 1095)
        self.assertTrue(np.all(np.isfinite(hist.Tdew_hist)))
        self.assertGreater(float(np.mean(hist.rad_wm2_hist)), 100.0)

    def test_replay_plan_uses_montecarlo_across_multi_month_phases(self):
        today = date(2026, 11, 15)
        nasa_hist = _build_mock_nasa_daily_payload(today - timedelta(days=1120), today, base_temp=9.0, lag_days=3)
        hourly = {
            key: {f"20230401{hour:02d}": value for hour in range(24)}
            for key, value in dict(T2M=15.0, RH2M=65.0, ALLSKY_SFC_SW_DWN=150.0).items()
        }
        cell = dict(latitude=-12.06, longitude=-75.21, altitude_m=3200.0, slope_deg=12.0, area_m2=900.0)
        phases = [
            dict(cropId="papa", start="2026-11-15", harvest="2027-03-25"),
            dict(cropId="frijol", start="2027-04-08", harvest="2027-07-07"),
        ]

        with patch.object(parcel_edo1, "read_json", return_value=nasa_hist), patch(
            "backend.services.parcel_edo1.load_power", return_value=(date(2023, 4, 1), hourly, False)
        ):
            res = replay_plan(
                {"cells": [dict(cell)]},
                phases,
                "2027-06-15",
                mc_samples=12,
                seed=42,
            )
            cold_res = replay_plan(
                {"cells": [dict(cell)]},
                phases,
                "2027-06-15",
                mc_samples=12,
                delta_T_whatif=-10.0,
                seed=42,
            )

        self.assertEqual(res["climate_source"], "NASA POWER + Fourier/AR(1)-Gamma Monte Carlo")
        self.assertEqual(res["crop_id"], CROP_CATALOG["frijol"].key)
        self.assertEqual(len(res["phase_forecasts"]), 2)
        self.assertEqual(res["phase_forecasts"][0]["crop_id"], "papa")
        self.assertEqual(res["phase_forecasts"][1]["crop_id"], "frijol")
        for pf in res["phase_forecasts"]:
            self.assertLessEqual(pf["yield_t_ha"]["p10"], pf["yield_t_ha"]["p50"])
            self.assertLessEqual(pf["yield_t_ha"]["p50"], pf["yield_t_ha"]["p90"])
        self.assertGreaterEqual(len(res["monthly_forecast"]), 8)
        self.assertEqual(res["monthly_forecast"][0]["month"], "2026-11")
        self.assertEqual(res["monthly_forecast"][-1]["month"], "2027-07")
        # Transition month 2027-04 should observe both Transition / Fallow and Dry Bean
        april = next(m for m in res["monthly_forecast"] if m["month"] == "2027-04")
        self.assertIn("Transition / Fallow", april["active_crops"])
        self.assertIn("Dry Bean", april["active_crops"])

        # Severe cold what-if scenario must raise frost risk, cool phase climate, and reduce confidence
        self.assertAlmostEqual(
            cold_res["phase_forecasts"][1]["climate"]["temp_mean_c"],
            res["phase_forecasts"][1]["climate"]["temp_mean_c"] - 10.0,
            places=1,
        )
        self.assertLess(cold_res["montecarlo_confidence_pct"], res["montecarlo_confidence_pct"])
        self.assertGreater(cold_res["phase_forecasts"][1]["frost_risk_pct"], res["phase_forecasts"][1]["frost_risk_pct"])

        # Timeline snapshots cover the full rotation from start to final harvest
        snapshots = res.get("timeline_snapshots", [])
        self.assertGreaterEqual(len(snapshots), 10)
        self.assertEqual(snapshots[0]["date"], "2026-11-15")
        self.assertEqual(snapshots[-1]["date"], "2027-07-07")
        self.assertTrue(any(s["phase"] == "transicion" for s in snapshots))
        # Verify terrain color and biomass evolve between phase start and pre-harvest peak
        p1_start = next(s for s in snapshots if s["date"] == "2026-11-15")
        p1_peak = next(s for s in snapshots if s["date"] == "2027-03-24")
        self.assertGreater(p1_peak["lot_mean_biomass_t_ha"], p1_start["lot_mean_biomass_t_ha"])
        self.assertNotEqual(p1_peak["cells"][0]["soil_color_rgb"], p1_start["cells"][0]["soil_color_rgb"])

    def test_rotation_and_climate_forecast_endpoint(self):
        today = date(2026, 11, 15)
        nasa_hist = _build_mock_nasa_daily_payload(today - timedelta(days=1120), today, base_temp=15.0, lag_days=2)
        sent = []

        class MockPostHandler(AgroPhasorHandler):
            def __init__(self, path, payload_dict):
                raw = json.dumps(payload_dict).encode("utf-8")
                self.path = path
                self.headers = {"Content-Length": str(len(raw))}
                self.rfile = io.BytesIO(raw)

            def send_json_response(self, data, status=200):
                sent.append((status, data))

        with patch.object(parcel_edo1, "read_json", return_value=nasa_hist):
            MockPostHandler(
                "/api/v1/clima/predecir",
                {
                    "latitude": -12.06,
                    "longitude": -75.21,
                    "start_date": "2026-12-01",
                    "months": 4,
                    "n_mc": 20,
                    "delta_T_whatif": 1.0,
                    "delta_P_pct_whatif": -15.0,
                    "seed": 11,
                },
            ).do_POST()

            status, body = sent[-1]
            self.assertEqual(status, 200)
            self.assertEqual(body["model"], "GeneradorClimaticoMontecarlo")
            self.assertEqual(len(body["summary"]["monthly"]), 4)
            self.assertEqual(len(body["representative_series"]), 120)
            self.assertIn("T_NASA", body["representative_series"][0])
            self.assertIn("T_soil_7d", body["representative_series"][0])

            # Test /api/v1/parcelas/simulacion with phases and climate what-if options
            geometry = {
                "type": "Polygon",
                "coordinates": [[
                    [-75.21000, -12.06000], [-75.20938, -12.06000],
                    [-75.20938, -12.05948], [-75.21000, -12.05948],
                    [-75.21000, -12.06000],
                ]],
            }
            hourly = {
                key: {f"20231115{hour:02d}": value for hour in range(24)}
                for key, value in dict(T2M=15.0, RH2M=65.0, ALLSKY_SFC_SW_DWN=150.0).items()
            }
            with patch.object(parcel_edo1, "load_power", return_value=(date(2023, 11, 15), hourly, False)), patch.object(
                parcel_edo1, "load_root_wetness", return_value=0.65
            ), patch.object(
                parcel_edo1, "load_elevations", side_effect=lambda pts: [3200.0] * len(pts)
            ):
                MockPostHandler(
                    "/api/v1/parcelas/simulacion",
                    {
                        "geometry": geometry,
                        "crop_id": "papa",
                        "phases": [
                            {"cropId": "papa", "start": "2026-11-15", "harvest": "2027-03-25"},
                            {"cropId": "maiz", "start": "2027-04-08", "harvest": "2027-08-06"},
                        ],
                        "selected_date": "2027-05-01",
                        "mc_samples": 8,
                        "delta_T_whatif": 1.5,
                        "delta_P_pct_whatif": -10.0,
                    },
                ).do_POST()
            sim_status, sim_body = sent[-1]
            self.assertEqual(sim_status, 200)
            self.assertTrue(sim_body["plan_simulation"])
            self.assertEqual(len(sim_body["phase_forecasts"]), 2)
            self.assertGreaterEqual(len(sim_body["monthly_forecast"]), 9)
            self.assertEqual(sim_body["climate_forecast"]["delta_T_whatif"], 1.5)

            # Test rotation service with real Monte Carlo uncertainty calibration
            rot = rotation_service.recommend_rotation(
                {
                    "crop_id": "papa",
                    "crop_count": 2,
                    "start_date": "2026-11-15",
                    "latitude": -12.06,
                    "longitude": -75.21,
                    "region": "Junin",
                    "evaluate_uncertainty": True,
                    "uncertainty_samples": 6,
                }
            )
            self.assertEqual(rot["climate_source"], "NASA POWER + Fourier/AR(1)-Gamma Monte Carlo")
            self.assertIn("Fourier (K=2) + AR(1) + Bernoulli-Gamma", rot["uncertainty_assumptions"])
            self.assertTrue(rot["routes"])
            self.assertIn("confidence_pct", rot["routes"][0]["uncertainty"])
