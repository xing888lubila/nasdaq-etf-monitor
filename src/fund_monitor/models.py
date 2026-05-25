from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EtfQuote:
    symbol: str
    name: str
    price: float | None
    change_pct: float | None
    turnover_cny: float | None
    iopv: float | None
    premium_rate: float | None
    updated_at: str | None
    source: str


@dataclass(frozen=True)
class MarketSignal:
    name: str
    symbol: str
    change_pct: float | None
    is_down: bool
    updated_at: str | None
    source: str


@dataclass(frozen=True)
class Alert:
    quote: EtfQuote
    market_signal: MarketSignal | None
    triggered_at: datetime
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MonitorRun:
    quotes: tuple[EtfQuote, ...]
    market_signal: MarketSignal | None
    alerts: tuple[Alert, ...]
    checked_at: datetime
