# Code Review Audit Report

**Verdict**: [NEEDS_FIX]
**Role**: 21 `code-reviewer`, Codex L3 independent review
**Date**: 2026-08-13T11:54:38+07:00
**Gate**: `MACRO_NEWS_PIPELINE_code`
**L2 Session**: `.ly_state/session/l2_role15_macro_news_pipeline_fix4_20260812.md`
**L2 Identity**: Role 15 `data-engineer`
**L3 Session**: `role21_macro_news_pipeline_audit_fix4`
**L3 Session Key**: `role21_macro_news_pipeline_audit_fix4`
**Approved Plan**: `.ly_state/session/implementation_plan_macro_news_v2.md`

## Result

Source-invariant LLM caching and vnstock one-article/many-provenance persistence pass. PIT universe parsing, hashing, and window filtering pass in isolation. The approved v2 contract remains incomplete: CLI fail-before-import behavior, schema-v1 migration, source-time PIT semantics, registry/network validation, accepted-row health accounting, persisted-store validation, and run-manifest requirements still fail.

## Audit Checklist

- [x] SoD: `l2_role_id=15`; `l3_role_id=21`; `15 != 21`.
- [x] Repo-local role files declare Role 15 `data-engineer` and Role 21 `code-reviewer`.
- [ ] Approved scope: blocking deviations from `.ly_state/session/implementation_plan_macro_news_v2.md` remain.
- [x] Scoped `py_compile` passed.
- [x] Targeted tests passed: `96 passed`.
- [x] Full `python -m pytest -q` passed; 3 skipped; warnings only.
- [ ] PIT safety: universe primitives pass; import ordering and source-time semantics fail.
- [x] L3 boundary: no production code changed; only this report and named gate record updated.
- [x] L2 report lists repo-local role/skill evidence.
- [x] Missing `ruff` or lint failure was not a rejection reason.

## Required Checks

### PIT Universe Integration

- PASS: universe parser, canonical hash, and membership-window enforcement reject malformed or out-of-window records.
- FAIL: `scripts/run_macro_news_pipeline.py:17` imports adapters before universe validation at line 46, violating fail-before-import.
- FAIL: `src/omega/data/macro_news_pipeline.py:178` applies `max(published_at + 15 minutes, ingested_at)` universally. The plan requires source-specific timing; valid historical static backfills become PIT-ineligible.

### Source-Invariant LLM Caching

- PASS: provenance-only changes produced identical request bytes, hash, and endpoint identity.
- PASS: explicit extraction/evidence/link sidecars, current-raw evidence validation, duplicate rejection, and read-modify-write locking are present.

### vnstock Provenance Persistence

- PASS: two ticker-source rows produced 2 rows, 1 article ID, 1 revision ID, 2 provenance IDs, and 2 raw IDs.
- FAIL: `src/omega/data/macro_news_pipeline.py:328` accepts invalid schema versions, hashes, tier/kind/ticker values, and universe bindings.

## Blocking Findings

- `scripts/run_macro_news_pipeline.py:54`: schema-v1 pre-read accesses `raw_record_id`; probe failed with `KeyError: 'raw_record_id'` before migration.
- `src/omega/data/macro_news_pipeline.py:156`: registry accepts malformed IDs/types/tiers, invalid booleans, negative limits/timeouts, and private HTTP hosts.
- `src/omega/data/macro_news_pipeline.py:285`: missing DNS/private-IP and redirect/final-host enforcement; VCBS detail lacks configured byte cap.
- `src/omega/data/macro_news_pipeline.py:298`: health counts parsed rows, not PIT-accepted rows. Probe persisted 0 while health reported `accepted=1`.
- `scripts/run_macro_news_pipeline.py:71`: manifest path differs from `.ly_state/session/macro_news_runs/<run_id>.json`; required run/schema/input metadata is absent.
- `scripts/run_macro_news_pipeline.py:64`: provenance additions count as `raw_revised`.
- Registry delay/tier/name/paging/pacing/PDF controls are not consistently enforced.

## Required Remediation

1. Validate universe before adapter imports.
2. Migrate v1 stores before v2-field reads.
3. Implement exact source-specific availability timing.
4. Fail closed on registry, public-host/DNS/redirect, response, and paging controls.
5. Report PIT-accepted persistence outcomes.
6. Validate complete persisted schema and bindings.
7. Write the required complete run manifest; separate provenance inserts from revisions.
8. Add regressions for each reproduced failure.

## Modified Scope Files Reviewed

- `config/macro_news_sources.json`
- `requirements.txt`
- `scripts/run_hybrid_alpha_evolution.py`
- `scripts/run_macro_news_pipeline.py`
- `src/omega/core/llm_config.py`
- `src/omega/data/macro_news_llm.py`
- `src/omega/data/macro_news_pipeline.py`
- `src/omega/data/macro_pipeline.py`
- `src/omega/data/news_aggregator.py`
- `tests/test_hybrid_alpha_real_market.py`
- `tests/test_macro_news_llm.py`
- `tests/test_macro_news_pipeline.py`
- `tests/test_news_aggregator.py`
- `tests/test_news_aggregator_scrapers.py`

The worktree contains unrelated staged and unstaged changes. Review covered the full L2-declared scope and plan-integration files; Git state cannot independently attribute every dirty file to this L2 session.

## Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/agent/data-engineer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/implementation_plan_macro_news_v2.md`
- `.ly_state/session/l2_role15_macro_news_pipeline_20260812.md`
- `.ly_state/session/l2_role15_macro_news_pipeline_fix1_20260812.md`
- `.ly_state/session/l2_role15_macro_news_pipeline_fix2_20260812.md`
- `.ly_state/session/l2_role15_macro_news_pipeline_fix3_20260812.md`
- `.ly_state/session/l2_role15_macro_news_pipeline_fix4_20260812.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_audit.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_audit_fix1.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_audit_fix2.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_audit_fix4.md`
- `.ly_state/session/phase_gates.json`
- `config/macro_news_sources.json`
- `requirements.txt`
- `scripts/run_hybrid_alpha_evolution.py`
- `scripts/run_macro_news_pipeline.py`
- `scripts/sod_gate_enforcer.py`
- `src/omega/core/llm_config.py`
- `src/omega/data/macro_news_llm.py`
- `src/omega/data/macro_news_pipeline.py`
- `src/omega/data/macro_pipeline.py`
- `src/omega/data/news_aggregator.py`
- `tests/test_hybrid_alpha_real_market.py`
- `tests/test_macro_news_llm.py`
- `tests/test_macro_news_pipeline.py`
- `tests/test_news_aggregator.py`
- `tests/test_news_aggregator_scrapers.py`

Only role-required skills under `.agents/skills` were authoritative. No forbidden path was opened or used.

## Forbidden Path Scan

- Scope: L2 fix4 report plus 14 reviewed source, test, config, and dependency files.
- Patterns: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.
- Result: 4 textual matches, all on `.ly_state/session/l2_role15_macro_news_pipeline_fix4_20260812.md:43`, where L2 records its scan evidence.
- Zero matches in source, tests, config, or `requirements.txt`.
- No forbidden path was opened, written, or used as role/skill authority.

## Verdict

[NEEDS_FIX]
