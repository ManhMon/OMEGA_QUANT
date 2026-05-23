# OpenCode External Directory Whitelist Configuration

**Date**: 2026-05-21  
**Issue**: OpenCode blocked reading skill files from `C:\Users\GHC\.openclaw\workspace\skills\elite_karpathy\karpathy-coder\*`  
**Error**: `permission requested: external_directory (...); auto-rejecting`

## Root Cause

OpenCode has a separate permission layer independent of OpenClaw's exec approvals. Even with OpenClaw YOLO mode (`security=full`, `ask=off`), OpenCode still enforces its own `external_directory` permission checks.

## Solution

Edit OpenCode config file to allow external directory access globally.

### Config File Location
```
C:\Users\GHC\.config\opencode\opencode.json
```

### Configuration Change

Add `permission` section at root level:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": { ... },
  "model": "9router/kr/claude-sonnet-4.6",
  "agent": { ... },
  "permission": {
    "external_directory": "allow"
  }
}
```

**Valid values**: `"ask"` | `"allow"` | `"deny"`

### Usage Pattern

After configuration, OpenCode can read skill files without approval prompts:

```bash
# Standard call (with skill auto-loading)
opencode run "[L2-Impl:Role9-Backend] <task>"

# Pure mode (skip external plugins, but still respects permission config)
opencode run --pure "[L2-Impl:Role9-Backend] <task>"
```

### Verification

Test skill file access:

```bash
opencode run "[L2-Impl:Role9-Backend] Read C:\Users\GHC\.openclaw\workspace\skills\elite_karpathy\karpathy-coder\SKILL.md and output first 3 lines."
```

Expected: No permission error, skill content displayed.

## Notes

- OpenCode permission system is **independent** from OpenClaw exec approvals
- Setting `external_directory: "allow"` grants global access to all external paths
- For finer-grained control, use agent-level permission overrides (not documented here)
- This configuration persists across OpenCode restarts

## Related

- OpenClaw exec approvals: `~/.openclaw/exec-approvals.json`
- OpenClaw config: `~/.openclaw/openclaw.json`
- OpenCode SDK types: `@opencode-ai/sdk/dist/gen/types.gen.d.ts` (PermissionActionConfig)
