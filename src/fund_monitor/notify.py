from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.message import EmailMessage

from .config import EmailConfig, require_keys
from .models import Alert, EtfQuote, FuturesTrendSnapshot, MarketSignal, TreasuryYieldSnapshot, USMarketSnapshot
from .scoring import ScoreItem, ScoreResult


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

    def send_prediction_report(self, subject: str, body: str) -> None:
        self._deliver(subject, body)

    def _deliver(self, subject: str, body: str) -> None:
        if not self.config.enabled:
            print(body)
            return

        missing = require_keys(self.config)
        if missing:
            print(f"Email config missing: {', '.join(missing)}. Printing message instead of failing.")
            print(f"Subject: {subject}")
            print(body)
            return

        password = os.environ.get(self.config.password_env)
        if not password:
            print(f"Missing SMTP password env var: {self.config.password_env}. Printing message instead of failing.")
            print(f"Subject: {subject}")
            print(body)
            return

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
        lines.append("已触发对应提醒档位，请人工打开东方财富证券 App 再确认。")
        lines.append("")
    us_market = alerts[0].us_market if alerts else None
    if us_market:
        lines.extend(_format_us_market_reference(us_market))
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
    if snapshot.nasdaq_index_trend:
        trend = snapshot.nasdaq_index_trend
        lines.append(
            f"{trend.symbol} 趋势：昨日 {_format_percent_from_pct(trend.one_day_change_pct)}，"
            f"近3日 {_format_percent_from_pct(trend.three_day_change_pct)}，"
            f"近5日 {_format_percent_from_pct(trend.five_day_change_pct)}"
        )
    if snapshot.fx:
        lines.append(_format_us_quote("汇率", snapshot.fx))
    for quote in snapshot.mega_caps:
        lines.append(_format_us_quote("权重股", quote))
    lines.append(f"修正因子：{_format_percent(snapshot.adjustment_rate)}（{snapshot.adjustment_source or 'N/A'}）")
    return lines


def _format_us_market_reference(snapshot: USMarketSnapshot) -> list[str]:
    lines = ["美股参考信息（不参与本次提醒触发）："]
    if snapshot.nasdaq_index_trend:
        trend = snapshot.nasdaq_index_trend
        lines.extend(
            [
                f"{trend.symbol} 最近收盘：{_format_float(trend.latest_close)}（{trend.latest_date or 'N/A'}）",
                f"{trend.symbol} 昨日变化：{_format_percent_from_pct(trend.one_day_change_pct)}",
                f"{trend.symbol} 近3个交易日：{_format_percent_from_pct(trend.three_day_change_pct)}",
                f"{trend.symbol} 近5个交易日：{_format_percent_from_pct(trend.five_day_change_pct)}",
            ]
        )
    elif snapshot.nasdaq_index:
        lines.append(_format_us_quote("纳指收盘", snapshot.nasdaq_index))
    if snapshot.primary:
        lines.append(_format_us_quote("当天实时期货", snapshot.primary))
    if snapshot.fallback:
        lines.append(_format_us_quote("QQQ昨夜/盘前", snapshot.fallback))
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


def format_score_report(
    title_date: str,
    score: ScoreResult,
    key_reasons: list[str],
    risk_reversals: list[str],
    extra_sections: list[tuple[str, str]] | None = None,
) -> tuple[str, str]:
    subject = f"【纳指预测】{title_date}：{_cn_trend(score.trend_label)}，总分 {score.total_score:+d}，建议买入 {score.recommended_buy} 元"
    lines = [
        f"今日结论：{_cn_trend(score.trend_label)}，建议买入 {score.recommended_buy} 元。",
        "",
        "1. 五项打分表",
    ]
    for item in score.items:
        lines.append(f"- {item.name}: {item.score:+d}，{item.label}。{item.reason}")

    lines.extend(
        [
            "",
            "2. 关键原因",
        ]
    )
    lines.extend(f"- {reason}" for reason in key_reasons)
    lines.extend(
        [
            "",
            f"3. 趋势预测：上涨概率 {score.upside_probability}%，下跌概率 {score.downside_probability}%。",
            f"主判断：{_cn_trend(score.trend_label)}。最关键变量：{score.key_variable}。",
            "",
            f"4. 今日操作：南方纳指100 I 类今日买入 {score.recommended_buy} 元。",
            "",
            "5. 风险提示：以下情况会推翻判断",
        ]
    )
    lines.extend(f"- {item}" for item in risk_reversals)
    if extra_sections:
        for heading, body in extra_sections:
            lines.extend(["", heading, body])
    return subject, "\n".join(lines).strip()


def format_yield_update(snapshot: TreasuryYieldSnapshot, score: ScoreResult, yield_item: ScoreItem | None = None) -> tuple[str, str]:
    title_date = snapshot.latest_date or snapshot.checked_at.date().isoformat()
    subject = f"【美债收益率更新】{title_date}：{_cn_trend(score.trend_label)}，建议买入 {score.recommended_buy} 元"
    two = snapshot.two_year
    ten = snapshot.ten_year
    lines = [
        "【美债收益率更新】",
        f"2Y：{_format_yield(two.value if two else None)}，较前一交易日 {_format_bp(snapshot.two_year_change_bp)}",
        f"10Y：{_format_yield(ten.value if ten else None)}，较前一交易日 {_format_bp(snapshot.ten_year_change_bp)}",
        f"判断：{yield_item.reason if yield_item else score.rationale}",
        f"对纳指影响：{_cn_score_label(yield_item) if yield_item else _cn_trend(score.trend_label)}。",
        f"操作建议：买入 {score.recommended_buy} 元。",
        f"来源：{snapshot.source}",
    ]
    return subject, "\n".join(lines).strip()


def _cn_trend(value: str) -> str:
    return {
        "strong bullish": "明显偏多",
        "bullish": "偏多",
        "range-bound": "震荡",
        "bearish": "偏空",
        "strong bearish": "明显偏空",
    }.get(value, value)


def _cn_score_label(item: ScoreItem | None) -> str:
    if item is None:
        return "中性"
    if item.score <= -2:
        return "明显偏空"
    if item.score <= -1:
        return "偏空"
    if item.score >= 1:
        return "偏多"
    return "中性"


def _format_yield(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def _format_bp(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.0f}bp"


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
