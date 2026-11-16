"""
Parcel Simulation Service for ODE 4 (Biomass Growth and Stover Residue).
AgroPhasor - Qillawasi / National University of Engineering (UNI).

Connects the `edo4_engine` solver, `edo4_validator`, and `edo4_data_adapter`
to resolve temporal and spatial biomass dynamics across agricultural parcels under
NASA forcings (POWER, SMAP, GPM, ECOSTRESS, SRTM, GEDI) and USDA / FAO datasets.
"""

from typing import Dict, Any, List, Optional, Union

from backend.models.crop_parameters import get_crop_parameters, CropParameters
from backend.models.edo4_validator import validate_edo4_catalog
from backend.core.edo4_engine import (
    solve_edo4_step,
    execute_harvest_event,
    simulate_edo4_timeseries,
    biomass_to_satellite_ndvi,
    biomass_to_canopy_cover,
    EDO4StepOutput,
    EDO4HarvestResult
)
from backend.services.edo4_data_adapter import (
    EDO4DataAdapter,
    EnvironmentalForcingEDO4
)


class ParcelEDO4Service:
    """Agrophysical simulation and satellite remote-sensing service for ODE 4."""

    @staticmethod
    def validate_catalog(catalog_path_or_dict: Any) -> Dict[str, Any]:
        """Formally validates a JSON file or dictionary catalog for ODE 4."""
        return validate_edo4_catalog(catalog_path_or_dict)

    @staticmethod
    def calibrate_crop(
        crop_id: str,
        fao_gaez_yield_potential_t_ha: Optional[float] = None,
        nass_historical_county_yield_t_ha: Optional[float] = None,
        gedi_max_biomass_t_ha: Optional[float] = None
    ) -> CropParameters:
        """Calibrates genetic biomass ceiling and harvest potential from FAO GAEZ, USDA NASS, and GEDI."""
        return EDO4DataAdapter.calibrate_crop_ceiling_from_faog_and_nass(
            crop_id=crop_id,
            fao_gaez_yield_potential_t_ha=fao_gaez_yield_potential_t_ha,
            nass_historical_county_yield_t_ha=nass_historical_county_yield_t_ha,
            gedi_max_biomass_t_ha=gedi_max_biomass_t_ha
        )

    @staticmethod
    def simulate_crop_cycle(
        crop_id: str,
        f_rad_series_mj_m2: List[float],
        t_canopy_series_c: List[float],
        soil_water_series_mm: List[float],
        nitrogen_series_kg_ha: List[float],
        phosphorus_series_kg_ha: List[float],
        potassium_series_kg_ha: List[float],
        b0_t_ha: Optional[float] = None,
        residue_fraction_rres: float = 0.30,
        market_price_usd_t: Optional[float] = None,
        satellite_ndvi_observations: Optional[Dict[int, float]] = None,
        gedi_biomass_observations: Optional[Dict[int, float]] = None,
        custom_crop: Optional[CropParameters] = None
    ) -> Dict[str, Any]:
        """
        Runs a full ODE 4 time-series simulation for a crop season.
        Supports simultaneous validation against Landsat/MODIS NDVI and GEDI Lidar observations.
        """
        crop = custom_crop if custom_crop is not None else get_crop_parameters(crop_id)
        
        n_days = len(f_rad_series_mj_m2)
        forcing_series = []

        for d in range(n_days):
            obs_ndvi = satellite_ndvi_observations.get(d) if satellite_ndvi_observations else None
            obs_gedi = gedi_biomass_observations.get(d) if gedi_biomass_observations else None

            forcing = EnvironmentalForcingEDO4(
                date_str=f"Day {d+1}",
                f_rad_daily_mj_m2=f_rad_series_mj_m2[d],
                temp_canopy_c=t_canopy_series_c[d],
                soil_water_mm=soil_water_series_mm[d],
                nitrogen_kg_ha=nitrogen_series_kg_ha[d],
                phosphorus_kg_ha=phosphorus_series_kg_ha[d],
                potassium_kg_ha=potassium_series_kg_ha[d],
                satellite_observed_ndvi=obs_ndvi,
                observed_biomass_gedi_t_ha=obs_gedi
            )
            forcing_series.append(forcing)

        return EDO4DataAdapter.simulate_crop_and_contrast_satellite(
            forcing_series=forcing_series,
            crop=crop,
            b0_t_ha=b0_t_ha,
            residue_fraction_rres=residue_fraction_rres,
            market_price_usd_t=market_price_usd_t
        )

    @staticmethod
    def simulate_grid_cells(
        grid_cells: List[Dict[str, Any]],
        crop_id: str,
        nasa_hourly_data: Dict[str, Dict[str, float]],
        soil_water_mm: float = 65.0,
        soil_nutrients: Optional[Dict[str, float]] = None,
        simulation_days: int = 30
    ) -> Dict[str, Any]:
        """
        Simulates a spatial 2.5D grid of 30x30m cells (SRTM) under ODE 4.
        Computes spatial biomass, canopy cover, and expected yield for each parcel cell.
        """
        crop = get_crop_parameters(crop_id)
        nutrients = soil_nutrients or {"N": 55.0, "P": 30.0, "K": 70.0}

        # Extract mean daily radiation and temperature from NASA POWER
        t2m_dict = nasa_hourly_data.get("T2M", {})
        rad_dict = nasa_hourly_data.get("ALLSKY_SFC_SW_DWN", {})

        mean_t2m = (sum(float(v) for v in t2m_dict.values()) / max(1, len(t2m_dict))) if t2m_dict else 20.0
        # Convert summed hourly radiation to MJ/m²·day
        mean_rad_mj = (sum(float(v) for v in rad_dict.values())) if rad_dict else 18.0

        cells_summary = []
        for cell in grid_cells:
            cell_id = cell.get("cell_id", "0_0")
            slope = float(cell.get("slope_deg", 0.0))
            aspect = float(cell.get("aspect_deg", 180.0))
            alt = float(cell.get("altitude_m", 3000.0))

            # Local per-cell topoclimatic adjustments
            from backend.core.topoclimatic import topographic_solar_factor, lapse_rate_air_temperature
            g_topo = topographic_solar_factor(slope, aspect)
            f_rad_cell = max(5.0, mean_rad_mj * g_topo)
            t_cell = lapse_rate_air_temperature(mean_t2m, alt, 3000.0)

            # Constant forcing series for the cell
            f_rad_series = [f_rad_cell] * simulation_days
            t_series = [t_cell] * simulation_days
            w_series = [soil_water_mm] * simulation_days
            n_series = [nutrients["N"]] * simulation_days
            p_series = [nutrients["P"]] * simulation_days
            k_series = [nutrients["K"]] * simulation_days

            sim = simulate_edo4_timeseries(
                f_rad_series_mj_m2=f_rad_series,
                t_canopy_series_c=t_series,
                soil_water_series_mm=w_series,
                nitrogen_series_kg_ha=n_series,
                phosphorus_series_kg_ha=p_series,
                potassium_series_kg_ha=k_series,
                crop=crop
            )

            harvest = execute_harvest_event(
                biomass_pre_harvest_t_ha=sim["final_biomass_t_ha"],
                crop=crop
            )

            cells_summary.append({
                "cell_id": cell_id,
                "altitude_m": alt,
                "slope_deg": slope,
                "aspect_deg": aspect,
                "final_biomass_t_ha": sim["final_biomass_t_ha"],
                "final_ndvi": sim["summary"]["final_ndvi"],
                "final_cover": sim["summary"]["final_cover"],
                "commercial_yield_t_ha": harvest.commercial_yield_t_ha,
                "net_margin_usd_ha": harvest.net_margin_usd_ha
            })

        mean_biomass = round(sum(c["final_biomass_t_ha"] for c in cells_summary) / len(cells_summary), 2)
        mean_yield = round(sum(c["commercial_yield_t_ha"] for c in cells_summary) / len(cells_summary), 2)
        mean_ndvi = round(sum(c["final_ndvi"] for c in cells_summary) / len(cells_summary), 3)

        return {
            "crop": crop.name,
            "cells_simulated": len(cells_summary),
            "simulation_days": simulation_days,
            "mean_biomass_t_ha": mean_biomass,
            "mean_yield_t_ha": mean_yield,
            "mean_ndvi": mean_ndvi,
            "cells": cells_summary
        }
