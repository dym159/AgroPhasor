"""
Unit Test Suite for ODE 1 (AgroPhasor).
Verifies numerical stability, physical asymptotic bounds, and the 4 validation criteria.
Implemented in pure Python for maximum portability.
"""

import math
try:
    import pytest
except ImportError:
    pytest = None

from backend.models.crop_parameters import get_crop_parameters, CROP_CATALOG
from backend.core.physics import (
    saturation_vapor_pressure,
    penman_saturation_slope,
    actual_vapor_pressure,
    vapor_pressure_deficit,
    stomatal_conductance_factor
)
from backend.core.edo1_engine import solve_edo1_step, simulate_canopy_diurnal_cycle
from backend.core.topoclimatic import lapse_rate_air_temperature, convert_nasa_radiation_to_wm2
from backend.services.simulation_service import SimulationService


def test_tetens_physics():
    """Verify that Tetens saturation vapor pressure yields physically accurate values."""
    es_0 = saturation_vapor_pressure(0.0)
    assert 0.60 <= es_0 <= 0.62  # e_s(0°C) ≈ 0.611 kPa
    
    es_20 = saturation_vapor_pressure(20.0)
    assert 2.30 <= es_20 <= 2.40  # e_s(20°C) ≈ 2.34 kPa
    
    delta = penman_saturation_slope(20.0)
    assert delta > 0.0


def test_nighttime_asymptotic_cooling():
    """
    Asymptotic Criterion: At night (no solar radiation), the plant must cool
    toward air temperature via sensible heat transfer (Newton's cooling).
    """
    crop = get_crop_parameters("maiz")
    t_air = 8.0
    t_leaf_initial = 22.0  # Warm leaf entering nighttime
    
    t_curr = t_leaf_initial
    for _ in range(4):  # 4 hours of nighttime
        step = solve_edo1_step(
            t_current_c=t_curr,
            t_ext_c=t_air,
            f_rad_wm2=0.0,
            rh_pct=90.0,
            soil_water_mm=60.0,
            crop=crop,
            dt_seconds=3600.0
        )
        t_curr = step.t_canopy_c
        
    assert abs(t_curr - t_air) < 0.2


def test_cooling_with_water_vs_drought_fever():
    """
    Verify that an irrigated crop stays cool while a drought-stressed crop
    triggers midday leaf fever (Criteria 1 and 2).
    """
    crop = get_crop_parameters("maiz")
    t_air = 16.0
    f_rad = 750.0  # High midday radiation
    rh = 45.0
    
    # Case 1: Well-watered soil (W = 70 mm > W_crit)
    step_water = solve_edo1_step(
        t_current_c=t_air,
        t_ext_c=t_air,
        f_rad_wm2=f_rad,
        rh_pct=rh,
        soil_water_mm=70.0,
        crop=crop
    )
    
    # Case 2: Soil in extreme drought (W = 10 mm < W_pmp)
    step_drought = solve_edo1_step(
        t_current_c=t_air,
        t_ext_c=t_air,
        f_rad_wm2=f_rad,
        rh_pct=rh,
        soil_water_mm=10.0,
        crop=crop
    )
    
    assert step_water.t_canopy_c < step_drought.t_canopy_c
    diff_drought = step_drought.t_canopy_c - t_air
    assert diff_drought >= 8.0
    assert step_drought.is_fever is True


def test_simulation_service_field_and_smap():
    """Verify parcel processing and automatic GWETROOT (SMAP) inference."""
    mock_nasa_data = {
        "T2M": {f"20230101{h:02d}": 12.0 + 5.0 * math.sin(h * math.pi / 12) for h in range(24)},
        "ALLSKY_SFC_SW_DWN": {f"20230101{h:02d}": max(0.0, 2.5 * math.sin(h * math.pi / 12)) for h in range(24)},
        "RH2M": {f"20230101{h:02d}": 60.0 for h in range(24)},
        "GWETROOT": {f"20230101{h:02d}": 0.80 for h in range(24)}  # 80% root-zone wetness per SMAP
    }
    
    grid = [
        {"cell_id": "0_0", "altitude_m": 3100.0, "slope_deg": 2.0, "aspect_deg": 180.0},
        {"cell_id": "0_1", "altitude_m": 3250.0, "slope_deg": 12.0, "aspect_deg": 90.0}
    ]
    
    # Omit soil_water_mm so it is inferred from NASA GWETROOT
    res = SimulationService.run_field_simulation(
        nasa_hourly_data=mock_nasa_data,
        grid_cells=grid,
        crop_id="maiz",
        soil_water_mm=None
    )
    
    assert res["crop"] == "Maize"
    assert res["cells_count"] == 2
    assert res["soil_moisture_source"] == "NASA_SMAP_GWETROOT"
    assert res["soil_water_mm"] > 0
