import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from rotation_ranking import METRICS, Candidate, rank_rotations


# Synthetic metrics and weights for this example only.
BOUNDS = dict(zip(METRICS, ((0, 10), (0, 10), (-10, 0), (0, 10))))
WEIGHTS = {
    "resilience": dict(zip(METRICS, (0.5, 0.3, 0.1, 0.1))),
    "balance": dict(zip(METRICS, (0.25, 0.25, 0.25, 0.25))),
    "profit": dict(zip(METRICS, (0.05, 0.05, 0.85, 0.05))),
}


def route(route_id, risk, soil, loss, payback):
    return Candidate(route_id, dict(zip(METRICS, (risk, soil, loss, payback))))


class RotationRankingTest(unittest.TestCase):
    def test_pareto_front_and_winners(self):
        candidates = [
            route("D", 9, 9, -1, 9),
            route("C", 8, 7, -10, 8),
            route("B", 3, 3, -8, 3),
            route("A", 1, 1, -2, 4),
        ]

        ranking = rank_rotations(candidates, BOUNDS, WEIGHTS)

        self.assertEqual(ranking.pareto, ("A", "B", "C"))
        self.assertEqual(ranking.by_mode["resilience"][0], "A")
        self.assertEqual(ranking.by_mode["balance"][0], "B")
        self.assertEqual(ranking.by_mode["profit"][0], "C")

    def test_missing_net_margin_disables_profit(self):
        candidates = [route("B", 2, 2, -10, 5), route("A", 1, 1, None, 5)]

        ranking = rank_rotations(candidates, BOUNDS, WEIGHTS)

        self.assertEqual(ranking.pareto, ("A",))
        self.assertEqual(ranking.by_mode["balance"], ("A",))
        self.assertIsNone(ranking.by_mode["profit"])

    def test_constant_metric_and_ties(self):
        candidates = [route("B", 2, 2, -5, 5), route("A", 2, 2, -5, 5)]
        bounds = {**BOUNDS, "payback_time": (5, 5)}

        ranking = rank_rotations(candidates, bounds, WEIGHTS)

        self.assertEqual(ranking.by_mode["balance"], ("A", "B"))

    def test_rejects_weights_that_do_not_sum_to_one(self):
        weights = {**WEIGHTS, "balance": dict.fromkeys(METRICS, 0.5)}

        with self.assertRaises(ValueError):
            rank_rotations([route("A", 1, 1, -2, 4)], BOUNDS, weights)


if __name__ == "__main__":
    unittest.main()
