from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.message import EmailMessage

from .config import EmailConfig, require_keys
from .models import Alert, EtfQuote, MarketSignal


class EmailNotifier:
    def __init__(self, config: EmailConfig) -> None:
        self.config = config

    def send(self, alerts: list[Alert]) -> None:
        if not alerts:
            return

        body = format_alerts(alerts)
        self._deliver("【纳指 ETF 机会提醒】", body)

    def send_snapshot(
        self,
        quotes: list[EtfQuote],
        market_signal: MarketSignal | None,
        checked_at: datetime,
    ) -> None:
        body = format_snapshot(quotes, market_signal, checked_at)
        self._deliver("【纳指 ETF 实时快照】", body)

    def _deliver(self, subject: str, body: str) -> None:
        if not self.config.enabled:
            print(body)
            return

        missing = require_keys(self.config)
        if missing:
            raise ValueError(f"Email config missing: {', '.join(missing)}")

        password = os.environ.get(self.config.password_env)
        if not password:
            raise ValueError(f"Missing SMTP password env var: {self.config.password_env}")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.config.from_addr
        message["To"] = ", ".join(self.config.to_addrs)
        message.set_content(body)

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=20) as smtp:
            if self.config.use_tls:
                smtp.starttls()
            smtp.login(self.config.username, password)
            smtp.send_message(message)


def format_alerts(alerts: list[Alert]) -> str:
    lines = ["【纳指 ETF 机会提醒】", ""]
    for alert in alerts:
        quote = alert.quote
        signal = alert.market_signal
        lines.extend(
            [
                f"{quote.symbol} {quote.name}",
                f"当前价格：{_format_float(quote.price)}",
                f"IOPV：{_format_float(quote.iopv)}",
                f"溢价率：{_format_percent(quote.premium_rate)}",
                f"涨跌幅：{_format_percent_from_pct(quote.change_pct)}",
                f"成交额：{_format_cny(quote.turnover_cny)}",
                f"ETF更新时间：{quote.updated_at or 'N/A'}",
            ]
        )
        if signal:
            lines.append(
                f"{signal.name}：{_format_percent_from_pct(signal.change_pct)}"
                f"（{signal.updated_at or signal.source}）"
            )
        lines.append("符合买入第一档条件，请人工打开东方财富证券 App 再确认。")
        lines.append("")
    return "\n".join(lines).strip()


def format_snapshot(
    quotes: list[EtfQuote],
    market_signal: MarketSignal | None,
    checked_at: datetime,
) -> str:
    lines = ["【纳指 ETF 实时快照】", f"检查时间：{checked_at.isoformat(timespec='seconds')}", ""]
    if market_signal:
        lines.append(
            f"{market_signal.name}({market_signal.symbol})："
            f"{_format_percent_from_pct(market_signal.change_pct)}，来源：{market_signal.source}"
        )
    else:
        lines.append("纳指数据：暂不可用")
    lines.append("")

    for quote in quotes:
        lines.extend(
            [
                f"{quote.symbol} {quote.name}",
                f"当前价格：{_format_float(quote.price)}",
                f"IOPV：{_format_float(quote.iopv)}",
                f"溢价率：{_format_percent(quote.premium_rate)}",
                f"涨跌幅：{_format_percent_from_pct(quote.change_pct)}",
                f"成交额：{_format_cny(quote.turnover_cny)}",
                f"ETF更新时间：{quote.updated_at or 'N/A'}",
                "",
            ]
        )

    lines.append("此邮件只做监控提醒，不构成买入建议；下单前请在东方财富证券 App 再确认。")
    return "\n".join(lines).strip()


def _format_float(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def _format_percent_from_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def _format_cny(value: float | None) -> str:
    if value is None:
        return "N/A"
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:.2f} 亿"
    if abs(value) >= 10_000:
        return f"{value / 10_000:.2f} 万"
    return f"{value:.2f}"
