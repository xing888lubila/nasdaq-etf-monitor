from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fund_monitor.config import MonitorConfig
from fund_monitor.main import run_once
from fund_monitor.models import EtfQuote


class MainTests(unittest.TestCase):
    def test_run_once_keeps_etf_snapshot_when_nasdaq_source_fails(self) -> None:
        provider = FailingNasdaqProvider()

        result = run_once(MonitorConfig(), provider)

        self.assertEqual(len(result.quotes), 1)
        self.assertIsNone(result.market_signal)
        self.assertEqual(result.alerts, ())


class FailingNasdaqProvider:
    def get_etf_quotes(self, symbols):
        return [
            EtfQuote(
                symbol="159659",
                name="纳斯达克100ETF招商",
                price=2.02,
                change_pct=1.2,
                turnover_cny=230_000_000,
                iopv=2.0,
                premium_rate=0.01,
                updated_at="2026-05-25 10:00:00+08:00",
                source="test",
            )
        ]

    def get_nasdaq_signal(self, config):
        raise RuntimeError("index source failed")


if __name__ == "__main__":
    unittest.main()
