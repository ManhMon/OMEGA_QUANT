# uninstall_openclaw_cron.ps1
# Purpose: Remove OpenClaw wakeup cron job from Windows Task Scheduler
# Usage: Run as Administrator: powershell -ExecutionPolicy Bypass -File uninstall_openclaw_cron.ps1

param(
    [string]$TaskName = "OpenClawWakeup"
)

$ErrorActionPreference = "Stop"

# Check if running as Administrator
$IsAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    Write-Host "❌ ERROR: This script must be run as Administrator!" -ForegroundColor Red
    exit 1
}

# Unregister task
Write-Host "🗑️  Removing scheduled task: $TaskName" -ForegroundColor Yellow
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "✅ OpenClaw wakeup cron removed successfully!" -ForegroundColor Green
}
catch {
    Write-Host "⚠️ Task not found or error: $($_.Exception.Message)" -ForegroundColor Yellow
}
