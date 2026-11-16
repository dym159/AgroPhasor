"""
Parcel Simulation Service for ODE 2 (Root-Zone Water Balance).
Connects climate forcing (NASA POWER / GPM / SMAP) and terrain parameters (SRTM)
to the `edo2_engine` agrophysical solver.
"""

import math
from typing import Dict, Any, List, Optional

from backend.models.crop_parameters import get_crop_parameters, CROP_CATALOG, CropParameters
from backend.models.edo2_validator import validate_edo2_catalog
from backend.core.edo2_engine import (
    solve_edo2_step,
    simulate_edo2_timeseries,
    compute_soil_limits,
    SoilHydraulicLimits,
    EDO2StepOutput
)


class ParcelEDO2Service:
    """Agrophysical service for running parcel-level ODE 2 simulations."""

    @staticmethod
    def validate_catalog(catalog_path_or_dict: Any) -> Dict[str, Any]:
        """Formally validates a JSON file or dictionary catalog for ODE 2."""
        return validate_edo2_catalog(catalog_path_or_dict)

    @staticmethod
    def simulate_timeseries(
        precip_series: List[float],
        t_air_series: List[float],
        rh_series: List[float],
        crop_id: str = "maiz",
        slope_deg: float = 5.0,
        smap_root_wetness: Optional[float] = 0.50,
        w0_mm: Optional[float] = None,
        theta_fc: float = 0.30,
        theta_wp: float = 0.14,
        auto_irrigate: bool = False,
        eta_irrigation: float = 0.85,
        dt_days: float = 1.0,
        custom_catalog_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Runs the ODE 2 time-series simulation for a given crop and slope.
        Supports the official catalog or a validated external JSON catalog.
        """
        crop = get_crop_parameters(crop_id)

        # If a custom catalog is specified, validate it before simulating
        if custom_catalog_path:
            validation = validate_edo2_catalog(custom_catalog_path, theta_fc, theta_wp)
            if not validation["valid"]:
                raise ValueError(f"Invalid custom catalog for ODE 2: {validation['errors']}")

        return simulate_edo2_timeseries(
            precip_series=precip_series,
            t_air_series=t_air_series,
            rh_series=rh_series,
            crop=crop,
            slope_deg=slope_deg,
            w0_mm=w0_mm,
            smap_root_wetness=smap_root_wetness,
            theta_fc=theta_fc,
            theta_wp=theta_wp,
            auto_irrigate=auto_irrigate,
            eta_irrigation=eta_irrigation,
            dt_days=dt_days
        )
