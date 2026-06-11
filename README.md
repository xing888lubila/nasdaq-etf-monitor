# 纳指 ETF 监控提醒 / Nasdaq ETF Monitor

一个面向个人投资者的半自动纳指 ETF 监控工具。它使用免费行情源读取场内 ETF 价格、IOPV、溢价率、成交额、美股期货、QQQ、核心权重股和美元人民币汇率，根据配置规则发送邮件提醒；程序不自动下单，最终买入仍需人工打开证券 App 确认。

A semi-automatic Nasdaq ETF monitor for individual investors. It reads free market data for exchange-traded ETFs, US futures, QQQ, key mega-cap stocks, and USD/CNH exchange rates, then sends email alerts based on configurable rules. It never places orders automatically; final trading decisions must be confirmed manually in a brokerage app.

> 风险提示 / Risk Notice  
> 免费行情源可能延迟、失败或字段缺失。本项目只适合作为提醒工具，不构成投资建议。  
> Free market data can be delayed, unavailable, or incomplete. This project is an alerting tool only and is not financial advice.

## 功能 / Features

- 监控 5 只纳指相关场内 ETF：`513100`、`159941`、`159632`、`159659`、`513300`
- 读取当前价格、涨跌幅、成交额、IOPV 和溢价率
- 读取 `NQ=F`、`QQQ`、`^NDX`、`AAPL`、`MSFT`、`NVDA`、`CNH=X`
- 计算普通溢价率和美股/汇率修正后溢价率
- 在 14:30 发送 NQ=F 北京时间 09:30-14:30 趋势快照和规则模型判断
- 按规则发送邮件提醒，默认只提醒人工确认，不自动交易
- 支持一次性快照邮件，用于测试当前行情和邮箱配置
- 支持启动时发送一次开盘前快照
- 支持 Windows 计划任务，在 A 股交易时段自动运行
- 通过 `.gitignore` 排除本地配置、日志、虚拟环境和缓存

- Monitors five Nasdaq-related exchange-traded ETFs: `513100`, `159941`, `159632`, `159659`, `513300`
- Reads current price, change percentage, turnover, IOPV, and premium rate
- Reads `NQ=F`, `QQQ`, `^NDX`, `AAPL`, `MSFT`, `NVDA`, and `CNH=X`
- Calculates both regular premium rate and US-market-adjusted premium rate
- Sends a 14:30 NQ=F trend snapshot for the Beijing-time 09:30-14:30 window with rule-based interpretation
- Sends email alerts based on rules, with manual confirmation required before trading
- Supports one-time snapshot emails for testing market data and email setup
- Supports a startup snapshot before the A-share market opens
- Supports Windows Task Scheduler for A-share trading sessions
- Keeps local config, logs, virtual environments, and caches out of Git

## 监控逻辑 / Monitoring Logic

溢价率由程序自行计算：

```text
premium_rate = current_price / iopv - 1
溢价率 = 当前价格 / IOPV - 1
```

当前默认提醒条件：

```text
premium_rate <= 1.5%
adjusted_premium_rate <= 1.5%
turnover >= 100,000,000 CNY
NQ=F change <= -2.5%
```

修正后参考值和修正后溢价率：

```text
market_adjustment = (1 + NQ_change) * (1 + USD_CNH_change) - 1
adjusted_reference_value = IOPV * (1 + market_adjustment)
adjusted_premium_rate = current_price / adjusted_reference_value - 1
```

The adjusted premium rate estimates whether the domestic ETF is still expensive after considering US futures and USD/CNH movement. It is an estimate, not official NAV.

14:30 的 NQ=F 趋势模型使用北京时间 09:30-14:30 的 5 分钟分时数据，计算区间涨跌幅、后段动量和最大回撤，并输出 `偏空`、`震荡偏空`、`震荡`、`震荡偏多` 或 `偏多`。这个结果只用于判断当晚纳指情绪，不是保证性预测。

