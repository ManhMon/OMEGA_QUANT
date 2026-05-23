# Phase 1.3 Production Data Pipeline - Admin Test Runner
# Run this script in PowerShell as Administrator
# Purpose: Stable pytest execution with proper temp folder permissions

Write-Host "=== Phase 1.3 Admin Test Runner ===" -ForegroundColor Cyan
Write-Host "Checking admin privileges..." -ForegroundColor Yellow

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "ERROR: This script must run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

Write-Host "Admin privileges confirmed." -ForegroundColor Green

# 1) Prepare temp roots
Write-Host "`nStep 1: Creating temp directories..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path C:\omega_tmp | Out-Null
New-Item -ItemType Directory -Force -Path C:\Users\GHC\.openclaw\workspace\.pytest_tmp | Out-Null
Write-Host "Temp directories ready." -ForegroundColor Green

# 2) Grant stable ACLs
Write-Host "`nStep 2: Setting permissions..." -ForegroundColor Yellow
icacls "C:\omega_tmp" /grant "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" "GHC:(OI)(CI)F" /T /C /Q | Out-Null
icacls "C:\Users\GHC\.openclaw\workspace\.pytest_tmp" /grant "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" "GHC:(OI)(CI)F" /T /C /Q | Out-Null
Write-Host "Permissions set." -ForegroundColor Green

# 3) Run pytest with explicit basetemp + clear addopts
Write-Host "`nStep 3: Running Phase 1.3 tests..." -ForegroundColor Yellow
Write-Host "Command: pytest OMEGA_QUANT/tests/phase2/test_loader.py OMEGA_QUANT/tests/phase2/test_production_pipeline.py -v --basetemp=C:\omega_tmp\admin_run -o 'addopts='" -ForegroundColor Gray

cd C:\Users\GHC\.openclaw\workspace
python -m pytest OMEGA_QUANT/tests/phase2/test_loader.py OMEGA_QUANT/tests/phase2/test_production_pipeline.py -v --basetemp=C:\omega_tmp\admin_run -o "addopts="

$exitCode = $LASTEXITCODE

# 4) Report results
Write-Host "`n=== Test Results ===" -ForegroundColor Cyan
if ($exitCode -eq 0) {
    Write-Host "SUCCESS: All tests passed!" -ForegroundColor Green
} else {
    Write-Host "FAILED: Exit code $exitCode" -ForegroundColor Red
}

Write-Host "`nTo run L3 audit with these permissions:" -ForegroundColor Yellow
Write-Host "codex exec --full-auto '[L3-Audit:Role21-Review] Phase 1.3 Final Audit'" -ForegroundColor Gray

exit $exitCode
