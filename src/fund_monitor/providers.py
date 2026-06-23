from __future__ import annotations

import math
import csv
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, time, timedelta
from io import StringIO
from typing import Iterable
from urllib.parse import quote as url_quote
from zoneinfo import ZoneInfo

import requests

from .config import NasdaqConfig, USMarketConfig
from .models import (
    EtfQuote,
    FuturesTrendPoint,
    FuturesTrendSnapshot,
    IntradayTrendShape,
    MarketRelativeSnapshot,
    MarketSignal,
    TreasuryYieldPoint,
    TreasuryYieldSnapshot,
    USIndexTrend,
    USMarketQuote,
    USMarketSnapshot,
)


EASTMONEY_NDX_URL = (
    "https://push2.eastmoney.com/api/qt/stock/get"
    "?secid=100.NDX&fields=f43,f57,f58,f60,f169,f170,f152"
)
EASTMONEY_ETF_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
EASTMONEY_ETF_FIELDS = "f12,f14,f2,f3,f6,f402,f441,f297,f124"
YAHOO_CHART_URLS = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
    "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
)
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
TREASURY_YIELD_XML_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"


class MarketDataError(RuntimeError):
    pass


class AkshareMarketDataProvider:
    def get_etf_quotes(self, symbols: Iterable[str]) -> list[EtfQuote]:
        symbol_list = [str(symbol).zfill(6) for symbol in symbols]
        try:
            return self._get_etf_quotes_from_eastmoney(symbol_list)
        except Exception as eastmoney_exc:
            print(f"Eastmoney ETF data failed: {eastmoney_exc}")
        try:
            return self._get_etf_quotes_from_eastmoney_single(symbol_list)
        except Exception as single_exc:
            print(f"Eastmoney single ETF data failed: {single_exc}")
        try:
            return self._get_etf_quotes_from_tencent(symbol_list)
        except Exception as tencent_exc:
            print(f"Tencent ETF data failed: {tencent_exc}")
        try:
            return self._get_etf_quotes_from_akshare(symbol_list)
        except Exception as akshare_exc:
            print(f"AKShare ETF data failed: {akshare_exc}")
            return [_missing_quote(symbol, "eastmoney/tencent/akshare unavailable") for symbol in symbol_list]

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

    def _get_etf_quotes_from_eastmoney_single(self, symbols: list[str]) -> list[EtfQuote]:
        quotes: list[EtfQuote] = []
        errors: list[str] = []
        for symbol in symbols:
            try:
                quote = self._get_etf_quote_from_eastmoney_single(symbol)
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")
                quote = _missing_quote(symbol, "eastmoney.stock.get")
            quotes.append(quote)
        if all(quote.price is None for quote in quotes) and errors:
            raise MarketDataError("; ".join(errors))
        return sorted(quotes, key=lambda item: item.symbol)

    def _get_etf_quote_from_eastmoney_single(self, symbol: str) -> EtfQuote:
        response = requests.get(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={
                "secid": _eastmoney_secid(symbol),
                "fields": "f43,f57,f58,f170,f152,f441,f6,f124",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json().get("data") or {}
        if not data:
            raise MarketDataError(f"Eastmoney single quote returned no data for {symbol}")

        scale = int(_to_float(data.get("f152")) or 2)
        price = _scaled_float(data.get("f43"), scale)
        change_pct = _scaled_float(data.get("f170"), scale)
        iopv = _scaled_float(data.get("f441"), scale)
        turnover = _to_float(data.get("f6"))
        return EtfQuote(
            symbol=str(data.get("f57", symbol)).zfill(6),
            name=str(data.get("f58", "")),
            price=price,
            change_pct=change_pct,
            turnover_cny=turnover,
            iopv=iopv,
            premium_rate=_premium_rate(price, iopv),
            updated_at=_format_eastmoney_timestamp(data.get("f124")),
            source="eastmoney.stock.get",
        )

    def _get_etf_quotes_from_tencent(self, symbols: list[str]) -> list[EtfQuote]:
        query = ",".join(_tencent_symbol(symbol) for symbol in symbols)
        response = requests.get(
            "https://qt.gtimg.cn/q=" + query,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        rows_by_symbol: dict[str, EtfQuote] = {}
        for raw_row in response.text.splitlines():
            if '="' not in raw_row:
                continue
            payload = raw_row.split('="', 1)[1].rstrip('";')
            fields = payload.split("~")
            if len(fields) < 38:
                continue
            symbol = fields[2].zfill(6)
            price = _to_float(fields[3])
            change_pct = _to_float(fields[32])
            turnover_cny = _to_float(fields[37])
            if turnover_cny is not None:
                turnover_cny *= 10_000
            rows_by_symbol[symbol] = EtfQuote(
                symbol=symbol,
                name=fields[1],
                price=price,
                change_pct=change_pct,
                turnover_cny=turnover_cny,
                iopv=None,
                premium_rate=None,
                updated_at=_format_tencent_timestamp(fields[30]),
                source="tencent.qt",
            )
        quotes = [rows_by_symbol.get(symbol) or _missing_quote(symbol, "tencent.qt") for symbol in symbols]
        if all(quote.price is None for quote in quotes):
            raise MarketDataError("Tencent quote returned no usable ETF rows")
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

    def get_market_relative_snapshot(self) -> MarketRelativeSnapshot:
        return MarketRelativeSnapshot(
            qqq=self._try_get_yahoo_chart_quote("QQQ"),
            ndx=self._try_get_yahoo_chart_quote("^NDX"),
            spy=self._try_get_yahoo_chart_quote("SPY"),
            dia=self._try_get_yahoo_chart_quote("DIA"),
            smh=self._try_get_yahoo_chart_quote("SMH"),
            qqq_shape=self._try_get_intraday_trend_shape("QQQ"),
            checked_at=datetime.now(),
        )

    def get_treasury_yield_snapshot(self) -> TreasuryYieldSnapshot:
        two_year = self._try_get_fred_series_latest_two("DGS2")
        ten_year = self._try_get_fred_series_latest_two("DGS10")
        source = "fred.csv:DGS2,DGS10"
        if two_year[0] is None or ten_year[0] is None:
            treasury_two, treasury_ten = self._try_get_treasury_xml_latest_two()
            if two_year[0] is None:
                two_year = treasury_two
            if ten_year[0] is None:
                ten_year = treasury_ten
            if treasury_two[0] is not None or treasury_ten[0] is not None:
                source = "treasury.xml:daily_treasury_yield_curve"
        return TreasuryYieldSnapshot(
            two_year=two_year[0],
            two_year_previous=two_year[1],
            ten_year=ten_year[0],
            ten_year_previous=ten_year[1],
            source=source,
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

    def _try_get_intraday_trend_shape(self, symbol: str) -> IntradayTrendShape | None:
        try:
            return self._get_intraday_trend_shape(symbol)
        except Exception as exc:
            print(f"Yahoo intraday trend 数据获取失败：{symbol}：{exc}")
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

    def _get_intraday_trend_shape(self, symbol: str) -> IntradayTrendShape:
        data = self._get_yahoo_chart_data(symbol, range_value="5d", interval="15m")
        timestamps = data.get("timestamp") or []
        quote = data.get("indicators", {}).get("quote", [{}])[0]
        opens = quote.get("open", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        closes = quote.get("close", [])
        tz = ZoneInfo("America/New_York")
        rows: list[tuple[datetime, float, float, float, float]] = []

        for timestamp, open_value, high_value, low_value, close_value in zip(timestamps, opens, highs, lows, closes):
            timestamp_value = _to_float(timestamp)
            open_price = _to_float(open_value)
            high_price = _to_float(high_value)
            low_price = _to_float(low_value)
            close_price = _to_float(close_value)
            if (
                timestamp_value is None
                or open_price is None
                or high_price is None
                or low_price is None
                or close_price is None
            ):
                continue
            point_at = datetime.fromtimestamp(timestamp_value, tz)
            if time(9, 30) <= point_at.time() <= time(16, 0):
                rows.append((point_at, open_price, high_price, low_price, close_price))

        if not rows:
            raise MarketDataError(f"No regular-session bars for {symbol}")

        latest_date = rows[-1][0].date()
        session = [row for row in rows if row[0].date() == latest_date]
        open_price = session[0][1]
        high_price = max(row[2] for row in session)
        low_price = min(row[3] for row in session)
        close_price = session[-1][4]
        change_pct = (close_price / open_price - 1) * 100 if open_price > 0 else None
        close_position = (close_price - low_price) / (high_price - low_price) if high_price > low_price else None

        return IntradayTrendShape(
            symbol=symbol,
            change_pct=change_pct,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            shape=_classify_intraday_shape(session, close_position),
            close_position=close_position,
            source="yahoo.chart",
            checked_at=datetime.now(),
        )

    def _get_yahoo_chart_data(self, symbol: str, range_value: str, interval: str) -> dict:
        last_exc: Exception | None = None
        for url in YAHOO_CHART_URLS:
            try:
                response = requests.get(
                    url.format(symbol=url_quote(symbol, safe="")),
                    params={"range": range_value, "interval": interval, "includePrePost": "true"},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=8,
                )
                response.raise_for_status()
                payload = response.json()
                results = payload.get("chart", {}).get("result") or []
                if results:
                    return results[0]
                last_exc = MarketDataError(f"Yahoo chart returned no data for {symbol}")
            except Exception as exc:
                last_exc = exc
        raise MarketDataError(f"Yahoo chart failed for {symbol}: {last_exc}")

    def _get_fred_series_latest_two(self, series_id: str) -> tuple[TreasuryYieldPoint | None, TreasuryYieldPoint | None]:
        response = requests.get(
            FRED_CSV_URL,
            params={"id": series_id, "cosd": (datetime.now().date() - timedelta(days=370)).isoformat()},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        response.raise_for_status()
        rows = csv.DictReader(StringIO(response.text))
        points: list[TreasuryYieldPoint] = []
        for row in rows:
            date_value = (row.get("observation_date") or "").strip()
            value = _to_float(row.get(series_id))
            if date_value and value is not None:
                points.append(TreasuryYieldPoint(date=date_value, value=value))
        if not points:
            return None, None
        if len(points) == 1:
            return points[-1], None
        return points[-1], points[-2]

    def _try_get_fred_series_latest_two(self, series_id: str) -> tuple[TreasuryYieldPoint | None, TreasuryYieldPoint | None]:
        try:
            return self._get_fred_series_latest_two(series_id)
        except Exception as exc:
            print(f"FRED yield data failed: {series_id}: {exc}")
            return None, None

    def _try_get_treasury_xml_latest_two(
        self,
    ) -> tuple[
        tuple[TreasuryYieldPoint | None, TreasuryYieldPoint | None],
        tuple[TreasuryYieldPoint | None, TreasuryYieldPoint | None],
    ]:
        try:
            return self._get_treasury_xml_latest_two()
        except Exception as exc:
            print(f"Treasury yield data failed: {exc}")
            return (None, None), (None, None)

    def _get_treasury_xml_latest_two(
        self,
    ) -> tuple[
        tuple[TreasuryYieldPoint | None, TreasuryYieldPoint | None],
        tuple[TreasuryYieldPoint | None, TreasuryYieldPoint | None],
    ]:
        response = requests.get(
            TREASURY_YIELD_XML_URL,
            params={"data": "daily_treasury_yield_curve", "field_tdr_date_value": datetime.now().year},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        two_year_points: list[TreasuryYieldPoint] = []
        ten_year_points: list[TreasuryYieldPoint] = []

        for properties in root.iter():
            if not properties.tag.endswith("properties"):
                continue
            row = {_local_name(child.tag): (child.text or "").strip() for child in properties}
            date_value = row.get("NEW_DATE") or row.get("NEW_DATE_VALUE") or row.get("DATE")
            if not date_value:
                continue
            date_value = date_value[:10]
            two_year = _to_float(row.get("BC_2YEAR"))
            ten_year = _to_float(row.get("BC_10YEAR"))
            if two_year is not None:
                two_year_points.append(TreasuryYieldPoint(date=date_value, value=two_year))
            if ten_year is not None:
                ten_year_points.append(TreasuryYieldPoint(date=date_value, value=ten_year))

        two_year_points.sort(key=lambda point: point.date)
        ten_year_points.sort(key=lambda point: point.date)
        return _latest_two_points(two_year_points), _latest_two_points(ten_year_points)


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


def _tencent_symbol(symbol: str) -> str:
    prefix = "sh" if symbol.startswith(("5", "6", "9")) else "sz"
    return f"{prefix}{symbol}"


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


def _format_tencent_timestamp(value: object) -> str | None:
    text = str(value or "").strip()
    if len(text) < 14 or not text[:14].isdigit():
        return None
    try:
        return datetime.strptime(text[:14], "%Y%m%d%H%M%S").isoformat(sep=" ", timespec="seconds")
    except ValueError:
        return None


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


def _classify_intraday_shape(
    session: list[tuple[datetime, float, float, float, float]],
    close_position: float | None,
) -> str:
    if len(session) < 3:
        return "unclear"

    open_price = session[0][1]
    close_price = session[-1][4]
    midpoint = len(session) // 2
    first_close = session[0][4]
    mid_close = session[midpoint][4]
    high_price = max(row[2] for row in session)
    low_price = min(row[3] for row in session)
    high_index = max(range(len(session)), key=lambda index: session[index][2])
    low_index = min(range(len(session)), key=lambda index: session[index][3])

    # A session that finishes below its open is not a bullish V reversal even if
    # it bounces after the intraday low. Treat early strength followed by a lower
    # close as a failed rally.
    if close_price < open_price and high_index <= midpoint and low_index > high_index:
        return "rally faded"
    if close_price < open_price and close_price <= low_price * 1.003:
        return "opened low kept falling"

    if close_position is not None:
        if close_position <= 0.2:
            return "close near low"
        if close_position >= 0.8:
            return "close near high"

    if close_price > open_price and low_index < midpoint and close_price > mid_close:
        return "v reversal"
    if first_close > open_price and close_price < mid_close:
        return "gap up fade"
    if first_close < open_price and close_price > mid_close:
        return "gap down rally"
    if close_price > open_price and close_price >= high_price * 0.997:
        return "opened high kept rising"
    return "unclear"


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


def _scaled_float(value: object, scale: int) -> float | None:
    number = _to_float(value)
    if number is None:
        return None
    return number / (10**scale)


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


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _latest_two_points(points: list[TreasuryYieldPoint]) -> tuple[TreasuryYieldPoint | None, TreasuryYieldPoint | None]:
    if not points:
        return None, None
    if len(points) == 1:
        return points[-1], None
    return points[-1], points[-2]
