from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fund_monitor.models import EtfQuote, FuturesTrendPoint, USMarketQuote, USMarketSnapshot
from fund_monitor.providers import AkshareMarketDataProvider, _build_futures_trend_snapshot


class ProviderTests(unittest.TestCase):
    def test_apply_us_market_adjustment_sets_adjusted_premium(self) -> None:
        quote = EtfQuote(
            symbol="159659",
            name="纳斯达克100ETF招商",
            price=2.02,
            change_pct=1.2,
            turnover_cny=230_000_000,
            iopv=2.0,
            premium_rate=0.01,
            updated_at="2026-05-25 10:00:00",
            source="test",
        )
        snapshot = USMarketSnapshot(
            primary=_quote("NQ=F", -2.0),
            fallback=None,
            nasdaq_index=None,
            nasdaq_index_trend=None,
            fx=_quote("CNH=X", 0.5),
            mega_caps=(),
            adjustment_rate=(1 - 0.02) * (1 + 0.005) - 1,
            adjustment_source="NQ=F+CNH=X",
            checked_at=datetime(2026, 5, 25, 10, 0),
        )

        adjusted = AkshareMarketDataProvider().apply_us_market_adjustment([quote], snapshot)[0]

        self.assertAlmostEqual(adjusted.adjusted_reference_value or 0, 1.9698, places=4)
        self.assertAlmostEqual(adjusted.adjusted_premium_rate or 0, 0.0255, places=4)

    def test_futures_trend_classifies_bearish_day_session(self) -> None:
        points = [
            FuturesTrendPoint(datetime(2026, 6, 11, 9, 30), 100.0),
            FuturesTrendPoint(datetime(2026, 6, 11, 10, 30), 99.0),
            FuturesTrendPoint(datetime(2026, 6, 11, 11, 30), 98.5),
            FuturesTrendPoint(datetime(2026, 6, 11, 14, 30), 98.0),
        ]

        snapshot = _build_futures_trend_snapshot(
            symbol="NQ=F",
            name="E-mini Nasdaq-100 Futures",
            points=points,
            checked_at=datetime(2026, 6, 11, 14, 30),
            source="test",
        )

        self.assertEqual(snapshot.trend_label, "偏空")
        self.assertAlmostEqual(snapshot.change_pct or 0, -2.0, places=4)


def _quote(symbol: str, change_pct: float) -> USMarketQuote:
    return USMarketQuote(
        symbol=symbol,
        name=symbol,
        price=100.0,
        previous_close=100.0 / (1 + change_pct / 100),
        change_pct=change_pct,
        updated_at="2026-05-25 10:00:00",
        source="test",
    )


if __name__ == "__main__":
    unittest.main()
