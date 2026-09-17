## L2 Evidence Report

Gate: `sod_wording_preflight_prompt_20260725`
Role: `9 backend-engineer` (OpenCode L2)

## Repo-Local Files Read

- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/AGENTS.md`
- `scripts/omega_role_router.py`

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: non-authoritative scan evidence only; no reliance.
- `.codex\memories`: non-authoritative scan evidence only; no reliance.

## Changes

- Added recommended `python scripts/lint_sod_report_evidence.py <report> --gate <gate>` preflight guidance to authoritative L2/L3 producer prompts.
- Added the same guidance to the routed prompt builder.
- Explicitly preserved `python scripts/sod_gate_enforcer.py` as the final hard gate.

## Verification

- `python -m py_compile scripts/omega_role_router.py` - PASS

No audit or approval performed. L3 handoff required.
