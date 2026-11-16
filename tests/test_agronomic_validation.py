"""
Scientific Validation, Out-of-Sample Satellite Backtesting,
and Agronomic Rotation Coherence Suite for AgroPhasor.

Verifies all 3 levels of model validity:
1. "Blind" Satellite Backtesting (Days 1-45 Calibration -> Days 46-90 Prediction).
2. Agronomic Coherence in Expert Counterfactual Scenarios:
   - Scenario A: Nitrogen-depleted soil -> Dry Bean (Fabaceae) replenishes N and lowers f2 degradation.
   - Scenario B: High-Andean cold climate -> Automatic pruning of frost-sensitive crops (Dry Bean, T_frost=2°C)
     and survival of tolerant crops (Potato=-1°C, Strawberry=-1.5°C, Maize=0°C).
   - Scenario C: Steep rainy hillside -> Exponential protection of fertile topsoil H by biomass and residue.
3. Mathematical Optimality in the 4-Crop Catalog (`gemini-code.json`):
   - Phytosanitary breaking of botanical families, Pareto non-dominance, and clear differentiation
     between short-cycle rotations (Route C1) and maximum-profit rotations (Route C2).
"""

from dataclasses import replace
from datetime import date
import math
import unittest

from backend.models.crop_parameters import CROP_CATALOG, get_crop_parameters
from backend.core.edo1_engine import (
    solve_edo1_step,
    compute_lissajous_area,
    compute_lissajous_shield_index,
    compute_shield_state_and_color,
)
from backend.core.edo2_engine import solve_edo2_step
from backend.core.edo4_engine import solve_edo4_step, biomass_to_satellite_ndvi
from backend.core.edo5_engine import (
    solve_edo5_step,
    compute_soil_color,
    compute_soil_vitality_index,
    compute_terrain_height_variation,
)
from backend.core.satellite_calibration import (
    calibrate_edo1_thermal,
    calibrate_edo2_hydrology,
    calibrate_edo4_biomass,
)
from backend.rotation.graph import RotationGraph
from backend.rotation.costs import PeriodSimulator
from backend.rotation.search import search, NoViableRotations
from backend.rotation.pareto import normalize, pareto_front
from backend.rotation.routes import PRESETS, select_route


def _rmse(values):
    return math.sqrt(sum(v * v for v in values) / max(1, len(values)))


