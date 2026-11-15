=======
"""
API Backend Local de AgroPhasor (FastAPI).
Permite recibir las coordenadas, datos de NASA POWER y celdas SRTM desde el frontend/mapa,
y devolver la simulación de EDO 1 con la temperatura del dosel y el Escudo Térmico.
"""

from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.models.crop_parameters import CROP_CATALOG, get_crop_parameters
from backend.services.simulation_service import SimulationService
from backend.core.edo1_engine import simulate_canopy_diurnal_cycle
from backend.core.topoclimatic import convert_nasa_radiation_to_wm2

app = FastAPI(
    title="AgroPhasor Simulation Engine - Backend Local",
    description="Motor de física y balance térmico (EDO 1) para rotación de cultivos bajo estrés climático",
    version="1.0.0"
)


class CellData(BaseModel):
    cell_id: str
    altitude_m: float = 3000.0
    slope_deg: float = 0.0
    aspect_deg: float = 0.0


class FieldSimulationRequest(BaseModel):
    crop_id: str = Field(default="papa", description="Identificador del cultivo ('papa', 'maiz', 'haba', 'barbecho')")
    soil_water_mm: float = Field(default=50.0, description="Humedad del suelo en raíces [mm]")
    ref_altitude_m: Optional[float] = Field(default=None, description="Altitud de referencia del lote [m]")
    nasa_hourly_data: Dict[str, Dict[str, float]] = Field(
        ...,
        description="Respuesta horaria de NASA POWER conteniendo 'T2M', 'ALLSKY_SFC_SW_DWN', 'RH2M'"
    )
    grid_cells: List[CellData] = Field(
        default_factory=lambda: [CellData(cell_id="0_0", altitude_m=3200.0, slope_deg=2.0, aspect_deg=180.0)],
        description="Lista de celdas de 30x30m de la parcela dibujada"
    )


class SinglePointSimulationRequest(BaseModel):
    crop_id: str = "papa"
    soil_water_mm: float = 50.0
    t_air_hourly: List[float]
    radiation_hourly: List[float] = Field(..., description="Radiación solar en W/m² (o MJ/hr si is_radiation_mj_hr=True)")
    rh_hourly: List[float]
    is_radiation_mj_hr: bool = False


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "AgroPhasor EDO 1 Engine"}


@app.get("/crops")
def list_crops():
    """Devuelve la lista de cultivos precalibrados en el sistema."""
    return {
        crop_id: {
            "name": crop.name,
            "family": crop.botanical_family,
            "T_opt": crop.T_opt,
            "T_frost": crop.T_frost,
            "T_lethal": crop.T_lethal,
            "W_pmp": crop.W_pmp,
            "W_crit": crop.W_crit
        }
        for crop_id, crop in CROP_CATALOG.items()
    }


@app.post("/simulate/edo1")
def simulate_field(request: FieldSimulationRequest):
    """
    Simulación completa de la parcela:
    Recibe la respuesta cruda de NASA POWER y las celdas 30x30m de SRTM,
    y devuelve la temperatura del dosel y métricas de confort para cada celda.
    """
    try:
        cells_dict = [cell.model_dump() for cell in request.grid_cells]
        result = SimulationService.run_field_simulation(
            nasa_hourly_data=request.nasa_hourly_data,
            grid_cells=cells_dict,
            crop_id=request.crop_id,
            soil_water_mm=request.soil_water_mm,
            ref_altitude_m=request.ref_altitude_m
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/simulate/edo1/point")
def simulate_point(request: SinglePointSimulationRequest):
    """
    Simulación para un punto / celda individual en una serie de horas.
    """
    crop = get_crop_parameters(request.crop_id)
    rad_wm2 = (
        [convert_nasa_radiation_to_wm2(r) for r in request.radiation_hourly]
        if request.is_radiation_mj_hr
        else request.radiation_hourly
    )
    result = simulate_canopy_diurnal_cycle(
        t_ext_hourly=request.t_air_hourly,
        f_rad_wm2_hourly=rad_wm2,
        rh_pct_hourly=request.rh_hourly,
        soil_water_mm=request.soil_water_mm,
        crop=crop
    )
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
>>>>>>> Stashed changes
