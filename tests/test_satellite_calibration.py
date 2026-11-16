"""
Unit Test Suite for the Real-Time Satellite Calibration Engine
(`backend/core/satellite_calibration.py`), verifying the 3 methods of `guia_calibracion_satelital`
defined in `gemini-code.json`:
1. Thermal ODE 1: Nonlinear least squares over a 30-60 day window (ECOSTRESS LST / NASA POWER TS).
2. Hydrological ODE 2: Post-rain drydown rate fitting following GPM/IMERG events (SMAP + OpenET).
3. Biomass ODE 4: Normalized curve scaling B(t)/B_max against satellite vigor (Sentinel-2 / Landsat NDVI).
"""

from dataclasses import replace
import math
from time import perf_counter
import unittest

from backend.models.crop_parameters import get_crop_parameters
from backend.core.edo1_engine import solve_edo1_step
from backend.core.edo2_engine import solve_edo2_step
from backend.core.edo4_engine import solve_edo4_step, biomass_to_satellite_ndvi
from backend.core.satellite_calibration import (
    calibrate_edo1_thermal,
    calibrate_edo2_hydrology,
    calibrate_edo4_biomass,
    calibrate_parcel_realtime,
)


class TestSatelliteCalibration(unittest.TestCase):

    def test_edo1_thermal_nonlinear_least_squares_recovery(self):
        """
        Verifies that `calibrate_edo1_thermal` tunes `h_c_W_m2C`, `Cp_c_J_m2C`, and `h_suelo_W_m2C`
        while reducing RMSE against ECOSTRESS LST / NASA POWER TS observations over a 45-day window.
        """
        prior_crop = get_crop_parameters("maiz")  # hc=28.0, Cp=48000.0
        true_crop = replace(prior_crop, hc=22.5, Cp=41000.0)
        true_soil = replace(
            prior_crop,
            hc=19.5,
            Cp=18000.0,
            alpha=0.72,
            gamma_max=0.0,
            gamma_max_daily_mm=0.0,
            lambda_gamma_max=0.0,
        )

        days = 45
        t_air = [18.0 + 4.0 * math.sin(2.0 * math.pi * d / 15.0) for d in range(days)]
        f_rad = [450.0 + 180.0 * math.cos(2.0 * math.pi * d / 12.0) for d in range(days)]
        rh = [55.0 + 15.0 * math.sin(2.0 * math.pi * d / 10.0) for d in range(days)]
        w_soil = [80.0] * days
        is_crop_flags = [d >= 10 for d in range(days)]  # Bare soil for first 10 days, then crop

        obs_lst = []
        t_curr = t_air[0]
        for d in range(days):
            mod = true_crop if is_crop_flags[d] else true_soil
            step = solve_edo1_step(
                t_current_c=t_curr,
                t_ext_c=t_air[d],
                f_rad_wm2=f_rad[d],
                rh_pct=rh[d],
                soil_water_mm=w_soil[d],
                crop=mod,
                dt_seconds=3600.0,
            )
            t_curr = step.t_canopy_c
            obs_lst.append(t_curr)

        t0 = perf_counter()
        res = calibrate_edo1_thermal(
            crop=prior_crop,
            t_air_series_c=t_air,
            f_rad_series_wm2=f_rad,
            rh_series_pct=rh,
            soil_water_series_mm=w_soil,
            observed_lst_or_ts_c=obs_lst,
            is_crop_series=is_crop_flags,
            reg_weight=0.005,
        )
        elapsed_ms = (perf_counter() - t0) * 1000.0

        self.assertTrue(res.converged)
        self.assertEqual(res.samples_used, 45)
        self.assertLess(res.rmse_after_c, res.rmse_before_c * 0.25)
        self.assertLess(abs(res.h_c_W_m2C - 22.5), abs(res.h_c_prior - 22.5))
        self.assertLess(abs(res.h_suelo_W_m2C - 19.5), abs(res.h_suelo_prior - 19.5))
        self.assertLess(elapsed_ms, 250.0)

    def test_edo2_hydrology_post_rain_drydown_calibration(self):
        """
        Verifies that `calibrate_edo2_hydrology` detects post-rain drydown pulses
        (GPM/IMERG -> SMAP + OpenET) and recovers `kd` and `E_suelo0_mm_dia`.
        """
        crop = get_crop_parameters("frijol")
        days = 40
        precip = [25.0 if d in (0, 12, 25) else 0.0 for d in range(days)]
        t_air = [21.0] * days
        rh = [58.0] * days
        slope = 14.0

        true_kd = 0.105
        true_es0 = 5.1

        smap_w = [140.0]
        openet = [0.0]
        for d in range(1, days):
            step = solve_edo2_step(
                w_current_mm=smap_w[-1],
                precip_mm=precip[d],
                t_air_c=t_air[d],
                rh_pct=rh[d],
                slope_deg=slope,
                crop=crop,
                kd=true_kd,
                e_suelo0=true_es0,
                biomass_t_ha=crop.B_max_t_ha * 0.35,
            )
            smap_w.append(step.soil_water_mm)
            openet.append(step.etc_mm)

        res = calibrate_edo2_hydrology(
            crop=crop,
            precip_series_mm=precip,
            t_air_series_c=t_air,
            rh_series_pct=rh,
            smap_soil_water_series_mm=smap_w,
            slope_deg=slope,
            openet_series_mm_day=openet,
            reg_weight=0.005,
        )

        self.assertEqual(res.rain_events_detected, 3)
        self.assertGreater(res.drydown_steps_used, 25)
        self.assertLess(res.rmse_after_mm, res.rmse_before_mm * 0.35)
        self.assertLess(abs(res.kd_calibrated - true_kd), abs(res.kd_prior - true_kd))
        self.assertLess(abs(res.e_suelo0_mm_dia - true_es0), abs(res.e_suelo0_prior - true_es0))
        self.assertIn(res.closest_ssurgo_class, res.hidrologia_por_clase_drenaje_ssurgo)

    def test_edo4_biomass_ndvi_scaling_calibration(self):
        """
        Verifies that `calibrate_edo4_biomass` scales `kp_c_t_ha_MJ_m2` against a
        Sentinel-2/Landsat NDVI time series while reducing NDVI error.
        """
        prior_crop = get_crop_parameters("papa")  # kp_c = 0.016
        true_crop = replace(prior_crop, kp_c=0.0205)

        days = 45
        f_rad = [19.5] * days
        t_canopy = [18.0] * days
        w_soil = [90.0] * days
        n_s = [95.0] * days
        p_s = [45.0] * days
        k_s = [130.0] * days

        b_curr = true_crop.B0_t_ha
        obs_ndvi = []
        for d in range(days):
            step = solve_edo4_step(
                b_current_t_ha=b_curr,
                f_rad_daily_mj_m2=f_rad[d],
                temp_canopy_c=t_canopy[d],
                soil_water_mm=w_soil[d],
                nitrogen_kg_ha=n_s[d],
                phosphorus_kg_ha=p_s[d],
                potassium_kg_ha=k_s[d],
                crop=true_crop,
            )
            b_curr = step.biomass_t_ha
            # Simulate cloud-free overpasses every 5 days (Sentinel-2 revisit)
            obs_ndvi.append(biomass_to_satellite_ndvi(b_curr) if d % 5 == 0 else None)

        res = calibrate_edo4_biomass(
            crop=prior_crop,
            f_rad_series_mj_m2=f_rad,
            t_canopy_series_c=t_canopy,
            soil_water_series_mm=w_soil,
            nitrogen_series_kg_ha=n_s,
            phosphorus_series_kg_ha=p_s,
            potassium_series_kg_ha=k_s,
            observed_ndvi_series=obs_ndvi,
            reg_weight=0.002,
        )

        self.assertTrue(res.converged)
        self.assertEqual(res.observations_used, 9)
        self.assertLess(res.rmse_ndvi_after, res.rmse_ndvi_before * 0.25)
        self.assertGreater(res.kp_c_t_ha_MJ_m2, res.kp_c_prior)
        self.assertAlmostEqual(res.kp_c_t_ha_MJ_m2, 0.0205, delta=0.0015)

    def test_unified_realtime_pipeline_and_guardrails(self):
        """
        Verifies the `calibrate_parcel_realtime` orchestrator over a 45-day window.
        """
        days = 45
        window_data = {
            "T2M": [20.0 + 2.0 * math.sin(d * 0.3) for d in range(days)],
            "TS": [22.5 + 2.2 * math.sin(d * 0.3) for d in range(days)],
            "RH2M": [60.0] * days,
            "ALLSKY_SFC_SW_DWN": [20.0] * days,
            "PRECTOTCORR": [18.0 if d % 14 == 0 else 0.0 for d in range(days)],
            "GWETROOT": [0.75 - 0.02 * (d % 14) for d in range(days)],
            "observed_ndvi_series": [min(0.82, 0.22 + 0.012 * d) if d % 5 == 0 else None for d in range(days)],
        }

        out = calibrate_parcel_realtime(
            crop_id="fresa",
            window_data=window_data,
            slope_deg=10.0,
        )

        self.assertEqual(out["status"], "calibrated")
        self.assertEqual(out["crop_name"], "Strawberry")
        self.assertEqual(out["window_days_evaluated"], 45)
        self.assertIn("edo1_termica", out)
        self.assertIn("edo2_hidrologica", out)
        self.assertIn("edo4_biomasa", out)
        self.assertLessEqual(out["edo1_termica"]["rmse_after_c"], out["edo1_termica"]["rmse_before_c"])
        self.assertLessEqual(out["edo2_hidrologica"]["rmse_after_mm"], out["edo2_hidrologica"]["rmse_before_mm"])
        self.assertLessEqual(out["edo4_biomasa"]["rmse_ndvi_after"], out["edo4_biomasa"]["rmse_ndvi_before"])


if __name__ == "__main__":
    unittest.main()