The 14:30 NQ=F trend model uses five-minute bars from 09:30 to 14:30 Beijing time. It calculates session change, late-session momentum, and maximum drawdown, then labels the trend as bearish, mildly bearish, neutral, mildly bullish, or bullish. This is a sentiment signal for the coming US session, not a guaranteed forecast.

## 项目结构 / Project Structure

```text
.
├── config.example.json        # 示例配置 / Example config
├── README.md                  # 中英双语说明 / Bilingual documentation
├── requirements.txt           # 安装入口 / Install entry
├── pyproject.toml             # Python package metadata
├── scripts/
│   ├── install_market_task.ps1 # 安装计划任务 / Install scheduled task
│   ├── run_futures_trend_snapshot.ps1 # 14:30 期货趋势快照 / 14:30 futures trend snapshot
│   ├── run_monitor_session.ps1 # 计划任务运行脚本 / Scheduled session runner
│   ├── start_monitor_now.ps1   # 手动启动 / Start manually
│   └── stop_monitor.ps1        # 手动停止 / Stop manually
├── src/fund_monitor/
│   ├── config.py              # 配置读取 / Config loading
│   ├── main.py                # CLI 入口 / CLI entry point
│   ├── models.py              # 数据模型 / Data models
│   ├── notify.py              # 邮件通知 / Email notifications
│   ├── providers.py           # 行情数据源 / Market data providers
│   └── rules.py               # 提醒规则 / Alert rules
└── tests/
    ├── test_main.py
    └── test_rules.py
```

## 安装 / Installation

```powershell
cd G:\codex\基金监测
py -m venv .venv
.\.venv\Scripts\Activate.ps1

New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TEMP="$PWD\.tmp"
$env:TMP="$PWD\.tmp"
$env:PIP_CACHE_DIR="$PWD\.pip-cache"

pip install --no-cache-dir -r requirements.txt
```

## 配置 / Configuration

复制示例配置：

Copy the example config:

```powershell
Copy-Item config.example.json config.json
```

编辑 `config.json`：

Edit `config.json`:

- `poll_interval_seconds`: 数据读取间隔，当前默认 60 秒
- `etfs`: 要监控的 ETF 代码
- `rules.max_premium_rate`: 最高可接受溢价率，`0.015` 表示 1.5%
- `rules.max_adjusted_premium_rate`: 最高可接受修正后溢价率
- `rules.use_adjusted_premium`: 是否要求修正后溢价率也满足阈值
- `rules.min_turnover_cny`: 最低成交额，单位人民币
- `rules.require_nasdaq_down`: 是否要求美股侧或纳指同时下跌
- `rules.market_max_change_pct`: 美股侧主指标触发阈值，默认 `-2.5`
- `rules.stale_after_seconds`: ETF 行情超过该秒数则不触发买入提醒
- `rules.dedupe_minutes`: 同一 ETF 重复提醒间隔
- `us_market.primary_symbol`: 主美股指标，默认 `NQ=F`
- `us_market.fallback_symbol`: 备用美股指标，默认 `QQQ`
- `us_market.nasdaq_index_symbol`: 纳指收盘指标，默认 `^NDX`
- `us_market.fx_symbol`: 汇率指标，默认 `CNH=X`
- `us_market.mega_cap_symbols`: 辅助确认的核心权重股
- `email`: SMTP 邮件配置

- `poll_interval_seconds`: polling interval, currently 60 seconds
- `etfs`: ETF symbols to monitor
- `rules.max_premium_rate`: maximum acceptable premium rate, `0.015` means 1.5%
- `rules.max_adjusted_premium_rate`: maximum acceptable adjusted premium rate
- `rules.use_adjusted_premium`: whether adjusted premium must also pass the threshold
- `rules.min_turnover_cny`: minimum turnover in CNY
- `rules.require_nasdaq_down`: whether US market or Nasdaq must also be down
- `rules.market_max_change_pct`: primary US-market trigger threshold, default `-2.5`
- `rules.stale_after_seconds`: suppress opportunity alerts when ETF quotes are older than this many seconds
- `rules.dedupe_minutes`: cooldown for repeated alerts on the same ETF
- `us_market.primary_symbol`: primary US-market signal, default `NQ=F`
- `us_market.fallback_symbol`: fallback US-market signal, default `QQQ`
- `us_market.nasdaq_index_symbol`: Nasdaq-100 index close signal, default `^NDX`
- `us_market.fx_symbol`: FX signal, default `CNH=X`
- `us_market.mega_cap_symbols`: mega-cap confirmation symbols
- `email`: SMTP email settings

