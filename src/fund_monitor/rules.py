from __future__ import annotations

from datetime import datetime

from .config import RuleConfig
from .models import Alert, EtfQuote, MarketSignal, USMarketSnapshot


def evaluate_alerts(
    quotes: list[EtfQuote],
    market_signal: MarketSignal | None,
    us_market: USMarketSnapshot | None,
    rules: RuleConfig,
    now: datetime,
) -> list[Alert]:
    alerts: list[Alert] = []
    for quote in quotes:
        reasons = _check_quote(quote, market_signal, us_market, rules, now)
        if reasons:
            alerts.append(
                Alert(
                    quote=quote,
                    market_signal=market_signal,
                    us_market=us_market,
                    triggered_at=now,
                    reasons=tuple(reasons),
                )
            )
    return alerts


def _check_quote(
    quote: EtfQuote,
    market_signal: MarketSignal | None,
    us_market: USMarketSnapshot | None,
    rules: RuleConfig,
    now: datetime,
) -> list[str]:
    if quote.price is None:
        return []
    if quote.iopv is None or quote.premium_rate is None:
        return []
    if quote.turnover_cny is None:
        return []
    if not _is_quote_fresh(quote, now=now, rules=rules):
        return []

    premium_ok = quote.premium_rate <= rules.max_premium_rate
    adjusted_premium_ok = True
    if rules.use_adjusted_premium:
        if quote.adjusted_premium_rate is None:
            return []
        adjusted_premium_ok = quote.adjusted_premium_rate <= rules.max_adjusted_premium_rate

    turnover_ok = quote.turnover_cny >= rules.min_turnover_cny
    nasdaq_ok = True
    if rules.require_nasdaq_down:
        nasdaq_ok = _is_market_down(market_signal, us_market, rules)

    if not (premium_ok and adjusted_premium_ok and turnover_ok and nasdaq_ok):
        return []

    reasons = [
        f"溢价率 {_format_percent(quote.premium_rate)} <= {_format_percent(rules.max_premium_rate)}",
        f"成交额 {_format_cny(quote.turnover_cny)} >= {_format_cny(rules.min_turnover_cny)}",
    ]
    if rules.use_adjusted_premium:
        reasons.insert(
            1,
            f"修正后溢价率 {_format_percent(quote.adjusted_premium_rate)} <= "
            f"{_format_percent(rules.max_adjusted_premium_rate)}",
        )
    if rules.require_nasdaq_down and market_signal:
        reasons.append(f"{market_signal.name} 涨跌幅 {_format_percent(market_signal.change_pct / 100)}")
    if rules.require_nasdaq_down and us_market and us_market.primary and us_market.primary.change_pct is not None:
        reasons.append(f"{us_market.primary.symbol} 涨跌幅 {_format_percent(us_market.primary.change_pct / 100)}")
    return reasons


def _is_market_down(
    market_signal: MarketSignal | None,
    us_market: USMarketSnapshot | None,
    rules: RuleConfig,
) -> bool:
    if us_market and us_market.primary and us_market.primary.change_pct is not None:
        return us_market.primary.change_pct <= rules.market_max_change_pct
    if market_signal:
        return market_signal.is_down
    return False


def _format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def _is_quote_fresh(quote: EtfQuote, now: datetime, rules: RuleConfig) -> bool:
    if rules.stale_after_seconds <= 0 or quote.updated_at is None:
        return True
    try:
        updated_at = datetime.fromisoformat(quote.updated_at)
    except ValueError:
        return True
    if updated_at.tzinfo is not None:
        updated_at = updated_at.astimezone().replace(tzinfo=None)
    return (now - updated_at).total_seconds() <= rules.stale_after_seconds


def _format_cny(value: float | None) -> str:
    if value is None:
        return "N/A"
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:.2f} 亿"
    if abs(value) >= 10_000:
        return f"{value / 10_000:.2f} 万"
    return f"{value:.2f}"
