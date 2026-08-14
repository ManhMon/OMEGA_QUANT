# Macro News Pipeline v5 Plan Re-Audit

- Verdict: `[NEEDS_FIX]`
- Date: `2026-08-13T20:06:45+07:00`
- Scope: `.ly_state/session/implementation_plan_macro_news_v5.md`
- L2 Session: `.ly_state/session/implementation_plan_macro_news_v5.md`
- L2 Role: `26 planning-architect`
- L3 Session ID: `role21_macro_news_pipeline_plan_v5_reaudit_20260813`
- L3 Session Key: `role21_macro_news_pipeline_plan_v5_reaudit_20260813`
- L3 Role: `21 code-reviewer`
- Submission SHA-256: `EBBC3F72B6987BFC88257FAC7E08C25676630BBCF1E29E297A7961600F07B41E`
- REPO_AGENT_ROOT: `.agents/agent`
- REPO_SKILL_ROOT: `.agents/skills`

## Audit Evidence Checklist

1. **Writer/auditor separation - PASS.** `l2_role_id=26` differs from `l3_role_id=21`; role 26 is planning-only and non-audit, while role 21 is the independent audit role.
2. **Approved scope - PASS.** The v4-to-v5 submission diff changes only `.ly_state/session/implementation_plan_macro_news_v5.md` and removes two evidence-label lines. No production or test file was modified by this plan submission or this audit.
3. **All tests - PASS.** `python -m pytest` completed with `3261 passed, 3 skipped, 864 warnings` in `201.44s`, exit `0`. Focused macro tests completed with `53 passed, 12 warnings`, exit `0`.
4. **PIT safety - NEEDS_FIX.** The generic publication, availability, cutoff, source-delay, and raw-before-LLM controls at `.ly_state/session/implementation_plan_macro_news_v5.md:166` are sound, but the plan defines no PIT-safe acquisition or publication contract for SBV interest rates or SBV exchange rates.
5. **SOD boundaries - PASS.** Role 26 changed only the plan. Role 21 changed only this audit report and the target gate metadata. Production source and tests remain read-only.
6. **L2 repo-local skill evidence - PASS.** The plan's section 18 source-evidence block lists `.agents/agent/planning-architect.md` plus all four declared repo-local skill files. Strict L2 skill-source parsing and forbidden-path validation pass with zero violations.

## Blocking Findings

1. **P1 - SBV interest-rate contract absent.** The plan's exact file-change list at `.ly_state/session/implementation_plan_macro_news_v5.md:226` omits `src/omega/data/macro_pipeline.py`, and the source plan at `.ly_state/session/implementation_plan_macro_news_v5.md:137` covers only news/research feeds. Current code maps `interbank_rate` to SBV at `src/omega/data/macro_pipeline.py:23`, then calls `_sbv_records()` without extending returned records at `src/omega/data/macro_pipeline.py:89`; `_sbv_records()` returns `None` at `src/omega/data/macro_pipeline.py:172`. The plan therefore cannot deliver or test SBV interest rates.
2. **P1 - SBV exchange-rate contract absent.** Current `usd_vnd` uses Yahoo at `src/omega/data/macro_pipeline.py:27`. The plan has no official SBV exchange-rate endpoint, parser, publication-time evidence, source-delay rule, revision identity, failure policy, fixture, or acceptance test. Runtime inspection of pinned `vnstock==4.0.4` exposes `vcb_exchange_rate(date=...)`, documented as Vietcombank data; it is not an SBV substitute.
3. **P1 - Unsupported Vnstock parameters preserved.** Pinned `vnstock==4.0.4` resolves VCI provider `news()` to `news() -> DataFrame`; it does not support `cursor`, `limit`, or `sort`. Current code nevertheless passes all three at `src/omega/data/macro_news_pipeline.py:158` and assumes `frame.attrs.pagination.next_cursor` at `src/omega/data/macro_news_pipeline.py:341`. The plan says to preserve the existing Vnstock path but never requires removal of unsupported parameters or a supported bounded-fetch contract, so the proposed pagination and ordering guarantees are unverified.
4. **P1 - v5 artifact identity remains stale.** `.ly_state/session/implementation_plan_macro_news_v5.md:1` labels the artifact as v3, and `.ly_state/session/implementation_plan_macro_news_v5.md:6` declares the v3 path. This breaks plan-version traceability. The v4-to-v5 diff only removes two evidence-label lines and does not correct either identity.

## Required Actions

1. Add binding planned changes and fixture-backed tests for PIT-safe SBV interest-rate ingestion, including returned-record integration into `fetch()`.
2. Add a distinct official SBV exchange-rate contract; do not represent Yahoo or Vietcombank data as SBV data.
3. Bind the VCI adapter to the pinned `vnstock==4.0.4` API: call supported parameters only, apply deterministic local filtering/sorting/caps, and remove cursor pagination assumptions unless a verified provider contract supplies them.
4. Rename the plan title and artifact declaration to v5, then resubmit a materially updated plan.

## Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/agent/planning-architect.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/implementation_plan_macro_news_v4.md`
- `.ly_state/session/implementation_plan_macro_news_v5.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan_v5_20260813.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan_v5_reaudit_20260813.md`
- `.ly_state/session/phase_gates.json`
- `requirements.txt`
- `src/omega/data/macro_pipeline.py`
- `src/omega/data/macro_news_pipeline.py`
- `scripts/sod_gate_enforcer.py`
- `scripts/sod_report_evidence.py`

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: non-authoritative scan evidence only; no reliance.
- `.codex\memories`: non-authoritative scan evidence only; no reliance.
- Result: zero forbidden content reads; zero forbidden authoritative reliance; zero forbidden path writes.

## Verdict

`[NEEDS_FIX]`

The plan does not yet satisfy the required SBV interest-rate, SBV exchange-rate, Vnstock API-contract, or artifact-traceability checks.
