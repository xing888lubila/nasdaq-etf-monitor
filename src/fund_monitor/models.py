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
    adjusted_reference_value: float | None = None
    adjusted_premium_rate: float | None = None


@dataclass(frozen=True)
class MarketSignal:
    name: str
    symbol: str
    change_pct: float | None
    is_down: bool
    updated_at: str | None
    source: str


@dataclass(frozen=True)
class USMarketQuote:
    symbol: str
    name: str
    price: float | None
    previous_close: float | None
    change_pct: float | None
    updated_at: str | None
    source: str


@dataclass(frozen=True)
class USMarketSnapshot:
    primary: USMarketQuote | None
    fallback: USMarketQuote | None
    fx: USMarketQuote | None
    mega_caps: tuple[USMarketQuote, ...]
    adjustment_rate: float | None
    adjustment_source: str | None
    checked_at: datetime


@dataclass(frozen=True)
class Alert:
    quote: EtfQuote
    market_signal: MarketSignal | None
    us_market: USMarketSnapshot | None
    triggered_at: datetime
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MonitorRun:
    quotes: tuple[EtfQuote, ...]
    market_signal: MarketSignal | None
    us_market: USMarketSnapshot | None
    alerts: tuple[Alert, ...]
    checked_at: datetime
