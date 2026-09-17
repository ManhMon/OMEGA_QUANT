# Lesson Gate Repair Plan Audit

**Role**: `21 code-reviewer` (Codex L3 Plan Review)
**Gate**: `lesson_gate_repair_plan_20260726`
**Date**: `2026-07-26`
**Reviewed plan**: `C:\Users\GHC\.gemini\antigravity-ide\brain\3d6d7760-071e-42d2-a99e-b9922376d700\implementation_plan.md`
**Scope**: Plan review only; no production source or `phase_gates.json` modified.

## Repo-Local Files Read

- `REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`
- `REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`
- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `scripts/extract_lessons.py`
- `scripts/get_relevant_lessons.py`
- `tests/test_extract_lessons.py`

## Review Findings

1. **Root cause confirmed.** `scripts/get_relevant_lessons.py:5` imports `normalize_lesson_text`; `scripts/extract_lessons.py` does not define or export it.
2. **Repair is minimal.** One pure normalization helper plus focused tests repairs the import without bypass or unrelated abstraction.
3. **Fallback is deterministic and nonfatal.** The plan preserves role matching, local fallback, newest-first JSONL fallback, and safe missing/malformed handling without traceback.
4. **CLI import regression is covered.** A subprocess test executes `scripts/get_relevant_lessons.py`, checks exit `0`, and catches the exact import-time failure.
5. **No bypass or configuration expansion.** Mandatory lookup remains required; lesson content, graph materialization, LLM configuration, and alpha modules remain excluded.
6. **SoD routing valid.** L2 `9 backend-engineer`; L3 `21 code-reviewer`.

## Required Implementation Guardrails

- `None` maps to empty text; other values use string conversion, trim, lowercase.
- Missing/malformed tests isolate paths; they must not mutate `.agents/knowledge/lessons.jsonl` or `.agents/knowledge/chromadb`.
- CLI regression asserts no traceback, not only exit `0`.
- No changes to `phase_gates.json`, graph/LLM configuration, graph modules, or alpha modules.

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit` non-authoritative scan evidence only; no reliance.
- `.openclaw\skills` non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents` non-authoritative scan evidence only; no reliance.
- `.codex\memories` non-authoritative scan evidence only; no reliance.

## Verdict

[APPROVED]
