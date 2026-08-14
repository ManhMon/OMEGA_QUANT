# L2 Report Template

Copy this template EXACTLY. Fill in `[PLACEHOLDER]` values only.

---

```markdown
# L2 Implementation Report

- **Role**: [ROLE_ID] [ROLE_NAME] - OpenCode L2 Implementation
- **Gate**: [GATE_NAME]
- **Session**: [L2_SESSION_ID]
- **Date**: [YYYYMMDD]

## Summary

[Brief description of what was implemented]

## Repo-Local Files Read

Role and skill files read from REPO_AGENT_ROOT and REPO_SKILL_ROOT only:

- `.agents/agent/[ROLE_NAME].md`
- `.agents/skills/[SKILL_NAME]/SKILL.md`
- [list every file actually read]

## Changes Made

- `[file path]`: [what changed]

## Verification

- [test command run and result]

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: [absent|not read]; non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: [absent|not read]; non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: [absent|not read]; non-authoritative scan evidence only; no reliance.
- `.codex\memories`: [absent|not read]; non-authoritative scan evidence only; no reliance.
```

---

## Critical Rules

| Field | Requirement |
|-------|-------------|
| `## Repo-Local Files Read` | Must exist. Must list at least one `.agents/agent/*.md` file |
| Forbidden path lines | Must end with EXACTLY: `non-authoritative scan evidence only; no reliance.` |
| Report filename | Must be `l2_role{id}_{gate_slug}_{YYYYMMDD}.md` — NO `_retry` suffix |
| Scope | Only modify files listed in SCOPE. Never edit `.ly_state/` except the report |

## Pre-L3 Validation (Mandatory)

After writing L2 report, run:
```powershell
python scripts/validate_l2_report.py [L2_SESSION_ID] [ROLE_ID] [ROLE_NAME]
```

**Only dispatch L3 if exit code = 0.**
