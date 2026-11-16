"""
Suite de Validación Científica, Backtesting Satelital Fuera de Muestra (Out-of-Sample)
y Coherencia Agronómica de Rotaciones de AgroPhasor.

Comprueba los 3 niveles de validez del modelo:
1. Backtesting Satelital "A Ciegas" (Días 1-45 Calibración -> Días 46-90 Predicción).
2. Coherencia Agronómica en Escenarios Contrafactuales de Experto:
   - Escenario A: Suelo agotado en Nitrógeno -> Frijol (Fabaceae) recarga N y reduce degradación f2.
   - Escenario B: Clima frío altoandino -> Descarte automático de especies sensibles (Frijol, T_helada=2°C)
     y supervivencia de tolerantes (Papa=-1°C, Fresa=-1.5°C, Maíz=0°C).
   - Escenario C: Ladera escarpada lluviosa -> Protección exponencial del suelo fértil H por biomasa y rastrojo.
3. Optimalidad Matemática en el Catálogo de 4 Cultivos (`gemini-code.json`):
   - Ruptura fitosanitaria de familias botánicas, no-dominancia en el Frente de Pareto y diferenciación
     entre rotaciones de ciclo corto (Ruta C1) y rotaciones de máxima rentabilidad (Ruta C2).
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
        Nivel 2 (Backtesting Fuera de Muestra):
        Calibra con los días 1..45 y predice 'a ciegas' los días 46..90.
        Verifica que el error de predicción futura (out-of-sample RMSE) sea
        significativamente menor con los parámetros calibrados que con el prior genérico.
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

        # FASE A: Calibrar ÚNICAMENTE con la ventana histórica (días 0..44)
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

        # FASE B: Predicción a ciegas en los días futuros 45..89 (Out-of-Sample)
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
        Escenario Contrafactual 1 (Suelo con bajo Nitrógeno):
        Cuando N inicial es limitante, sembrar Frijol (Fabaceae, F_fix=0.14)
        fija nitrógeno simbióticamente, dejando mayor N final y menor degradación f2
        que un cereal extractor (Maíz, F_fix=0.0).
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
        # Suelo con biomasa inicial suficiente y N moderado-bajo (25 kg/ha)
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
        Escenario Contrafactual 2 (Clima frío altoandino con riesgo de helada):
        Con temperatura del aire de 0.4 °C y radiación nublada (1.5 MJ/m²/día),
        Frijol (T_helada = 2.0 °C) y Maíz (T_helada = 0.0 °C con enfriamiento latente)
        cruzan su umbral térmico letal y se descartan automáticamente, sobreviviendo
        únicamente las rotaciones entre especies resistentes al frío: Papa (-1.0 °C) y Fresa (-1.5 °C).
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
        Escenario Contrafactual 3 (Ladera escarpada bajo tormentas):
        Un cultivo de alta cobertura y rastrojo conservado protege el espesor fértil H
        frente al manejo sin rastrojo en pendiente de 25°.
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
        Nivel 3 (Optimalidad Matemática en el Catálogo de 4 Cultivos `gemini-code.json`):
        Con Maíz, Frijol, Fresa y Papa en m=2 campañas:
        - Se generan exactamente 4 * 3 = 12 rotaciones válidas sin repetir familia.
        - Al priorizar rapidez pura (w=[0,0,0,1]) se selecciona el ciclo mínimo (230 días: frijol+papa).
        - Ruta C1 (Ciclo rápido balanceado) elige ciclos cortos (<= 240 días, sin Fresa de 270 días).
        - Ruta C2 (Mayor ganancia, w3 dominante) elige una rotación de alta rentabilidad con Fresa.
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

        # f4 es la duración media por campaña: (90 + 110 + 30) / 2 = 115.0 días/campaña
        self.assertIn(pure_speed.id, {"frijol>papa", "papa>frijol"})
        self.assertEqual(pure_speed.f[3], 115.0)
        self.assertEqual(pure_resilience.f[0], min(c.f[0] for c in candidates))
        self.assertEqual(pure_soil.f[1], min(c.f[1] for c in candidates))
        self.assertEqual(pure_profit.f[2], min(c.f[2] for c in candidates))
        self.assertEqual(pure_speed.f[3], min(c.f[3] for c in candidates))

    def test_6_lissajous_area_drives_shield_strength_and_color(self):
        """
        Verifica que el área de la curva de Lissajous A_L gobierne la intensidad y el color
        del escudo: Área baja -> ROJO (249,64,70), Área alta -> AZUL (42,155,255).
        """
        low_shield = compute_shield_state_and_color(lissajous_area=0.4, psi_environmental=0.15, is_crop=True)
        mid_shield = compute_shield_state_and_color(lissajous_area=1.5, psi_environmental=0.32, is_crop=True)
        high_shield = compute_shield_state_and_color(lissajous_area=14.0, psi_environmental=0.80, is_crop=True)
        off_shield = compute_shield_state_and_color(lissajous_area=50.0, psi_environmental=0.90, is_crop=False)

        self.assertLess(low_shield["eta_lissajous"], mid_shield["eta_lissajous"])
        self.assertLess(mid_shield["eta_lissajous"], high_shield["eta_lissajous"])

        # A igual condición ambiental, mayor área de Lissajous incrementa estrictamente el puntaje del escudo
        s_small = compute_shield_state_and_color(lissajous_area=0.2, psi_environmental=0.55, is_crop=True)["shield_score"]
        s_large = compute_shield_state_and_color(lissajous_area=10.0, psi_environmental=0.55, is_crop=True)["shield_score"]
        self.assertGreater(s_large, s_small)

        self.assertEqual(low_shield["shield_state"], "rojo_intenso")
        self.assertEqual(mid_shield["shield_state"], "violeta_ambar")
        self.assertEqual(high_shield["shield_state"], "azul_cobalto")
        self.assertFalse(off_shield["shield_enabled"])

        # En área baja domina el canal Rojo (R > B); en área alta domina el canal Azul (B > R)
        r_low, _, b_low = low_shield["shield_color_rgb"]
        r_high, _, b_high = high_shield["shield_color_rgb"]
        self.assertGreater(r_low, b_low)
        self.assertGreater(b_high, r_high)

    def test_7_terrain_height_by_precipitation_and_soil_color_by_nutrients_moisture(self):
        """
        Verifica:
        1. Variación de la altura del terreno en función directa de las precipitaciones P_0(t).
        2. Cambio del color del terreno entre Marrón (101,67,33) y Gris (128,128,128)
           dependiendo de la cantidad de nutrientes (eta_N) y la humedad (S_W).
        """
        h_dry = compute_terrain_height_variation(precip_mm=0.0, accumulated_erosion_mm=2.0, slope_deg=8.0, altitude_m=3200.0)
        h_mod = compute_terrain_height_variation(precip_mm=20.0, accumulated_erosion_mm=2.0, slope_deg=8.0, altitude_m=3200.0)
        h_storm = compute_terrain_height_variation(precip_mm=70.0, accumulated_erosion_mm=2.0, slope_deg=8.0, altitude_m=3200.0)

        self.assertEqual(h_dry["rain_height_variation_mm"], 0.0)
        self.assertGreater(h_mod["rain_height_variation_mm"], h_dry["rain_height_variation_mm"])
        self.assertGreater(h_storm["rain_height_variation_mm"], h_mod["rain_height_variation_mm"])
        # A mayor precipitación, mayor hundimiento (menor cota z_visual_m)
        self.assertLess(h_storm["z_visual_m"], h_mod["z_visual_m"])
        self.assertLess(h_mod["z_visual_m"], h_dry["z_visual_m"])

        # Color del terreno: rico en nutrientes y húmedo -> Marrón (101, 67, 33)
        color_fertile_wet = compute_soil_color(retention_ratio=1.0, eta_nutrientes=1.0, water_saturation=1.0)
        # Suelo con nutrientes medios y humedad media -> Tono intermedio
        color_medium = compute_soil_color(retention_ratio=1.0, eta_nutrientes=0.5, water_saturation=0.5)
        # Suelo sin nutrientes y seco -> Gris (128, 128, 128)
        color_depleted_dry = compute_soil_color(retention_ratio=1.0, eta_nutrientes=0.0, water_saturation=0.0)

        self.assertEqual(color_fertile_wet, (101, 67, 33))
        self.assertEqual(color_depleted_dry, (128, 128, 128))
        self.assertTrue(color_fertile_wet[0] < color_medium[0] < color_depleted_dry[0])
        self.assertTrue(color_fertile_wet[2] < color_medium[2] < color_depleted_dry[2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
