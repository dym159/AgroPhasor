"""
Supervised Calibration & Stratified Cross-Validation (4-Fold) Test Suite
for the Environmental & Lissajous Shield across labeled biomes:
- Humid Rainforest (Maize, Dry Bean, Strawberry, Potato under heat stress)
- Andean & Temperate Fields (optimal vs moderate water/NPK stress)
- Arid Deserts & High-Andean Frosts
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
        Verifies that supervised calibration (grid search + coordinate descent)
        generalizes out-of-sample (4-fold CV) with >= 85% accuracy and RMSE < 0.12.
        """
        report = run_stratified_cross_validation(k_folds=4)
        self.assertEqual(report["total_scenarios"], len(LABELED_BIOME_SCENARIOS))
        self.assertGreaterEqual(report["oos_accuracy"], 0.85)
        self.assertLess(report["oos_rmse"], 0.12)

        final_p = report["final_parameters"]
        self.assertGreaterEqual(final_p["train_accuracy"], 0.95)

        # All Desert, Frost, Andean Field, and Rainforest scenarios must classify accurately
        for pred in report["oos_predictions"]:
            if pred["biome"] in ("Desert", "Frost", "Rainforest", "Andean_Field"):
                self.assertTrue(
                    pred["correct"],
                    f"Out-of-sample failure in {pred['scenario_id']}: {pred}",
                )

    def test_calibrated_engine_matches_biome_expectations(self):
        """
        Verifies that `compute_shield_state_and_color` using parameters loaded from
        `gemini-code.json` yields Blue in optimal Rainforest/Field and Red in Desert/Frost.
        """
        features = {f.scenario.scenario_id: f for f in evaluate_biome_features()}

        selva_maiz = compute_shield_state_and_color(
            features["rainforest_maize_opt"].lissajous_area_eff,
            features["rainforest_maize_opt"].psi_environmental,
            is_crop=True,
        )
        andino_papa = compute_shield_state_and_color(
            features["andean_potato_opt"].lissajous_area_eff,
            features["andean_potato_opt"].psi_environmental,
            is_crop=True,
        )
        desierto_maiz = compute_shield_state_and_color(
            features["desert_maize_drought"].lissajous_area_eff,
            features["desert_maize_drought"].psi_environmental,
            is_crop=True,
        )
        helada_frijol = compute_shield_state_and_color(
            features["frost_bean_critical"].lissajous_area_eff,
            features["frost_bean_critical"].psi_environmental,
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
