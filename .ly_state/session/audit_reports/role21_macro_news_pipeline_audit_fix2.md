# Code Review Audit Report

**Verdict**: [NEEDS_FIX]
**Role**: 21 `code-reviewer`, Codex L3 independent review
**Date**: 2026-08-12T20:40:26+07:00
**Gate**: `MACRO_NEWS_PIPELINE_code`
**L2 Session**: `.ly_state/session/l2_role15_macro_news_pipeline_fix2_20260812.md`
**L2 Identity**: Role 15 `data-engineer`
**L3 Session**: `role21_macro_news_pipeline_audit_fix2`
**Approved Plan**: `.ly_state/session/implementation_plan_macro_news_v2.md`

## Result

PIT universe-window validation, source-invariant LLM request bytes, and vnstock one-article/many-provenance identity pass. The approved v2 contract remains incomplete. Blocking PIT revision timing, cache schema/concurrency/integrity, vnstock run-cap, registry, VCBS, manifest, and dependency-scope defects remain.

## Audit Checklist

- [x] SoD separation: `l2_role_id=15`; `l3_role_id=21`; `15 != 21`.
- [x] Authoritative identities: repo-local role files declare Role 15 `data-engineer` and Role 21 `code-reviewer`.
- [ ] Approved scope: implementation remains incomplete; `requirements.txt` removes tracked `pyarrow` while adding `vnstock==4.0.4`.
- [x] Full suite: `python -m pytest -q` exited 0; 3 skipped; warnings only.
- [x] Scoped `python -m py_compile` exited 0.
- [ ] PIT safety: universe-window validation passes; revision availability can be backdated before ingestion.
- [x] L3 boundary: no production code changed; only this report and the named gate entry are audit outputs.
- [x] L2 report lists repo-local role/skill source evidence under `.agents`.
- [x] Missing `ruff` or lint failure was not used as a rejection reason.

## Required Checks

### 1. PIT Universe Integration

- PASS: universe lifecycle timestamps are UTC-aware and fail closed; publication/availability bounds are enforced against `cutoff` and `as_of`.
- PASS: static and vnstock records are constrained to the requested PIT window.
- FAIL: `src/omega/data/macro_news_pipeline.py:176` assigns every revision `available_at = published_at + 15 minutes`. Content first observed later can therefore receive an availability timestamp before `ingested_at`.
- Probe: changed content observed on `2026-08-02T00:00:00Z` received `available_at=2026-08-01T00:15:00Z`; `backdated=True`.
- FAIL: schema migration preserves legacy `available_at` at `src/omega/data/macro_news_pipeline.py:281`, then rejects valid legacy values below 15 minutes at `src/omega/data/macro_news_pipeline.py:290`.
- Probe: a five-minute legacy availability was rejected with `Macro news available_at violates PIT delay`.

### 2. Source-Invariant LLM Caching

- PASS: canonical LLM request bytes exclude source/ticker provenance. Provenance-only changes produced identical requests and hashes.
- FAIL: `src/omega/data/macro_news_llm.py:25` persists opaque `result_json`, not the approved explicit fixed-schema extraction sidecar.
- FAIL: sidecars are read before locks at `src/omega/data/macro_news_llm.py:117`; locks cover writes only at line 147. Concurrent writers can overwrite links or extractions from another process.
- FAIL: duplicate link keys are accepted at `src/omega/data/macro_news_llm.py:141` through line 146.
- Probe: duplicate-link input returned 2 rows with 1 duplicated key.
- FAIL: startup evidence at `src/omega/data/macro_news_llm.py:122` through line 126 is checked against cached evidence itself, not rebound to the current raw article text.
- FAIL: retry handling does not enforce the approved bounded `Retry-After`; response-size enforcement occurs after the full response is allocated.
- FAIL: the prompt does not contain the complete fixed output schema required by the plan.

### 3. vnstock Provenance Persistence

- PASS: identical ticker stories share one article and one revision while retaining ticker-specific provenance/raw identities.
- Probe: 2 records produced 1 article ID, 1 revision ID, 2 provenance IDs, and 2 raw IDs.
- FAIL: `max_items` is applied per ticker, not across the vnstock run.
- Probe: `max_items=1` returned `AAA`, `BBB`, and `CCC` rows.
- FAIL: source-registry controls are ignored by runtime ingestion; approved expansion candidates are absent.
- FAIL: the required VCBS listing/detail/PDF ingestion contract is absent.

## Additional Blocking Findings

### Manifest and Failure Semantics

- `scripts/run_macro_news_pipeline.py` reports raw metrics that do not reflect actual persistence outcomes.
- `retrospective` is emitted unconditionally rather than derived from the run.
- Required per-source health, attempt, duration, acceptance/rejection, insert/skip/revision, cache, and link metrics remain incomplete.

### Cache Integrity and Persistence

- Persisted extraction/evidence/link rows lack the approved explicit schemas and complete foreign-key/integrity binding.
- Lock scope does not protect read-modify-write transactions, allowing lost updates.
- Duplicate link identity is not rejected fail-closed.

### Dependency Scope

- The approved plan permits adding `vnstock==4.0.4` while retaining existing dependencies.
- `requirements.txt:4` replaces tracked `pyarrow` with `vnstock==4.0.4`; `pyarrow` must remain.

### Scope Attribution

- The worktree contains unrelated changes; main macro files are largely untracked. Git cannot establish exact L2 authorship.
- Review covered every L2-declared file plus all modified plan-integration files listed below.

## Required Remediation

1. Set revision availability from observation/ingestion time without backdating; preserve valid legacy availability exactly.
2. Implement the approved explicit extraction/evidence/link schemas and bind evidence to current raw text.
3. Lock the complete sidecar read-modify-write transaction; reject duplicate keys; enforce foreign-key integrity.
4. Enforce bounded `Retry-After`, streaming/early response limits, and the complete fixed prompt/output schema.
5. Apply vnstock `max_items` run-wide; honor registry controls; add all approved candidates and VCBS detail/PDF ingestion.
6. Emit truthful manifest health/count/cache/link/retrospective fields.
7. Restore `pyarrow`; retain `vnstock==4.0.4`; add regressions for every reproduced defect.

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
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_audit.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_audit_fix1.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_audit_fix2.md`
- `.ly_state/session/phase_gates.json`
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

## Forbidden Path Scan

- Scope: 13 named L2/source/test/config/dependency files.
- Exact result: four textual occurrences on two lines only: `.ly_state/session/l2_role15_macro_news_pipeline_fix2_20260812.md:57` and `.ly_state/session/l2_role15_macro_news_pipeline_fix2_20260812.md:58`.
- Counts: Antigravity 1; OpenClaw 1; global `.agents` 1; Codex memory 1.
- Zero matches occurred in source, tests, config, or `requirements.txt`.
- No forbidden path was opened, written, or used as role/skill authority.

## Verdict

[NEEDS_FIX]
