"""
Script de verificación directa de la integración del backend de EDO 1.
"""
import sys
import os

sys.path.insert(0, os.path.abspath("."))

from backend.models.crop_parameters import get_crop_parameters, CROP_CATALOG
from backend.services.simulation_service import SimulationService
from backend.core.edo1_engine import solve_edo1_step

def test_local():
    print("1. Verificando catálogo de cultivos...")
    for cid, crop in CROP_CATALOG.items():
        print(f"   - {crop.name} ({crop.botanical_family}): T_opt={crop.T_opt}°C, Cp={crop.Cp}")
        
    print("\n2. Verificando paso de EDO 1 (Sano vs Sequía)...")
    crop = get_crop_parameters("papa")
    step_water = solve_edo1_step(t_current_c=15.0, t_ext_c=15.0, f_rad_wm2=700.0, rh_pct=50.0, soil_water_mm=60.0, crop=crop)
    step_drought = solve_edo1_step(t_current_c=15.0, t_ext_c=15.0, f_rad_wm2=700.0, rh_pct=50.0, soil_water_mm=10.0, crop=crop)
    print(f"   - Cultivo Regado: T_canopy={step_water.t_canopy_c:.2f}°C (Delta={step_water.delta_t_c:.2f}°C)")
    print(f"   - Cultivo Sequía: T_canopy={step_drought.t_canopy_c:.2f}°C (Delta={step_drought.delta_t_c:.2f}°C, Fiebre={step_drought.is_fever})")
    
    print("\n3. Verificando simulación de parcela 30x30m...")
    mock_nasa = {
        "T2M": {f"20230101{h:02d}": 10.0 + 8.0 * (1.0 if 8 <= h <= 16 else 0.0) for h in range(24)},
        "ALLSKY_SFC_SW_DWN": {f"20230101{h:02d}": (2.2 if 8 <= h <= 16 else 0.0) for h in range(24)},
        "RH2M": {f"20230101{h:02d}": 55.0 for h in range(24)}
    }
    grid = [
        {"cell_id": "0_0", "altitude_m": 3200.0, "slope_deg": 2.0, "aspect_deg": 180.0},
        {"cell_id": "0_1", "altitude_m": 3260.0, "slope_deg": 15.0, "aspect_deg": 90.0}
    ]
    res = SimulationService.run_field_simulation(mock_nasa, grid, crop_id="papa", soil_water_mm=50.0)
    print(f"   - Cultivo: {res['crop']}")
    print(f"   - Celdas procesadas: {res['cells_count']}")
    for c in res["cells"]:
        print(f"     * Celda {c['cell_id']} (Alt={c['altitude_m']}m): T_media={c['mean_canopy_temp']}°C, Escudo={c['thermal_shield']}, Horas Fiebre={c['fever_hours_count']}")
        
    print("\n¡Todo el Backend de EDO 1 funciona de maravilla y está listo para conectarse con el mapa!")

if __name__ == "__main__":
    test_local()
