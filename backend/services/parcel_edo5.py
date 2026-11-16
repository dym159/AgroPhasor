"""
Spatial simulation service for ODE 5 over 2.5D discretized parcels (M x L cells).
Connects SRTM digital elevation models (z_i,j, theta_i,j), SSURGO/WSS soil data (H0, theta_fc),
and GPM/IMERG/NASA POWER precipitation time series to map spatial water-erosion vulnerability
across every cell of the parcel.
"""

from typing import List, Dict, Any, Optional
import numpy as np

from backend.core.edo5_engine import solve_edo5_step, simulate_edo5_timeseries, compute_soil_pareto_metric_f2


class ParcelEDO5Service:
    @staticmethod
    def simulate_parcel_grid(
        grid_cells: List[Dict[str, Any]],
        precip_series: List[float],
        biomass_series: List[float],
        transition_flags: List[bool],
        default_h0_mm: float = 400.0,
        theta_fc: float = 0.30,
        theta_wp: float = 0.14
    ) -> Dict[str, Any]:
        """
        Runs erosion simulation for each cell of the 2.5D grid.
        
        Each cell contains:
        - cell_id: Cell identifier
        - altitude_m: SRTM elevation
        - slope_deg: SRTM slope inclination (theta)
        - aspect_deg: Aspect orientation
        - h0_mm: Optional initial fertile depth
        """
        results = []
        total_loss_accum = 0.0
        max_erosion_cell = None
        max_erosion_val = -1.0

        for cell in grid_cells:
            c_id = cell.get("cell_id", "0_0")
            slope = float(cell.get("slope_deg", 0.0))
            h0 = float(cell.get("h0_mm", default_h0_mm))

            sim = simulate_edo5_timeseries(
                precip_series=precip_series,
                slope_deg=slope,
                biomass_series=biomass_series,
                transition_flags=transition_flags,
                h0_mm=h0,
                theta_fc=theta_fc,
                theta_wp=theta_wp
            )

            loss_mm = sim["total_erosion_loss_mm"]
            total_loss_accum += loss_mm
            if loss_mm > max_erosion_val:
                max_erosion_val = loss_mm
                max_erosion_cell = c_id

            results.append({
                "cell_id": c_id,
                "slope_deg": slope,
                "altitude_m": cell.get("altitude_m", 3000.0),
                "h0_mm": h0,
                "final_h_mm": sim["final_h_mm"],
                "erosion_loss_mm": loss_mm,
                "erosion_loss_pct": sim["erosion_loss_pct"],
                "final_w_cc_mm": sim["final_w_cc_mm"],
                "p_drag_kg_ha": sim["cumulative_p_drag_kg_ha"]
            })

        avg_loss = round(total_loss_accum / max(1, len(grid_cells)), 3)

        return {
            "cells_count": len(grid_cells),
            "sim_days": len(precip_series),
            "average_erosion_loss_mm": avg_loss,
            "hotspot_critical_cell": max_erosion_cell,
            "hotspot_max_loss_mm": round(max_erosion_val, 3),
            "cells": results
        }
