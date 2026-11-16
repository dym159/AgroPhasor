"""
Agro-Physical Unit Test Suite for ODE 4 (AgroPhasor).
Verifies:
1. Asymptotic logistic growth and biological bounding 0 <= B(t) <= B_max.
2. Liebig's Law of the Minimum: chemical collapse upon N, P, or K deficiency.
3. Photosynthetic thermal comfort envelope eta_T and arrest on frost/lethal heat.
4. Root-zone water regulation f_W (SMAP) and drought arrest.
5. Transition / fallow regime: strict exponential stover decay B(t) = B0 * exp(-k_dec * t).
6. Hybrid discrete jumps at harvest (Y_k, residue r_res) and planting (B0).
7. Satellite remote sensing projection & calibration (Landsat/MODIS NDVI and GEDI).
8. Catalog validation via EDO4Validator.
9. Integration with Multi-Source Satellite Data Adapter (NASA POWER, SMAP, SRTM, ECOSTRESS, USDA).
"""

import math
import os
import unittest

from backend.models.crop_parameters import get_crop_parameters, CropParameters
from backend.core.edo4_engine import (
    solve_edo4_step,
    execute_harvest_event,
    thermal_photosynthetic_efficiency,
    water_limitation_factor,
    liebig_nutrient_efficiency,
    biomass_to_canopy_cover,
    biomass_to_satellite_ndvi,
    satellite_ndvi_to_biomass,
    simulate_edo4_timeseries
)
from backend.models.edo4_validator import validate_edo4_catalog
from backend.services.edo4_data_adapter import (
    EDO4DataAdapter,
    EnvironmentalForcingEDO4
)
from backend.services.parcel_edo4 import ParcelEDO4Service


