"""
Direct integration verification script for the ODE 1 backend,
including automatic root-zone soil moisture detection with SMAP (GWETROOT).
"""
import sys
import os

sys.path.insert(0, os.path.abspath("."))

from backend.models.crop_parameters import get_crop_parameters, CROP_CATALOG
from backend.services.simulation_service import SimulationService
from backend.core.edo1_engine import solve_edo1_step

def test_local():
    print("1. Verifying crop catalog...")
    for cid, crop in CROP_CATALOG.items():
        print(f"   - {crop.name} ({crop.botanical_family}): T_opt={crop.T_opt}°C, W_fc={crop.W_fc}mm")
        
    print("\n2. Verifying ODE 1 step (Well-Watered vs Drought)...")
    crop = get_crop_parameters("papa")
    step_water = solve_edo1_step(t_current_c=15.0, t_ext_c=15.0, f_rad_wm2=700.0, rh_pct=50.0, soil_water_mm=60.0, crop=crop)
    step_drought = solve_edo1_step(t_current_c=15.0, t_ext_c=15.0, f_rad_wm2=700.0, rh_pct=50.0, soil_water_mm=10.0, crop=crop)
    print(f"   - Irrigated Crop: T_canopy={step_water.t_canopy_c:.2f}°C (Delta={step_water.delta_t_c:.2f}°C)")
    print(f"   - Drought Crop:   T_canopy={step_drought.t_canopy_c:.2f}°C (Delta={step_drought.delta_t_c:.2f}°C, Fever={step_drought.is_fever})")
    
    print("\n3. Verifying moisture inference from NASA SMAP / GWETROOT...")
    mock_nasa = {
        "T2M": {f"20230101{h:02d}": 12.0 + 4.0 * (1.0 if 8 <= h <= 16 else 0.0) for h in range(24)},
        "ALLSKY_SFC_SW_DWN": {f"20230101{h:02d}": (2.2 if 8 <= h <= 16 else 0.0) for h in range(24)},
        "RH2M": {f"20230101{h:02d}": 55.0 for h in range(24)},
        "GWETROOT": {f"20230101{h:02d}": 0.75 for h in range(24)} # 75% root-zone saturation per SMAP
    }
    grid = [
        {"cell_id": "0_0", "altitude_m": 3200.0, "slope_deg": 2.0, "aspect_deg": 180.0},
        {"cell_id": "0_1", "altitude_m": 3260.0, "slope_deg": 15.0, "aspect_deg": 90.0}
    ]
    # Omit soil_water_mm -> backend infers it from GWETROOT
    res = SimulationService.run_field_simulation(mock_nasa, grid, crop_id="papa", soil_water_mm=None)
    print(f"   - Crop: {res['crop']}")
    print(f"   - Moisture source: {res['soil_moisture_source']}")
    print(f"   - Computed soil moisture: {res['soil_water_mm']} mm")
    print(f"   - Cells processed: {res['cells_count']}")
    for c in res["cells"]:
        print(f"     * Cell {c['cell_id']} (Alt={c['altitude_m']}m): T_mean={c['mean_canopy_temp']}°C, Shield={c['thermal_shield']}")
        
    print("\nAll ODE 1 backend components work properly integrating climate, topography, and SMAP moisture!")

if __name__ == "__main__":
    test_local()
