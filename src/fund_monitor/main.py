from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_config, resolve_config_path
from .econ_calendar import describe_macro_preview, get_today_macro_events, is_near_830_et
from .models import Alert, MonitorRun
from .news import fallback_news_impacts
from .notify import EmailNotifier, format_score_report, format_yield_update
from .providers import AkshareMarketDataProvider
from .rules import evaluate_alerts
from .scoring import (
    combine_scores,
    score_macro_event,
    score_nq_futures,
    score_tech_relative,
    score_trend_shape,
    score_yields,
)
from .state import load_state, save_state


def main() -> int:
    parser = argparse.ArgumentParser(description="纳指 ETF 监控提醒")
    parser.add_argument("--config", help="配置文件路径，默认优先读取 config.json")
    parser.add_argument("--once", action="store_true", help="只检查一次后退出")
    parser.add_argument("--send-snapshot", action="store_true", help="发送当前全部 ETF 明细")
    parser.add_argument("--send-startup-snapshot", action="store_true", help="启动后只发送一次快照")
    parser.add_argument("--send-futures-trend", action="store_true", help="发送 NQ=F 中国交易时段下午趋势快照")
    parser.add_argument("--send-afternoon-brief", action="store_true", help="发送 14:30 纳指期货预测邮件")
    parser.add_argument("--send-morning-prediction", action="store_true", help="发送 9:20 纳指复盘和买入建议邮件")
    parser.add_argument("--check-yield-alert", action="store_true", help="检测 2Y/10Y 美债收益率新日期并发送提醒")
    parser.add_argument("--check-econ-release-alert", action="store_true", help="检测 8:30 ET 宏观数据窗口并发送提醒")
    parser.add_argument("--state-path", default="storage/state.json", help="去重状态文件路径")
    parser.add_argument("--max-runtime-seconds", type=int, help="持续运行的最长秒数，到时正常退出")
    args = parser.parse_args()

    started_at = datetime.now()
    project_root = Path.cwd()
    config_path = resolve_config_path(args.config, project_root)
    config = load_config(config_path)
    provider = AkshareMarketDataProvider()
    notifier = EmailNotifier(config.email)
    sent_at_by_alert_key: dict[str, datetime] = {}
    startup_snapshot_sent = False
    state_path = Path(args.state_path)

    print(f"Using config: {config_path}")
    if args.send_afternoon_brief:
        send_afternoon_brief(config, provider, notifier)
        if args.once:
            return 0
    if args.send_morning_prediction:
        send_morning_prediction(config, provider, notifier)
        if args.once:
            return 0
    if args.check_yield_alert:
        check_yield_alert(provider, notifier, state_path)
        if args.once:
            return 0
    if args.check_econ_release_alert:
        check_econ_release_alert(provider, notifier, state_path)
        if args.once:
            return 0

    if args.send_futures_trend:
        trend_snapshot = provider.get_futures_trend_snapshot(config.us_market.primary_symbol)
        notifier.send_futures_trend_snapshot(trend_snapshot)
        print(
            f"{datetime.now().isoformat(timespec='seconds')} "
            f"已发送 NQ=F 趋势快照：{trend_snapshot.trend_label}"
        )
        if args.once:
            return 0

    while True:
        snapshot = run_once(config, provider)
        if args.send_snapshot or (args.send_startup_snapshot and not startup_snapshot_sent):
            notifier.send_snapshot(
                list(snapshot.quotes),
                snapshot.market_signal,
                snapshot.us_market,
                snapshot.checked_at,
            )
            startup_snapshot_sent = True

        fresh_alerts = dedupe_alerts(list(snapshot.alerts), sent_at_by_alert_key, config.rules.dedupe_minutes)
        if fresh_alerts:
            notifier.send(fresh_alerts)
            for alert in fresh_alerts:
                sent_at_by_alert_key[_alert_key(alert)] = alert.triggered_at
        elif snapshot.alerts:
            print(f"{datetime.now().isoformat(timespec='seconds')} 已触发但处于去重窗口内")
        else:
            print(f"{datetime.now().isoformat(timespec='seconds')} 暂无符合条件的 ETF")

        if args.once:
            return 0
        if args.max_runtime_seconds is not None:
            elapsed_seconds = (datetime.now() - started_at).total_seconds()
            remaining_seconds = args.max_runtime_seconds - elapsed_seconds
            if remaining_seconds <= 0:
                print(f"{datetime.now().isoformat(timespec='seconds')} 已达到最大运行时长，正常退出")
                return 0
            time.sleep(min(config.poll_interval_seconds, remaining_seconds))
        else:
            time.sleep(config.poll_interval_seconds)


