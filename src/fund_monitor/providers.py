from __future__ import annotations

import math
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, time
from io import StringIO
from typing import Iterable
from urllib.parse import quote as url_quote
from zoneinfo import ZoneInfo

import requests

from .config import NasdaqConfig, USMarketConfig
from .models import EtfQuote, FuturesTrendPoint, FuturesTrendSnapshot, MarketSignal, USIndexTrend, USMarketQuote, USMarketSnapshot


EASTMONEY_NDX_URL = (
    "https://push2.eastmoney.com/api/qt/stock/get"
    "?secid=100.NDX&fields=f43,f57,f58,f60,f169,f170,f152"
)
EASTMONEY_ETF_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
EASTMONEY_ETF_FIELDS = "f12,f14,f2,f3,f6,f402,f441,f297,f124"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


class MarketDataError(RuntimeError):
    pass


class AkshareMarketDataProvider:
    def get_etf_quotes(self, symbols: Iterable[str]) -> list[EtfQuote]:
        symbol_list = [str(symbol).zfill(6) for symbol in symbols]
        try:
            return self._get_etf_quotes_from_eastmoney(symbol_list)
        except Exception:
            return self._get_etf_quotes_from_akshare(symbol_list)

    def _get_etf_quotes_from_eastmoney(self, symbols: list[str]) -> list[EtfQuote]:
        response = requests.get(
            EASTMONEY_ETF_URL,
            params={
                "fltt": "2",
                "invt": "2",
                "fields": EASTMONEY_ETF_FIELDS,
                "secids": ",".join(_eastmoney_secid(symbol) for symbol in symbols),
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data", {}).get("diff", [])
        rows_by_symbol = {str(row.get("f12", "")).zfill(6): row for row in rows}

        quotes: list[EtfQuote] = []
        for symbol in symbols:
            row = rows_by_symbol.get(symbol)
            if row is None:
                quotes.append(_missing_quote(symbol, "eastmoney.ulist"))
                continue

            price = _to_float(row.get("f2"))
            iopv = _to_float(row.get("f441"))
            quotes.append(
                EtfQuote(
                    symbol=symbol,
                    name=str(row.get("f14", "")),
                    price=price,
                    change_pct=_to_float(row.get("f3")),
                    turnover_cny=_to_float(row.get("f6")),
                    iopv=iopv,
                    premium_rate=_premium_rate(price, iopv),
                    updated_at=_format_eastmoney_timestamp(row.get("f124")),
                    source="eastmoney.ulist",
                )
            )
        return sorted(quotes, key=lambda item: item.symbol)

    def get_us_market_snapshot(self, config: USMarketConfig) -> USMarketSnapshot | None:
        if not config.enabled:
            return None

        primary = self._try_get_yahoo_chart_quote(config.primary_symbol)
        fallback = self._try_get_yahoo_chart_quote(config.fallback_symbol)
        nasdaq_index = self._try_get_yahoo_chart_quote(config.nasdaq_index_symbol)
        nasdaq_index_trend = self._try_get_yahoo_index_trend(config.nasdaq_index_symbol)
        fx = self._try_get_yahoo_chart_quote(config.fx_symbol)
        mega_caps = tuple(
            quote for symbol in config.mega_cap_symbols if (quote := self._try_get_yahoo_chart_quote(symbol)) is not None
        )

        adjustment_quote = primary or fallback
        adjustment_rate = _combined_adjustment_rate(adjustment_quote, fx)
        adjustment_source = None
        if adjustment_quote:
            adjustment_source = adjustment_quote.symbol
            if fx and fx.change_pct is not None:
                adjustment_source = f"{adjustment_source}+{fx.symbol}"

        return USMarketSnapshot(
            primary=primary,
            fallback=fallback,
            nasdaq_index=nasdaq_index,
            nasdaq_index_trend=nasdaq_index_trend,
            fx=fx,
            mega_caps=mega_caps,
            adjustment_rate=adjustment_rate,
            adjustment_source=adjustment_source,
            checked_at=datetime.now(),
        )

    def get_futures_trend_snapshot(
        self,
        symbol: str = "NQ=F",
        timezone_name: str = "Asia/Shanghai",
    ) -> FuturesTrendSnapshot:
        local_tz = ZoneInfo(timezone_name)
        checked_at = datetime.now(local_tz)
        start_at = datetime.combine(checked_at.date(), time(9, 30), local_tz)
        end_at = datetime.combine(checked_at.date(), time(14, 30), local_tz)
        data = self._get_yahoo_chart_data(symbol, range_value="5d", interval="5m")
        meta = data.get("meta", {})
        timestamps = data.get("timestamp") or []
        closes = data.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        points: list[FuturesTrendPoint] = []

        for timestamp, close in zip(timestamps, closes):
            timestamp_value = _to_float(timestamp)
            close_value = _to_float(close)
            if timestamp_value is None or close_value is None:
                continue
            point_at = datetime.fromtimestamp(timestamp_value, local_tz)
            if start_at <= point_at <= end_at:
                points.append(FuturesTrendPoint(timestamp=point_at, price=close_value))

        name = str(meta.get("shortName") or meta.get("longName") or meta.get("symbol", symbol))
        return _build_futures_trend_snapshot(
            symbol=str(meta.get("symbol", symbol)),
            name=name,
            points=points,
            checked_at=checked_at,
            source="yahoo.chart",
        )

    def apply_us_market_adjustment(
        self,
        quotes: list[EtfQuote],
        snapshot: USMarketSnapshot | None,
    ) -> list[EtfQuote]:
        if snapshot is None or snapshot.adjustment_rate is None:
            return quotes

        adjusted: list[EtfQuote] = []
        multiplier = 1 + snapshot.adjustment_rate
        for quote in quotes:
            if quote.iopv is None or quote.price is None or quote.iopv <= 0 or multiplier <= 0:
                adjusted.append(quote)
                continue
            adjusted_reference_value = quote.iopv * multiplier
            adjusted.append(
                replace(
                    quote,
                    adjusted_reference_value=adjusted_reference_value,
                    adjusted_premium_rate=quote.price / adjusted_reference_value - 1,
                )
            )
        return adjusted

    def _get_etf_quotes_from_akshare(self, symbols: list[str]) -> list[EtfQuote]:
        ak = _import_akshare()
        df = _call_quietly(ak.fund_etf_spot_em)
        symbol_set = set(symbols)
        df = df.copy()
        df["代码"] = df["代码"].astype(str).str.zfill(6)
        rows_by_symbol = {
            str(row["代码"]).zfill(6): row for _, row in df[df["代码"].isin(symbol_set)].iterrows()
        }

        quotes: list[EtfQuote] = []
        for symbol in symbol_set:
            row = rows_by_symbol.get(symbol)
            if row is None:
                quotes.append(_missing_quote(symbol, "akshare.fund_etf_spot_em"))
                continue

            price = _to_float(row.get("最新价"))
            iopv = _to_float(row.get("IOPV实时估值"))
            quotes.append(
                EtfQuote(
                    symbol=symbol,
                    name=str(row.get("名称", "")),
                    price=price,
                    change_pct=_to_float(row.get("涨跌幅")),
                    turnover_cny=_to_float(row.get("成交额")),
                    iopv=iopv,
                    premium_rate=_premium_rate(price, iopv),
                    updated_at=_to_optional_str(row.get("更新时间")),
                    source="akshare.fund_etf_spot_em",
                )
            )
        return sorted(quotes, key=lambda item: item.symbol)

    def get_nasdaq_signal(self, config: NasdaqConfig) -> MarketSignal | None:
        if not config.enabled:
            return None

        try:
            return self._get_nasdaq_signal_from_akshare(config)
        except Exception:
            return self._get_nasdaq_signal_from_eastmoney(config)

    def _get_nasdaq_signal_from_akshare(self, config: NasdaqConfig) -> MarketSignal:
        ak = _import_akshare()
        df = _call_quietly(ak.index_global_spot_em)
        symbol = config.symbol.upper()
        code_mask = df["代码"].astype(str).str.upper() == symbol
        name_mask = df["名称"].astype(str).str.contains("纳斯达克", na=False)
        rows = df[code_mask | name_mask]
        if rows.empty:
            raise MarketDataError(f"Cannot find Nasdaq row for {config.symbol}")

        row = rows.iloc[0]
        change_pct = _to_float(row.get("涨跌幅"))
        if change_pct is None:
            raise MarketDataError("Nasdaq change percent is missing")

        return MarketSignal(
            name=str(row.get("名称", "纳斯达克")),
            symbol=str(row.get("代码", config.symbol)),
            change_pct=change_pct,
            is_down=change_pct <= config.max_change_pct,
            updated_at=_to_optional_str(row.get("最新行情时间")),
            source="akshare.index_global_spot_em",
        )

    def _get_nasdaq_signal_from_eastmoney(self, config: NasdaqConfig) -> MarketSignal:
        response = requests.get(EASTMONEY_NDX_URL, timeout=10)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        if not data:
            raise MarketDataError("Eastmoney Nasdaq fallback returned no data")

        price_scale = _to_float(data.get("f152")) or 2.0
        change_pct_raw = _to_float(data.get("f170"))
        if change_pct_raw is None:
            raise MarketDataError("Eastmoney Nasdaq fallback has no change percent")

        change_pct = change_pct_raw / (10**price_scale)
        return MarketSignal(
            name=str(data.get("f58", "纳斯达克")),
            symbol=str(data.get("f57", config.symbol)),
            change_pct=change_pct,
            is_down=change_pct <= config.max_change_pct,
            updated_at=None,
            source="eastmoney.push2.NDX",
        )

    def _get_yahoo_chart_quote(self, symbol: str) -> USMarketQuote | None:
        data = self._get_yahoo_chart_data(symbol, range_value="1d", interval="1m")
        meta = data.get("meta", {})
        timestamps = data.get("timestamp") or []
        closes = data.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        latest_point = _latest_chart_point(timestamps, closes)

        if latest_point:
            updated_at_ts, price = latest_point
        else:
            updated_at_ts = _to_float(meta.get("regularMarketTime"))
            price = _to_float(meta.get("regularMarketPrice"))

        previous_close = _to_float(meta.get("chartPreviousClose")) or _to_float(meta.get("previousClose"))
        change_pct = None
        if price is not None and previous_close is not None and previous_close > 0:
            change_pct = (price / previous_close - 1) * 100

        return USMarketQuote(
            symbol=str(meta.get("symbol", symbol)),
            name=str(meta.get("shortName") or meta.get("longName") or meta.get("symbol", symbol)),
            price=price,
            previous_close=previous_close,
            change_pct=change_pct,
            updated_at=_format_unix_timestamp(updated_at_ts),
            source="yahoo.chart",
        )

    def _try_get_yahoo_chart_quote(self, symbol: str) -> USMarketQuote | None:
        try:
            return self._get_yahoo_chart_quote(symbol)
        except Exception as exc:
            print(f"Yahoo chart 数据获取失败：{symbol}：{exc}")
            return None

    def _try_get_yahoo_index_trend(self, symbol: str) -> USIndexTrend | None:
        try:
            return self._get_yahoo_index_trend(symbol)
        except Exception as exc:
            print(f"Yahoo index trend 数据获取失败：{symbol}：{exc}")
            return None

    def _get_yahoo_index_trend(self, symbol: str) -> USIndexTrend:
        data = self._get_yahoo_chart_data(symbol, range_value="1mo", interval="1d")
        meta = data.get("meta", {})
        timestamps = data.get("timestamp") or []
        closes = data.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        points: list[tuple[float, float]] = []
        for timestamp, close in zip(timestamps, closes):
            timestamp_value = _to_float(timestamp)
            close_value = _to_float(close)
            if timestamp_value is None or close_value is None:
                continue
            points.append((timestamp_value, close_value))

        latest_date = None
        latest_close = None
        if points:
            latest_ts, latest_close = points[-1]
            latest_date = datetime.fromtimestamp(latest_ts).date().isoformat()

        return USIndexTrend(
            symbol=str(meta.get("symbol", symbol)),
            name=str(meta.get("shortName") or meta.get("longName") or meta.get("symbol", symbol)),
            latest_close=latest_close,
            latest_date=latest_date,
            one_day_change_pct=_trend_change_pct(points, 1),
            three_day_change_pct=_trend_change_pct(points, 3),
            five_day_change_pct=_trend_change_pct(points, 5),
            source="yahoo.chart",
        )

    def _get_yahoo_chart_data(self, symbol: str, range_value: str, interval: str) -> dict:
        response = requests.get(
            YAHOO_CHART_URL.format(symbol=url_quote(symbol, safe="")),
            params={"range": range_value, "interval": interval, "includePrePost": "true"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("chart", {}).get("result") or []
        if not results:
            raise MarketDataError(f"Yahoo chart returned no data for {symbol}")
        return results[0]


def _import_akshare():
    try:
        import akshare as ak
    except ImportError as exc:
        raise MarketDataError("请先运行 pip install -r requirements.txt 安装 AKShare") from exc
    return ak


def _call_quietly(func, *args, **kwargs):
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        return func(*args, **kwargs)


def _eastmoney_secid(symbol: str) -> str:
    market = "1" if symbol.startswith(("5", "6", "9")) else "0"
    return f"{market}.{symbol}"


def _missing_quote(symbol: str, source: str) -> EtfQuote:
    return EtfQuote(
        symbol=symbol,
        name="未找到",
        price=None,
        change_pct=None,
        turnover_cny=None,
        iopv=None,
        premium_rate=None,
        updated_at=None,
        source=source,
    )


def _format_eastmoney_timestamp(value: object) -> str | None:
    timestamp = _to_float(value)
    if timestamp is None or timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp).isoformat(sep=" ", timespec="seconds")


def _format_unix_timestamp(value: object) -> str | None:
    timestamp = _to_float(value)
    if timestamp is None or timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp).isoformat(sep=" ", timespec="seconds")


def _latest_chart_point(timestamps: list[object], closes: list[object]) -> tuple[float, float] | None:
    latest: tuple[float, float] | None = None
    for timestamp, close in zip(timestamps, closes):
        close_value = _to_float(close)
        timestamp_value = _to_float(timestamp)
        if close_value is None or timestamp_value is None:
            continue
        latest = (timestamp_value, close_value)
    return latest


def _combined_adjustment_rate(
    market_quote: USMarketQuote | None,
    fx_quote: USMarketQuote | None,
) -> float | None:
    if market_quote is None or market_quote.change_pct is None:
        return None

    market_rate = market_quote.change_pct / 100
    fx_rate = 0.0
    if fx_quote and fx_quote.change_pct is not None:
        fx_rate = fx_quote.change_pct / 100
    return (1 + market_rate) * (1 + fx_rate) - 1


def _trend_change_pct(points: list[tuple[float, float]], sessions_back: int) -> float | None:
    if len(points) <= sessions_back:
        return None
    previous = points[-1 - sessions_back][1]
    latest = points[-1][1]
    if previous <= 0:
        return None
    return (latest / previous - 1) * 100


def _build_futures_trend_snapshot(
    symbol: str,
    name: str,
    points: list[FuturesTrendPoint],
    checked_at: datetime,
    source: str,
) -> FuturesTrendSnapshot:
    if not points:
        return FuturesTrendSnapshot(
            symbol=symbol,
            name=name,
            points=(),
            start_at=None,
            end_at=None,
            start_price=None,
            end_price=None,
            change_pct=None,
            high_price=None,
            low_price=None,
            max_drawdown_pct=None,
            late_change_pct=None,
            trend_label="数据不足",
            prediction="无法判断，当天 09:30-14:30 没有可用的 NQ=F 分时点。",
            rationale=("没有足够分时数据，可能是数据源延迟、假期或网络问题。",),
            source=source,
            checked_at=checked_at,
        )

    prices = [point.price for point in points]
    start_price = prices[0]
    end_price = prices[-1]
    change_pct = (end_price / start_price - 1) * 100 if start_price > 0 else None
    high_price = max(prices)
    low_price = min(prices)
    max_drawdown_pct = _max_drawdown_pct(prices)
    late_change_pct = _late_change_pct(prices)
    trend_label, prediction, rationale = _classify_futures_trend(change_pct, late_change_pct, max_drawdown_pct, len(points))

    return FuturesTrendSnapshot(
        symbol=symbol,
        name=name,
        points=tuple(points),
        start_at=points[0].timestamp,
        end_at=points[-1].timestamp,
        start_price=start_price,
        end_price=end_price,
        change_pct=change_pct,
        high_price=high_price,
        low_price=low_price,
        max_drawdown_pct=max_drawdown_pct,
        late_change_pct=late_change_pct,
        trend_label=trend_label,
        prediction=prediction,
        rationale=tuple(rationale),
        source=source,
        checked_at=checked_at,
    )


def _max_drawdown_pct(prices: list[float]) -> float | None:
    if not prices:
        return None
    peak = prices[0]
    max_drawdown = 0.0
    for price in prices:
        if price > peak:
            peak = price
        if peak > 0:
            max_drawdown = min(max_drawdown, (price / peak - 1) * 100)
    return max_drawdown


def _late_change_pct(prices: list[float]) -> float | None:
    if len(prices) < 3:
        return None
    start_index = max(0, int(len(prices) * 2 / 3) - 1)
    start_price = prices[start_index]
    if start_price <= 0:
        return None
    return (prices[-1] / start_price - 1) * 100


def _classify_futures_trend(
    change_pct: float | None,
    late_change_pct: float | None,
    max_drawdown_pct: float | None,
    point_count: int,
) -> tuple[str, str, list[str]]:
    if change_pct is None or point_count < 3:
        return "数据不足", "无法判断，分时点数量不足。", [f"有效分时点数量：{point_count}。"]

    late = late_change_pct or 0.0
    drawdown = max_drawdown_pct or 0.0
    score = change_pct * 0.7 + late * 0.3
    rationale = [
        f"09:30-14:30 区间涨跌幅 {change_pct:.2f}%。",
        f"后段动量 {late:.2f}%。",
        f"区间最大回撤 {drawdown:.2f}%。",
    ]

    if score <= -0.8 or (change_pct <= -0.8 and late <= 0):
        return "偏空", "NQ=F 白天明显走弱，当晚纳指偏弱概率较高；适合作为看空定投的重点观察日。", rationale
    if score <= -0.3 or (change_pct < 0 and late <= -0.2):
        return "震荡偏空", "NQ=F 白天偏弱但强度一般，当晚纳指有走弱风险；适合提高关注但不宜只凭该信号重仓。", rationale
    if score >= 0.8 or (change_pct >= 0.8 and late >= 0):
        return "偏多", "NQ=F 白天明显走强，当晚纳指偏强概率较高；看空定投信号较弱。", rationale
    if score >= 0.3 or (change_pct > 0 and late >= 0.2):
        return "震荡偏多", "NQ=F 白天略强，当晚纳指下跌预期不明显；看空定投需要等待更强回落信号。", rationale
    return "震荡", "NQ=F 白天方向不清晰，当晚纳指走势不宜提前下结论。", rationale


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() in {"", "-", "--", "nan", "None"}:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return result


def _premium_rate(price: float | None, iopv: float | None) -> float | None:
    if price is None or iopv is None or iopv <= 0:
        return None
    return price / iopv - 1


def _to_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--", "nan", "NaT"}:
        return None
    return text
