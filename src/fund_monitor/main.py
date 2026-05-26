from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path

from .config import load_config, resolve_config_path
from .models import Alert, MonitorRun
from .notify import EmailNotifier
from .providers import AkshareMarketDataProvider
from .rules import evaluate_alerts


def main() -> int:
    parser = argparse.ArgumentParser(description="纳指 ETF 监控提醒")
    parser.add_argument("--config", help="配置文件路径，默认优先读取 config.json")
    parser.add_argument("--once", action="store_true", help="只检查一次后退出")
    parser.add_argument("--send-snapshot", action="store_true", help="发送当前全部 ETF 明细")
    parser.add_argument("--send-startup-snapshot", action="store_true", help="启动后只发送一次快照")
    args = parser.parse_args()

    project_root = Path.cwd()
    config_path = resolve_config_path(args.config, project_root)
    config = load_config(config_path)
    provider = AkshareMarketDataProvider()
    notifier = EmailNotifier(config.email)
    sent_at_by_symbol: dict[str, datetime] = {}
    startup_snapshot_sent = False

    print(f"Using config: {config_path}")
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

        fresh_alerts = dedupe_alerts(list(snapshot.alerts), sent_at_by_symbol, config.rules.dedupe_minutes)
        if fresh_alerts:
            notifier.send(fresh_alerts)
            for alert in fresh_alerts:
                sent_at_by_symbol[alert.quote.symbol] = alert.triggered_at
        elif snapshot.alerts:
            print(f"{datetime.now().isoformat(timespec='seconds')} 已触发但处于去重窗口内")
        else:
            print(f"{datetime.now().isoformat(timespec='seconds')} 暂无符合条件的 ETF")

        if args.once:
            return 0
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


def dedupe_alerts(
    alerts: list[Alert],
    sent_at_by_symbol: dict[str, datetime],
    dedupe_minutes: int,
) -> list[Alert]:
    if dedupe_minutes <= 0:
        return alerts

    window = timedelta(minutes=dedupe_minutes)
    fresh: list[Alert] = []
    for alert in alerts:
        last_sent_at = sent_at_by_symbol.get(alert.quote.symbol)
        if last_sent_at is None or alert.triggered_at - last_sent_at >= window:
            fresh.append(alert)
    return fresh


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
