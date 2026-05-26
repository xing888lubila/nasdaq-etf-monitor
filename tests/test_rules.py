from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fund_monitor.config import RuleConfig
from fund_monitor.models import EtfQuote, MarketSignal, USMarketQuote, USMarketSnapshot
from fund_monitor.rules import evaluate_alerts


class RuleTests(unittest.TestCase):
    def test_alert_when_all_conditions_match(self) -> None:
        quote = _quote(premium_rate=0.012, turnover_cny=230_000_000)
        signal = _signal(change_pct=-0.8)

        alerts = evaluate_alerts(
            [quote], signal, None, RuleConfig(use_adjusted_premium=False), datetime(2026, 5, 25, 10, 0)
        )

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].quote.symbol, "159659")

    def test_premium_rate_uses_positive_value_for_premium(self) -> None:
        quote = _quote(premium_rate=0.1084, turnover_cny=230_000_000)
        signal = _signal(change_pct=-0.8)

        alerts = evaluate_alerts(
            [quote],
            signal,
            None,
            RuleConfig(max_premium_rate=0.11, use_adjusted_premium=False),
            datetime(2026, 5, 25, 10, 0),
        )

        self.assertEqual(len(alerts), 1)

    def test_adjusted_premium_can_block_alert(self) -> None:
        quote = _quote(premium_rate=0.01, turnover_cny=230_000_000, adjusted_premium_rate=0.025)
        signal = _signal(change_pct=-0.8)

        alerts = evaluate_alerts(
            [quote],
            signal,
            _us_market(change_pct=-3.0),
            RuleConfig(max_adjusted_premium_rate=0.015, use_adjusted_premium=True),
            datetime(2026, 5, 25, 10, 0),
        )

        self.assertEqual(alerts, [])

    def test_no_alert_when_premium_is_too_high(self) -> None:
        quote = _quote(premium_rate=0.02, turnover_cny=230_000_000)
        signal = _signal(change_pct=-0.8)

        alerts = evaluate_alerts(
            [quote], signal, None, RuleConfig(use_adjusted_premium=False), datetime(2026, 5, 25, 10, 0)
        )

        self.assertEqual(alerts, [])

    def test_no_alert_when_nasdaq_is_not_down_enough(self) -> None:
        quote = _quote(premium_rate=0.012, turnover_cny=230_000_000)
        signal = _signal(change_pct=-0.2)

        alerts = evaluate_alerts(
            [quote], signal, None, RuleConfig(use_adjusted_premium=False), datetime(2026, 5, 25, 10, 0)
        )

        self.assertEqual(alerts, [])

    def test_no_alert_when_etf_quote_is_stale(self) -> None:
        quote = _quote(premium_rate=0.012, turnover_cny=230_000_000, updated_at="2026-05-25 09:55:00")
        signal = _signal(change_pct=-0.8)

        alerts = evaluate_alerts(
            [quote],
            signal,
            None,
            RuleConfig(use_adjusted_premium=False, stale_after_seconds=120),
            datetime(2026, 5, 25, 10, 0),
        )

        self.assertEqual(alerts, [])


def _quote(
    premium_rate: float,
    turnover_cny: float,
    adjusted_premium_rate: float | None = None,
    updated_at: str = "2026-05-25 10:00:00",
) -> EtfQuote:
    return EtfQuote(
        symbol="159659",
        name="纳斯达克100ETF招商",
        price=2.0 * (1 + premium_rate),
        change_pct=1.2,
        turnover_cny=turnover_cny,
        iopv=2.0,
        premium_rate=premium_rate,
        updated_at=updated_at,
        source="test",
        adjusted_reference_value=2.0,
        adjusted_premium_rate=adjusted_premium_rate,
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


def _us_market(change_pct: float) -> USMarketSnapshot:
    quote = USMarketQuote(
        symbol="NQ=F",
        name="E-mini Nasdaq-100",
        price=100.0,
        previous_close=100.0 / (1 + change_pct / 100),
        change_pct=change_pct,
        updated_at="2026-05-25 09:30:00",
        source="test",
    )
    return USMarketSnapshot(
        primary=quote,
        fallback=None,
        fx=None,
        mega_caps=(),
        adjustment_rate=change_pct / 100,
        adjustment_source="NQ=F",
        checked_at=datetime(2026, 5, 25, 10, 0),
    )


if __name__ == "__main__":
    unittest.main()
