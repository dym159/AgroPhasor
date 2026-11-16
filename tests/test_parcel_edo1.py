from datetime import date
import math
from urllib.parse import parse_qs
from unittest.mock import patch
import unittest

from backend.services import parcel_edo1


GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [-75.21000, -12.06000], [-75.20938, -12.06000],
        [-75.20938, -12.05948], [-75.21000, -12.05948],
        [-75.21000, -12.06000],
    ]],
}


class TestParcelEDO1(unittest.TestCase):

    def test_parcel_simulation_clips_grid_and_passes_hourly_data_to_edo1(self):
        def provider(request):
            if isinstance(request, str):
                query = parse_qs(request.split("?")[1])
                day = query["start"][0]
                if query["parameters"] == ["GWETROOT"]:
                    return {"properties": {"parameter": {"GWETROOT": {day: 0.9}}}}
                hourly = {
                    f"{day}{hour:02d}": 17 + 8 * math.cos(hour * math.pi / 12)
                    for hour in range(24)
                }
                return {
                    "header": {"fill_value": -999},
                    "parameters": {"ALLSKY_SFC_SW_DWN": {"units": "W/m^2"}},
                    "properties": {"parameter": {
                        "T2M": hourly,
                        "ALLSKY_SFC_SW_DWN": dict.fromkeys(hourly, 400),
                        "RH2M": dict.fromkeys(hourly, 60),
                        "PRECTOT": dict.fromkeys(hourly, 1.0),
                    }},
                }
            locations = parse_qs(request.data.decode())["locations"][0].split("|")
            return {
                "status": "OK",
                "results": [
                    {"elevation": 3200 + (float(point.split(",")[1]) + 75.21) * 50000}
                    for point in locations
                ],
            }

        with patch.object(parcel_edo1, "read_json", side_effect=provider), patch.object(parcel_edo1, "sleep"):
            result = parcel_edo1.simulate_parcel({"geometry": GEOMETRY, "crop_id": "maiz_amilaceo"})
            self.assertEqual(result["cell_size_m"], 30)
            self.assertEqual(result["crop_id"], "maiz")
            self.assertIn(result["cells_count"], (4, 6))
            self.assertEqual(len(result["timestamps"]), 24)
            self.assertEqual(result["phase"], "cultivo")
            self.assertEqual(result["precipitation_daily_mm"], 24)
            self.assertEqual(result["soil_moisture_source"], "NASA_POWER_GWETROOT")
            for cell in result["cells"]:
                self.assertTrue(0 < cell["area_m2"] <= 900.01)
                self.assertGreater(cell["slope_deg"], 0)
                self.assertAlmostEqual(cell["aspect_deg"], 270, delta=0.5)
                self.assertTrue(-75.21 <= cell["longitude"] <= -75.20938)
                self.assertTrue(-12.06 <= cell["latitude"] <= -12.05948)
                self.assertEqual(len(cell["hourly_canopy_temps"]), 24)
                self.assertEqual(len(cell["hourly_air_temps"]), 24)
                self.assertTrue(cell["shield_enabled"])
                self.assertFalse(cell["rain_exposure_alert"])
                conditions = cell["hourly_environmental_index"]
                self.assertEqual(len(conditions), 24)
                self.assertGreater(len(set(conditions)), 1)
                for comfort, psi in zip(cell["hourly_thermal_comfort"], conditions):
                    self.assertGreaterEqual(psi, 0)
                    self.assertLessEqual(psi, 1)
                    expected = comfort * cell["water_condition_index"] * cell["eta_nutrientes"]
                    self.assertAlmostEqual(psi, expected, delta=0.0002)
                # Verify that ODE 4 and ODE 5 were solved per cell
                self.assertIn("biomass_t_ha", cell)
                self.assertIn("ndvi_satelital", cell)
                self.assertIn("erosion_loss_mm", cell)
                self.assertIn("h_current_mm", cell)
            self.assertGreater(len({cell["mean_canopy_temp"] for cell in result["cells"]}), 1)
            # Verify lot-level aggregates for ODE 4 and ODE 5
            self.assertIn("lot_mean_biomass_t_ha", result)
            self.assertIn("lot_mean_ndvi", result)
            self.assertIn("lot_mean_erosion_loss_mm", result)
            self.assertIn("lot_mean_h_mm", result)
            self.assertIn("erosion_risk_level", result)
            self.assertIn("data_sources", result)

            transition = parcel_edo1.simulate_parcel({
                "geometry": GEOMETRY, "crop_id": "suelo_desnudo_transicion",
                "h_current_mm": 200.0, "h0_mm": 400.0,
            })
            self.assertEqual(transition["phase"], "transicion")
            for cell in transition["cells"]:
                self.assertFalse(cell["shield_enabled"])
                self.assertTrue(cell["rain_exposure_alert"])
                self.assertIsNone(cell["hourly_environmental_index"])
                self.assertEqual(cell["biomass_t_ha"], 0)
                self.assertLess(cell["soil_retention_ratio"], 0.5)
                self.assertGreater(cell["accumulated_erosion_mm"], 200)
                self.assertIn(cell["limiting_nutrient"], ["N", "P", "K"])

    def test_power_rejects_missing_hours(self):
        with patch.object(parcel_edo1, "read_json", return_value={
            "header": {"fill_value": -999},
            "properties": {"parameter": {"T2M": {"2026010100": -999}}},
        }):
            with self.assertRaises(parcel_edo1.ParcelDataError):
                parcel_edo1.load_power(-75.21, -12.06, date(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
