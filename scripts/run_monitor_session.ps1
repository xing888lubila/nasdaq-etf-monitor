$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir ("monitor-" + (Get-Date -Format "yyyyMMdd") + ".log")
$Runner = Join-Path $ProjectRoot ".venv\Scripts\fund-monitor.exe"
$Config = Join-Path $ProjectRoot "config.json"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $ProjectRoot

function Write-MonitorLog {
    param([string]$Message)
    $Line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -LiteralPath $LogFile -Value $Line -Encoding UTF8
}

Write-MonitorLog "ETF monitor session starting."

if (-not (Test-Path -LiteralPath $Runner)) {
    Write-MonitorLog "ERROR: runner not found: $Runner"
    throw "runner not found: $Runner"
}

if (-not (Test-Path -LiteralPath $Config)) {
    Write-MonitorLog "ERROR: config not found: $Config"
    throw "config not found: $Config"
}

if (-not $env:ETF_MONITOR_SMTP_PASSWORD) {
    Write-MonitorLog "ERROR: ETF_MONITOR_SMTP_PASSWORD is missing. Set it as a User environment variable."
    throw "ETF_MONITOR_SMTP_PASSWORD is missing"
}

& $Runner --config $Config *>> $LogFile

