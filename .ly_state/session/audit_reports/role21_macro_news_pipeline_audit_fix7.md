# Code Review Audit Report

**Verdict**: [NEEDS_FIX]
**Role**: 21 `code-reviewer`, Codex L3 independent review
**Date**: 2026-08-13T14:17:33+07:00
**Gate**: `MACRO_NEWS_PIPELINE_code`
**L2 Session**: `.ly_state/session/l2_role15_macro_news_pipeline_fix7_20260813.md`
**L2 Identity**: Role 15 `data-engineer`
**L3 Session**: `role21_macro_news_pipeline_audit_fix7`
**Approved Plan**: `.ly_state/session/implementation_plan_macro_news_v2.md`

## Result

Fix7 repairs the immutable PIT-universe handoff and cutoff pagination findings. Source-invariant LLM caching and vnstock provenance persistence also pass. Approval remains blocked because the new `ThreadPoolExecutor` timeout returns control without cancelling the running provider call, leaving the prior required real-cancellable-deadline remediation incomplete.

## Audit Checklist

- [x] SoD: `l2_role_id=15`; `l3_role_id=21`; `15 != 21`.
- [x] Scope: all three L2-declared files were reviewed and match the approved remediation scope.
- [ ] Approved behavior: one blocking timeout deviation remains.
- [x] Targeted macro-news suite: `26 passed`.
- [x] Approved five-file regression suite: exit `0`; 108 tests.
- [x] Full `python -m pytest -q`: exit `0`; 3 skipped; warnings only.
- [x] Focused PIT/cache/provenance/cutoff/timeout cases: `5 passed`.
- [x] Scoped `py_compile`: pass.
- [x] PIT safety: exact-byte universe handoff, interval checks, publication cutoff, source-delay availability, and no-look-ahead constraints pass.
- [x] L3 boundary: only this audit report and the named gate entry were changed.
- [x] L2 report lists repo-local role/skill source evidence.
- [x] Missing `ruff` and lint-stage failure were not rejection reasons.

## Required Checks

### PIT Universe Integration

- PASS: `scripts/run_macro_news_pipeline.py:44` reads the universe once before package import or network work.
- PASS: exact bytes are passed at `scripts/run_macro_news_pipeline.py:79` to `load_universe_snapshot`; the mutable path is not reopened.
- PASS: replacement-between-stages regression preserves the prevalidated `AAA` bytes.
- PASS: universe lifecycle, `cutoff <= as_of`, article publication, and source-delay eligibility prevent future-data admission.

### Source-Invariant LLM Caching

- PASS: `src/omega/data/macro_news_llm.py:54` canonicalizes only title, summary, and body text.
- PASS: source, URL, ticker, and raw-record provenance changes leave request bytes, `request_sha256`, and endpoint identity unchanged.
- PASS: identical content across two raw records performs one extraction and writes two links.

### vnstock Provenance Persistence

- PASS: one provider story for `AAA`/HSX and `BBB`/HNX produced one `article_id`, one `revision_id`, two `provenance_id` values, and two `raw_record_id` values.
- PASS: both rows retained exact ticker, exchange, universe ID, universe version, and universe hash provenance.
- PASS: identity bindings are recomputed during frame validation.

## Blocking Finding

1. **vnstock timeout does not cancel the provider call** - `src/omega/data/macro_news_pipeline.py:304` submits `Company.news` to a thread. On timeout, `future.cancel()` at line 308 cannot cancel a task already running, and `executor.shutdown(wait=False, cancel_futures=True)` at line 310 does not stop that thread. An adversarial event probe returned within the deadline but reported `PROVIDER_RUNNING_AFTER_RETURN True`. A permanently blocked provider can therefore retain a live worker and block clean process shutdown. This does not satisfy the Fix6 required remediation for a real cancellable vnstock deadline.

## Required Remediation

1. Execute the vnstock request behind a genuinely terminable boundary or enforce a provider-native transport deadline that stops the underlying call. Add a regression proving the provider worker is no longer alive after timeout, not only that `fetch()` returned quickly.

## Modified Scope Files Reviewed

- `scripts/run_macro_news_pipeline.py`
- `src/omega/data/macro_news_pipeline.py`
- `tests/test_macro_news_pipeline.py`

The shared worktree contains extensive unrelated changes. Attribution remains limited to the L2 Fix7 scope and approved macro-news integration checks.

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
- `.ly_state/session/l2_role15_macro_news_pipeline_fix7_20260813.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_audit_fix6.md`
- `.ly_state/session/phase_gates.json`
- `config/macro_news_sources.json`
- `scripts/run_macro_news_pipeline.py`
- `src/omega/data/macro_news_pipeline.py`
- `src/omega/data/macro_news_llm.py`
- `tests/test_macro_news_pipeline.py`
- `tests/test_macro_news_llm.py`

Only required role skills under `.agents/skills` were authoritative. No Antigravity scratch, OpenClaw, global `C:\Users\GHC\.agents`, or Codex-memory source was read or used as authority.

## Forbidden Path Scan

- Scope: `config/macro_news_sources.json`, `scripts/run_macro_news_pipeline.py`, `src/omega/data/macro_news_pipeline.py`, `src/omega/data/macro_news_llm.py`, `tests/test_macro_news_pipeline.py`, and `tests/test_macro_news_llm.py`.
- Patterns: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.
- Result: zero matches across all six macro-news files. The L2 report contains only its required textual non-use declarations.

## Verdict

[NEEDS_FIX]
