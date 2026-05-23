# install_openclaw_cron.ps1
# Purpose: Install OpenClaw wakeup cron job via Windows Task Scheduler
# Usage: Run as Administrator: powershell -ExecutionPolicy Bypass -File install_openclaw_cron.ps1

param(
    [string]$TaskName = "OpenClawWakeup",
    [string]$ScriptPath = "C:\Users\GHC\.openclaw\workspace\scripts\wakeup_openclaw_cron.ps1",
    [int]$IntervalMinutes = 1
)

$ErrorActionPreference = "Stop"

# Check if running as Administrator
$IsAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "   Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

# Verify script path exists
if (-not (Test-Path $ScriptPath)) {
    Write-Host "ERROR: Script not found: $ScriptPath" -ForegroundColor Red
    exit 1
}

# Remove existing task if exists
Write-Host "Removing existing task if exists..." -ForegroundColor Yellow
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Create action
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$ScriptPath`""

# Create trigger - repeat every $IntervalMinutes indefinitely
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 365)

# Create settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable:$false

# Register task
Write-Host "Registering scheduled task: $TaskName" -ForegroundColor Yellow
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "OpenClaw Gateway Wakeup Cron (PD v4.2)"

Write-Host "OpenClaw wakeup cron installed successfully!" -ForegroundColor Green
Write-Host "   Task Name: $TaskName" -ForegroundColor Cyan
Write-Host "   Interval: Every 60 seconds" -ForegroundColor Cyan
Write-Host "   Script: $ScriptPath" -ForegroundColor Cyan
Write-Host "" -ForegroundColor Cyan
Write-Host "To verify: Get-ScheduledTask -TaskName OpenClawWakeup | Format-List *" -ForegroundColor Yellow
Write-Host "To uninstall: powershell -ExecutionPolicy Bypass -File uninstall_openclaw_cron.ps1" -ForegroundColor Yellow
