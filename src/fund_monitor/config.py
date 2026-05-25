from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ETFS = ("513100", "159941", "159632", "159659", "513300")


@dataclass(frozen=True)
class RuleConfig:
    max_premium_rate: float = 0.015
    min_turnover_cny: float = 100_000_000
    require_nasdaq_down: bool = True
    dedupe_minutes: int = 60


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
    nasdaq: NasdaqConfig = NasdaqConfig()
    email: EmailConfig = EmailConfig()


def load_config(path: Path) -> MonitorConfig:
    data = json.loads(path.read_text(encoding="utf-8"))

    rules_data = data.get("rules", {})
    nasdaq_data = data.get("nasdaq", {})
    email_data = data.get("email", {})

    return MonitorConfig(
        poll_interval_seconds=int(data.get("poll_interval_seconds", 300)),
        etfs=tuple(str(item).zfill(6) for item in data.get("etfs", DEFAULT_ETFS)),
        rules=RuleConfig(
            max_premium_rate=float(rules_data.get("max_premium_rate", 0.015)),
            min_turnover_cny=float(rules_data.get("min_turnover_cny", 100_000_000)),
            require_nasdaq_down=bool(rules_data.get("require_nasdaq_down", True)),
            dedupe_minutes=int(rules_data.get("dedupe_minutes", 60)),
        ),
        nasdaq=NasdaqConfig(
            enabled=bool(nasdaq_data.get("enabled", True)),
            symbol=str(nasdaq_data.get("symbol", "NDX")),
            max_change_pct=float(nasdaq_data.get("max_change_pct", -0.5)),
        ),
        email=EmailConfig(
            enabled=bool(email_data.get("enabled", False)),
            smtp_host=str(email_data.get("smtp_host", "")),
            smtp_port=int(email_data.get("smtp_port", 587)),
            use_tls=bool(email_data.get("use_tls", True)),
            username=str(email_data.get("username", "")),
            password_env=str(email_data.get("password_env", "ETF_MONITOR_SMTP_PASSWORD")),
            from_addr=str(email_data.get("from_addr", "")),
            to_addrs=tuple(str(item) for item in email_data.get("to_addrs", [])),
        ),
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

