from datetime import date
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
                day = parse_qs(request.split("?")[1])["start"][0]
                return {
                    "header": {"fill_value": -999},
                    "parameters": {"ALLSKY_SFC_SW_DWN": {"units": "W/m^2"}},
                    "properties": {"parameter": {
                        key: {f"{day}{hour:02d}": value for hour in range(24)}
                        for key, value in zip(parcel_edo1.POWER_PARAMETERS, [15, 400, 60])
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

        with patch.object(parcel_edo1, "read_json", side_effect=provider):
            result = parcel_edo1.simulate_parcel({"geometry": GEOMETRY, "crop_id": "maiz_amilaceo"})
            self.assertEqual(result["cell_size_m"], 30)
            self.assertEqual(result["crop_id"], "maiz")
            self.assertIn(result["cells_count"], (4, 6))
            self.assertEqual(len(result["timestamps"]), 24)
            for cell in result["cells"]:
                self.assertTrue(0 < cell["area_m2"] <= 900.01)
                self.assertGreater(cell["slope_deg"], 0)
                self.assertAlmostEqual(cell["aspect_deg"], 270, delta=0.5)
                self.assertTrue(-75.21 <= cell["longitude"] <= -75.20938)
                self.assertTrue(-12.06 <= cell["latitude"] <= -12.05948)
                self.assertEqual(len(cell["hourly_canopy_temps"]), 24)
                # Verifica que EDO 4 y EDO 5 se hayan resuelto por celda
                self.assertIn("biomass_t_ha", cell)
                self.assertIn("ndvi_satelital", cell)
                self.assertIn("erosion_loss_mm", cell)
                self.assertIn("h_current_mm", cell)
            self.assertGreater(len({cell["mean_canopy_temp"] for cell in result["cells"]}), 1)
            # Verifica agregados de lote para EDO 4 y EDO 5
            self.assertIn("lot_mean_biomass_t_ha", result)
            self.assertIn("lot_mean_ndvi", result)
            self.assertIn("lot_mean_erosion_loss_mm", result)
            self.assertIn("lot_mean_h_mm", result)
            self.assertIn("erosion_risk_level", result)
            self.assertIn("data_sources", result)

    def test_power_rejects_missing_hours(self):
        with patch.object(parcel_edo1, "read_json", return_value={
            "header": {"fill_value": -999},
            "properties": {"parameter": {"T2M": {"2026010100": -999}}},
        }):
            with self.assertRaises(parcel_edo1.ParcelDataError):
                parcel_edo1.load_power(-75.21, -12.06, date(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
