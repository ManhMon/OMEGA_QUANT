# test_opencode_context.ps1 - Test OpenCode Context Awareness

# Step 1: Load context
& "C:\Users\GHC\.openclaw\workspace\scripts\setup_agent_context.ps1"

# Step 2: Ask OpenCode about its role
Write-Host "`n=== Testing OpenCode Context Awareness ===" -ForegroundColor Cyan
opencode run "According to AGENTS.md and SOUL.md in my context, what is your role and what are the Golden Rules you must follow?"
