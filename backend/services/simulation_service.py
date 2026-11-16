"""
Spatiotemporal Simulation Service for AgroPhasor.
Orchestrates:
1. Ingestion and normalization of NASA POWER data (T2M, Radiation, RH, GWETROOT).
2. Automatic detection of actual root-zone soil moisture via NASA (SMAP / GWETROOT).
3. Processing of the 30x30m grid cells (SRTM topography).
4. Local topoclimatic downscaling.
5. Analytical execution of ODE 1 across the entire parcel.
6. Generation of Thermal Shield diagnostics and alerts.
"""

import math
from typing import Dict, Any, List, Optional

from backend.models.crop_parameters import get_crop_parameters, CropParameters
from backend.core.topoclimatic import (
    lapse_rate_air_temperature,
    topographic_solar_factor,
    convert_nasa_radiation_to_wm2
)
from backend.core.edo1_engine import (
    solve_edo1_step,
    compute_lissajous_area,
    compute_shield_state_and_color,
)


class SimulationService:
    @staticmethod
    def run_field_simulation(
        nasa_hourly_data: Dict[str, Dict[str, float]],
        grid_cells: List[Dict[str, Any]],
        crop_id: str,
        soil_water_mm: Optional[float] = None,
        ref_altitude_m: Optional[float] = None,
        is_radiation_mj_hr: bool = True,
        crop_parameters: Optional[CropParameters] = None,
    ) -> Dict[str, Any]:
        """
        Runs the simulation for all 30x30m terrain cells over the available hours.
        """
        crop = crop_parameters or get_crop_parameters(crop_id)
        
        t2m_dict = nasa_hourly_data.get("T2M", {})
        rad_dict = nasa_hourly_data.get("ALLSKY_SFC_SW_DWN", {})
        rh_dict = nasa_hourly_data.get("RH2M", {})
        gwetroot_dict = nasa_hourly_data.get("GWETROOT", {})
        
        timestamps = sorted(t2m_dict.keys())
        if not timestamps:
            raise ValueError("No valid time series found in NASA POWER data.")
            
        t2m_raw = [float(t2m_dict[ts]) for ts in timestamps]
        if is_radiation_mj_hr:
            rad_raw_wm2 = [convert_nasa_radiation_to_wm2(float(rad_dict.get(ts, 0.0))) for ts in timestamps]
        else:
            rad_raw_wm2 = [float(rad_dict.get(ts, 0.0)) for ts in timestamps]
            
        rh_raw = [float(rh_dict.get(ts, 60.0)) for ts in timestamps]
        
        # Inference or direct reading of root-zone soil moisture (SMAP / NASA GWETROOT)
        soil_moisture_source = "manual"
        if soil_water_mm is None:
            if gwetroot_dict:
                gwet_vals = [float(v) for v in gwetroot_dict.values() if float(v) >= 0.0]
                gwet_mean = (sum(gwet_vals) / float(len(gwet_vals))) if gwet_vals else 0.65
                soil_water_mm = round(gwet_mean * crop.W_fc, 2)
                soil_moisture_source = "NASA_SMAP_GWETROOT"
            else:
                soil_water_mm = round(0.70 * crop.W_fc, 2)
                soil_moisture_source = "default_70pct_Wfc"
        
        # Default reference altitude if not specified
        if ref_altitude_m is None and grid_cells:
            alts = [float(c.get("altitude_m", 3000.0)) for c in grid_cells]
            ref_altitude_m = sum(alts) / float(len(alts))
        elif ref_altitude_m is None:
            ref_altitude_m = 3000.0
            
        cells_output = []
        all_canopy_means = []
        
        for cell in grid_cells:
            cell_id = cell.get("cell_id", "0_0")
            alt = float(cell.get("altitude_m", ref_altitude_m))
            slope_rad = math.radians(float(cell.get("slope_deg", 0.0)))
            aspect_rad = math.radians(float(cell.get("aspect_deg", 0.0)))
            
            # Fixed topographic solar projection factor for the cell
            topo_solar = topographic_solar_factor(slope_rad, aspect_rad)
            
            canopy_temps = []
            air_temps = []
            comfort_list = []
            fever_hours = 0
            
            t_curr = t2m_raw[0]
            
            for h in range(len(timestamps)):
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
                    sub_steps=12
                )
                
                t_curr = step_res.t_canopy_c
                canopy_temps.append(round(step_res.t_canopy_c, 2))
                air_temps.append(round(t_air_local, 2))
                comfort_list.append(round(step_res.comfort_index, 3))
                if step_res.is_fever:
                    fever_hours += 1
                    
            al_area = compute_lissajous_area(air_temps, canopy_temps)
            mean_temp = sum(canopy_temps) / float(len(canopy_temps))
            all_canopy_means.append(mean_temp)
            
            mean_comfort = sum(comfort_list) / float(len(comfort_list))
            is_crop_mode = crop.botanical_family != "None"
            shield_info = compute_shield_state_and_color(
                lissajous_area=al_area,
                psi_environmental=mean_comfort,
                is_crop=is_crop_mode,
            )
            shield_color = shield_info["shield_label"]
                
            cells_output.append({
                "cell_id": cell_id,
                "altitude_m": alt,
                "mean_canopy_temp": round(mean_temp, 2),
                "max_canopy_temp": round(max(canopy_temps), 2),
                "min_canopy_temp": round(min(canopy_temps), 2),
                "lissajous_area": round(al_area, 2),
                "eta_lissajous": shield_info["eta_lissajous"],
                "shield_score": shield_info["shield_score"],
                "shield_state": shield_info["shield_state"],
                "shield_color_rgb": shield_info["shield_color_rgb"],
                "thermal_shield": shield_color,
                "fever_hours_count": fever_hours,
                "hourly_canopy_temps": canopy_temps,
                "hourly_air_temps": air_temps,
            })
            
        lot_mean = sum(all_canopy_means) / float(len(all_canopy_means)) if all_canopy_means else 0.0
        return {
            "crop": crop.name,
            "soil_water_mm": soil_water_mm,
            "soil_moisture_source": soil_moisture_source,
            "is_radiation_mj_hr": is_radiation_mj_hr,
            "timestamps_count": len(timestamps),
            "timestamps": timestamps,
            "lot_mean_temp": round(lot_mean, 2),
            "cells_count": len(cells_output),
            "cells": cells_output
        }
