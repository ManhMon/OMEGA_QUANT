# setup_agent_context.ps1 - V21_QUANT Agent Context Configuration (V21.38 FIXED)
# Chi thiet lap bien moi truong - khong spam loi nua
$workspace = "C:\Users\GHC\.openclaw\workspace"

$env:V21_WORKSPACE = $workspace
$env:V21_AGENTS_RULES = "$workspace\AGENTS.md"
$env:V21_PIT_RULES = "$workspace\SOUL.md"
$env:V21_TOOLS_CONFIG = "$workspace\TOOLS.md"
$env:V21_RAM_LIMIT_MB = "4096"
$env:V21_DATA_CUTOFF = Get-Date -Format "yyyy-MM-dd"

# Audit log (non-critical - SUPPRESS ALL ERRORS)
try {
    $auditTrailFile = "C:/Users/GHC/.openclaw/workspace/V21_QUANT/logs/skill_requests.log"
    $logDir = Split-Path $auditTrailFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    $auditLogEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - V21 Paths Loaded"
    [System.IO.File]::AppendAllText($auditTrailFile, $auditLogEntry + [Environment]::NewLine)
} catch { }

# Context file - SUPPRESS ALL ERRORS (non-critical file write)
$contextFile = "$workspace\scripts\agent_context.txt"
$contextOutput = @"
V21_QUANT Agent Context ($(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
V21_WORKSPACE: $env:V21_WORKSPACE
V21_AGENTS_RULES: $env:V21_AGENTS_RULES
V21_PIT_RULES: $env:V21_PIT_RULES
V21_TOOLS_CONFIG: $env:V21_TOOLS_CONFIG
V21_RAM_LIMIT_MB: $env:V21_RAM_LIMIT_MB
"@
try {
    $null = [System.IO.File]::WriteAllText($contextFile, $contextOutput, [System.Text.Encoding]::UTF8)
} catch { }
