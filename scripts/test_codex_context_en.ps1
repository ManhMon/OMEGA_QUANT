# test_codex_context_en.ps1 - Test Codex Context Awareness (English)

# Step 1: Load context
& "C:\Users\GHC\.openclaw\workspace\scripts\setup_agent_context.ps1"

# Step 2: Ask Codex about its role and feedback
Write-Host "`n=== Testing Codex Context Awareness & Feedback (English) ===" -ForegroundColor Cyan
codex exec "Review my provided context ($env:CODEX_CONTEXT).
1. State your role and the specific auditing standards (Karpathy, PIT, Institutional Grade) you enforce.
2. Provide feedback on the current 'Elite CLI Mode + Env Var Context' configuration. 
3. Propose any architectural improvements for better context preservation and token efficiency in the V21_QUANT project.
Be precise and professional."
