from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fund_monitor.config import RuleConfig
from fund_monitor.models import EtfQuote, MarketSignal
from fund_monitor.rules import evaluate_alerts


class RuleTests(unittest.TestCase):
    def test_alert_when_all_conditions_match(self) -> None:
        quote = _quote(premium_rate=0.012, turnover_cny=230_000_000)
        signal = _signal(change_pct=-0.8)

        alerts = evaluate_alerts([quote], signal, RuleConfig(), datetime(2026, 5, 25, 10, 0))

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].quote.symbol, "159659")

    def test_premium_rate_uses_positive_value_for_premium(self) -> None:
        quote = _quote(premium_rate=0.1084, turnover_cny=230_000_000)
        signal = _signal(change_pct=-0.8)

        alerts = evaluate_alerts([quote], signal, RuleConfig(max_premium_rate=0.11), datetime(2026, 5, 25, 10, 0))

        self.assertEqual(len(alerts), 1)

    def test_no_alert_when_premium_is_too_high(self) -> None:
        quote = _quote(premium_rate=0.02, turnover_cny=230_000_000)
        signal = _signal(change_pct=-0.8)

        alerts = evaluate_alerts([quote], signal, RuleConfig(), datetime(2026, 5, 25, 10, 0))

        self.assertEqual(alerts, [])

    def test_no_alert_when_nasdaq_is_not_down_enough(self) -> None:
        quote = _quote(premium_rate=0.012, turnover_cny=230_000_000)
        signal = _signal(change_pct=-0.2)

        alerts = evaluate_alerts([quote], signal, RuleConfig(), datetime(2026, 5, 25, 10, 0))

        self.assertEqual(alerts, [])


def _quote(premium_rate: float, turnover_cny: float) -> EtfQuote:
    return EtfQuote(
        symbol="159659",
        name="纳斯达克100ETF招商",
        price=2.0 * (1 + premium_rate),
        change_pct=1.2,
        turnover_cny=turnover_cny,
        iopv=2.0,
        premium_rate=premium_rate,
        updated_at="2026-05-25 10:00:00+08:00",
        source="test",
    )


def _signal(change_pct: float) -> MarketSignal:
    return MarketSignal(
        name="纳斯达克",
        symbol="NDX",
        change_pct=change_pct,
        is_down=change_pct <= -0.5,
        updated_at="2026-05-25 09:30:00",
        source="test",
    )


if __name__ == "__main__":
    unittest.main()
