$ErrorActionPreference = "Stop"

$TaskName = "ETFMonitor"
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($Task) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}

Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -match "fund-monitor|fund_monitor|run_monitor_session.ps1" -and
        $_.CommandLine -notmatch "stop_monitor.ps1"
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
        Write-Host "Stopped process $($_.ProcessId): $($_.Name)"
    }