不要把邮箱授权码写进 `config.json`。请使用环境变量：

Do not write the email authorization code into `config.json`. Use an environment variable:

```powershell
[Environment]::SetEnvironmentVariable("ETF_MONITOR_SMTP_PASSWORD", "your_email_authorization_code", "User")
```

## 运行 / Usage

发送一次当前行情快照，用于测试：

Send one current market snapshot for testing:

```powershell
fund-monitor --once --send-snapshot --config config.json
```

只检查一次，不发送快照邮件：

Run one check without a snapshot email:

```powershell
fund-monitor --once --config config.json
```

发送一次 NQ=F 下午趋势快照：

Send one NQ=F afternoon trend snapshot:

```powershell
fund-monitor --once --send-futures-trend --config config.json
```

持续监控：

Run continuously:

```powershell
fund-monitor --config config.json
```

## 交易时段自动运行 / Trading-Session Scheduling

Windows 计划任务会在工作日 09:20 启动，先发送一次启动快照，然后运行约 6 小时，覆盖 A 股交易时段。另一个计划任务会在工作日 14:30 发送一次 NQ=F 下午趋势快照。

The Windows scheduled task starts at 09:20 on weekdays, sends one startup snapshot, and runs for about six hours, covering A-share trading sessions. A second scheduled task sends one NQ=F afternoon trend snapshot at 14:30 on weekdays.

计划任务使用 `--max-runtime-seconds 21000`，因此会在覆盖收盘后自动正常退出。

The scheduled task uses `--max-runtime-seconds 21000`, so it exits cleanly after covering the market close.

计划任务使用 `--max-runtime-seconds 21000`，因此会在覆盖收盘后自动正常退出。

The scheduled task uses `--max-runtime-seconds 21000`, so it exits cleanly after covering the market close.

安装计划任务：

Install the scheduled task:

```powershell
.\scripts\install_market_task.ps1
```

手动启动：

Start manually:

```powershell
.\scripts\start_monitor_now.ps1
```

手动停止：

Stop manually:

```powershell
.\scripts\stop_monitor.ps1
```

日志位置：

Log path:

```text
logs\monitor-YYYYMMDD.log
logs\futures-trend-YYYYMMDD.log
```

## 上传到 GitHub / Uploading to GitHub

建议创建空仓库，不要在 GitHub 页面勾选 Add README、Add .gitignore 或 License，因为本项目已经包含 README 和 `.gitignore`。

Create an empty repository. Do not enable Add README, Add .gitignore, or License on GitHub, because this project already includes README and `.gitignore`.

```powershell
git init
git add .gitignore README.md config.example.json pyproject.toml requirements.txt scripts src tests
git commit -m "Initial Nasdaq ETF monitor"
git branch -M main
git remote add origin https://github.com/<owner>/<repo>.git
git push -u origin main
```

## 安全边界 / Safety Boundaries

- 本项目不保存证券账户、交易密码或验证码
- 本项目不自动买入或卖出
- `config.json`、日志、缓存和虚拟环境不会提交到 Git
- 邮箱授权码通过环境变量读取，不写入代码仓库

- This project does not store brokerage accounts, trading passwords, or verification codes
- This project does not buy or sell automatically
- `config.json`, logs, caches, and virtual environments are excluded from Git
- Email authorization codes are read from environment variables, not stored in the repository
