from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ETFS = ("513100", "159941", "159632", "159659", "513300")


@dataclass(frozen=True)
class AlertTierConfig:
    enabled: bool = True
    name: str = ""
    etf_max_change_pct: float = 0.0
    max_premium_rate: float = 0.0
    max_adjusted_premium_rate: float | None = None
    min_turnover_cny: float = 100_000_000


@dataclass(frozen=True)
class RuleConfig:
    max_premium_rate: float = 0.015
    max_adjusted_premium_rate: float = 0.015
    use_adjusted_premium: bool = True
    min_turnover_cny: float = 100_000_000
    stale_after_seconds: int = 120
    dedupe_minutes: int = 60
    alert_tiers: tuple[AlertTierConfig, ...] = (
        AlertTierConfig(
            name="观察提醒",
            etf_max_change_pct=-1.5,
            max_premium_rate=0.03,
            max_adjusted_premium_rate=None,
            min_turnover_cny=100_000_000,
        ),
        AlertTierConfig(
            name="重点提醒",
            etf_max_change_pct=-2.5,
            max_premium_rate=0.02,
            max_adjusted_premium_rate=0.02,
            min_turnover_cny=100_000_000,
        ),
        AlertTierConfig(
            name="强抄底提醒",
            etf_max_change_pct=-4.0,
            max_premium_rate=0.015,
            max_adjusted_premium_rate=0.015,
            min_turnover_cny=100_000_000,
        ),
        AlertTierConfig(
            name="极端提醒",
            etf_max_change_pct=-6.0,
            max_premium_rate=0.01,
            max_adjusted_premium_rate=0.01,
            min_turnover_cny=100_000_000,
        ),
    )


@dataclass(frozen=True)
class USMarketConfig:
    enabled: bool = True
    primary_symbol: str = "NQ=F"
    fallback_symbol: str = "QQQ"
    nasdaq_index_symbol: str = "^NDX"
    fx_symbol: str = "CNH=X"
    mega_cap_symbols: tuple[str, ...] = ("AAPL", "MSFT", "NVDA")
    stale_after_minutes: int = 720


@dataclass(frozen=True)
class NasdaqConfig:
    enabled: bool = True
    symbol: str = "NDX"
    max_change_pct: float = -0.5


@dataclass(frozen=True)
class EmailConfig:
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    use_tls: bool = True
    username: str = ""
    password_env: str = "ETF_MONITOR_SMTP_PASSWORD"
    from_addr: str = ""
    to_addrs: tuple[str, ...] = ()


@dataclass(frozen=True)
class MonitorConfig:
    poll_interval_seconds: int = 300
    etfs: tuple[str, ...] = DEFAULT_ETFS
    rules: RuleConfig = RuleConfig()
    us_market: USMarketConfig = USMarketConfig()
    nasdaq: NasdaqConfig = NasdaqConfig()
    email: EmailConfig = EmailConfig()


