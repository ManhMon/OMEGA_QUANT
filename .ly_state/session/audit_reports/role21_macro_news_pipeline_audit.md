# Code Review Audit Report
**Role**: Code Reviewer (Role 21)
**Date**: 2026-08-12T18:39:23+07:00
**Gate**: MACRO_NEWS_PIPELINE_code
**L2 Session**: `.ly_state/session/l2_role9_macro_news_pipeline_20260812.md`
**L2 Identity Requested**: data-engineer (Role 9)
**L3 Session**: `role21_macro_news_pipeline_audit`
**L3 Session Key**: `role21_macro_news_pipeline_audit`
**Approved Plan**: `.ly_state/session/implementation_plan_macro_news_v2.md`

## Repo-Local Files Read
- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/agent/data-engineer.md`
- `.agents/agent/backend-engineer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/l2_role9_macro_news_pipeline_20260812.md`
- `.ly_state/session/implementation_plan_macro_news_v2.md`
- `.ly_state/session/phase_gates.json`
- `config/macro_news_sources.json`
- `requirements.txt`
- `scripts/run_macro_news_pipeline.py`
- `src/omega/core/llm_config.py`
- `src/omega/data/macro_news_pipeline.py`
- `src/omega/data/macro_news_llm.py`
- `src/omega/factors/llm_alpha.py`
- `src/omega/integration/llm_alpha.py`
- `tests/test_macro_news_pipeline.py`
- `tests/test_macro_news_llm.py`
- `tests/test_hybrid_alpha_real_market.py`

## Forbidden Path Scan
- Result: 21 textual matches, confined to repo-local protocol/skill documents and the L2 report's explicit non-authoritative evidence.
- No Antigravity scratch, OpenClaw, global `C:\Users\GHC\.agents`, or Codex memory path was read or relied on as role/skill authority.
- No scoped production source used a forbidden authority path.

## Audit Evidence Checklist
- [x] Numeric writer/auditor separation: requested `l2_role_id=9` differs from `l3_role_id=21`.
- [ ] SOD identity validity: `.agents/agent/data-engineer.md:4` declares Role 15; `.agents/agent/backend-engineer.md:4` declares Role 9. Requested `9 data-engineer` is invalid.
- [ ] Scope conformity: `requirements.txt:1` contains unrelated dependency additions and pins beyond required `vnstock==4.0.4`.
- [x] L3 boundary: no production or test code changed; only this report and named gate entry written.
- [x] Focused validation: plan-focused pytest selection exited 0 with 87 passed.
- [x] Full validation: `python -m pytest -q` exited 0; all collected tests passed, 3 skipped.
- [x] Compilation: scoped Python compilation exited 0.
- [x] Whitespace: `git diff --check` reported only three unrelated pre-existing EOF failures.
- [ ] PIT safety: upper `as_of` filtering and strict UTC universe timestamps are not enforced.
- [x] L2 evidence lists repo-local role/skill paths and forbidden-path result; requested role metadata conflicts with authority.

## Required Checks

### 1. PIT Universe Integration
Partial implementation; blocking PIT defects remain.

- PASS: explicit universe input, session-path rejection, lifecycle checks, exact-byte SHA-256, ticker/exchange/universe provenance.
- FAIL: `src/omega/data/macro_news_pipeline.py:62` interprets naive timestamps as Vietnam time; plan requires timezone-aware UTC.
- FAIL: `src/omega/data/macro_news_pipeline.py:165` accepts only cutoff; line 178 admits records newer than `as_of`.
- FAIL: static sources at `src/omega/data/macro_news_pipeline.py:193` receive neither cutoff nor `as_of`.
- FAIL: `scripts/run_macro_news_pipeline.py:49` omits universe lifecycle fields and per-exchange counts.

### 2. Source-Invariant LLM Caching
Request construction is source-invariant, but cache integrity fails closed requirements.

- PASS: provenance-only changes produce identical canonical request bytes and `request_sha256`.
- FAIL: `src/omega/data/macro_news_llm.py:56` loads persisted cache rows without schema validation; line 57 indexes only by stored `extraction_id`; line 61 trusts a hit without verifying persisted request hash, provider, or endpoint.
- Reproduction: a corrupted cached row caused zero HTTP calls while retaining mismatched extraction/link hashes. The approved plan requires corruption to fail closed.
- FAIL: `src/omega/data/macro_news_llm.py:62` has no bounded retry or response-size limit.
- FAIL: `src/omega/data/macro_news_llm.py:66` writes both sidecars directly, without schema/FK validation, fixed-order writer locks, or atomic replacement.

### 3. vnstock Provenance Persistence
Core provenance identity behavior passes.

- PASS: two tickers returning the same provider story produced one article, one revision, two provenance IDs, two raw IDs, and the exact universe hash.
- FAIL: schema-v1 migration at `src/omega/data/macro_news_pipeline.py:215` reconstructs records without preserving legacy `available_at`; the audit probe changed `02:00` to synthesized `00:15`.
- FAIL: raw persistence at `src/omega/data/macro_news_pipeline.py:205` has atomic replacement but no exclusive writer lock.

## Additional Blocking Findings

### Source Registry and Health
- `config/macro_news_sources.json:1` contains six entries, not the required current ten-source baseline plus every evaluated candidate.
- No complete per-source health contract exists. Required `vcbs_research` uses the generic parser at `src/omega/data/macro_news_pipeline.py:152`, not the approved source-specific listing/detail/PDF path.
- `src/omega/data/macro_news_pipeline.py:198` silently skips HTTP failures. Required VCBS failure can exit successfully and produce an untruthful manifest.

### CLI Manifest
- `scripts/run_macro_news_pipeline.py:49` lacks source statuses/counts/durations, inserted/skipped/revised counts, extraction/cache/link statistics, retrospective extraction, sanitized runtime summary, universe lifecycle metadata, and per-exchange counts.

### Runtime Parity
- Shared alpha wrappers correctly delegate to `src/omega/core/llm_config.py:32`.
- Current sanitized runtime probe resolves model `cx/gpt-5.5`, not approved acceptance value `cx/gpt-5.6-terra`.

### Scope Attribution
- Worktree contains 5,783 dirty paths; most declared implementation files are untracked. Exact L2 authorship cannot be established from Git state. Audit reviewed the L2-declared scope directly.

## Required Remediation
1. Correct L2 identity: authoritative `data-engineer` is Role 15; Role 9 is `backend-engineer`. Regenerate consistent session/gate metadata.
2. Enforce UTC-aware universe timestamps and `cutoff <= published_at <= as_of` for vnstock and every static source.
3. Preserve the ten-source baseline, evaluate every planned candidate, implement truthful source health, and fail non-zero for required-source failure after raw persistence.
4. Validate cache rows against recomputed request/provider/endpoint identity; add strict sidecar schemas, FK checks, bounded retries, response limits, locks, and atomic replacement.
5. Preserve exact legacy `available_at` during v1 migration; add an exclusive raw-store writer lock.
6. Complete the manifest contract; remove unrelated `requirements.txt` changes.
7. Reconcile the effective model with the approved acceptance criterion, or amend the plan through a separate planning gate.

## Verdict
[NEEDS_FIX]
