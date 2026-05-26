$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SessionScript = Join-Path $ProjectRoot "scripts\run_monitor_session.ps1"
$TaskName = "ETFMonitor"

if (-not (Test-Path -LiteralPath $SessionScript)) {
    throw "session script not found: $SessionScript"
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
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Run Nasdaq ETF monitor on weekday A-share trading sessions." `
    -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Schedule: Monday-Friday 09:20, stops after 6 hours."
Write-Host "Logs: $ProjectRoot\logs"