class TestEDO4Engine(unittest.TestCase):

    def setUp(self):
        self.crop_maiz = get_crop_parameters("maiz")
        self.crop_frijol = get_crop_parameters("frijol")
        self.crop_papa = get_crop_parameters("papa")

    def test_asymptotic_logistic_saturation_and_bounds(self):
        """
        Criterion 1: Growth and Strict Physical Bounding 0 <= B(t) <= B_max.
        Under continuous ideal environmental conditions, biomass must grow rapidly
        initially and decelerate asymptotically toward B_max without exceeding it.
        """
        crop = self.crop_maiz
        b_curr = crop.B0_t_ha  # 0.25 t/ha
        b_max = crop.B_max_t_ha  # 22.0 t/ha

        # Simulate 180 days with optimal forcing
        f_rad = 22.0  # MJ/m²·day
        t_canopy = crop.T_opt  # 25°C
        w_soil = 80.0  # mm (> W_crit)
        n_avail = 120.0  # kg/ha
        p_avail = 80.0   # kg/ha
        k_avail = 150.0  # kg/ha

        trajectory = [b_curr]
        growth_rates = []

        for _ in range(180):
            step = solve_edo4_step(
                b_current_t_ha=b_curr,
                f_rad_daily_mj_m2=f_rad,
                temp_canopy_c=t_canopy,
                soil_water_mm=w_soil,
                nitrogen_kg_ha=n_avail,
                phosphorus_kg_ha=p_avail,
                potassium_kg_ha=k_avail,
                crop=crop
            )
            b_curr = step.biomass_t_ha
            trajectory.append(b_curr)
            growth_rates.append(step.db_dt)

            self.assertGreaterEqual(b_curr, 0.0)
            self.assertLessEqual(b_curr, b_max)

        # Final biomass should grow substantially and approach asymptotic equilibrium
        self.assertGreater(trajectory[-1], 8.0)
        self.assertLessEqual(trajectory[-1], b_max)

        # Growth rate must decelerate as biomass approaches B_max
        peak_rate = max(growth_rates)
        final_rate = growth_rates[-1]
        self.assertLess(final_rate, peak_rate)

    def test_liebig_minimum_nutrient_law(self):
        """
        Criterion 2: Liebig's Law of the Minimum (PDF Sec. 3.3 and 1.2):
        eta_N = min( N/(N+KN), P/(P+KP), K/(K+KK) ).
        If a single nutrient is depleted (e.g. N = 0), the chemical factor collapses to 0
        and halts net photosynthesis regardless of abundant P and K.
        """
        crop = self.crop_maiz
        kn, kp, kk = crop.K_N, crop.K_P, crop.K_K

        # Case 1: All balanced
        eta_bal, lim_bal = liebig_nutrient_efficiency(kn, kp, kk, kn, kp, kk)
        self.assertAlmostEqual(eta_bal, 0.5, places=2)

        # Case 2: Severely Nitrogen-depleted (N = 0.5 kg/ha, P = 100, K = 150)
        eta_n_dep, lim_n = liebig_nutrient_efficiency(0.5, 100.0, 150.0, kn, kp, kk)
        self.assertEqual(lim_n, "N")
        self.assertLess(eta_n_dep, 0.05)

        # Verify in solve_edo4_step
        step_n_dep = solve_edo4_step(
            b_current_t_ha=2.0,
            f_rad_daily_mj_m2=20.0,
            temp_canopy_c=25.0,
            soil_water_mm=70.0,
            nitrogen_kg_ha=0.1,  # Practically zero
            phosphorus_kg_ha=100.0,
            potassium_kg_ha=100.0,
            crop=crop
        )
        self.assertEqual(step_n_dep.limiting_nutrient, "N")
        self.assertTrue(step_n_dep.is_nutrient_arrest)
        # With photosynthesis blocked, maintenance respiration yields negative net change
        self.assertLess(step_n_dep.db_dt, 0.0)

        # Case 3: Phosphorus limiting
        eta_p_dep, lim_p = liebig_nutrient_efficiency(100.0, 0.2, 100.0, kn, kp, kk)
        self.assertEqual(lim_p, "P")
        self.assertLess(eta_p_dep, 0.05)

        # Case 4: Potassium limiting
        eta_k_dep, lim_k = liebig_nutrient_efficiency(100.0, 100.0, 0.2, kn, kp, kk)
        self.assertEqual(lim_k, "K")
        self.assertLess(eta_k_dep, 0.05)

    def test_thermal_photosynthetic_envelope_and_frost_arrest(self):
        """
        Criterion 3: Photosynthetic Thermal Envelope eta_T(T) (PDF Sec. 3.3):
        - At T = T_opt: eta_T = 1.0 (maximum photosynthesis).
        - At T_opt +- delta_T_tol: eta_T = 0.0.
        - On frost T <= T_frost or lethal heat T >= T_lethal: strict arrest eta_T = 0.
        """
        crop = self.crop_maiz  # T_opt = 25°C, dT_tol = 14°C, T_frost = 0°C, T_lethal = 42°C

        # 1. Optimal
        eta_opt = thermal_photosynthetic_efficiency(25.0, crop.T_opt, crop.delta_T_tol)
        self.assertAlmostEqual(eta_opt, 1.0, places=2)

        # 2. Symmetric deviation
        eta_warm = thermal_photosynthetic_efficiency(32.0, crop.T_opt, crop.delta_T_tol)
        eta_cool = thermal_photosynthetic_efficiency(18.0, crop.T_opt, crop.delta_T_tol)
        self.assertAlmostEqual(eta_warm, eta_cool, places=2)
        self.assertLess(eta_warm, 1.0)
        self.assertGreater(eta_warm, 0.0)

        # 3. Severe frost (T = -2°C)
        eta_frost = thermal_photosynthetic_efficiency(
            -2.0, crop.T_opt, crop.delta_T_tol, crop.T_frost, crop.T_lethal
        )
        self.assertEqual(eta_frost, 0.0)

        # Verify in solve_edo4_step
        step_frost = solve_edo4_step(
            b_current_t_ha=5.0,
            f_rad_daily_mj_m2=20.0,
            temp_canopy_c=-1.5,
            soil_water_mm=60.0,
            nitrogen_kg_ha=50.0,
            phosphorus_kg_ha=30.0,
            potassium_kg_ha=60.0,
            crop=crop
        )
        self.assertEqual(step_frost.eta_thermal, 0.0)
        self.assertTrue(step_frost.is_thermal_arrest)

        # 4. Lethal heat (T = 44°C)
        eta_lethal = thermal_photosynthetic_efficiency(
            44.0, crop.T_opt, crop.delta_T_tol, crop.T_frost, crop.T_lethal
        )
        self.assertEqual(eta_lethal, 0.0)

    def test_water_limitation_and_drought_arrest(self):
        """
        Criterion 4: Water Limitation Factor f_W(W) (PDF Sec. 3.2.4 & SMAP):
        - W >= W_crit: f_W = 1.0.
        - W <= W_pmp: f_W = 0.0 (photosynthetic arrest from drought).
        """
        crop = self.crop_maiz
        w_pmp = crop.W_pmp  # 20 mm
        w_crit = crop.W_crit  # 50 mm

        # At permanent wilting point
        fw_wilting = water_limitation_factor(w_pmp - 5.0, w_pmp, w_crit)
        self.assertAlmostEqual(fw_wilting, (w_pmp - 5) / (w_pmp - 5 + max(1, .5 * (w_crit - w_pmp))))

        # Above critical threshold (comfort)
        fw_optimal = water_limitation_factor(w_crit + 20.0, w_pmp, w_crit)
        self.assertGreaterEqual(fw_optimal, 0.70)

        # Verify in solve_edo4_step
        step_drought = solve_edo4_step(
            b_current_t_ha=4.0,
            f_rad_daily_mj_m2=20.0,
            temp_canopy_c=25.0,
            soil_water_mm=0.0,  # Zero water
            nitrogen_kg_ha=50.0,
            phosphorus_kg_ha=30.0,
            potassium_kg_ha=60.0,
            crop=crop
        )
        self.assertEqual(step_drought.eta_water, 0.0)
        self.assertTrue(step_drought.is_drought_arrest)
        self.assertLess(step_drought.db_dt, 0.0)

    def test_bare_soil_transition_regime_and_residue_decomposition(self):
        """
        Criterion 5: Transition / Stover Regime (q = Transition, PDF Sec. 3.2.4):
        dB/dt = - k_dec * B.
        Remaining residue biomass must decay monotonically along the exact
        analytical curve: B(t) = B0 * exp(-k_dec * t).
        """
        crop = self.crop_maiz
        b_residue_initial = 3.0  # 3 t/ha of crop residue
        k_dec = 0.025  # 1/day

        b_curr = b_residue_initial
        t_canopy = 20.0  # At 20°C Q10 factor = 1.0

        for day in range(1, 11):
            step = solve_edo4_step(
                b_current_t_ha=b_curr,
                f_rad_daily_mj_m2=20.0,
                temp_canopy_c=t_canopy,
                soil_water_mm=60.0,
                nitrogen_kg_ha=50.0,
                phosphorus_kg_ha=30.0,
                potassium_kg_ha=60.0,
                crop=crop,
                q_is_crop=False,  # Transition mode
                k_dec_daily=k_dec
            )
            b_curr = step.biomass_t_ha

            # Compare against exact analytical solution
            expected_b = b_residue_initial * math.exp(-k_dec * day)
            self.assertAlmostEqual(b_curr, expected_b, places=3)
            self.assertEqual(step.gross_growth_t_ha, 0.0)
            self.assertFalse(step.is_growth_active)

    def test_discrete_harvest_event_and_market_economics(self):
        """
        Criterion 6: Discrete Harvest Jump and Economic Valuation (PDF Sec. 3.4 & 1.1):
        Y_k = HI * (1 - r_res) * B(t_s^-)
        B(t_s^+) = r_res * B(t_s^-)
        Gross Revenue = Y_k * P_market (USDA AMS)
        """
        crop = self.crop_maiz  # HI = 0.48, price = 220 USD/t, base_cost = 650 USD/ha
        b_pre_harvest = 10.0  # 10 t/ha standing biomass prior to harvest
        r_res = 0.30  # 30% retained as crop residue

        harvest = execute_harvest_event(
            biomass_pre_harvest_t_ha=b_pre_harvest,
            crop=crop,
            residue_fraction_rres=r_res,
            market_price_usd_t=220.0
        )

        expected_yield = 0.48 * (1.0 - 0.30) * 10.0  # 3.36 t/ha
        expected_residue = 0.30 * 10.0               # 3.00 t/ha
        expected_revenue = expected_yield * 220.0     # 739.20 USD/ha
        expected_net_margin = expected_revenue - 650.0 # 89.20 USD/ha

        self.assertAlmostEqual(harvest.commercial_yield_t_ha, expected_yield, places=2)
        self.assertAlmostEqual(harvest.residue_left_t_ha, expected_residue, places=2)
        self.assertAlmostEqual(harvest.gross_revenue_usd_ha, expected_revenue, places=2)
        self.assertAlmostEqual(harvest.net_margin_usd_ha, expected_net_margin, places=2)

    def test_satellite_ndvi_and_canopy_cover_mapping(self):
        """
        Criterion 7: Satellite Remote Sensing Projection (Landsat / MODIS NDVI):
        - B = 0 -> NDVI = NDVI_soil (0.15) and cover = 0.0.
        - High B -> NDVI saturates asymptotically at NDVI_max (0.88) and cover -> 1.0.
        - Empirical inversion: satellite_ndvi_to_biomass inverts cleanly.
        """
        # Bare soil
        ndvi_bare = biomass_to_satellite_ndvi(0.0)
        self.assertAlmostEqual(ndvi_bare, 0.15, places=2)
        cover_bare = biomass_to_canopy_cover(0.0)
        self.assertEqual(cover_bare, 0.0)

        # Well-developed crop
        ndvi_dense = biomass_to_satellite_ndvi(15.0)
        self.assertGreater(ndvi_dense, 0.85)
        cover_dense = biomass_to_canopy_cover(15.0)
        self.assertGreater(cover_dense, 0.99)

        # Inversion
        b_reconstructed = satellite_ndvi_to_biomass(ndvi_dense, b_max_t_ha=20.0)
        self.assertGreater(b_reconstructed, 5.0)

    def test_edo4_validator_success_and_failure_detection(self):
        """
        Criterion 8: Agro-Physical Validator for ODE 4 Catalogs:
        - Properly validates the official crop_catalog.json.
        - Rejects catalogs with kp_c <= 0 or B_max <= B0.
        """
        # Official catalog
        res_valid = validate_edo4_catalog("backend/data/crop_catalog.json")
        self.assertTrue(res_valid["valid"])
        self.assertGreater(res_valid["crops_validated_count"], 0)

        # Invalid catalog
        invalid_data = {
            "constantes_globales": {
                "k_dec_dia": 0.025,
                "lambda_B_ha_t": 0.45,
                "Q10": 2.0
            },
            "cultivos": {
                "CultivoInvalido": {
                    "kp_c": -0.05,        # ERROR: negative
                    "B_max_t_ha": 5.0,
                    "B0_t_ha": 10.0,       # ERROR: B0 > B_max
                    "km_c_dia": 0.008,
                    "HI": 1.25,            # ERROR: HI > 1.0
                    "K_N": 30.0,
                    "K_P": 20.0,
                    "K_K": 40.0
                }
            }
        }
        res_invalid = validate_edo4_catalog(invalid_data)
        self.assertFalse(res_invalid["valid"])
        self.assertGreaterEqual(len(res_invalid["errors"]), 3)

    def test_nasa_and_usda_data_adapter_complete_cycle(self):
        """
        Criterion 9: Multi-Source Integration Adapter (NASA POWER, SMAP, ECOSTRESS, SRTM, USDA).
        Runs a 30-day cycle simulating a cell with varying weather forcing,
        Landsat/MODIS NDVI satellite comparison, and FAO GAEZ / GEDI biomass ceiling calibration.
        """
        crop_calibrated = EDO4DataAdapter.calibrate_crop_ceiling_from_faog_and_nass(
            crop_id="maiz",
            fao_gaez_yield_potential_t_ha=9.5,
            nass_historical_county_yield_t_ha=8.8,
            gedi_max_biomass_t_ha=21.0
        )
        self.assertGreater(crop_calibrated.B_max_t_ha, 15.0)

        # Generate 30 days of biophysical forcing
        forcing_series = []
        for d in range(30):
            nasa_day = {
                "ALLSKY_SFC_SW_DWN": 18.0 + 3.0 * math.sin(d * math.pi / 15.0),
                "T2M": 22.0 + 4.0 * math.cos(d * math.pi / 15.0)
            }
            terrain = {"slope_deg": 5.0, "aspect_deg": 180.0, "altitude_m": 3100.0, "ref_altitude_m": 3000.0}
            soil_smap = {"smap_wetness": 0.75 - 0.01 * d}  # Soil gradually drying out
            nutrients = {"W_cc_mm": 90.0, "W_pmp_mm": 25.0, "N_kg_ha": 60.0, "P_kg_ha": 35.0, "K_kg_ha": 80.0}
            
            # Intermittent satellite observations (Landsat NDVI every 8 days)
            obs_ndvi = (0.20 + 0.015 * d) if (d % 8 == 0) else None
            obs_gedi = (0.3 + 0.1 * d) if (d == 16) else None

            f = EDO4DataAdapter.build_daily_forcing(
                nasa_power_day=nasa_day,
                cell_terrain=terrain,
                soil_smap_s2=soil_smap,
                nutrients_ssurgo=nutrients,
                landsat_ndvi=obs_ndvi,
                gedi_biomass_t_ha=obs_gedi,
                date_str=f"2026-05-{d+1:02d}"
            )
            forcing_series.append(f)

        sim_res = EDO4DataAdapter.simulate_crop_and_contrast_satellite(
            forcing_series=forcing_series,
            crop=crop_calibrated,
            b0_t_ha=0.30,
            residue_fraction_rres=0.30,
            market_price_usd_t=230.0
        )

        self.assertEqual(sim_res["days_simulated"], 30)
        self.assertGreater(sim_res["final_biomass_t_ha"], 0.30)
        self.assertGreater(sim_res["harvest_result"]["commercial_yield_t_ha"], 0.0)
        self.assertGreater(sim_res["harvest_result"]["gross_revenue_usd_ha"], 0.0)
        self.assertGreater(sim_res["satellite_validation"]["ndvi_points_evaluated"], 0)
        self.assertIsNotNone(sim_res["satellite_validation"]["ndvi_mean_absolute_error"])

    def test_parcel_edo4_service_spatial_grid(self):
        """
        Criterion 10: 2.5D Spatial Grid Simulation (ParcelEDO4Service).
        Simulates a heterogeneous parcel with varying slopes and altitudes (SRTM),
        verifying spatially differentiated responses in biomass, NDVI, and yield.
        """
        grid = [
            {"cell_id": "0_0", "altitude_m": 3050.0, "slope_deg": 2.0, "aspect_deg": 180.0},
            {"cell_id": "0_1", "altitude_m": 3250.0, "slope_deg": 18.0, "aspect_deg": 90.0}
        ]
        nasa_data = {
            "T2M": {f"20260101{h:02d}": 16.0 + 6.0 * math.sin(h * math.pi / 12) for h in range(24)},
            "ALLSKY_SFC_SW_DWN": {f"20260101{h:02d}": max(0.0, 2.5 * math.sin(h * math.pi / 12)) for h in range(24)}
        }
        res = ParcelEDO4Service.simulate_grid_cells(
            grid_cells=grid,
            crop_id="maiz",
            nasa_hourly_data=nasa_data,
            soil_water_mm=65.0,
            simulation_days=20
        )
        self.assertEqual(res["crop"], "Maize")
        self.assertEqual(res["cells_simulated"], 2)
        self.assertGreater(res["mean_biomass_t_ha"], 0.0)
        self.assertGreater(res["mean_yield_t_ha"], 0.0)
        self.assertEqual(len(res["cells"]), 2)


if __name__ == "__main__":
    unittest.main()
