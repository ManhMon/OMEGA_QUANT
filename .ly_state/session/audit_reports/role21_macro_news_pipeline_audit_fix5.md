# Code Review Audit Report

**Verdict**: [NEEDS_FIX]
**Role**: 21 `code-reviewer`, Codex L3 independent review
**Date**: 2026-08-13T12:47:31+07:00
**Gate**: `MACRO_NEWS_PIPELINE_code`
**L2 Session**: `.ly_state/session/l2_role15_macro_news_pipeline_fix5_20260813.md`
**L2 Identity**: Role 15 `data-engineer`
**L3 Session**: `role21_macro_news_pipeline_audit_fix5`
**Approved Plan**: `.ly_state/session/implementation_plan_macro_news_v2.md`

## Result

Source-invariant LLM caching passes. vnstock one-article/many-provenance persistence passes. The checked-in registry is unusable. Required PIT fail-before-import/network behavior fails. Persisted identities are shape-checked but not recomputed. vnstock registry controls are ignored.

## Audit Checklist

- [x] SoD: `l2_role_id=15`; `l3_role_id=21`; `15 != 21`.
- [x] Repo-local frontmatter confirms Role 15 `data-engineer`, Role 21 `code-reviewer`.
- [x] L2 fix5 files remain within approved remediation scope.
- [ ] Approved behavior: blocking plan deviations remain.
- [x] Targeted tests: `98 passed`.
- [x] Full `python -m pytest -q`: exit `0`; 3 skipped; warnings only.
- [x] Scoped compilation and `git diff --check` passed.
- [ ] PIT safety: universe parsing/window checks pass; fail-before-import/network fails.
- [x] L3 boundary: no production/test code changed; report plus named gate only.
- [x] L2 report lists repo-local skill sources.
- [x] Missing `ruff` or lint failure was not a rejection reason.

## Required Checks

### PIT Universe Integration

- PASS: explicit universe parsing, exact-byte SHA-256, lifecycle/window validation, membership filtering, and copied ticker/exchange/universe provenance.
- FAIL: `scripts/run_macro_news_pipeline.py:40` imports `omega.data.macro_news_pipeline` before universe validation at `scripts/run_macro_news_pipeline.py:42`. Probe: `VNSTOCK_IMPORTED_BEFORE_UNIVERSE_VALIDATION True`.
- FAIL: registry DNS resolution at `src/omega/data/macro_news_pipeline.py:206` also precedes universe validation.

### Source-Invariant LLM Caching

- PASS: provenance-only changes preserve request bytes/hash and endpoint/extraction identity. Probe: `SOURCE_INVARIANT True`.
- PASS: extraction/link sidecars, evidence validation, duplicate rejection, cache reuse, and link repair.

### vnstock Provenance Persistence

- PASS: two ticker-source rows produced 2 raw rows, 1 `article_id`, 1 `revision_id`, 2 `provenance_id` values, and 2 `raw_record_id` values; ticker/exchange/universe fields persisted.
- FAIL: `src/omega/data/macro_news_pipeline.py:376` accepts tampered valid-looking identity hashes without recomputing their bindings. Probe: `INVALID_IDENTITIES_ACCEPTED`.

## Blocking Findings

1. `config/macro_news_sources.json:2` correctly uses nullable `discovery_url` for required `vnstock_vci`; `src/omega/data/macro_news_pipeline.py:202` rejects every enabled nullable URL. Default-registry probe: `ValueError: invalid macro source registry controls`.
2. `scripts/run_macro_news_pipeline.py:40` imports `omega` before universe validation. Eager package imports in `src/omega/__init__.py:5` and `src/omega/data/__init__.py:4` defeat the intended lazy vnstock boundary.
3. `src/omega/data/macro_news_pipeline.py:206` performs DNS work before PIT universe acceptance.
4. `src/omega/data/macro_news_pipeline.py:376` validates hash syntax, not `content_hash`, `article_id`, `revision_id`, `provenance_id`, and `raw_record_id` derivations.
5. `scripts/run_macro_news_pipeline.py:45` applies only CLI `max_articles`. Registry paging, pacing, timeout, and delay controls are ignored; defaults/hard-coded values remain at `src/omega/data/macro_news_pipeline.py:277`, `src/omega/data/macro_news_pipeline.py:290`, `src/omega/data/macro_news_pipeline.py:298`, and `src/omega/data/macro_news_pipeline.py:300`.

## Additional Safety Gaps

- `src/omega/data/macro_news_pipeline.py:141` reads full `response.content` before the byte-cap check.
- `src/omega/data/macro_news_pipeline.py:236` uses raw hostname suffix matching instead of the allowlist helper.

## Required Remediation

1. Permit nullable `discovery_url` only for the validated vnstock kind/adapter.
2. Validate universe without importing `omega`; import adapters and perform DNS/network work afterward.
3. Recompute persisted identities/hashes from bound normalized fields.
4. Pass and enforce vnstock registry paging, item, pacing, timeout, and delay controls.
5. Stream bounded responses; use canonical hostname allowlisting.
6. Add checked-in-registry regressions for every reproduced failure.

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

The worktree contains unrelated staged, unstaged, and untracked changes. Review covered the L2-declared fix5 files plus all approved-plan integration files; Git state cannot independently attribute every dirty file to this L2 session.

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
- `.ly_state/session/l2_role15_macro_news_pipeline_fix4_20260812.md`
- `.ly_state/session/l2_role15_macro_news_pipeline_fix5_20260813.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_audit_fix4.md`
- `.ly_state/session/phase_gates.json`
- `config/macro_news_sources.json`
- `requirements.txt`
- `scripts/run_hybrid_alpha_evolution.py`
- `scripts/run_macro_news_pipeline.py`
- `src/omega/__init__.py`
- `src/omega/core/__init__.py`
- `src/omega/core/llm_config.py`
- `src/omega/data/__init__.py`
- `src/omega/data/macro_news_llm.py`
- `src/omega/data/macro_news_pipeline.py`
- `src/omega/data/macro_pipeline.py`
- `src/omega/data/news_aggregator.py`
- `tests/test_hybrid_alpha_real_market.py`
- `tests/test_macro_news_llm.py`
- `tests/test_macro_news_pipeline.py`
- `tests/test_news_aggregator.py`
- `tests/test_news_aggregator_scrapers.py`

Only required role skills under `.agents/skills` were authoritative.

## Forbidden Path Scan

- Patterns: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.
- Result: zero matches across the 14 reviewed implementation, config, dependency, and test files.
- Policy/evidence files contain declarations and prior scan results only; 26 textual matches were observed in that evidence scan.
- No forbidden path was opened, written, or used as role/skill authority.

## Verdict

[NEEDS_FIX]
