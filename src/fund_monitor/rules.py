from __future__ import annotations

from datetime import datetime

from .config import RuleConfig
from .models import Alert, EtfQuote, MarketSignal


def evaluate_alerts(
    quotes: list[EtfQuote],
    market_signal: MarketSignal | None,
    rules: RuleConfig,
    now: datetime,
) -> list[Alert]:
    alerts: list[Alert] = []
    for quote in quotes:
        reasons = _check_quote(quote, market_signal, rules)
        if reasons:
            alerts.append(
                Alert(
                    quote=quote,
                    market_signal=market_signal,
                    triggered_at=now,
                    reasons=tuple(reasons),
                )
            )
    return alerts


def _check_quote(
    quote: EtfQuote,
    market_signal: MarketSignal | None,
    rules: RuleConfig,
) -> list[str]:
    if quote.price is None:
        return []
    if quote.iopv is None or quote.premium_rate is None:
        return []
    if quote.turnover_cny is None:
        return []

    premium_ok = quote.premium_rate <= rules.max_premium_rate
    turnover_ok = quote.turnover_cny >= rules.min_turnover_cny
    nasdaq_ok = True
    if rules.require_nasdaq_down:
        nasdaq_ok = bool(market_signal and market_signal.is_down)

    if not (premium_ok and turnover_ok and nasdaq_ok):
        return []

    reasons = [
        f"溢价率 {_format_percent(quote.premium_rate)} <= {_format_percent(rules.max_premium_rate)}",
        f"成交额 {_format_cny(quote.turnover_cny)} >= {_format_cny(rules.min_turnover_cny)}",
    ]
    if rules.require_nasdaq_down and market_signal:
        reasons.append(f"{market_signal.name} 涨跌幅 {_format_percent(market_signal.change_pct / 100)}")
    return reasons


def _format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def _format_cny(value: float | None) -> str:
    if value is None:
        return "N/A"
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:.2f} 亿"
    if abs(value) >= 10_000:
        return f"{value / 10_000:.2f} 万"
    return f"{value:.2f}"

