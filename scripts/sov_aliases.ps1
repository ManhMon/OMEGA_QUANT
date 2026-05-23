# Sovereign V13 Aliases for PowerShell
function sov-run { python scripts/sovereign_orchestrator.py $args }
function sov-status { Get-Content .ly_state/session/ui_dashboard.json | ConvertFrom-Json | ConvertTo-Json -Depth 10 }
function sov-tasks { Get-Content .ly_state/session/active_tasks.json | ConvertFrom-Json | ConvertTo-Json -Depth 10 }
function sov-snap { python scripts/state_sentinel.py snapshot $args }
function sov-rollback { python scripts/state_sentinel.py rollback $args }
function sov-list-snaps { python scripts/state_sentinel.py list }
function sov-prune { python scripts/context_pruning.py prune --force }
function sov-stats { python scripts/context_pruning.py stats ; python scripts/observability_engine.py stats }

Write-Host "[OK] Sovereign V13 Aliases Activated!" -ForegroundColor Sovereign
