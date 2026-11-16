from datetime import date, timedelta
from unittest import TestCase
from unittest.mock import patch

from backend.main import rotation_response
from backend.services import rotation_service as service


class TestRotationRecommendation(TestCase):
    def setUp(self):
        self.payload = dict(crop_id="papa", crop_count=3, start_date="2026-11-15",
                            latitude=-12.06, longitude=-75.21, region="Junin")
        climate = {(m, d): (3., 16., 65., 18.) for m in range(1, 13) for d in range(1, 32)}
        climate_patch = patch.object(service, "load_climate", return_value=climate)
        climate_patch.start()
        self.addCleanup(climate_patch.stop)

    def test_fixed_first_crop_and_dates_across_campaigns(self):
        result, status = rotation_response(self.payload)
        self.assertEqual(status, 200)
        self.assertEqual(result["economic_metric"], "revenue")
        stages = result["routes"][0]["stages"]
        self.assertEqual(len(stages), 3)
        self.assertEqual(stages[0]["crop_id"], "papa")
        self.assertEqual(stages[0]["price_pen_kg"], .91)
        self.assertEqual(stages[0]["harvest"], "2027-03-05")
        for previous, following in zip(stages, stages[1:]):
            self.assertNotEqual(previous["crop_id"], following["crop_id"])
            gap = date.fromisoformat(following["start"]) - date.fromisoformat(previous["harvest"])
            self.assertEqual(gap, timedelta(days=14))

    def test_costs_switch_from_revenue_to_margin(self):
        costs = dict(papa=1200, maiz=1000, frijol=900)
        result, status = rotation_response({**self.payload, "costs_pen_ha": costs})
        self.assertEqual(status, 200)
        self.assertEqual(result["economic_metric"], "margin")
        route = result["routes"][0]
        self.assertAlmostEqual(route["margin_pen_ha"],
                               route["revenue_pen_ha"] - sum(costs[s["crop_id"]] for s in route["stages"]))

    def test_missing_prices_with_economics_only(self):
        result, status = rotation_response({**self.payload, "region": "",
            "weights": dict(w1=0, w2=0, w3=100, w4=0)})
        self.assertEqual(status, 200)
        self.assertEqual(result["economic_metric"], "unavailable")
        self.assertEqual(result["routes"], [])

    def test_unknown_crop_does_not_fall_back_to_maize(self):
        result, status = rotation_response({**self.payload, "crop_id": "quinua"})
        self.assertEqual(status, 422)
        self.assertIn("error", result)

    def test_moving_knobs_updates_route_ranking_and_exposes_candidates(self):
        eco_res, status_eco = rotation_response({
            **self.payload,
            "weights": dict(w1=100, w2=0, w3=0, w4=0),
        })
        soil_res, status_soil = rotation_response({
            **self.payload,
            "weights": dict(w1=0, w2=100, w3=0, w4=0),
        })
        profit_res, status_profit = rotation_response({
            **self.payload,
            "weights": dict(w1=0, w2=0, w3=100, w4=0),
        })
        self.assertEqual((status_eco, status_soil, status_profit), (200, 200, 200))
        self.assertEqual(len(eco_res.get("candidates", [])), 4)
        self.assertIn("bounds", eco_res)
        self.assertNotEqual(eco_res["routes"][0]["id"], soil_res["routes"][0]["id"])
        self.assertNotEqual(
            [r["id"] for r in eco_res["routes"]],
            [r["id"] for r in profit_res["routes"]],
        )
