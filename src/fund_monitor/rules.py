from __future__ import annotations

from datetime import datetime

from .config import AlertTierConfig, RuleConfig
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
        matched = _check_quote(quote, market_signal, us_market, rules, now)
        if matched:
            level, reasons = matched
            alerts.append(
                Alert(
                    quote=quote,
                    market_signal=market_signal,
                    us_market=us_market,
                    triggered_at=now,
                    reasons=tuple(reasons),
                    level=level,
                )
            )
    return alerts


def _check_quote(
    quote: EtfQuote,
    market_signal: MarketSignal | None,
    us_market: USMarketSnapshot | None,
    rules: RuleConfig,
    now: datetime,
) -> tuple[str, list[str]] | None:
    if quote.price is None:
        return None
    if quote.iopv is None or quote.premium_rate is None:
        return None
    if quote.turnover_cny is None:
        return None
    if quote.change_pct is None:
        return None
    if not _is_quote_fresh(quote, now=now, rules=rules):
        return None

    matched_tier = _match_alert_tier(quote, market_signal, us_market, rules)
    if matched_tier is None:
        return None

    tier, us_weak_reason = matched_tier
    reasons = [
        f"ETF跌幅 {_format_percent(quote.change_pct / 100)} <= {_format_percent(tier.etf_max_change_pct / 100)}",
        f"溢价率 {_format_percent(quote.premium_rate)} <= {_format_percent(tier.max_premium_rate)}",
        f"成交额 {_format_cny(quote.turnover_cny)} >= {_format_cny(tier.min_turnover_cny)}",
    ]
    if tier.max_adjusted_premium_rate is not None:
        reasons.insert(
            2,
            f"修正后溢价率 {_format_percent(quote.adjusted_premium_rate)} <= "
            f"{_format_percent(tier.max_adjusted_premium_rate)}",
        )
    if us_weak_reason:
        reasons.append(us_weak_reason)
    return tier.name, reasons


def _match_alert_tier(
    quote: EtfQuote,
    market_signal: MarketSignal | None,
    us_market: USMarketSnapshot | None,
    rules: RuleConfig,
) -> tuple[AlertTierConfig, str | None] | None:
    matched: tuple[AlertTierConfig, str | None] | None = None
    for tier in rules.alert_tiers:
        if not tier.enabled:
            continue
        if not tier.name:
            continue
        if not _quote_matches_tier(quote, tier):
            continue
        us_weak_reason = None
        if tier.require_us_weak:
            us_weak_reason = _us_weak_reason(market_signal, us_market, rules)
            if us_weak_reason is None:
                continue
        matched = (tier, us_weak_reason)
    return matched


def _quote_matches_tier(quote: EtfQuote, tier: AlertTierConfig) -> bool:
    if quote.change_pct is None or quote.change_pct > tier.etf_max_change_pct:
        return False
    if quote.premium_rate is None or quote.premium_rate > tier.max_premium_rate:
        return False
    if quote.turnover_cny is None or quote.turnover_cny < tier.min_turnover_cny:
        return False
    if tier.max_adjusted_premium_rate is not None:
        if quote.adjusted_premium_rate is None:
            return False
        if quote.adjusted_premium_rate > tier.max_adjusted_premium_rate:
            return False
    return True


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


def _us_weak_reason(
    market_signal: MarketSignal | None,
    us_market: USMarketSnapshot | None,
    rules: RuleConfig,
) -> str | None:
    candidates: list[tuple[str, float]] = []
    if us_market:
        for quote in (us_market.primary, us_market.nasdaq_index, us_market.fallback):
            if quote and quote.change_pct is not None:
                candidates.append((quote.symbol, quote.change_pct))
    if market_signal and market_signal.change_pct is not None:
        candidates.append((market_signal.symbol, market_signal.change_pct))

    for symbol, change_pct in candidates:
        if change_pct <= rules.market_max_change_pct:
            return (
                f"美股侧明显偏弱：{symbol} 涨跌幅 "
                f"{_format_percent(change_pct / 100)} <= {_format_percent(rules.market_max_change_pct / 100)}"
            )
    return None


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