def load_config(path: Path) -> MonitorConfig:
    data = json.loads(path.read_text(encoding="utf-8"))

    rules_data = data.get("rules", {})
    default_rules = RuleConfig()
    us_market_data = data.get("us_market", {})
    nasdaq_data = data.get("nasdaq", {})
    email_data = data.get("email", {})

    return MonitorConfig(
        poll_interval_seconds=int(data.get("poll_interval_seconds", 300)),
        etfs=tuple(str(item).zfill(6) for item in data.get("etfs", DEFAULT_ETFS)),
        rules=RuleConfig(
            max_premium_rate=float(rules_data.get("max_premium_rate", 0.015)),
            max_adjusted_premium_rate=float(
                rules_data.get("max_adjusted_premium_rate", rules_data.get("max_premium_rate", 0.015))
            ),
            use_adjusted_premium=bool(rules_data.get("use_adjusted_premium", True)),
            min_turnover_cny=float(rules_data.get("min_turnover_cny", 100_000_000)),
            stale_after_seconds=int(rules_data.get("stale_after_seconds", 120)),
            dedupe_minutes=int(rules_data.get("dedupe_minutes", 60)),
            alert_tiers=_load_alert_tiers(rules_data.get("alert_tiers"), default_rules.alert_tiers),
        ),
        us_market=USMarketConfig(
            enabled=bool(us_market_data.get("enabled", True)),
            primary_symbol=str(us_market_data.get("primary_symbol", "NQ=F")),
            fallback_symbol=str(us_market_data.get("fallback_symbol", "QQQ")),
            nasdaq_index_symbol=str(us_market_data.get("nasdaq_index_symbol", "^NDX")),
            fx_symbol=str(us_market_data.get("fx_symbol", "CNH=X")),
            mega_cap_symbols=tuple(
                str(item).upper() for item in us_market_data.get("mega_cap_symbols", ["AAPL", "MSFT", "NVDA"])
            ),
            stale_after_minutes=int(us_market_data.get("stale_after_minutes", 720)),
        ),
        nasdaq=NasdaqConfig(
            enabled=bool(nasdaq_data.get("enabled", True)),
            symbol=str(nasdaq_data.get("symbol", "NDX")),
            max_change_pct=float(nasdaq_data.get("max_change_pct", -0.5)),
        ),
        email=_load_email_config(email_data),
    )


def resolve_config_path(path_arg: str | None, cwd: Path) -> Path:
    if path_arg:
        return Path(path_arg)

    config_path = cwd / "config.json"
    if config_path.exists():
        return config_path

    return cwd / "config.example.json"


def require_keys(config: EmailConfig) -> list[str]:
    missing: list[str] = []
    required: dict[str, Any] = {
        "smtp_host": config.smtp_host,
        "username": config.username,
        "from_addr": config.from_addr,
        "to_addrs": config.to_addrs,
    }
    for key, value in required.items():
        if not value:
            missing.append(key)
    return missing


def _load_email_config(email_data: dict[str, Any]) -> EmailConfig:
    to_addrs = _env("ETF_MONITOR_MAIL_TO")
    if to_addrs:
        parsed_to_addrs = tuple(item.strip() for item in to_addrs.split(",") if item.strip())
    else:
        parsed_to_addrs = tuple(str(item) for item in email_data.get("to_addrs", []))

    return EmailConfig(
        enabled=_env_bool("ETF_MONITOR_EMAIL_ENABLED", bool(email_data.get("enabled", False))),
        smtp_host=_env("ETF_MONITOR_SMTP_HOST", str(email_data.get("smtp_host", ""))),
        smtp_port=int(_env("ETF_MONITOR_SMTP_PORT", str(email_data.get("smtp_port", 587)))),
        use_tls=_env_bool("ETF_MONITOR_SMTP_TLS", bool(email_data.get("use_tls", True))),
        username=_env("ETF_MONITOR_SMTP_USER", str(email_data.get("username", ""))),
        password_env=str(email_data.get("password_env", "ETF_MONITOR_SMTP_PASSWORD")),
        from_addr=_env("ETF_MONITOR_MAIL_FROM", str(email_data.get("from_addr", ""))),
        to_addrs=parsed_to_addrs,
    )


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_alert_tiers(value: object, defaults: tuple[AlertTierConfig, ...]) -> tuple[AlertTierConfig, ...]:
    if not isinstance(value, list):
        return defaults

    tiers: list[AlertTierConfig] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        max_adjusted = item.get("max_adjusted_premium_rate")
        tiers.append(
            AlertTierConfig(
                enabled=bool(item.get("enabled", True)),
                name=str(item.get("name", "")),
                etf_max_change_pct=float(item.get("etf_max_change_pct", 0.0)),
                max_premium_rate=float(item.get("max_premium_rate", 0.0)),
                max_adjusted_premium_rate=None if max_adjusted is None else float(max_adjusted),
                min_turnover_cny=float(item.get("min_turnover_cny", 100_000_000)),
            )
        )
    return tuple(tiers) or defaults
