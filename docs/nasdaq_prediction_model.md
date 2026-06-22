# Nasdaq prediction model

## Commands

Run from the repository root.

```powershell
.\.venv\Scripts\python.exe -m fund_monitor.main --once --send-afternoon-brief --config config.example.json
.\.venv\Scripts\python.exe -m fund_monitor.main --once --send-morning-prediction --config config.example.json
.\.venv\Scripts\python.exe -m fund_monitor.main --once --check-yield-alert --config config.example.json
.\.venv\Scripts\python.exe -m fund_monitor.main --once --check-econ-release-alert --config config.example.json
```

When email is disabled, the message body is printed to stdout.

## GitHub Actions secrets

Set these repository secrets:

- `ETF_MONITOR_EMAIL_ENABLED`: use `true`
- `ETF_MONITOR_SMTP_HOST`
- `ETF_MONITOR_SMTP_PORT`
- `ETF_MONITOR_SMTP_USER`
- `ETF_MONITOR_SMTP_PASSWORD`
- `ETF_MONITOR_MAIL_FROM`
- `ETF_MONITOR_MAIL_TO`, comma-separated for multiple recipients

The yield and economic-release workflows commit `storage/state.json` back to the
repository so repeated scheduled runs do not send the same event again.

## Data sources

- NQ futures, QQQ, NDX, SPY, DIA, SMH: Yahoo chart API.
- 2Y/10Y yields: FRED `DGS2` and `DGS10` first, U.S. Treasury Daily Treasury
  Yield Curve XML fallback.
- Economic release timing: `zoneinfo` checks the current `America/New_York`
  time and only sends inside the 08:30 ET window. Built-in weekly jobless
  claims detection is included; CPI, PPI, GDP, PCE and retail-sales exact-date
  parsers can be added later.
- News: structured fallback section is included. A live news API can be added
  later without changing the scoring contract.

## Sample email

```text
【纳指预测】2026-06-18：偏多，总分 +1，建议买入 30 元

今日结论：偏多，建议买入 30 元。

1. 五项打分表
- NQ futures: +1，bullish。NQ is up 1.40%, showing positive overnight risk appetite.
- Treasury yields: +0，neutral。2Y/10Y yield data is incomplete.
- 8:30 ET macro data: +0，neutral。tonight 8:30 ET macro calendar has no clear directional result yet.
- Tech relative strength: +1，tech leadership。QQQ outperformed SPY and DIA.
- QQQ/NDX trend shape: -1，bearish。Intraday shape: close near low.

3. 趋势预测：上涨概率 60%，下跌概率 40%。
4. 今日操作：南方纳指100 I 类今日买入 30 元。
```