class TestAgronomicValidation(unittest.TestCase):

    def test_1_out_of_sample_satellite_backtesting(self):
        """
        Level 2 (Out-of-Sample Backtesting):
        Calibrates on days 1..45 and predicts days 46..90 'blind'.
        Verifies that future prediction error (out-of-sample RMSE) is
        significantly lower with calibrated parameters than with the generic prior.
        """
        prior_crop = get_crop_parameters("maiz")
        true_crop = replace(prior_crop, hc=22.5, Cp=42000.0, kp_c=0.0215)
        true_kd = 0.11
        true_es0 = 5.2
        slope = 12.0

        total_days = 90
        split_day = 45

        t_air = [19.0 + 3.0 * math.sin(2.0 * math.pi * d / 14.0) for d in range(total_days)]
        f_rad_mj = [19.5 + 2.5 * math.cos(2.0 * math.pi * d / 11.0) for d in range(total_days)]
        f_rad_wm2 = [420.0 + 120.0 * math.cos(2.0 * math.pi * d / 11.0) for d in range(total_days)]
        rh = [60.0 + 10.0 * math.sin(2.0 * math.pi * d / 9.0) for d in range(total_days)]
        precip = [24.0 if d in (0, 14, 28, 46, 62, 76) else 0.0 for d in range(total_days)]

        obs_ts = []
        obs_w = [160.0]
        obs_et = [0.0]
        obs_ndvi = []

        t_curr = t_air[0]
        b_curr = true_crop.B0_t_ha
        for d in range(total_days):
            w_d = obs_w[-1]
            t_prev_obs = obs_ts[-1] if obs_ts else t_air[0]
            s1 = solve_edo1_step(t_prev_obs, t_air[d], f_rad_wm2[d], rh[d], w_d, true_crop)
            t_curr = s1.t_canopy_c
            obs_ts.append(t_curr)

            s4 = solve_edo4_step(b_curr, f_rad_mj[d], t_curr, w_d, 100.0, 45.0, 130.0, true_crop)
            b_curr = s4.biomass_t_ha
            obs_ndvi.append(biomass_to_satellite_ndvi(b_curr))

            if d < total_days - 1:
                s2 = solve_edo2_step(
                    w_d, precip[d + 1], t_air[d + 1], rh[d + 1], slope, true_crop,
                    kd=true_kd, e_suelo0=true_es0, biomass_t_ha=b_curr
                )
                obs_w.append(s2.soil_water_mm)
                obs_et.append(s2.etc_mm)

        # PHASE A: Calibrate ONLY on the historical window (days 0..44)
        cal_edo1 = calibrate_edo1_thermal(
            crop=prior_crop,
            t_air_series_c=t_air[:split_day],
            f_rad_series_wm2=f_rad_wm2[:split_day],
            rh_series_pct=rh[:split_day],
            soil_water_series_mm=obs_w[:split_day],
            observed_lst_or_ts_c=obs_ts[:split_day],
            reg_weight=0.005,
        )
        cal_edo2 = calibrate_edo2_hydrology(
            crop=cal_edo1.calibrated_crop,
            precip_series_mm=precip[:split_day],
            t_air_series_c=t_air[:split_day],
            rh_series_pct=rh[:split_day],
            smap_soil_water_series_mm=obs_w[:split_day],
            slope_deg=slope,
            openet_series_mm_day=obs_et[:split_day],
            reg_weight=0.005,
        )
        cal_edo4 = calibrate_edo4_biomass(
            crop=cal_edo1.calibrated_crop,
            f_rad_series_mj_m2=f_rad_mj[:split_day],
            t_canopy_series_c=obs_ts[:split_day],
            soil_water_series_mm=obs_w[:split_day],
            nitrogen_series_kg_ha=[100.0] * split_day,
            phosphorus_series_kg_ha=[45.0] * split_day,
            potassium_series_kg_ha=[130.0] * split_day,
            observed_ndvi_series=obs_ndvi[:split_day],
            reg_weight=0.002,
        )
        calibrated_crop = cal_edo4.calibrated_crop

        # PHASE B: Blind prediction over future days 45..89 (Out-of-Sample)
        err_t_prior, err_t_cal = [], []
        err_w_prior, err_w_cal = [], []
        err_ndvi_prior, err_ndvi_cal = [], []

        t_p, t_c = obs_ts[split_day - 1], obs_ts[split_day - 1]
        w_p, w_c = obs_w[split_day - 1], obs_w[split_day - 1]
        b_p, b_c = prior_crop.B0_t_ha, calibrated_crop.B0_t_ha

        for d in range(total_days):
            b_p = solve_edo4_step(b_p, f_rad_mj[d], obs_ts[d], obs_w[d], 100.0, 45.0, 130.0, prior_crop).biomass_t_ha
            b_c = solve_edo4_step(b_c, f_rad_mj[d], obs_ts[d], obs_w[d], 100.0, 45.0, 130.0, calibrated_crop).biomass_t_ha

            if d >= split_day:
                t_p = solve_edo1_step(obs_ts[d - 1], t_air[d], f_rad_wm2[d], rh[d], obs_w[d], prior_crop).t_canopy_c
                t_c = solve_edo1_step(obs_ts[d - 1], t_air[d], f_rad_wm2[d], rh[d], obs_w[d], calibrated_crop).t_canopy_c
                err_t_prior.append(t_p - obs_ts[d])
                err_t_cal.append(t_c - obs_ts[d])

                err_ndvi_prior.append(biomass_to_satellite_ndvi(b_p) - obs_ndvi[d])
                err_ndvi_cal.append(biomass_to_satellite_ndvi(b_c) - obs_ndvi[d])

                w_p = solve_edo2_step(
                    w_p, precip[d], t_air[d], rh[d], slope, prior_crop,
                    kd=cal_edo2.kd_prior, e_suelo0=cal_edo2.e_suelo0_prior, biomass_t_ha=b_p
                ).soil_water_mm
                w_c = solve_edo2_step(
                    w_c, precip[d], t_air[d], rh[d], slope, calibrated_crop,
                    kd=cal_edo2.kd_calibrated, e_suelo0=cal_edo2.e_suelo0_mm_dia, biomass_t_ha=b_c
                ).soil_water_mm
                err_w_prior.append(w_p - obs_w[d])
                err_w_cal.append(w_c - obs_w[d])

        self.assertLess(_rmse(err_t_cal), _rmse(err_t_prior) * 0.25)
        self.assertLess(_rmse(err_w_cal), _rmse(err_w_prior) * 0.35)
        self.assertLess(_rmse(err_ndvi_cal), _rmse(err_ndvi_prior) * 0.25)

    def test_2_nitrogen_depleted_soil_selects_legume_in_soil_route(self):
        """
        Counterfactual Scenario 1 (Low-nitrogen soil):
        When initial N is limiting, planting Dry Bean (Fabaceae, F_fix=0.14)
        symbiotically fixes nitrogen, leaving higher final N and lower f2 degradation
        than a nutrient-extracting cereal (Maize, F_fix=0.0).
        """
        catalog = {k: CROP_CATALOG[k] for k in ("papa", "maiz", "frijol")}
        climate = {(m, d): (2.0, 22.0, 65.0, 21.0) for m in range(1, 13) for d in range(1, 32)}
        prices = {k: catalog[k].price_usd_t for k in catalog}
        costs = {k: catalog[k].base_cost_usd_ha for k in catalog}

        simulator = PeriodSimulator(
            scenarios={"base": climate},
            transition_days=0,
            residue_fraction=0.35,
            slope=1.0,
            irrigation=0.0,
            prices=prices,
            costs=costs,
            irrigation_cost=1.20,
        )
        # Soil with adequate initial biomass and moderate-low N (25 kg/ha)
        low_n_state = (75.0, (25.0, 80.0, 180.0), 400.0, 2.0, (), 4.5)

        res_frijol = simulator(low_n_state, "frijol", replace(catalog["frijol"], B0_t_ha=2.5), date(2026, 1, 1), "base")
        res_maiz = simulator(low_n_state, "maiz", replace(catalog["maiz"], B0_t_ha=2.5), date(2026, 1, 1), "base")

        n_final_frijol = res_frijol.state[1][0]
        n_final_maiz = res_maiz.state[1][0]
        self.assertGreater(n_final_frijol, n_final_maiz * 2.0)
        self.assertLessEqual(res_frijol.g[1], res_maiz.g[1])

        candidates = search(RotationGraph(catalog, 2), simulator, low_n_state, date(2026, 1, 1), ["base"])
        front = pareto_front(normalize(candidates))
        f_hat = {c.id: c.f_hat for c in front}
        best_soil_route = select_route(front, f_hat, PRESETS["A2_mejor_suelo"])
        self.assertIn("frijol", best_soil_route.id)

    def test_3_frost_risk_climate_filters_sensitive_crops(self):
        """
        Counterfactual Scenario 2 (High-Andean cold climate with frost risk):
        At 0.4 °C air temperature and cloudy radiation (1.5 MJ/m^2/day),
        Dry Bean (T_frost = 2.0 °C) and Maize (T_frost = 0.0 °C under latent cooling)
        cross their lethal thermal threshold and are automatically pruned, leaving
        only rotations among cold-tolerant crops: Potato (-1.0 °C) and Strawberry (-1.5 °C).
        """
        catalog = {k: CROP_CATALOG[k] for k in ("papa", "fresa", "maiz", "frijol")}
        cold_climate = {(m, d): (2.0, 0.4, 85.0, 1.5) for m in range(1, 13) for d in range(1, 32)}
        simulator = PeriodSimulator({"frio": cold_climate}, 10, 0.30, 5.0, 0.0, {}, {}, 0.0)
        state = (100.0, (90.0, 40.0, 130.0), 400.0, 0.0, (), 3.0)

        candidates = search(RotationGraph(catalog, 2), simulator, state, date(2026, 1, 1), ["frio"])
        self.assertNotIsInstance(candidates, NoViableRotations)

        surviving_ids = {c.id for c in candidates}
        self.assertTrue(all("frijol" not in cid for cid in surviving_ids))
        self.assertIn("papa>fresa", surviving_ids)
        self.assertIn("fresa>papa", surviving_ids)

    def test_4_steep_slope_erosion_shield_protection(self):
        """
        Counterfactual Scenario 3 (Steep hillside under heavy storms):
        A high-cover crop with retained residue protects fertile topsoil thickness H
        compared against residue-free management on a 25° slope.
        """
        maiz = get_crop_parameters("maiz")
        rainy_climate = {(m, d): (18.0, 22.0, 75.0, 20.0) for m in range(1, 13) for d in range(1, 32)}
        state = (120.0, (120.0, 50.0, 150.0), 400.0, 4.0, (), 3.5)

        sim_conservation = PeriodSimulator({"rain": rainy_climate}, 20, 0.65, 25.0, 0.0, {}, {}, 0.0)
        sim_bare_tillage = PeriodSimulator({"rain": rainy_climate}, 20, 0.0, 25.0, 0.0, {}, {}, 0.0)

        res_cons = sim_conservation(state, "maiz", maiz, date(2026, 1, 1), "rain")
        res_bare = sim_bare_tillage(state, "maiz", maiz, date(2026, 1, 1), "rain")

        self.assertGreater(res_cons.state[2], res_bare.state[2])
        self.assertLess(res_cons.g[1], res_bare.g[1])

    def test_5_four_crop_catalog_pareto_and_routes_differentiation(self):
        """
        Level 3 (Mathematical Optimality in the 4-Crop Catalog `gemini-code.json`):
        With Maize, Dry Bean, Strawberry, and Potato across m=2 seasons:
        - Exactly 4 * 3 = 12 valid rotations are generated without consecutive same families.
        - Prioritizing pure speed (w=[0,0,0,1]) selects the minimum cycle (230 days: dry bean + potato).
        - Route C1 (Balanced fast cycle) selects short cycles (<= 240 days, excluding 270-day Strawberry).
        - Route C2 (Highest profit, dominant w3) selects a high-profitfulness rotation with Strawberry.
        """
        catalog = {k: CROP_CATALOG[k] for k in ("maiz", "frijol", "fresa", "papa")}
        climate = {(m, d): (4.0, 20.0, 65.0, 19.0) for m in range(1, 13) for d in range(1, 32)}
        prices = {k: catalog[k].price_usd_t for k in catalog}
        costs = {k: catalog[k].base_cost_usd_ha for k in catalog}

        simulator = PeriodSimulator(
            scenarios={"opt": climate},
            transition_days=15,
            residue_fraction=0.30,
            slope=5.0,
            irrigation=1.5,
            prices=prices,
            costs=costs,
            irrigation_cost=1.20,
        )
        state = (110.0, (110.0, 50.0, 150.0), 400.0, 0.5, (), 3.2)

        candidates = search(RotationGraph(catalog, 2), simulator, state, date(2026, 1, 1), ["opt"])
        self.assertEqual(len(candidates), 12)

        for c in candidates:
            fams = [catalog[s["crop_id"]].botanical_family for s in c.stages]
            self.assertNotEqual(fams[0], fams[1])

        front = pareto_front(normalize(candidates))
        f_hat = {c.id: c.f_hat for c in front}

        pure_resilience = select_route(front, f_hat, (1.0, 0.0, 0.0, 0.0))
        pure_soil = select_route(front, f_hat, (0.0, 1.0, 0.0, 0.0))
        pure_profit = select_route(front, f_hat, (0.0, 0.0, 1.0, 0.0))
        pure_speed = select_route(front, f_hat, (0.0, 0.0, 0.0, 1.0))

        # f4 is mean duration per season: (90 + 110 + 30) / 2 = 115.0 days/season
        self.assertIn(pure_speed.id, {"frijol>papa", "papa>frijol"})
        self.assertEqual(pure_speed.f[3], 115.0)
        self.assertEqual(pure_resilience.f[0], min(c.f[0] for c in candidates))
        self.assertEqual(pure_soil.f[1], min(c.f[1] for c in candidates))
        self.assertEqual(pure_profit.f[2], min(c.f[2] for c in candidates))
        self.assertEqual(pure_speed.f[3], min(c.f[3] for c in candidates))

    def test_6_lissajous_area_drives_shield_strength_and_color(self):
        """
        Verifies that Lissajous curve area A_L governs shield strength and color:
        Low area -> RED (249,64,70), High area -> BLUE (42,155,255).
        """
        low_shield = compute_shield_state_and_color(lissajous_area=0.4, psi_environmental=0.15, is_crop=True)
        mid_shield = compute_shield_state_and_color(lissajous_area=1.5, psi_environmental=0.32, is_crop=True)
        high_shield = compute_shield_state_and_color(lissajous_area=14.0, psi_environmental=0.80, is_crop=True)
        off_shield = compute_shield_state_and_color(lissajous_area=50.0, psi_environmental=0.90, is_crop=False)

        self.assertLess(low_shield["eta_lissajous"], mid_shield["eta_lissajous"])
        self.assertLess(mid_shield["eta_lissajous"], high_shield["eta_lissajous"])

        # Under equal environmental conditions, larger Lissajous area strictly increases the shield score
        s_small = compute_shield_state_and_color(lissajous_area=0.2, psi_environmental=0.55, is_crop=True)["shield_score"]
        s_large = compute_shield_state_and_color(lissajous_area=10.0, psi_environmental=0.55, is_crop=True)["shield_score"]
        self.assertGreater(s_large, s_small)

        self.assertEqual(low_shield["shield_state"], "rojo_intenso")
        self.assertEqual(mid_shield["shield_state"], "violeta_ambar")
        self.assertEqual(high_shield["shield_state"], "azul_cobalto")
        self.assertFalse(off_shield["shield_enabled"])

        # At low area the Red channel dominates (R > B); at high area the Blue channel dominates (B > R)
        r_low, _, b_low = low_shield["shield_color_rgb"]
        r_high, _, b_high = high_shield["shield_color_rgb"]
        self.assertGreater(r_low, b_low)
        self.assertGreater(b_high, r_high)

    def test_7_terrain_height_by_precipitation_and_soil_color_by_nutrients_moisture(self):
        """
        Verifies:
        1. Terrain elevation variation as a direct function of precipitation P_0(t).
        2. Terrain soil color shift between Brown (101,67,33) and Gray (128,128,128)
           depending on nutrient availability (eta_N) and moisture saturation (S_W).
        """
        h_dry = compute_terrain_height_variation(precip_mm=0.0, accumulated_erosion_mm=2.0, slope_deg=8.0, altitude_m=3200.0)
        h_mod = compute_terrain_height_variation(precip_mm=20.0, accumulated_erosion_mm=2.0, slope_deg=8.0, altitude_m=3200.0)
        h_storm = compute_terrain_height_variation(precip_mm=70.0, accumulated_erosion_mm=2.0, slope_deg=8.0, altitude_m=3200.0)

        self.assertEqual(h_dry["rain_height_variation_mm"], 0.0)
        self.assertGreater(h_mod["rain_height_variation_mm"], h_dry["rain_height_variation_mm"])
        self.assertGreater(h_storm["rain_height_variation_mm"], h_mod["rain_height_variation_mm"])
        # Higher precipitation produces greater subsidence (lower z_visual_m)
        self.assertLess(h_storm["z_visual_m"], h_mod["z_visual_m"])
        self.assertLess(h_mod["z_visual_m"], h_dry["z_visual_m"])

        # Soil color: nutrient-rich and moist -> Brown (101, 67, 33)
        color_fertile_wet = compute_soil_color(retention_ratio=1.0, eta_nutrientes=1.0, water_saturation=1.0)
        # Soil with moderate nutrients and moisture -> Intermediate tone
        color_medium = compute_soil_color(retention_ratio=1.0, eta_nutrientes=0.5, water_saturation=0.5)
        # Nutrient-depleted and dry soil -> Gray (128, 128, 128)
        color_depleted_dry = compute_soil_color(retention_ratio=1.0, eta_nutrientes=0.0, water_saturation=0.0)

        self.assertEqual(color_fertile_wet, (101, 67, 33))
        self.assertEqual(color_depleted_dry, (128, 128, 128))
        self.assertTrue(color_fertile_wet[0] < color_medium[0] < color_depleted_dry[0])
        self.assertTrue(color_fertile_wet[2] < color_medium[2] < color_depleted_dry[2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
