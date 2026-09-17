# Code Review Plan Re-Audit Report

**Role**: Code Reviewer (Role 21, Codex L3)
**Date**: 2026-07-26
**Submission**: `C:\Users\GHC\.gemini\antigravity-ide\brain\3d6d7760-071e-42d2-a99e-b9922376d700\legacy_selector_timestamp_fallback_plan.md`
**Audit Type**: Plan re-audit after prior empty `NEEDS_FIX` report

## Scope

- Plan-only review. No code, test, or gate metadata edits.
- Proposed scope: `scripts/sod_report_evidence.py`, `scripts/sod_gate_enforcer.py`, focused selector/enforcer tests.

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
- `scripts/sod_report_evidence.py`
- `scripts/sod_gate_enforcer.py`
- `tests/test_sod_report_evidence.py`
- `C:\Users\GHC\.gemini\antigravity-ide\brain\3d6d7760-071e-42d2-a99e-b9922376d700\legacy_selector_timestamp_fallback_plan.md`

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: non-authoritative scan evidence only; no reliance.
- `.codex\memories`: non-authoritative scan evidence only; no reliance.

## Findings

1. **[blocking: unresolved data flow]** `validate_report_evidence()` receives no gate record. Require `scripts/sod_gate_enforcer.py` to resolve the date from the complete gate record, then pass it explicitly. The validator must not read `phase_gates.json`, infer a record, or silently reinterpret `gate_name`.

2. **[blocking: contradiction policy absent]** A valid gate-key `YYYYMMDD` remains authoritative, but an existing timestamp must parse and agree. Key date versus timestamp date in its declared offset mismatch fails closed. Test key `..._20260724` plus timestamp `2026-07-25T00:00:00+07:00`.

3. **[blocking: timestamp validity underspecified]** Require timezone-aware ISO-8601 with offset or `Z`. Naive, malformed, impossible, non-string, and missing values for undated gates fail closed. Use the date in the declared offset; never host local time.

4. **[blocking: filename contract ambiguous]** Define policy. Recommended: canonical gates (`resolved_gate_date >= 2026-07-25`) require one valid filename `YYYYMMDD`, not earlier than gate date. Legacy gates may use undated filenames; present selectors must be valid and not earlier. Malformed or multiple selectors fail closed.

5. **[blocking: tests incomplete]** Cover matching/mismatching dated key and timestamp; malformed/naive timestamp; undated pre/post-cutoff timestamp; missing timestamp; legacy/canonical undated filename; equal/newer/older filename; malformed/multiple filename selectors. Test validator API plus enforcer extraction integration.

6. **[blocking: API compatibility unstated]** Specify explicit `resolved_gate_date` for enforcer-driven validation. Isolate key/timestamp reconciliation in a helper. Retained `strict=` behavior must not bypass production contradiction checks.

## Acceptance Criteria

- Enforcer resolves and reconciles key plus timestamp before report validation.
- Pure validator receives resolved gate date explicitly.
- Key/timestamp disagreement fails closed.
- Only timezone-aware ISO timestamps enable fallback.
- Canonical versus legacy filename rules are documented and tested.
- Focused tests, compile checks, full enforcer inventory show no unplanned regression.

## Verdict

[NEEDS_FIX] — Goal valid; plan lacks gate-record data flow, contradiction semantics, timezone rules, filename policy, complete fail-closed tests.
