from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.message import EmailMessage

from .config import EmailConfig, require_keys
from .models import Alert, EtfQuote, FuturesTrendSnapshot, MarketSignal, USMarketSnapshot


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
        us_market: USMarketSnapshot | None,
        checked_at: datetime,
    ) -> None:
        body = format_snapshot(quotes, market_signal, us_market, checked_at)
        self._deliver("【纳指 ETF 实时快照】", body)

    def send_futures_trend_snapshot(self, snapshot: FuturesTrendSnapshot) -> None:
        body = format_futures_trend_snapshot(snapshot)
        self._deliver("【NQ=F 下午趋势快照】", body)

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
                f"【{alert.level}】{quote.symbol} {quote.name}",
                f"当前价格：{_format_float(quote.price)}",
                f"IOPV：{_format_float(quote.iopv)}",
                f"溢价率：{_format_percent(quote.premium_rate)}",
                f"修正后参考值：{_format_float(quote.adjusted_reference_value)}",
                f"修正后溢价率：{_format_percent(quote.adjusted_premium_rate)}",
                f"涨跌幅：{_format_percent_from_pct(quote.change_pct)}",
                f"成交额：{_format_cny(quote.turnover_cny)}",
                f"ETF更新时间：{quote.updated_at or 'N/A'}",
            ]
        )
        lines.append("触发条件：")
        lines.extend(f"- {reason}" for reason in alert.reasons)
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
    us_market: USMarketSnapshot | None,
    checked_at: datetime,
) -> str:
    lines = ["【纳指 ETF 实时快照】", f"检查时间：{checked_at.isoformat(timespec='seconds')}", ""]
    if us_market:
        lines.extend(_format_us_market_snapshot(us_market))
        lines.append("")
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
                f"修正后参考值：{_format_float(quote.adjusted_reference_value)}",
                f"修正后溢价率：{_format_percent(quote.adjusted_premium_rate)}",
                f"涨跌幅：{_format_percent_from_pct(quote.change_pct)}",
                f"成交额：{_format_cny(quote.turnover_cny)}",
                f"ETF更新时间：{quote.updated_at or 'N/A'}",
                "",
            ]
        )

    lines.append("此邮件只做监控提醒，不构成买入建议；下单前请在东方财富证券 App 再确认。")
    return "\n".join(lines).strip()


def _format_us_market_snapshot(snapshot: USMarketSnapshot) -> list[str]:
    lines = ["美股/汇率修正："]
    if snapshot.primary:
        lines.append(_format_us_quote("主指标", snapshot.primary))
    if snapshot.fallback:
        lines.append(_format_us_quote("备用", snapshot.fallback))
    if snapshot.nasdaq_index:
        lines.append(_format_us_quote("纳指收盘", snapshot.nasdaq_index))
    if snapshot.fx:
        lines.append(_format_us_quote("汇率", snapshot.fx))
    for quote in snapshot.mega_caps:
        lines.append(_format_us_quote("权重股", quote))
    lines.append(f"修正因子：{_format_percent(snapshot.adjustment_rate)}（{snapshot.adjustment_source or 'N/A'}）")
    return lines


def _format_us_quote(label: str, quote) -> str:
    return (
        f"{label} {quote.symbol}：{_format_float(quote.price)}，"
        f"涨跌幅 {_format_percent_from_pct(quote.change_pct)}，"
        f"更新时间 {quote.updated_at or 'N/A'}，来源 {quote.source}"
    )


def format_futures_trend_snapshot(snapshot: FuturesTrendSnapshot) -> str:
    lines = [
        "【NQ=F 下午趋势快照】",
        f"检查时间：{snapshot.checked_at.isoformat(timespec='seconds')}",
        "",
        f"{snapshot.symbol} {snapshot.name}",
        f"数据区间：{_format_dt(snapshot.start_at)} - {_format_dt(snapshot.end_at)}",
        f"有效分时点：{len(snapshot.points)}",
        f"起点价格：{_format_float(snapshot.start_price)}",
        f"最新价格：{_format_float(snapshot.end_price)}",
        f"区间涨跌幅：{_format_percent_from_pct(snapshot.change_pct)}",
        f"区间最高：{_format_float(snapshot.high_price)}",
        f"区间最低：{_format_float(snapshot.low_price)}",
        f"最大回撤：{_format_percent_from_pct(snapshot.max_drawdown_pct)}",
        f"后段动量：{_format_percent_from_pct(snapshot.late_change_pct)}",
        "",
        f"趋势结论：{snapshot.trend_label}",
        f"模型判断：{snapshot.prediction}",
        "",
        "判断依据：",
    ]
    lines.extend(f"- {item}" for item in snapshot.rationale)
    lines.extend(
        [
            "",
            "说明：这是基于 NQ=F 白天分时趋势的规则模型预测，只做当晚纳指方向观察，不构成买入建议。",
            f"来源：{snapshot.source}",
        ]
    )
    return "\n".join(lines).strip()


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return "N/A"
    return value.isoformat(sep=" ", timespec="minutes")


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
