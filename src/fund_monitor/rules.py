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
        matched = _check_quote(quote, rules, now)
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

    tier = _match_alert_tier(quote, rules)
    if tier is None:
        return None

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
    return tier.name, reasons


def _match_alert_tier(
    quote: EtfQuote,
    rules: RuleConfig,
) -> AlertTierConfig | None:
    matched: AlertTierConfig | None = None
    for tier in rules.alert_tiers:
        if not tier.enabled:
            continue
        if not tier.name:
            continue
        if not _quote_matches_tier(quote, tier):
            continue
        matched = tier
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
