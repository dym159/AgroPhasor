"""
Adaptador de Integración de Fuentes de Datos Satelitales y Agronómicas para EDO 4.
AgroPhasor - Qillawasi / Universidad Nacional de Ingeniería.

Mapea, normaliza y alimenta las 22 fuentes de datos satelitales y de campo (NASA, USDA, USGS, FAO)
a los parámetros, variables exógenas y estados del motor de EDO 4 (Crecimiento de Biomasa B_{i,j}(t)):

1.  NASA POWER: Radiación solar incidente (ALLSKY_SFC_SW_DWN), T2M, RH2M.
2.  SMAP: Humedad del suelo en la zona radicular W(t) y detección temprana de estrés hídrico.
3.  GPM & IMERG: Precipitación acumulada P0(t) para recarga del balance radicular.
4.  Landsat y MODIS/VIIRS: Series temporales de NDVI / EVI para contrastar B(t).
5.  SRTM: Elevación (z), pendiente (theta) y orientación (psi) para proyectar f_rad.
6.  ECOSTRESS: Temperatura superficial de dosel (LST) y evapotranspiración (ET).
7.  USDA Ag Data Commons: Ensayos agronómicos, fenología local y parámetros de manejo.
8.  Web Soil Survey (WSS): Mapas oficiales de suelo, capacidad de infiltración y drenaje.
9.  Cropland Data Layer (CDL/CropScape): Rotación histórica (30m) y cultivos basales.
10. PRISM Climate Data: Climatología de alta resolución corregida topográficamente.
11. USDA NRCS SSURGO/STATSGO2: Materia orgánica (OM), CIC y capacidad de campo (Wcc, Wpmp).
12. NAIP: Ortoimágenes aéreas de 1 m para calibración de cobertura foliar fina.
13. USGS NLCD: Clasificación de cobertura del suelo y zonas de amortiguamiento.
14. NLDAS / GLDAS: Asimilación continua de variables agroclimáticas subdiarias.
15. FAO GAEZ: Potencial agroecológico regional y techo genético de biomasa (B_max).
16. CoCoRaHS: Validación in-situ comunitaria de lluvia para calibrar GPM.
17. USGS NWIS: Caudales y acuíferos para determinar disponibilidad de riego.
18. USDA AMS Market News: Precios de mercado de materias primas (P_mercado) para el margen de Y_k.
19. USDA NASS QuickStats: Estadísticas históricas de rendimiento y calibración de HI.
20. OpenET: Evapotranspiración real a escala de parcela para balance de agua.
21. USFS LANDFIRE: Dinámica de cobertura vegetal y biomasa perenne circundante.
22. GEDI: Mediciones Lidar Nivel 4 de estructura y biomasa aérea sobre el terreno.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

from backend.models.crop_parameters import CropParameters, get_crop_parameters
from backend.core.topoclimatic import topographic_solar_factor, lapse_rate_air_temperature
from backend.core.edo4_engine import (
    solve_edo4_step,
    execute_harvest_event,
    biomass_to_satellite_ndvi,
    biomass_to_canopy_cover,
    satellite_ndvi_to_biomass,
    EDO4StepOutput,
    EDO4HarvestResult
)
from backend.core.satellite_calibration import calibrate_edo4_biomass


@dataclass
class EnvironmentalForcingEDO4:
    """Vector consolidado de forzamiento biofísico diario para una celda (i, j)."""
    date_str: str
    f_rad_daily_mj_m2: float         # Radiación solar incidente proyectada (NASA POWER + SRTM)
    temp_canopy_c: float             # Temperatura efectiva del dosel (EDO 1 / ECOSTRESS / NASA POWER)
    soil_water_mm: float             # Humedad útil en zona radicular (SMAP / EDO 2 / SSURGO)
    nitrogen_kg_ha: float            # Nitrógeno disponible en suelo (SSURGO / Ag Data Commons / EDO 3)
    phosphorus_kg_ha: float          # Fósforo asimilable en suelo (SSURGO / EDO 3)
    potassium_kg_ha: float           # Potasio asimilable en suelo (SSURGO / EDO 3)
    satellite_observed_ndvi: Optional[float] = None  # NDVI observado (Landsat / MODIS / Sentinel-2)
    observed_biomass_gedi_t_ha: Optional[float] = None  # Biomasa observada por Lidar GEDI L4


class EDO4DataAdapter:
    """
    Adaptador unificado que transforma entradas satelitales y edáficas en el flujo
    de forzamiento y calibración requerido por EDO 4.
    """

    @staticmethod
    def build_daily_forcing(
        nasa_power_day: Dict[str, float],
        cell_terrain: Dict[str, float],
        soil_smap_s2: Dict[str, float],
        nutrients_ssurgo: Dict[str, float],
        ecostress_lst_c: Optional[float] = None,
        landsat_ndvi: Optional[float] = None,
        gedi_biomass_t_ha: Optional[float] = None,
        date_str: str = "2026-01-01"
    ) -> EnvironmentalForcingEDO4:
        """
        Construye el vector de forzamiento diario combinando satélites y modelos de terreno:
        
        - f_rad: ALLSKY_SFC_SW_DWN de NASA POWER modulado por factor topográfico SRTM G(theta, psi).
        - temp_canopy: Si ECOSTRESS LST está disponible se utiliza directamente como temperatura
          real del dosel; si no, se usa T2M de NASA POWER ajustada por gradiente altitudinal SRTM.
        - soil_water: Humedad radicular derivada de SMAP GWETROOT combinada con Wcc de SSURGO.
        - nutrients: N, P, K iniciales o actualizados calibrados con SSURGO / Ag Data Commons.
        """
        # 1. Radiación incidente (NASA POWER) y proyección topográfica (SRTM)
        rad_raw_mj = float(nasa_power_day.get("ALLSKY_SFC_SW_DWN", 18.5))
        slope_deg = float(cell_terrain.get("slope_deg", 0.0))
        aspect_deg = float(cell_terrain.get("aspect_deg", 180.0))
        g_topo = topographic_solar_factor(slope_deg, aspect_deg)
        f_rad_projected = max(0.0, rad_raw_mj * g_topo)

        # 2. Temperatura del dosel (ECOSTRESS LST vs NASA POWER T2M + SRTM lapse rate)
        if ecostress_lst_c is not None and not math.isnan(ecostress_lst_c):
            t_canopy = float(ecostress_lst_c)
        else:
            t_nasa = float(nasa_power_day.get("T2M", 18.0))
            alt_m = float(cell_terrain.get("altitude_m", 3000.0))
            ref_alt_m = float(cell_terrain.get("ref_altitude_m", 3000.0))
            t_canopy = lapse_rate_air_temperature(t_nasa, alt_m, ref_alt_m)

        # 3. Humedad radicular (NASA SMAP + SSURGO / WSS)
        # Si se provee fracción SMAP (0.0 a 1.0), se escala por la capacidad de campo de SSURGO
        w_fc = float(nutrients_ssurgo.get("W_cc_mm", 100.0))
        w_pmp = float(nutrients_ssurgo.get("W_pmp_mm", 30.0))
        if "smap_wetness" in soil_smap_s2:
            smap_wet = max(0.0, min(1.0, float(soil_smap_s2["smap_wetness"])))
            w_soil = w_pmp + smap_wet * (w_fc - w_pmp)
        else:
            w_soil = float(soil_smap_s2.get("soil_water_mm", 65.0))

        # 4. Macronutrientes (USDA SSURGO / Ag Data Commons / EDO 3)
        n_avail = float(nutrients_ssurgo.get("N_kg_ha", 45.0))
        p_avail = float(nutrients_ssurgo.get("P_kg_ha", 25.0))
        k_avail = float(nutrients_ssurgo.get("K_kg_ha", 60.0))

        return EnvironmentalForcingEDO4(
            date_str=date_str,
            f_rad_daily_mj_m2=round(f_rad_projected, 2),
            temp_canopy_c=round(t_canopy, 2),
            soil_water_mm=round(w_soil, 2),
            nitrogen_kg_ha=round(n_avail, 2),
            phosphorus_kg_ha=round(p_avail, 2),
            potassium_kg_ha=round(k_avail, 2),
            satellite_observed_ndvi=landsat_ndvi,
            observed_biomass_gedi_t_ha=gedi_biomass_t_ha
        )

    @staticmethod
    def calibrate_crop_ceiling_from_faog_and_nass(
        crop_id: str,
        fao_gaez_yield_potential_t_ha: Optional[float] = None,
        nass_historical_county_yield_t_ha: Optional[float] = None,
        gedi_max_biomass_t_ha: Optional[float] = None
    ) -> CropParameters:
        """
        Calibra los parámetros de EDO 4 del cultivo utilizando las fuentes oficiales:
        - B_max_t_ha: acotado por FAO GAEZ y biomasa estructural de GEDI L4.
        - HI: calibrado contra estadísticas de producción de USDA NASS QuickStats.
        """
        base_crop = get_crop_parameters(crop_id)
        
        # Ajuste de B_max_t_ha
        candidates = [base_crop.B_max_t_ha]
        if fao_gaez_yield_potential_t_ha is not None and fao_gaez_yield_potential_t_ha > 0:
            # Si FAO GAEZ provee rendimiento comercial potencial, B_max ≈ Y_pot / HI
            hi_est = getattr(base_crop, "HI", 0.45)
            b_max_fao = fao_gaez_yield_potential_t_ha / hi_est
            candidates.append(b_max_fao)
            
        if gedi_max_biomass_t_ha is not None and gedi_max_biomass_t_ha > 0:
            candidates.append(gedi_max_biomass_t_ha)

        calibrated_b_max = round(sum(candidates) / len(candidates), 2)

        # Ajuste de Harvest Index HI con USDA NASS
        calibrated_hi = base_crop.HI
        if nass_historical_county_yield_t_ha is not None and nass_historical_county_yield_t_ha > 0:
            # Verificación de plausibilidad
            implied_hi = nass_historical_county_yield_t_ha / calibrated_b_max
            if 0.10 <= implied_hi <= 0.85:
                calibrated_hi = round(0.5 * (base_crop.HI + implied_hi), 3)

        # Retorna el cultivo con parámetros actualizados
        # Como CropParameters es frozen dataclass, usamos __dict__ para reconstruir
        crop_dict = dict(base_crop.__dict__)
        crop_dict["B_max_t_ha"] = calibrated_b_max
        crop_dict["HI"] = calibrated_hi
        return CropParameters(**crop_dict)

    @staticmethod
    def calibrate_kp_from_ndvi_series(
        forcing_series: List[EnvironmentalForcingEDO4],
        crop: CropParameters,
        b0_t_ha: Optional[float] = None
    ) -> Tuple[CropParameters, Dict[str, Any]]:
        """
        Calibra en tiempo real `kp_c_t_ha_MJ_m2` de `crop` escalando la curva
        normalizada B(t)/B_max contra la serie `satellite_observed_ndvi`.
        """
        res = calibrate_edo4_biomass(
            crop=crop,
            f_rad_series_mj_m2=[f.f_rad_daily_mj_m2 for f in forcing_series],
            t_canopy_series_c=[f.temp_canopy_c for f in forcing_series],
            soil_water_series_mm=[f.soil_water_mm for f in forcing_series],
            nitrogen_series_kg_ha=[f.nitrogen_kg_ha for f in forcing_series],
            phosphorus_series_kg_ha=[f.phosphorus_kg_ha for f in forcing_series],
            potassium_series_kg_ha=[f.potassium_kg_ha for f in forcing_series],
            observed_ndvi_series=[f.satellite_observed_ndvi for f in forcing_series],
            b0_t_ha=b0_t_ha,
        )
        return res.calibrated_crop, {
            "kp_c_prior": res.kp_c_prior,
            "kp_c_calibrated": res.kp_c_t_ha_MJ_m2,
            "scale_factor": res.scale_factor,
            "rmse_ndvi_before": res.rmse_ndvi_before,
            "rmse_ndvi_after": res.rmse_ndvi_after,
            "observations_used": res.observations_used,
            "converged": res.converged,
        }

    @staticmethod
    def simulate_crop_and_contrast_satellite(
        forcing_series: List[EnvironmentalForcingEDO4],
        crop: CropParameters,
        b0_t_ha: Optional[float] = None,
        residue_fraction_rres: float = 0.30,
        market_price_usd_t: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta la simulación de ciclo completo de EDO 4 y la contrasta con:
        1. Las observaciones de NDVI satelital (Landsat 8/9, Sentinel-2, MODIS/VIIRS).
        2. La estimación de biomasa de Lidar GEDI L4.
        3. El rendimiento comercial y los ingresos según USDA AMS Market News.
        """
        curr_b = b0_t_ha if b0_t_ha is not None else crop.B0_t_ha
        
        sim_records = []
        ndvi_residuals = []
        gedi_residuals = []

        for f in forcing_series:
            step_res = solve_edo4_step(
                b_current_t_ha=curr_b,
                f_rad_daily_mj_m2=f.f_rad_daily_mj_m2,
                temp_canopy_c=f.temp_canopy_c,
                soil_water_mm=f.soil_water_mm,
                nitrogen_kg_ha=f.nitrogen_kg_ha,
                phosphorus_kg_ha=f.phosphorus_kg_ha,
                potassium_kg_ha=f.potassium_kg_ha,
                crop=crop,
                q_is_crop=True
            )
            curr_b = step_res.biomass_t_ha

            # Contraste satelital Landsat / MODIS NDVI
            ndvi_err = None
            if f.satellite_observed_ndvi is not None:
                ndvi_err = round(step_res.simulated_ndvi - f.satellite_observed_ndvi, 3)
                ndvi_residuals.append(abs(ndvi_err))

            # Contraste de biomasa GEDI L4
            gedi_err = None
            if f.observed_biomass_gedi_t_ha is not None:
                gedi_err = round(curr_b - f.observed_biomass_gedi_t_ha, 3)
                gedi_residuals.append(abs(gedi_err))

            sim_records.append({
                "date": f.date_str,
                "biomass_t_ha": curr_b,
                "db_dt": step_res.db_dt,
                "ndvi_simulated": step_res.simulated_ndvi,
                "ndvi_observed": f.satellite_observed_ndvi,
                "ndvi_residual": ndvi_err,
                "gedi_biomass_observed": f.observed_biomass_gedi_t_ha,
                "gedi_residual": gedi_err,
                "eta_thermal": step_res.eta_thermal,
                "eta_water": step_res.eta_water,
                "eta_nutrients": step_res.eta_nutrients,
                "limiting_nutrient": step_res.limiting_nutrient,
                "canopy_cover": step_res.canopy_cover_fraction
            })

        # Cosecha al final del ciclo
        harvest = execute_harvest_event(
            biomass_pre_harvest_t_ha=curr_b,
            crop=crop,
            residue_fraction_rres=residue_fraction_rres,
            market_price_usd_t=market_price_usd_t
        )

        mean_ndvi_mae = round(sum(ndvi_residuals) / len(ndvi_residuals), 3) if ndvi_residuals else None
        mean_gedi_mae = round(sum(gedi_residuals) / len(gedi_residuals), 3) if gedi_residuals else None

        return {
            "crop": crop.name,
            "days_simulated": len(forcing_series),
            "final_biomass_t_ha": round(curr_b, 3),
            "harvest_result": {
                "commercial_yield_t_ha": harvest.commercial_yield_t_ha,
                "residue_left_t_ha": harvest.residue_left_t_ha,
                "gross_revenue_usd_ha": harvest.gross_revenue_usd_ha,
                "net_margin_usd_ha": harvest.net_margin_usd_ha,
                "market_price_usd_t": harvest.market_price_usd_t
            },
            "satellite_validation": {
                "ndvi_points_evaluated": len(ndvi_residuals),
                "ndvi_mean_absolute_error": mean_ndvi_mae,
                "gedi_points_evaluated": len(gedi_residuals),
                "gedi_biomass_mae_t_ha": mean_gedi_mae
            },
            "daily_records": sim_records
        }
