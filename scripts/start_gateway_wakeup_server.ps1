# start_gateway_wakeup_server.ps1
# Purpose: Start the gateway wakeup HTTP server (background service)
# Usage: powershell -ExecutionPolicy Bypass -File start_gateway_wakeup_server.ps1

param(
    [string]$ServerScript = "C:\Users\GHC\.openclaw\workspace\scripts\gateway_wakeup_server.py",
    [string]$PythonExe = "C:\Users\GHC\AppData\Local\Programs\Python\Python314\python.exe"
)

# Verify files exist
if (-not (Test-Path $ServerScript)) {
    Write-Host "ERROR: Server script not found: $ServerScript" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $PythonExe)) {
    Write-Host "ERROR: Python executable not found: $PythonExe" -ForegroundColor Red
    exit 1
}

# Kill any existing process on port 8080
Write-Host "Checking for existing processes on port 8080..." -ForegroundColor Yellow
try {
    $ExistingProcess = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
    if ($ExistingProcess) {
        Write-Host "Killing existing process on port 8080..." -ForegroundColor Yellow
        Stop-Process -Id $ExistingProcess.OwningProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}
catch {
    # Port not in use, continue
}

# Start server in background
Write-Host "Starting gateway wakeup server..." -ForegroundColor Green
$ProcessArgs = @(
    $ServerScript
)

$Process = Start-Process -FilePath $PythonExe -ArgumentList $ProcessArgs -NoNewWindow -PassThru

Write-Host "Gateway wakeup server started successfully!" -ForegroundColor Green
Write-Host "   PID: $($Process.Id)" -ForegroundColor Cyan
Write-Host "   Endpoint: http://localhost:8080/callback/wakeup" -ForegroundColor Cyan
Write-Host "   Log: C:\Users\GHC\.openclaw\workspace\.ly_state\logs\gateway_server.log" -ForegroundColor Cyan
Write-Host "" -ForegroundColor Cyan
Write-Host "To stop: taskkill /PID $($Process.Id) /F" -ForegroundColor Yellow
Write-Host "To check: Get-Content -Path 'C:\Users\GHC\.openclaw\workspace\.ly_state\logs\gateway_server.log' -Tail 20" -ForegroundColor Yellow
