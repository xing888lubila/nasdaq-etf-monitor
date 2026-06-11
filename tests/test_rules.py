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
    def test_observation_alert_uses_domestic_etf_drop_as_primary_signal(self) -> None:
        quote = _quote(change_pct=-1.6, premium_rate=0.025, turnover_cny=230_000_000)

        alerts = evaluate_alerts([quote], None, None, RuleConfig(), datetime(2026, 5, 25, 10, 0))

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].level, "观察提醒")

    def test_focus_alert_requires_adjusted_premium(self) -> None:
        quote = _quote(
            change_pct=-2.6,
            premium_rate=0.018,
            adjusted_premium_rate=0.019,
            turnover_cny=230_000_000,
        )

        alerts = evaluate_alerts([quote], None, None, RuleConfig(), datetime(2026, 5, 25, 10, 0))

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].level, "重点提醒")

    def test_focus_alert_blocked_when_adjusted_premium_is_too_high(self) -> None:
        quote = _quote(
            change_pct=-2.6,
            premium_rate=0.018,
            adjusted_premium_rate=0.025,
            turnover_cny=230_000_000,
        )

        alerts = evaluate_alerts([quote], None, None, RuleConfig(), datetime(2026, 5, 25, 10, 0))

        self.assertEqual(alerts[0].level, "观察提醒")

    def test_strong_alert_requires_us_weak_confirmation(self) -> None:
        quote = _quote(
            change_pct=-4.2,
            premium_rate=0.012,
            adjusted_premium_rate=0.012,
            turnover_cny=230_000_000,
        )

        alerts_without_us = evaluate_alerts([quote], None, None, RuleConfig(), datetime(2026, 5, 25, 10, 0))
        alerts_with_us = evaluate_alerts(
            [quote], None, _us_market(primary_change_pct=-3.0), RuleConfig(), datetime(2026, 5, 25, 10, 0)
        )

        self.assertEqual(alerts_without_us[0].level, "重点提醒")
        self.assertEqual(alerts_with_us[0].level, "强抄底提醒")

    def test_extreme_alert_is_highest_matching_tier(self) -> None:
        quote = _quote(
            change_pct=-6.5,
            premium_rate=0.008,
            adjusted_premium_rate=0.009,
            turnover_cny=230_000_000,
        )

        alerts = evaluate_alerts(
            [quote], None, _us_market(primary_change_pct=-3.0), RuleConfig(), datetime(2026, 5, 25, 10, 0)
        )

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].level, "极端提醒")

    def test_no_alert_when_etf_drop_is_not_deep_enough(self) -> None:
        quote = _quote(change_pct=-1.0, premium_rate=0.01, turnover_cny=230_000_000)

        alerts = evaluate_alerts([quote], None, None, RuleConfig(), datetime(2026, 5, 25, 10, 0))

        self.assertEqual(alerts, [])

    def test_no_alert_when_turnover_is_too_low(self) -> None:
        quote = _quote(change_pct=-2.0, premium_rate=0.01, turnover_cny=50_000_000)

        alerts = evaluate_alerts([quote], None, None, RuleConfig(), datetime(2026, 5, 25, 10, 0))

        self.assertEqual(alerts, [])

    def test_no_alert_when_etf_quote_is_stale(self) -> None:
        quote = _quote(
            change_pct=-2.0,
            premium_rate=0.01,
            turnover_cny=230_000_000,
            updated_at="2026-05-25 09:55:00",
        )

        alerts = evaluate_alerts([quote], None, None, RuleConfig(), datetime(2026, 5, 25, 10, 0))

        self.assertEqual(alerts, [])


def _quote(
    change_pct: float,
    premium_rate: float,
    turnover_cny: float,
    adjusted_premium_rate: float | None = None,
    updated_at: str = "2026-05-25 10:00:00",
) -> EtfQuote:
    return EtfQuote(
        symbol="159659",
        name="纳斯达克100ETF招商",
        price=2.0 * (1 + premium_rate),
        change_pct=change_pct,
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


def _us_market(
    primary_change_pct: float | None = None,
    nasdaq_index_change_pct: float | None = None,
    fallback_change_pct: float | None = None,
) -> USMarketSnapshot:
    return USMarketSnapshot(
        primary=_us_quote("NQ=F", primary_change_pct) if primary_change_pct is not None else None,
        fallback=_us_quote("QQQ", fallback_change_pct) if fallback_change_pct is not None else None,
        nasdaq_index=_us_quote("^NDX", nasdaq_index_change_pct) if nasdaq_index_change_pct is not None else None,
        fx=None,
        mega_caps=(),
        adjustment_rate=None,
        adjustment_source=None,
        checked_at=datetime(2026, 5, 25, 10, 0),
    )


def _us_quote(symbol: str, change_pct: float) -> USMarketQuote:
    return USMarketQuote(
        symbol=symbol,
        name=symbol,
        price=100.0,
        previous_close=100.0 / (1 + change_pct / 100),
        change_pct=change_pct,
        updated_at="2026-05-25 09:30:00",
        source="test",
    )


if __name__ == "__main__":
    unittest.main()