def run_once(config, provider: AkshareMarketDataProvider) -> MonitorRun:
    now = datetime.now()
    quotes = provider.get_etf_quotes(config.etfs)
    try:
        us_market = provider.get_us_market_snapshot(config.us_market)
        quotes = provider.apply_us_market_adjustment(quotes, us_market)
    except Exception as exc:
        print(f"美股/汇率数据获取失败：{exc}")
        us_market = None

    try:
        market_signal = provider.get_nasdaq_signal(config.nasdaq)
    except Exception as exc:
        print(f"纳指数据获取失败：{exc}")
        market_signal = None

    _print_snapshot(quotes, market_signal, us_market)
    alerts = evaluate_alerts(quotes, market_signal, us_market, config.rules, now)
    return MonitorRun(
        quotes=tuple(quotes),
        market_signal=market_signal,
        us_market=us_market,
        alerts=tuple(alerts),
        checked_at=now,
    )


def send_afternoon_brief(config, provider: AkshareMarketDataProvider, notifier: EmailNotifier) -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    futures = provider._try_get_yahoo_chart_quote(config.us_market.primary_symbol)
    try:
        trend_snapshot = provider.get_futures_trend_snapshot(config.us_market.primary_symbol)
    except Exception as exc:
        print(f"Futures trend snapshot failed: {exc}")
        trend_snapshot = None
    nq_item = score_nq_futures(futures.change_pct if futures else None)
    items = [
        nq_item,
        score_yields(None, None),
        score_macro_event(None, "今晚 20:30 宏观数据预告"),
        score_tech_relative(None, None, None),
        score_trend_shape(None),
    ]
    score = combine_scores(items)
    subject, body = format_score_report(
        title_date=now.date().isoformat(),
        score=score,
        key_reasons=[
            nq_item.reason,
            "14:30 是第一版方向判断，最终金额应结合 9:20 复盘和 20:30 数据再修正。",
        ],
        risk_reversals=[
            "20:30 ET 宏观数据明显降温，同时美债收益率回落。",
            "美股开盘前 NQ 从偏空区间重新回到中性或偏多区间。",
            "大型科技股或芯片股明显强于大盘。",
        ],
        extra_sections=[
            (
                "【14:30 纳指期货快报】",
                "\n".join(
                    [
                        f"NQ 当前：{_fmt_num(futures.price if futures else None)}",
                        f"较前收盘：{_fmt_pct_from_pct(futures.change_pct if futures else None)}",
                        f"信号：{nq_item.label}",
                        f"解释：{nq_item.reason}",
                    ]
                ),
            ),
            (
                "【原 14:30 NQ 分时趋势快照】",
                _format_futures_trend_section(trend_snapshot),
            ),
        ],
    )
    notifier.send_prediction_report(subject, body)


def send_morning_prediction(config, provider: AkshareMarketDataProvider, notifier: EmailNotifier) -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    quotes = provider.get_etf_quotes(config.etfs)
    us_market = provider.get_us_market_snapshot(config.us_market)
    quotes = provider.apply_us_market_adjustment(quotes, us_market)
    relative = provider.get_market_relative_snapshot()
    try:
        yields = provider.get_treasury_yield_snapshot()
        yield_item = score_yields(yields.two_year_change_bp, yields.ten_year_change_bp)
    except Exception as exc:
        yields = None
        yield_item = score_yields(None, None)
        print(f"Yield data failed: {exc}")

    nq_item = score_nq_futures(us_market.primary.change_pct if us_market and us_market.primary else None)
    macro_item = score_macro_event(None, "今晚 8:30 ET 宏观数据日历")
    tech_item = score_tech_relative(
        relative.qqq.change_pct if relative.qqq else None,
        relative.spy.change_pct if relative.spy else None,
        relative.dia.change_pct if relative.dia else None,
        relative.smh.change_pct if relative.smh else None,
    )
    trend_item = score_trend_shape(
        relative.qqq_shape.shape if relative.qqq_shape else None,
        relative.qqq_shape.close_position if relative.qqq_shape else None,
    )
    score = combine_scores([nq_item, yield_item, macro_item, tech_item, trend_item])
    news_lines = [
        f"事件：{item.event}\n影响路径：{item.impact_path}\n对纳指方向：{item.nasdaq_direction}\n是否改变今日买入建议：{item.buy_change}"
        for item in fallback_news_impacts()
    ]
    subject, body = format_score_report(
        title_date=now.date().isoformat(),
        score=score,
        key_reasons=[nq_item.reason, yield_item.reason, tech_item.reason, trend_item.reason],
        risk_reversals=[
            "8:30 ET 数据公布结果与当前方向明显相反。",
            "数据公布后 2Y/10Y 美债收益率反向波动超过 5bp。",
            "美股开盘前 NQ 从偏空转为偏多，或从偏多转为偏空。",
        ],
        extra_sections=[
            ("今晚 20:30 美国数据预告", describe_macro_preview(now)),
            ("最新美国重要事件", "\n\n".join(news_lines)),
            (
                "QQQ/NDX 昨晚走势形态",
                "\n".join(
                    [
                        f"QQQ 涨跌幅：{_fmt_pct_from_pct(relative.qqq.change_pct if relative.qqq else None)}",
                        f"NDX 涨跌幅：{_fmt_pct_from_pct(relative.ndx.change_pct if relative.ndx else None)}",
                        f"盘中形态：{_cn_shape(relative.qqq_shape.shape if relative.qqq_shape else None)}",
                        f"尾盘位置：{_fmt_num(relative.qqq_shape.close_position if relative.qqq_shape else None)}",
                    ]
                ),
            ),
            (
                "美债收益率",
                "N/A"
                if yields is None
                else "\n".join(
                    [
                        f"2Y：{_fmt_num(yields.two_year.value if yields.two_year else None)}%，{_fmt_bp(yields.two_year_change_bp)}",
                        f"10Y：{_fmt_num(yields.ten_year.value if yields.ten_year else None)}%，{_fmt_bp(yields.ten_year_change_bp)}",
                    ]
                ),
            ),
            ("场内 ETF 实时快照", _format_etf_snapshot_section(quotes)),
        ],
    )
    notifier.send_prediction_report(subject, body)


