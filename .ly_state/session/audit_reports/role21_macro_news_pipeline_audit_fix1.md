# Code Review Audit Report

**Verdict**: [NEEDS_FIX]
**Role**: 21 `code-reviewer`, Codex L3 independent review
**Date**: 2026-08-12T19:20:42+07:00
**Gate**: `MACRO_NEWS_PIPELINE_code`
**L2 Session**: `.ly_state/session/l2_role15_macro_news_pipeline_fix1_20260812.md`
**L2 Identity**: Role 15 `data-engineer`
**L3 Session**: `role21_macro_news_pipeline_audit_fix1`
**Approved Plan**: `.ly_state/session/implementation_plan_macro_news_v2.md`

## Result

The fix adds PIT-window filtering, universe lifecycle/count manifest fields, basic cache-row validation, source-invariant request bytes, and correct vnstock one-article/many-provenance identity. The approved v2 contract remains incomplete. Blocking PIT, cache-integrity, persistence, registry, source-health, manifest, and dependency-scope defects remain.

## Audit Checklist

- [x] SoD separation: `l2_role_id=15`; `l3_role_id=21`; `15 != 21`.
- [x] Authoritative identities: repo-local role files declare Role 15 data-engineer and Role 21 code-reviewer.
- [ ] Approved scope: implementation incomplete; `requirements.txt` exceeds the approved dependency change.
- [x] Full suite: `python -m pytest -q` exited 0; all collected tests passed; 3 skipped; warnings only.
- [x] Focused plan suite and scoped compilation exited 0.
- [ ] PIT safety: window filtering passes; naive universe lifecycle timestamps do not fail closed.
- [x] L3 boundary: only this report and the named gate entry changed during audit.
- [x] L2 report lists its repo-local role plus eight repo-local skills; every listed file exists under `.agents`.

## Required Checks

### 1. PIT Universe Integration

- PASS: `src/omega/data/macro_news_pipeline.py:169` validates `cutoff/as_of`; lines 184-185 enforce publication and availability upper bounds for vnstock.
- PASS: `src/omega/data/macro_news_pipeline.py:200` applies the PIT window to static sources.
- PASS: `scripts/run_macro_news_pipeline.py:49` persists universe lifecycle fields plus HSX/HNX/UPCOM counts.
- FAIL: `src/omega/data/macro_news_pipeline.py:62` assigns Asia/Ho_Chi_Minh to naive timestamps. `load_universe_snapshot()` uses that parser at line 102, violating the UTC-aware fail-closed contract.
- Probe: naive `generated_at` and `effective_from` values were accepted.

### 2. Source-Invariant LLM Caching

- PASS: `src/omega/data/macro_news_llm.py:35` builds canonical request bytes from model plus title/summary/body only. Provenance-only changes produced identical requests and hashes.
- FAIL: `_validate_cache_row()` at line 52 checks shapes but does not recompute `extraction_id`, bind it to request/provider/endpoint, verify `response_sha256`, or bind evidence to raw text.
- FAIL: mismatch handling at line 82 calls HTTP instead of failing closed on persisted corruption.
- Probe: a forged cached `request_sha256` passed load validation, raised no exception, and caused one HTTP call.
- FAIL: line 83 lacks bounded retry/backoff, response-byte cap, and strict response-envelope validation.
- FAIL: `validate_output()` at line 41 lacks strict nested schemas for topics, entities, indicators, and numeric facts.
- FAIL: line 87 writes sidecars without fixed-order locks, atomic replacement, link schema validation, or raw/extraction FK validation.

### 3. vnstock Provenance Persistence

- PASS: `_record()` at `src/omega/data/macro_news_pipeline.py:138` shares article/revision identity while deriving distinct ticker provenance and raw IDs; universe metadata persists.
- Probe: identical AAA/HSX and BBB/HNX stories produced one article, one revision, two provenance IDs, two raw IDs, exact universe SHA-256.
- FAIL: schema-v1 migration at line 225 discards legacy `available_at` and regenerates `published_at + 15 minutes`.
- Probe: `2026-08-12T02:00:00+00:00` migrated to `2026-08-12T00:15:00+00:00`.
- FAIL: raw persistence at line 215 uses atomic replacement but no exclusive writer lock.

## Additional Blocking Findings

### Source Registry and Health

- `config/macro_news_sources.json:1` contains six entries, not the preserved ten-source baseline plus every approved candidate.
- Required `vcbs_research` uses the generic `<article>` regex parser at `src/omega/data/macro_news_pipeline.py:156`; no approved listing/detail/PDF source-specific contract exists.
- `src/omega/data/macro_news_pipeline.py:208` suppresses static HTTP failures. Required-source failure lacks truthful health evidence and may not affect exit status.

### Manifest and Failure Semantics

- `scripts/run_macro_news_pipeline.py:50` records universe lifecycle/count metadata but omits per-source health, attempts, duration, accepted/rejected counts, inserted/skipped/revised counts, cache metrics, link metrics, retrospective flag, and sanitized effective LLM runtime.
- Raw persistence before LLM extraction is correct, but incomplete source-health accounting prevents truthful required-source status.

### Dependency Scope

- `.ly_state/session/implementation_plan_macro_news_v2.md:591` authorizes only adding `vnstock==4.0.4` to `requirements.txt`.
- `requirements.txt:4` through line 12 also pins/adds Playwright, pyarrow, pypdf, requests, and bottleneck. Current gate scope therefore exceeds the approved dependency diff.

### Scope Attribution

- Review baseline: `HEAD=9ef3963e515869434881e25a12c47c323171abb1`.
- Main macro files are untracked; the worktree contains unrelated changes. Git cannot establish exact L2 authorship. Review covered every L2-declared file plus all modified plan-integration files.

## Required Remediation

1. Reject naive universe lifecycle timestamps; require explicit UTC-aware inputs.
2. Recompute persisted extraction identity; fail closed before network on cache inconsistency.
3. Add strict nested output/response/link schemas, FK checks, bounded retry, response cap, locks, and atomic sidecar replacement.
4. Preserve exact legacy `available_at`; add exclusive raw-store locking.
5. Restore the ten-source baseline, evaluate all planned candidates, implement VCBS-specific ingestion, and emit truthful required-source health.
6. Complete manifest metrics; remove dependency changes beyond `vnstock==4.0.4` unless separately approved.
7. Add regressions for every reproduced failure.

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
- `.ly_state/session/l2_role15_macro_news_pipeline_fix1_20260812.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_audit.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_audit_fix1.md`
- `.ly_state/session/phase_gates.json`
- `config/macro_news_sources.json`
- `requirements.txt`
- `scripts/run_hybrid_alpha_evolution.py`
- `scripts/run_macro_news_pipeline.py`
- `src/omega/core/llm_config.py`
- `src/omega/data/macro_news_llm.py`
- `src/omega/data/macro_news_pipeline.py`
- `tests/test_hybrid_alpha_real_market.py`
- `tests/test_macro_news_llm.py`
- `tests/test_macro_news_pipeline.py`
- `tests/test_news_aggregator.py`
- `tests/test_news_aggregator_scrapers.py`

## Forbidden Path Scan

- Exact scoped result: four textual matches, all in `.ly_state/session/l2_role15_macro_news_pipeline_fix1_20260812.md:39` through line 42.
- Every match explicitly marks Antigravity scratch, OpenClaw, global `C:\Users\GHC\.agents`, or Codex memory as non-authoritative and not read.
- Zero matches occurred in scoped source, tests, config, or `requirements.txt`.
- No forbidden path was opened, written, or used as role/skill authority.

## Verdict

[NEEDS_FIX]
