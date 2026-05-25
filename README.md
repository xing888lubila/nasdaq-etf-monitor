# 纳指 ETF 监控提醒 / Nasdaq ETF Monitor

一个面向个人投资者的半自动纳指 ETF 监控工具。它使用免费行情源读取场内 ETF 价格、IOPV、溢价率和成交额，根据配置规则发送邮件提醒；程序不自动下单，最终买入仍需人工打开证券 App 确认。

A semi-automatic Nasdaq ETF monitor for individual investors. It reads free market data for exchange-traded ETFs, checks price, IOPV, premium rate, and turnover, then sends email alerts based on configurable rules. It never places orders automatically; final trading decisions must be confirmed manually in a brokerage app.

> 风险提示 / Risk Notice  
> 免费行情源可能延迟、失败或字段缺失。本项目只适合作为提醒工具，不构成投资建议。  
> Free market data can be delayed, unavailable, or incomplete. This project is an alerting tool only and is not financial advice.

## 功能 / Features

- 监控 5 只纳指相关场内 ETF：`513100`、`159941`、`159632`、`159659`、`513300`
- 读取当前价格、涨跌幅、成交额、IOPV 和溢价率
- 按规则发送邮件提醒，默认只提醒人工确认，不自动交易
- 支持一次性快照邮件，用于测试当前行情和邮箱配置
- 支持 Windows 计划任务，在 A 股交易时段自动运行
- 通过 `.gitignore` 排除本地配置、日志、虚拟环境和缓存

- Monitors five Nasdaq-related exchange-traded ETFs: `513100`, `159941`, `159632`, `159659`, `513300`
- Reads current price, change percentage, turnover, IOPV, and premium rate
- Sends email alerts based on rules, with manual confirmation required before trading
- Supports one-time snapshot emails for testing market data and email setup
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
turnover >= 100,000,000 CNY
Nasdaq change <= -0.5%
```

当前配置仍是基础版。更适合“大跌提醒”的后续版本可以改成多级信号，例如观察、第一档、强信号和极端信号。

The current configuration is intentionally simple. A later version can use multi-level alerts, such as watch, first-entry, strong signal, and extreme signal, for larger Nasdaq drawdowns.

## 项目结构 / Project Structure

```text
.
├── config.example.json        # 示例配置 / Example config
├── README.md                  # 中英双语说明 / Bilingual documentation
├── requirements.txt           # 安装入口 / Install entry
├── pyproject.toml             # Python package metadata
├── scripts/
│   ├── install_market_task.ps1 # 安装计划任务 / Install scheduled task
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
- `rules.min_turnover_cny`: 最低成交额，单位人民币
- `rules.require_nasdaq_down`: 是否要求纳指同时下跌
- `rules.dedupe_minutes`: 同一 ETF 重复提醒间隔
- `email`: SMTP 邮件配置

- `poll_interval_seconds`: polling interval, currently 60 seconds
- `etfs`: ETF symbols to monitor
- `rules.max_premium_rate`: maximum acceptable premium rate, `0.015` means 1.5%
- `rules.min_turnover_cny`: minimum turnover in CNY
- `rules.require_nasdaq_down`: whether Nasdaq must also be down
- `rules.dedupe_minutes`: cooldown for repeated alerts on the same ETF
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

持续监控：

Run continuously:

```powershell
fund-monitor --config config.json
```

## 交易时段自动运行 / Trading-Session Scheduling

Windows 计划任务会在工作日 09:25 启动，运行约 6 小时，覆盖 A 股交易时段。

The Windows scheduled task starts at 09:25 on weekdays and runs for about six hours, covering A-share trading sessions.

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

