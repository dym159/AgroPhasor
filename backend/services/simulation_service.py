"""
Servicio de Simulación Espacio-Temporal para AgroPhasor.
Orquesta:
1. Recepción y normalización de datos de NASA POWER (T2M, Radiación, RH, Lluvia, GWETROOT).
2. Detección automática de la Humedad Radicular real del suelo vía NASA (SMAP / GWETROOT).
3. Procesamiento de la cuadrícula de celdas 30x30m (Topografía SRTM).
4. Downscaling topoclimático local.
5. Ejecución vectorizada de EDO 1 para todo el lote.
6. Generación de diagnósticos de Escudo Térmico y alertas.
"""

from typing import Dict, Any, List, Optional
import numpy as np

from backend.models.crop_parameters import get_crop_parameters, CropParameters
from backend.core.topoclimatic import (
    lapse_rate_air_temperature,
    topographic_solar_factor,
    convert_nasa_radiation_to_wm2
)
from backend.core.edo1_engine import solve_edo1_step, compute_lissajous_area


class SimulationService:
    @staticmethod
    def run_field_simulation(
        nasa_hourly_data: Dict[str, Dict[str, float]],
        grid_cells: List[Dict[str, Any]],
        crop_id: str,
        soil_water_mm: Optional[float] = None,
        ref_altitude_m: Optional[float] = None,
        is_radiation_mj_hr: bool = True,
    ) -> Dict[str, Any]:
        """
        Ejecuta la simulación para todas las celdas de 30x30m del terreno sobre las horas disponibles.
        
        Args:
            nasa_hourly_data: Diccionario con llaves 'T2M', 'ALLSKY_SFC_SW_DWN', 'RH2M'
                              y opcionalmente 'GWETROOT' (Humedad radicular asimilada de SMAP).
            grid_cells: Lista de celdas de la parcela [{'cell_id': '0_0', 'altitude_m': 3250.0, 'slope_deg': 5.0, 'aspect_deg': 180.0}, ...]
            crop_id: Identificador del cultivo ('papa', 'maiz', 'haba', 'barbecho')
            soil_water_mm: Nivel de humedad en suelo (mm). Si es None, se extrae de NASA GWETROOT.
            ref_altitude_m: Cota altitudinal de referencia para gradiente vertical
        """
        crop = get_crop_parameters(crop_id)
        
        t2m_dict = nasa_hourly_data.get("T2M", {})
        rad_dict = nasa_hourly_data.get("ALLSKY_SFC_SW_DWN", {})
        rh_dict = nasa_hourly_data.get("RH2M", {})
        gwetroot_dict = nasa_hourly_data.get("GWETROOT", {})
        
        timestamps = sorted(t2m_dict.keys())
        if not timestamps:
            raise ValueError("No se encontraron series temporales válidas en los datos de NASA POWER.")
            
        t2m_raw = [float(t2m_dict[ts]) for ts in timestamps]
        rad_raw = [max(0.0, float(rad_dict.get(ts, 0.0))) for ts in timestamps]
        rad_raw_wm2 = [convert_nasa_radiation_to_wm2(value) for value in rad_raw] if is_radiation_mj_hr else rad_raw
        rh_raw = [float(rh_dict.get(ts, 60.0)) for ts in timestamps]
        
        # Inferencia o lectura de la humedad radicular real del suelo (SMAP / NASA GWETROOT)
        soil_moisture_source = "manual"
        if soil_water_mm is None:
            if gwetroot_dict:
                # GWETROOT es fracción de saturación [0, 1] asimilada por NASA de SMAP
                gwet_vals = [float(v) for v in gwetroot_dict.values() if float(v) >= 0.0]
                gwet_mean = float(np.mean(gwet_vals)) if gwet_vals else 0.65
                # Escalamos según la Capacidad de Campo del cultivo
                soil_water_mm = round(gwet_mean * crop.W_fc, 2)
                soil_moisture_source = "NASA_SMAP_GWETROOT"
            else:
                # Valor por defecto típico de suelo con humedad media
                soil_water_mm = round(0.70 * crop.W_fc, 2)
                soil_moisture_source = "default_70pct_Wfc"
        
        # Altitud media de referencia si no se especifica
        if ref_altitude_m is None and grid_cells:
            ref_altitude_m = float(np.mean([c.get("altitude_m", 3000.0) for c in grid_cells]))
        elif ref_altitude_m is None:
            ref_altitude_m = 3000.0
            
        cells_output = []
        all_canopy_means = []
        
        for cell in grid_cells:
            cell_id = cell.get("cell_id", "0_0")
            alt = float(cell.get("altitude_m", ref_altitude_m))
            slope_rad = np.radians(float(cell.get("slope_deg", 0.0)))
            aspect_rad = np.radians(float(cell.get("aspect_deg", 0.0)))
            
            # Factor solar topográfico fijo de la celda
            topo_solar = topographic_solar_factor(slope_rad, aspect_rad)
            
            canopy_temps = []
            air_temps = []
            comfort_list = []
            fever_hours = 0
            
            t_curr = t2m_raw[0]
            
            for h in range(len(timestamps)):
                # Downscaling topoclimático del aire y radiación
                t_air_local = lapse_rate_air_temperature(t2m_raw[h], alt, ref_altitude_m)
                f_rad_local = rad_raw_wm2[h] * topo_solar
                rh_local = rh_raw[h]
                
                step_res = solve_edo1_step(
                    t_current_c=t_curr,
                    t_ext_c=t_air_local,
                    f_rad_wm2=f_rad_local,
                    rh_pct=rh_local,
                    soil_water_mm=soil_water_mm,
                    crop=crop,
                    dt_seconds=3600.0,
                    sub_steps=2
                )
                
                t_curr = step_res.t_canopy_c
                canopy_temps.append(round(step_res.t_canopy_c, 2))
                air_temps.append(round(t_air_local, 2))
                comfort_list.append(round(step_res.comfort_index, 3))
                if step_res.is_fever:
                    fever_hours += 1
                    
            al_area = compute_lissajous_area(np.array(air_temps), np.array(canopy_temps))
            mean_temp = float(np.mean(canopy_temps))
            all_canopy_means.append(mean_temp)
            
            # Clasificación del Escudo Térmico
            mean_comfort = float(np.mean(comfort_list))
            if mean_comfort >= 0.75:
                shield_color = "Azul Cobalto (Óptimo)"
            elif mean_comfort >= 0.45:
                shield_color = "Ámbar (Estrés Moderado)"
            else:
                shield_color = "Rojo Intenso (Estrés Crítico)"
                
            cells_output.append({
                "cell_id": cell_id,
                "altitude_m": alt,
                "mean_canopy_temp": round(mean_temp, 2),
                "max_canopy_temp": round(float(np.max(canopy_temps)), 2),
                "min_canopy_temp": round(float(np.min(canopy_temps)), 2),
                "lissajous_area": round(al_area, 2),
                "thermal_shield": shield_color,
                "fever_hours_count": fever_hours,
                "hourly_canopy_temps": canopy_temps
            })
            
        return {
            "crop": crop.name,
            "soil_water_mm": soil_water_mm,
            "soil_moisture_source": soil_moisture_source,
            "timestamps_count": len(timestamps),
            "lot_mean_temp": round(float(np.mean(all_canopy_means)), 2),
            "cells_count": len(cells_output),
            "cells": cells_output
        }
