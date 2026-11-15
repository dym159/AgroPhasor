from datetime import date
from unittest import TestCase
from unittest.mock import patch
from backend.services import rotation_service as rotation
from backend.services.coupled_model import advance_day
from backend.services.plan_service import replay_plan
from backend.models.crop_parameters import CROP_CATALOG
from backend.core.edo2_engine import compute_soil_limits, relative_stomatal_conductance, solve_edo2_step


class TestPdfIntegration(TestCase):
    def setUp(self):
        rotation._cached_rotation.cache_clear()
        self.climate = {(m, d): (3., 16., 65., 18.) for m in range(1, 13) for d in range(1, 32)}
        self.payload = dict(crop_id="papa", crop_count=2, start_date="2026-11-01",
                            latitude=-12.06, longitude=-75.21, region="Junin")

    def test_changing_weights_reuses_physical_simulation(self):
        with patch.object(rotation, "load_climate", return_value=self.climate):
            with patch.object(rotation, "simulate_segment", wraps=rotation.simulate_segment) as solver:
                rotation.recommend_rotation(self.payload)
                calls = solver.call_count
                result = rotation.recommend_rotation({**self.payload, "weights": dict(w1=50, w2=50, w3=0, w4=0)})
                self.assertEqual(solver.call_count, calls)
                self.assertTrue(result["routes"])

    def test_temperature_boundary_excludes_routes(self):
        cold = {key: (0., -40., 65., 1.) for key in self.climate}
        with patch.object(rotation, "load_climate", return_value=cold):
            result = rotation.recommend_rotation(self.payload)
        self.assertEqual(result["routes"], [])
        self.assertTrue(result["rejected"])

    def test_erosion_reduces_water_capacity_and_bedrock_has_zero_water(self):
        crop = CROP_CATALOG["papa"]
        self.assertEqual(compute_soil_limits(crop, depth_mm=0).w_cc, 0)
        self.assertEqual(relative_stomatal_conductance(0, compute_soil_limits(crop, depth_mm=0)), 0)
        state, _ = advance_day((120, (100, 40, 120), 1, 0, ()), crop, (100, 16, 65, 18), 70)
        self.assertLess(state[2], 1)
        self.assertLessEqual(state[0], state[2] * .30)

    def test_annualized_metrics_and_average_cycle(self):
        with patch.object(rotation, "load_climate", return_value=self.climate):
            result = rotation.recommend_rotation({**self.payload, "costs_pen_ha": dict(papa=100, maiz=100, frijol=100)})
        for route in result["routes"]:
            self.assertAlmostEqual(route["metrics"]["economic_loss"], -route["margin_pen_ha"] * 365 / route["days"])
            self.assertEqual(route["metrics"]["payback_time"], route["days"] / 2)
            self.assertGreaterEqual(route["metrics"]["soil_degradation"], .5 * (1-route["final_nutrient_index"]))

    def test_plan_date_replays_crop_then_harvest(self):
        import copy
        cell = dict(latitude=-12.06, longitude=-75.21, altitude_m=3200, slope_deg=20, area_m2=900)
        phases = [dict(cropId="papa", start="2026-11-01", harvest="2026-11-03")]
        hourly = {key: {f"20231103{hour:02d}": value for hour in range(24)}
                  for key, value in dict(T2M=16., RH2M=65., ALLSKY_SFC_SW_DWN=100.).items()}
        with patch.object(rotation, "load_climate", return_value=self.climate), patch(
            "backend.services.parcel_edo1.load_power", return_value=(date(2023,11,3), hourly, False)):
            growing = replay_plan({"cells": [copy.deepcopy(cell)]}, phases, "2026-11-01")
            harvested = replay_plan({"cells": [copy.deepcopy(cell)]}, phases, "2026-11-03")
        self.assertTrue(growing["cells"][0]["shield_enabled"])
        self.assertFalse(harvested["cells"][0]["shield_enabled"])
        self.assertEqual(harvested["date"], "2026-11-03")
        self.assertNotEqual(growing["cells"][0]["soil_water_mm"], harvested["cells"][0]["soil_water_mm"])
    def test_spatial_baseline_and_uncertainty(self):
        phases = [
            dict(cropId="papa", start="2026-11-01", harvest="2027-03-11"),
            dict(cropId="frijol", start="2027-03-25", harvest="2027-06-23"),
        ]
        with patch.object(rotation, "load_climate", return_value=self.climate):
            result = rotation.recommend_rotation({
                **self.payload, "baseline_phases": phases, "evaluate_uncertainty": True,
                "terrain_cells": [dict(area_m2=900, altitude_m=3200, slope_deg=10),
                                  dict(area_m2=450, altitude_m=3220, slope_deg=20)],
            })
        self.assertEqual(result["cells_count"], 2)
        self.assertIsNotNone(result["baseline"])
        self.assertEqual(result["baseline"]["stages"][1]["start"], "2027-03-25")
        for route in result["routes"]:
            self.assertEqual(route["uncertainty"]["samples"], 20)
            self.assertLessEqual(route["uncertainty"]["viable_samples"], 20)

    def test_exponential_water_step_conserves_reported_balance(self):
        crop = CROP_CATALOG["papa"]
        result = solve_edo2_step(80, 3, 20, 60, 30, crop, depth_mm=400)
        balance = 80 + result.infiltration_mm - result.etc_mm - result.drainage_mm - result.runoff_mm
        self.assertAlmostEqual(result.soil_water_mm, balance, delta=.01)
