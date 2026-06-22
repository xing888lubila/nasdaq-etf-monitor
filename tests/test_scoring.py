from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fund_monitor.scoring import CashPolicy, combine_scores, score_nq_futures, score_yields


class ScoringTests(unittest.TestCase):
    def test_nq_extreme_bearish_scores_minus_two(self) -> None:
        item = score_nq_futures(-1.2)

        self.assertEqual(item.score, -2)

    def test_yields_up_ten_bp_scores_minus_two(self) -> None:
        item = score_yields(11, 10)

        self.assertEqual(item.score, -2)

    def test_cash_floor_caps_recommended_buy(self) -> None:
        score = combine_scores(
            [score_nq_futures(-1.2), score_yields(11, 10)],
            CashPolicy(current_cash=560),
        )

        self.assertEqual(score.trend_label, "strong bearish")
        self.assertEqual(score.recommended_buy, 60)


if __name__ == "__main__":
    unittest.main()
