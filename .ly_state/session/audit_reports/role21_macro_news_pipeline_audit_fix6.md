# Code Review Audit Report

**Verdict**: [NEEDS_FIX]
**Role**: 21 `code-reviewer`, Codex L3 independent review
**Date**: 2026-08-13T13:38:58+07:00
**Gate**: `MACRO_NEWS_PIPELINE_code`
**L2 Session**: `.ly_state/session/l2_role15_macro_news_pipeline_fix6_20260813.md`
**L2 Identity**: Role 15 `data-engineer`
**L3 Session**: `role21_macro_news_pipeline_audit_fix6`
**L3 Session Key**: `role21_macro_news_pipeline_audit_fix6`
**Approved Plan**: `.ly_state/session/implementation_plan_macro_news_v2.md`

## Result

Fix6 repairs the prior registry, pre-import validation, bounded static-response, hostname, identity-recomputation, and vnstock-control wiring findings. Source-invariant LLM caching passes. vnstock one-article/many-provenance persistence passes. Approval remains blocked by a mutable double-read universe handoff, a post-hoc rather than enforced vnstock timeout, and pagination continuing after the cutoff is reached.

## Audit Checklist

- [x] SoD: `l2_role_id=15`; `l3_role_id=21`; `15 != 21`.
- [x] Scope: the three L2-declared files match approved fix6 remediation scope.
- [ ] Approved behavior: three blocking deviations remain.
- [x] Targeted tests: `23 passed`.
- [x] Approved five-file regression suite: exit `0`.
- [x] Full `python -m pytest -q`: exit `0`; 3 skipped; warnings only.
- [x] Scoped compilation and `git diff --check` passed.
- [ ] PIT safety: validation passes; immutable exact-byte handoff fails.
- [x] L3 boundary: no production/test code changed; report and named gate only.
- [x] L2 report lists exact repo-local role/skill sources.
- [x] Missing `ruff` or lint failure was not a rejection reason.

## Required Checks

### PIT Universe Integration

- PASS: explicit path, `.ly_state` rejection, strict schema, UTC lifecycle, PIT interval, member validation, exact-byte SHA-256, and row provenance.
- FAIL: plan line 159 requires one exact-byte read. `scripts/run_macro_news_pipeline.py:44` reads the file, then `src/omega/data/macro_news_pipeline.py:169` reopens it via `scripts/run_macro_news_pipeline.py:77`.
- FAIL: registry DNS at `scripts/run_macro_news_pipeline.py:76` occurs before the bytes ultimately used at line 77 are read.
- Probe: replacing valid `AAA` bytes with valid `BBB` bytes after prevalidation produced `TOCTOU_ACCEPTED True True`; executed membership/hash differed from prevalidated bytes.

### Source-Invariant LLM Caching

- PASS: `src/omega/data/macro_news_llm.py:54` includes only title, summary, and body text.
- PASS: different source/provenance with identical content produced identical request bytes/hash/endpoint identity: `CACHE_SOURCE_INVARIANT True`.
- PASS: separate links permit one extraction for multiple raw records.

### vnstock Provenance Persistence

- PASS: one story for two tickers produced equal `article_id`/`revision_id`, distinct `provenance_id`/`raw_record_id`, retained ticker/exchange/universe: `PROVENANCE_SPLIT True True True True`.
- PASS: identity bindings are recomputed at `src/omega/data/macro_news_pipeline.py:390`.

## Blocking Findings

1. **Mutable universe TOCTOU** - `scripts/run_macro_news_pipeline.py:73` validates one version; line 77 can accept another. Violates `.ly_state/session/implementation_plan_macro_news_v2.md:159`.
2. **Ineffective vnstock timeout** - `src/omega/data/macro_news_pipeline.py:298` has no enforced deadline. Line 299 checks only after return. A 10 ms timeout around a 150 ms fake call returned after the delay: `TIMEOUT_POST_HOC True`.
3. **Cutoff continues pagination** - `src/omega/data/macro_news_pipeline.py:307` exits only the row loop. Lines 312-314 request older pages. Probe: `CUTOFF_CONTINUES_PAGING [None, 'page2']`.

## Required Remediation

1. Read once; validate exact bytes before imports/network; pass immutable snapshot without reopening. Add replacement-between-stages regression.
2. Enforce a real cancellable vnstock deadline. Add hanging-call regression.
3. Stop ticker pagination immediately at cutoff. Assert no next-page call.

## Modified Scope Files Reviewed

- `scripts/run_macro_news_pipeline.py`
- `src/omega/data/macro_news_pipeline.py`
- `tests/test_macro_news_pipeline.py`

Worktree has extensive unrelated changes. Attribution remains limited to L2 fix6 scope and approved integration checks.

## Exact Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/agent/data-engineer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/implementation_plan_macro_news_v2.md`
- `.ly_state/session/l2_role15_macro_news_pipeline_fix6_20260813.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_audit_fix5.md`
- `.ly_state/session/phase_gates.json`
- `config/macro_news_sources.json`
- `scripts/run_macro_news_pipeline.py`
- `src/omega/data/macro_news_pipeline.py`
- `src/omega/data/macro_news_llm.py`
- `tests/test_macro_news_pipeline.py`
- `tests/test_macro_news_llm.py`

Only required role skills under `.agents/skills` were authoritative.

## Forbidden Path Scan

- Scope: three L2 files above.
- Patterns: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.
- Result: zero matches. No forbidden path opened, written, or used as authority. Policy/evidence files contain declarations only.

## Verdict

[NEEDS_FIX]
