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
class USIndexTrend:
    symbol: str
    name: str
    latest_close: float | None
    latest_date: str | None
    one_day_change_pct: float | None
    three_day_change_pct: float | None
    five_day_change_pct: float | None
    source: str


@dataclass(frozen=True)
class TreasuryYieldPoint:
    date: str
    value: float


@dataclass(frozen=True)
class TreasuryYieldSnapshot:
    two_year: TreasuryYieldPoint | None
    two_year_previous: TreasuryYieldPoint | None
    ten_year: TreasuryYieldPoint | None
    ten_year_previous: TreasuryYieldPoint | None
    source: str
    checked_at: datetime

    @property
    def latest_date(self) -> str | None:
        dates = [point.date for point in (self.two_year, self.ten_year) if point is not None]
        return max(dates) if dates else None

    @property
    def two_year_change_bp(self) -> float | None:
        if self.two_year is None or self.two_year_previous is None:
            return None
        return (self.two_year.value - self.two_year_previous.value) * 100

    @property
    def ten_year_change_bp(self) -> float | None:
        if self.ten_year is None or self.ten_year_previous is None:
            return None
        return (self.ten_year.value - self.ten_year_previous.value) * 100


@dataclass(frozen=True)
class IntradayTrendShape:
    symbol: str
    change_pct: float | None
    open_price: float | None
    high_price: float | None
    low_price: float | None
    close_price: float | None
    shape: str
    close_position: float | None
    source: str
    checked_at: datetime


@dataclass(frozen=True)
class MarketRelativeSnapshot:
    qqq: USMarketQuote | None
    ndx: USMarketQuote | None
    spy: USMarketQuote | None
    dia: USMarketQuote | None
    smh: USMarketQuote | None
    qqq_shape: IntradayTrendShape | None
    checked_at: datetime


@dataclass(frozen=True)
class FuturesTrendPoint:
    timestamp: datetime
    price: float


@dataclass(frozen=True)
class FuturesTrendSnapshot:
    symbol: str
    name: str
    points: tuple[FuturesTrendPoint, ...]
    start_at: datetime | None
    end_at: datetime | None
    start_price: float | None
    end_price: float | None
    change_pct: float | None
    high_price: float | None
    low_price: float | None
    max_drawdown_pct: float | None
    late_change_pct: float | None
    trend_label: str
    prediction: str
    rationale: tuple[str, ...]
    source: str
    checked_at: datetime


@dataclass(frozen=True)
class USMarketSnapshot:
    primary: USMarketQuote | None
    fallback: USMarketQuote | None
    nasdaq_index: USMarketQuote | None
    nasdaq_index_trend: USIndexTrend | None
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
    level: str = "机会提醒"


@dataclass(frozen=True)
class MonitorRun:
    quotes: tuple[EtfQuote, ...]
    market_signal: MarketSignal | None
    us_market: USMarketSnapshot | None
    alerts: tuple[Alert, ...]
    checked_at: datetime
