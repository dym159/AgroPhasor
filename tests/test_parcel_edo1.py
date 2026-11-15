from datetime import date
from urllib.parse import parse_qs

import pytest

from backend.services import parcel_edo1


GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[
        [-75.21000, -12.06000], [-75.20938, -12.06000],
        [-75.20938, -12.05948], [-75.21000, -12.05948],
        [-75.21000, -12.06000],
    ]],
}


def test_parcel_simulation_clips_grid_and_passes_hourly_data_to_edo1(monkeypatch):
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

    monkeypatch.setattr(parcel_edo1, "read_json", provider)
    result = parcel_edo1.simulate_parcel({"geometry": GEOMETRY, "crop_id": "maiz_amilaceo"})
    assert result["cell_size_m"] == 30
    assert result["crop_id"] == "maiz"
    assert result["cells_count"] == 6
    assert len(result["timestamps"]) == 24
    assert any(cell["area_m2"] < 899 for cell in result["cells"])
    for cell in result["cells"]:
        assert 0 < cell["area_m2"] <= 900.01
        assert cell["slope_deg"] > 0
        assert cell["aspect_deg"] == pytest.approx(270, abs=0.1)
        assert -75.21 <= cell["longitude"] <= -75.20938
        assert -12.06 <= cell["latitude"] <= -12.05948
        assert len(cell["hourly_canopy_temps"]) == 24
    assert len({cell["mean_canopy_temp"] for cell in result["cells"]}) > 1


def test_power_rejects_missing_hours(monkeypatch):
    monkeypatch.setattr(parcel_edo1, "read_json", lambda _: {
        "header": {"fill_value": -999},
        "properties": {"parameter": {"T2M": {"2026010100": -999}}},
    })
    with pytest.raises(parcel_edo1.ParcelDataError, match="NASA POWER"):
        parcel_edo1.load_power(-75.21, -12.06, date(2026, 1, 1))