def check_yield_alert(provider: AkshareMarketDataProvider, notifier: EmailNotifier, state_path: Path) -> None:
    state = load_state(state_path)
    snapshot = provider.get_treasury_yield_snapshot()
    latest_date = snapshot.latest_date
    if not latest_date:
        print("No Treasury yield date available.")
        return
    if state.get("last_yield_date") == latest_date:
        print(f"Treasury yield date {latest_date} already sent.")
        return

    yield_item = score_yields(snapshot.two_year_change_bp, snapshot.ten_year_change_bp)
    score = combine_scores(
        [
            score_nq_futures(None),
            yield_item,
            score_macro_event(None, "本次不是宏观数据触发邮件"),
            score_tech_relative(None, None, None),
            score_trend_shape(None),
        ]
    )
    subject, body = format_yield_update(snapshot, score, yield_item)
    notifier.send_prediction_report(subject, body)
    state["last_yield_date"] = latest_date
    save_state(state_path, state)


def check_econ_release_alert(provider: AkshareMarketDataProvider, notifier: EmailNotifier, state_path: Path) -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if not is_near_830_et(now):
        print("Not near 08:30 ET macro release window.")
        return
    events = get_today_macro_events(now)
    state = load_state(state_path)
    sent = state.setdefault("sent_econ_releases", {})
    date_key = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    if events:
        pending_names = [event.name for event in events]
        pending = [event for event in events if sent.get(f"{date_key}:{event.name}") is None]
        key_reasons = [event.impact_path for event in pending]
        event_section = "\n".join(f"{event.name}，发布机构：{event.agency}，时间：08:30 ET" for event in pending)
    else:
        pending_names = ["8:30 ET 宏观数据窗口监测"]
        pending = []
        state_key = f"{date_key}:8:30 ET macro window"
        if sent.get(state_key) is not None:
            print(f"Macro release window for {date_key} already sent.")
            return
        key_reasons = [
            "当前没有命中内置精确日历，但 08:30 ET 是 CPI、PPI、初请、GDP、PCE、零售销售等美国高频宏观数据常见发布时间窗口，需要人工核对官方日历和实际公布值。"
        ]
        event_section = (
            "未识别到内置明确事件。请核对 BLS、DOL、BEA、Census 官方日历；"
            "若实际公布值明显高于预期，通常压制纳指；若明显降温，通常利好纳指。"
        )
    if not pending:
        if events:
            print(f"Macro releases for {date_key} already sent.")
            return

    macro_item = score_macro_event(None, ", ".join(pending_names))
    score = combine_scores(
        [
            score_nq_futures(None),
            score_yields(None, None),
            macro_item,
            score_tech_relative(None, None, None),
            score_trend_shape(None),
        ]
    )
    subject, body = format_score_report(
        title_date=date_key,
        score=score,
        key_reasons=key_reasons,
        risk_reversals=[
            "实际数据明显高于预期，推动 2Y/10Y 收益率继续上行。",
            "实际数据明显低于预期，收益率回落且 NQ 反弹。",
        ],
        extra_sections=[("事件触发", event_section)],
    )
    notifier.send_prediction_report(subject, body)
    if events:
        for event in pending:
            sent[f"{date_key}:{event.name}"] = now.isoformat()
    else:
        sent[f"{date_key}:8:30 ET macro window"] = now.isoformat()
    save_state(state_path, state)


