"""
AgroPhasor - ODE 5 Agro-Physical Engine: Topsoil Water Erosion
=============================================================
Ordinary differential equation (Agrophasor.pdf, Sec 3.2.5):
    d H_i,j / dt = - k_er(q) * P_0(t) * sin(theta_i,j) * exp(-lambda_B * B_i,j(t))

Where H_i,j(t) in [0, H_i,j(0)] denotes fertile topsoil depth (mm).

Multi-Sensor Calibration & Satellite Data Fusion:
  - NASA GPM & IMERG / NASA POWER: Daily rainfall and storm extremes P0(t) (mm/day).
  - SRTM (z_i,j, theta_i,j): 2.5D topography, local slope theta and elevation z_i,j.
  - Landsat 8/9, Sentinel-2 & MODIS: Crop vigor, NDVI/EVI and protective biomass B_i,j(t) (t/ha).
  - USDA NRCS SSURGO / Web Soil Survey (WSS) / STATSGO2: Baseline topsoil thickness H0, theta_fc, theta_wp.
  - USDA CDL (CropScape) & Ag Data Commons: Cropping calendar and transition windows q(t).

Exact analytical solution over time step dt (Sec 3.2.5):
    H_i,j(t + dt) = max(0, H_i,j(t) - k_er(q) * P_0(t) * sin(theta_i,j) * exp(-lambda_B * B_i,j(t)) * dt)
"""

import math
import numpy as np
from typing import Dict, Any, List, Optional, Tuple


class AgroPhasorEDO5:
    """
    Specialized physics engine for ODE 5 simulation and validation.
    """
    def __init__(
        self,
        h0_mm: float = 400.0,            # Initial organic horizon thickness (SSURGO/WSS)
        slope_deg: float = 12.0,          # SRTM hillside slope angle (degrees)
        theta_fc: float = 0.30,           # Volumetric field capacity (SSURGO/WSS)
        theta_wp: float = 0.14,           # Volumetric permanent wilting point (SSURGO/WSS)
        k_er_cultivo: float = 0.0004,     # Living-crop erodibility (AgroPhasor JSON)
        k_er_labranza: float = 0.0035,    # Tillage/transition erodibility (AgroPhasor JSON)
        lambda_b: float = 0.45,           # Leaf biomass attenuation factor (ha/t)
        xi_n: float = 0.004,              # Erosion N drag coefficient
        xi_p: float = 0.008,              # Erosion P drag coefficient
        xi_k: float = 0.003,              # Erosion K drag coefficient
        kappa_er: float = 0.001           # 3D mesh subsidence scaling factor (m/mm)
    ):
        self.h0_mm = float(h0_mm)
        self.h_current_mm = float(h0_mm)
        self.slope_deg = float(slope_deg)
        self.slope_rad = math.radians(max(0.0, min(85.0, slope_deg)))
        self.sin_theta = math.sin(self.slope_rad)
        
        self.theta_fc = float(theta_fc)
        self.theta_wp = float(theta_wp)
        
        self.k_er_cultivo = float(k_er_cultivo)
        self.k_er_labranza = float(k_er_labranza)
        self.lambda_b = float(lambda_b)
        
        self.xi_n = float(xi_n)
        self.xi_p = float(xi_p)
        self.xi_k = float(xi_k)
        self.kappa_er = float(kappa_er)

    def step(
        self,
        precip_mm: float,
        biomass_t_ha: float,
        is_transition: bool = False,
        current_nutrients: Optional[Dict[str, float]] = None,
        dt_days: float = 1.0
    ) -> Dict[str, Any]:
        """
        Execute one dt integration step of ODE 5.
        """
        if self.h_current_mm <= 0.0:
            return {
                "h_mm": 0.0,
                "dh_dt": 0.0,
                "loss_step_mm": 0.0,
                "accum_loss_mm": self.h0_mm,
                "w_cc_mm": 0.0,
                "w_pmp_mm": 0.0,
                "veg_cover_factor": math.exp(-self.lambda_b * max(0.0, biomass_t_ha)),
                "p_drag_kg_ha": 0.0,
                "mesh_subsidence_m": self.kappa_er * self.h0_mm,
                "bedrock_exposed": True
            }

        k_er = self.k_er_labranza if is_transition else self.k_er_cultivo
        p0 = max(0.0, float(precip_mm))
        veg_cover = math.exp(-self.lambda_b * max(0.0, float(biomass_t_ha)))
        
        erosion_rate = k_er * p0 * self.sin_theta * veg_cover
        dh_dt = -erosion_rate
        
        loss_step = min(self.h_current_mm, erosion_rate * dt_days)
        h_next = max(0.0, self.h_current_mm - loss_step)
        
        self.h_current_mm = h_next
        accum_loss = self.h0_mm - h_next
        
        # Edaphic feedback
        w_cc = self.theta_fc * h_next
        w_pmp = self.theta_wp * h_next
        
        # Biochemical feedback (Phosphorus)
        p_drag = 0.0
        if current_nutrients and "P" in current_nutrients:
            p_drag = self.xi_p * loss_step * max(0.0, current_nutrients["P"])
            
        mesh_sub = self.kappa_er * accum_loss
        bedrock = h_next <= 0.05
        
        return {
            "h_mm": h_next,
            "dh_dt": dh_dt,
            "loss_step_mm": loss_step,
            "accum_loss_mm": accum_loss,
            "w_cc_mm": w_cc,
            "w_pmp_mm": w_pmp,
            "veg_cover_factor": veg_cover,
            "p_drag_kg_ha": p_drag,
            "mesh_subsidence_m": mesh_sub,
            "bedrock_exposed": bedrock
        }
