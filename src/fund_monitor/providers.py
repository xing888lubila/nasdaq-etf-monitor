from __future__ import annotations

import math
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Iterable

import requests

from .config import NasdaqConfig
from .models import EtfQuote, MarketSignal


EASTMONEY_NDX_URL = (
    "https://push2.eastmoney.com/api/qt/stock/get"
    "?secid=100.NDX&fields=f43,f57,f58,f60,f169,f170,f152"
)
EASTMONEY_ETF_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
EASTMONEY_ETF_FIELDS = "f12,f14,f2,f3,f6,f402,f441,f297,f124"


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
    from datetime import datetime

    return datetime.fromtimestamp(timestamp).isoformat(sep=" ", timespec="seconds")


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
