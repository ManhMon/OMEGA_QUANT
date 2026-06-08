param(
  [string]$RepoRoot = 'C:\Users\GHC\repos\OMEGA_QUANT'
)
$ErrorActionPreference = 'Stop'
$statePath = Join-Path $RepoRoot '.ly_state\session\goal_runner_state.json'
$logPath = Join-Path $RepoRoot '.ly_state\session\goal_runner.log'
$state = Get-Content $statePath -Raw | ConvertFrom-Json
$stamp = Get-Date -Format o
Add-Content -Path $logPath -Value "[$stamp] phase=$($state.phase) next=$($state.next_action)"

function Write-State($obj) {
  $obj.last_updated = [double]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
  $obj | ConvertTo-Json -Depth 10 | Set-Content $statePath -Encoding UTF8
}

if ($state.phase -eq 'awaiting_fresh_l3_audit') {
  $auditScript = Join-Path $RepoRoot '.ly_state\session\run_fresh_l3_audit.ps1'
  $auditCmd = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$auditScript`""
  $state.phase = 'l3_audit_running'
  $state.next_action = 'await fresh L3 verdict'
  Write-State $state
  Add-Content -Path $logPath -Value "[$stamp] launch audit script $auditScript"
  Start-Process -FilePath 'powershell' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$auditScript) -WindowStyle Hidden
}
elseif ($state.phase -eq 'l3_audit_running') {
  $report = $state.l3_previous_report
  if ($report -and (Test-Path (Join-Path $RepoRoot $report))) {
    $content = Get-Content (Join-Path $RepoRoot $report) -Raw
    if ($content -match 'final_verdict:\s*\[(APPROVED|NEEDS_FIX)\]') {
      $verdict = $Matches[1]
      $state.phase = if ($verdict -eq 'APPROVED') { 'completed' } else { 'needs_fix' }
      $state.next_action = if ($verdict -eq 'APPROVED') { 'stop' } else { 'run L2 fix for importer cleanup divergence' }
      $state.final_verdict = $verdict
      Write-State $state
      Add-Content -Path $logPath -Value "[$stamp] verdict=$verdict"
      if ($verdict -eq 'APPROVED') {
        Write-Host "VERDICT APPROVED"
      } else {
        Write-Host "VERDICT NEEDS_FIX"
      }
    }
    else {
      Add-Content -Path $logPath -Value "[$stamp] audit running no verdict"
    }
  }
  else {
    Add-Content -Path $logPath -Value "[$stamp] audit report missing"
  }
}
else {
  Add-Content -Path $logPath -Value "[$stamp] no-op phase=$($state.phase)"
}
