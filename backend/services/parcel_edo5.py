"""
Servicio espacial de simulación de EDO 5 sobre parcelas discretizadas 2.5D (M x L celdas).
Conecta el modelo digital de elevaciones SRTM (zi,j, theta_i,j), las bases edáficas SSURGO/WSS (H0, theta_fc)
y las series meteorológicas de precipitación GPM/IMERG/NASA POWER para mapear la vulnerabilidad
espacial a la erosión hídrica en cada celda del lote.
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
        Ejecuta la simulación de erosión para cada celda de la malla 2.5D.
        
        Cada celda contiene:
        - cell_id: Identificador
        - altitude_m: Cota SRTM
        - slope_deg: Inclinación SRTM (theta)
        - aspect_deg: Orientación
        - h0_mm: Espesor fértil inicial opcional
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