def dedupe_alerts(
    alerts: list[Alert],
    sent_at_by_alert_key: dict[str, datetime],
    dedupe_minutes: int,
) -> list[Alert]:
    if dedupe_minutes <= 0:
        return alerts

    window = timedelta(minutes=dedupe_minutes)
    fresh: list[Alert] = []
    for alert in alerts:
        last_sent_at = sent_at_by_alert_key.get(_alert_key(alert))
        if last_sent_at is None or alert.triggered_at - last_sent_at >= window:
            fresh.append(alert)
    return fresh


def _alert_key(alert: Alert) -> str:
    return f"{alert.quote.symbol}:{alert.level}"


def _print_snapshot(quotes, market_signal, us_market) -> None:
    print("")
    print(datetime.now().isoformat(timespec="seconds"))
    if us_market and us_market.primary:
        print(
            f"{us_market.primary.symbol} "
            f"涨跌幅={_fmt_pct_from_pct(us_market.primary.change_pct)} "
            f"更新时间={us_market.primary.updated_at or 'N/A'} "
            f"source={us_market.primary.source}"
        )
    if us_market and us_market.fx:
        print(
            f"{us_market.fx.symbol} "
            f"涨跌幅={_fmt_pct_from_pct(us_market.fx.change_pct)} "
            f"更新时间={us_market.fx.updated_at or 'N/A'}"
        )
    if market_signal:
        print(
            f"{market_signal.name}({market_signal.symbol}) "
            f"涨跌幅={_fmt_pct_from_pct(market_signal.change_pct)} "
            f"source={market_signal.source}"
        )
    print("代码      名称                  价格      IOPV      溢价率   修正后溢价     涨跌幅     成交额")
    for quote in quotes:
        print(
            f"{quote.symbol:<8}"
            f"{quote.name[:10]:<12}"
            f"{_fmt_num(quote.price):>8}"
            f"{_fmt_num(quote.iopv):>10}"
            f"{_fmt_pct(quote.premium_rate):>10}"
            f"{_fmt_pct(quote.adjusted_premium_rate):>12}"
            f"{_fmt_pct_from_pct(quote.change_pct):>10}"
            f"{_fmt_cny(quote.turnover_cny):>12}"
        )


def _fmt_num(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def _fmt_pct_from_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def _fmt_bp(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.0f}bp"


def _cn_shape(shape: str | None) -> str:
    return {
        "gap up fade": "高开低走",
        "selloff": "一路走弱",
        "opened low kept falling": "低开后继续走弱",
        "rally faded": "冲高回落",
        "close near low": "收盘接近最低点",
        "gap down rally": "低开高走",
        "v reversal": "V 型反转",
        "opened high kept rising": "高开后继续走强",
        "close near high": "收盘接近最高点",
    }.get(shape or "", shape or "N/A")


def _format_etf_snapshot_section(quotes) -> str:
    lines = ["代码  名称  价格  涨跌幅  成交额  IOPV  溢价率  修正后溢价率  来源"]
    for quote in quotes:
        lines.append(
            "  ".join(
                [
                    quote.symbol,
                    quote.name or "N/A",
                    _fmt_num(quote.price),
                    _fmt_pct_from_pct(quote.change_pct),
                    _fmt_cny(quote.turnover_cny),
                    _fmt_num(quote.iopv),
                    _fmt_pct(quote.premium_rate),
                    _fmt_pct(quote.adjusted_premium_rate),
                    quote.source,
                ]
            )
        )
    return "\n".join(lines)


def _format_futures_trend_section(snapshot) -> str:
    if snapshot is None:
        return "NQ 分时趋势数据暂不可用。"
    lines = [
        f"数据区间：{snapshot.start_at.isoformat(sep=' ', timespec='minutes') if snapshot.start_at else 'N/A'} - {snapshot.end_at.isoformat(sep=' ', timespec='minutes') if snapshot.end_at else 'N/A'}",
        f"有效分时点：{len(snapshot.points)}",
        f"起点价格：{_fmt_num(snapshot.start_price)}",
        f"最新价格：{_fmt_num(snapshot.end_price)}",
        f"区间涨跌幅：{_fmt_pct_from_pct(snapshot.change_pct)}",
        f"区间最高：{_fmt_num(snapshot.high_price)}",
        f"区间最低：{_fmt_num(snapshot.low_price)}",
        f"最大回撤：{_fmt_pct_from_pct(snapshot.max_drawdown_pct)}",
        f"后段动量：{_fmt_pct_from_pct(snapshot.late_change_pct)}",
        f"趋势结论：{snapshot.trend_label}",
        f"模型判断：{snapshot.prediction}",
    ]
    lines.extend(f"- {item}" for item in snapshot.rationale)
    return "\n".join(lines)


def _fmt_cny(value: float | None) -> str:
    if value is None:
        return "N/A"
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:.2f}亿"
    if abs(value) >= 10_000:
        return f"{value / 10_000:.2f}万"
    return f"{value:.0f}"


if __name__ == "__main__":
    raise SystemExit(main())
