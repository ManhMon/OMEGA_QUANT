# wakeup_openclaw_cron.ps1
# Purpose: Trigger OpenClaw gateway callback hook every 30 seconds to wake up pending tasks
# Usage: Run this script via Windows Task Scheduler

param(
    [int]$IntervalSeconds = 60,
    [string]$GatewayUrl = "http://localhost:8080",
    [string]$LogPath = "C:\Users\GHC\.openclaw\workspace\omega\.ly_state\logs\cron_wakeup.log"
)

# Ensure log directory exists
$LogDir = Split-Path -Parent $LogPath
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Log-Message {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    $LogEntry = "[$Timestamp] $Message"
    Add-Content -Path $LogPath -Value $LogEntry
    Write-Host $LogEntry
}

function Trigger-GatewayCallback {
    try {
        $Endpoint = "$GatewayUrl/callback/wakeup"
        $Response = Invoke-WebRequest -Uri $Endpoint -Method POST -TimeoutSec 5 -ErrorAction Stop -UseBasicParsing
        Log-Message "✅ Wakeup triggered: $($Response.StatusCode)"
        return $true
    }
    catch {
        Log-Message "⚠️ Wakeup failed: $($_.Exception.Message)"
        return $false
    }
}

Log-Message "🚀 OpenClaw Cron Wakeup started (Interval: ${IntervalSeconds}s)"

# Main loop - runs indefinitely
while ($true) {
    Trigger-GatewayCallback
    Start-Sleep -Seconds $IntervalSeconds
}
