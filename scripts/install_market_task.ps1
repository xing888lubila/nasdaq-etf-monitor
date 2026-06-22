$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SessionScript = Join-Path $ProjectRoot "scripts\run_monitor_session.ps1"
$FuturesTrendScript = Join-Path $ProjectRoot "scripts\run_futures_trend_snapshot.ps1"
$TaskName = "ETFMonitor"
$FuturesTrendTaskName = "ETFMonitorFuturesTrend"

if (-not (Test-Path -LiteralPath $SessionScript)) {
    throw "session script not found: $SessionScript"
}

if (-not (Test-Path -LiteralPath $FuturesTrendScript)) {
    throw "futures trend script not found: $FuturesTrendScript"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$SessionScript`""

$Trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At ([datetime]::Today.AddHours(9).AddMinutes(20))

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Run Nasdaq ETF monitor on weekday A-share trading sessions." `
    -Force | Out-Null

$FuturesTrendAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$FuturesTrendScript`""

$FuturesTrendTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At ([datetime]::Today.AddHours(14).AddMinutes(30))

$FuturesTrendSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $FuturesTrendTaskName `
    -Action $FuturesTrendAction `
    -Trigger $FuturesTrendTrigger `
    -Settings $FuturesTrendSettings `
    -Description "Send integrated Nasdaq futures prediction and scoring brief at 14:30 on weekdays." `
    -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Schedule: Monday-Friday 09:20, sends integrated prediction snapshot, then monitors ETF alerts for 6 hours."
Write-Host "Installed scheduled task: $FuturesTrendTaskName"
Write-Host "Schedule: Monday-Friday 14:30, sends integrated NQ futures prediction and scoring brief."
Write-Host "Logs: $ProjectRoot\logs"
