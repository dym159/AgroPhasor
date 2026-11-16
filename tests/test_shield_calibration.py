"""
Suite de Pruebas de Calibración Supervisada y Validación Cruzada Estratificada (4-Fold)
para el Escudo Ambiental y de Lissajous frente a biomas etiquetados:
- Selva Húmeda (Maíz, Frijol, Fresa, Papa bajo estrés térmico)
- Campos Andinos y Templados (óptimo vs estrés moderado hídrico/NPK)
- Desiertos Áridos y Heladas Altoandinas
"""

import unittest

from backend.core.edo1_engine import compute_shield_state_and_color
from backend.core.shield_calibration import (
    LABELED_BIOME_SCENARIOS,
    evaluate_biome_features,
    run_stratified_cross_validation,
)


class TestShieldCalibration(unittest.TestCase):

    def test_stratified_cross_validation_across_labeled_biomes(self):
        """
        Verifica que la calibración supervisada (grilla + descenso coordinado)
        generalice fuera de muestra (4-fold CV) con >= 85% de precisión y RMSE < 0.12.
        """
        report = run_stratified_cross_validation(k_folds=4)
        self.assertEqual(report["total_scenarios"], len(LABELED_BIOME_SCENARIOS))
        self.assertGreaterEqual(report["oos_accuracy"], 0.85)
        self.assertLess(report["oos_rmse"], 0.12)

        final_p = report["final_parameters"]
        self.assertGreaterEqual(final_p["train_accuracy"], 0.95)

        # Todos los escenarios de Desierto, Helada, Campo Andino y Selva deben clasificarse correctamente
        for pred in report["oos_predictions"]:
            if pred["biome"] in ("Desierto", "Helada", "Selva", "Campo_Andino"):
                self.assertTrue(
                    pred["correct"],
                    f"Fallo fuera de muestra en {pred['scenario_id']}: {pred}",
                )

    def test_calibrated_engine_matches_biome_expectations(self):
        """
        Verifica que `compute_shield_state_and_color` con los parámetros cargados desde
        `gemini-code.json` produzca Azul en Selva/Campo óptimo y Rojo en Desierto/Helada.
        """
        features = {f.scenario.scenario_id: f for f in evaluate_biome_features()}

        selva_maiz = compute_shield_state_and_color(
            features["selva_maiz_opt"].lissajous_area_eff,
            features["selva_maiz_opt"].psi_environmental,
            is_crop=True,
        )
        andino_papa = compute_shield_state_and_color(
            features["andino_papa_opt"].lissajous_area_eff,
            features["andino_papa_opt"].psi_environmental,
            is_crop=True,
        )
        desierto_maiz = compute_shield_state_and_color(
            features["desierto_maiz_sequia"].lissajous_area_eff,
            features["desierto_maiz_sequia"].psi_environmental,
            is_crop=True,
        )
        helada_frijol = compute_shield_state_and_color(
            features["helada_frijol_critico"].lissajous_area_eff,
            features["helada_frijol_critico"].psi_environmental,
            is_crop=True,
        )

        self.assertEqual(selva_maiz["shield_state"], "azul_cobalto")
        self.assertEqual(andino_papa["shield_state"], "azul_cobalto")
        self.assertEqual(desierto_maiz["shield_state"], "rojo_intenso")
        self.assertEqual(helada_frijol["shield_state"], "rojo_intenso")
        self.assertGreater(selva_maiz["shield_score"], 0.75)
        self.assertLess(desierto_maiz["shield_score"], 0.10)
        self.assertEqual(helada_frijol["shield_score"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
