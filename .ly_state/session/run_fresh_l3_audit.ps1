param(
  [string]$RepoRoot = 'C:\Users\GHC\repos\OMEGA_QUANT'
)
$statePath = Join-Path $RepoRoot '.ly_state\session\goal_runner_state.json'
$promptPath = Join-Path $RepoRoot '.ly_state\session\l3_audit_importer_cleanup_20260605.txt'
$logPath = Join-Path $RepoRoot '.ly_state\session\goal_runner.log'
$state = Get-Content $statePath -Raw | ConvertFrom-Json
$stamp = Get-Date -Format o
Add-Content -Path $logPath -Value "[$stamp] fresh-audit start"
$state.l3_audit_started = $stamp
$state.phase = 'l3_audit_running'
$state.next_action = 'await fresh L3 verdict'
$state.last_updated = [double]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
$state | ConvertTo-Json -Depth 10 | Set-Content $statePath -Encoding UTF8
$cmd = "python -c \"from pathlib import Path; p=Path(r'$promptPath'); print(p.read_text(encoding='utf-8'))\" | codex exec --dangerously-bypass-approvals-and-sandbox -"
Start-Process -FilePath 'powershell' -ArgumentList @('-NoProfile','-Command',$cmd) -WindowStyle Hidden
