$ErrorActionPreference = "Stop"

$TaskName = "ETFMonitor"
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($Task) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started scheduled task: $TaskName"
    return
}

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SessionScript = Join-Path $ProjectRoot "scripts\run_monitor_session.ps1"

Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$SessionScript`"" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden

Write-Host "Started ETF monitor in a hidden PowerShell process."

