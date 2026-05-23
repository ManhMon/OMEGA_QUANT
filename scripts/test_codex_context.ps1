# test_codex_context.ps1 - Test Codex Context Awareness and Feedback

# Step 1: Load context
& "C:\Users\GHC\.openclaw\workspace\scripts\setup_agent_context.ps1"

# Step 2: Ask Codex about its role and feedback on the configuration
Write-Host "`n=== Testing Codex Context Awareness & Feedback ===" -ForegroundColor Cyan
codex exec "Based on AGENTS.md, SOUL.md, and your current environment ($env:CODEX_CONTEXT):
1. Confirm your role and the specific auditing standards you must enforce (e.g., Karpathy, PIT).
2. Give your professional feedback on our current 'Elite CLI Mode + Env Var Context' configuration. 
3. Is there a more efficient way to ensure you never lose context while maintaining high auditing rigor for V21_QUANT?
Return your verdict clearly."
