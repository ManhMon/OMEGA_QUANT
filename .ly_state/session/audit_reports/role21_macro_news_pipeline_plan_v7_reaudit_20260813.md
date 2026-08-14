# Macro News Pipeline v7 Plan Re-Audit

- Verdict: `[NEEDS_FIX]`
- Date: `2026-08-13T22:56:56+07:00`
- Scope: `.ly_state/session/implementation_plan_macro_news_v7.md`
- L2 Session: `.ly_state/session/implementation_plan_macro_news_v7.md`
- L2 Role: `26 planning-architect`
- L3 Session ID: `role21_macro_news_pipeline_plan_v7_reaudit_20260813`
- L3 Session Key: `role21_macro_news_pipeline_plan_v7_reaudit_20260813`
- L3 Role: `21 code-reviewer`
- Submission SHA-256: `97000845FF414DD3A50161ED8D64FD9EA44D88D2066A02C8C6DBDDD403D160A8`
- REPO_AGENT_ROOT: `.agents/agent`
- REPO_SKILL_ROOT: `.agents/skills`

## Audit Evidence Checklist

1. **Writer/auditor separation - PASS.** `l2_role_id=26` differs from `l3_role_id=21`. Role 26 is planning-only; role 21 is independent audit-only.
2. **Approved scope - PASS.** The v6-to-v7 submission changes only `.ly_state/session/implementation_plan_macro_news_v7.md`. This audit writes only this report and the `MACRO_NEWS_PIPELINE_plan` gate entry. Unrelated pre-existing worktree changes remain untouched.
3. **All tests - PASS.** `python -m pytest` completed with `3261 passed, 3 skipped, 864 warnings` in `195.70s`, exit `0`.
4. **PIT safety - NEEDS_FIX.** Revision, immutable first receipt, delayed next-session availability, local cutoff, and raw-before-LLM rules pass. SBV FX civil-date normalization remains under-specified: live `NgayBatDau=2026-08-12T17:00:00Z` represents `2026-08-13` in `Asia/Ho_Chi_Minh`; extracting the UTC date first would create a one-day error.
5. **SOD boundaries - PASS.** Role 26 authored only the plan. Role 21 writes only this audit report and target gate metadata. No production or test files were modified.
6. **L2 repo-local skill evidence - PASS.** `.ly_state/session/implementation_plan_macro_news_v7.md:436` lists `.agents/agent/planning-architect.md` and all four declared skills under `.agents/skills`; `.ly_state/session/implementation_plan_macro_news_v7.md:455` reports forbidden-source handling.

## Contract Verification

- **SBV interest source values - PASS.** Official SBV article and reviewed PDF identify publication date `2026-08-05`, observation range `2026-07-27..2026-07-31`, overnight rate `2.65`, PDF bytes/hash `215439` / `b003b92e4795cbd70da5d7eb8ae4a089b1436e2df14c575765f1fb442380f475`.
- **SBV interest byte identity - NEEDS_FIX.** The declared `53401` bytes / `578222ef0273085312816f57a45c4a84834dea0abd4f829897502037ba9e8234` identify the selected article container `outerHTML`, not navigation `Response.body()`.
- **SBV exchange-rate identity - PASS.** Exact bootstrap/API, structure `137473`, parameters `page`, `pageSize=100`, `sort=datePublished:desc`, numeric authority `TyGiaSo=25566`, document `333/TB-NHNN`, and `datePublished=2026-08-13T01:26:00Z` are correctly specified. Yahoo/Vietcombank substitution is forbidden.
- **Vnstock parameters - PASS.** Installed and pinned `vnstock==4.0.4`; VCI `Company.news` signature is `(self) -> DataFrame`. The plan requires exactly one zero-argument `.news()` call per ticker and local filtering, sorting, dedupe, and caps.
- **Serializer syntax - PASS.** `separators=(',', ':')`, `ensure_ascii=False`, and `.encode('utf-8')` execute. One `body_bytes` object supplies both SHA-256 and `requests.post(..., data=body_bytes)`.
- **WAF transport - PARTIAL.** One bounded non-persistent Playwright context, article navigation, same-context PDF/API requests, host/status/MIME bounds, source isolation, and `finally` closure are viable. Raw full-page hashing is not viable as the canonical article identity.

## Blocking Findings

1. **P1 - Full navigation response is wrongly bound to the stable article hash.** `.ly_state/session/implementation_plan_macro_news_v7.md:123`, `.ly_state/session/implementation_plan_macro_news_v7.md:348`, and `.ly_state/session/implementation_plan_macro_news_v7.md:416` require `Response.body()` as hash/parser authority, while `.ly_state/session/implementation_plan_macro_news_v7.md:137` expects `53401` bytes and SHA-256 `578222ef...8234`. Two bounded live fetches returned full bodies `533458` / `63896fbc2285eb6c0282e5dda36e9d705b22b5e1258fad99d822f89974543958` and `533460` / `05211db2f5dfd166a3b29c113cbe50f48994527bce7e0c7b3c318f49540720ca`. Both selected article containers remained exactly `53401` bytes / `578222ef...8234`. The planned registry check would reject valid live pages or create false revisions from dynamic shell bytes.
2. **P2 - SBV FX observation date lacks an explicit Vietnam civil-date rule.** `.ly_state/session/implementation_plan_macro_news_v7.md:186` says to use parsed `NgayBatDau`, but does not require conversion to `Asia/Ho_Chi_Minh` before date normalization. The source instant `2026-08-12T17:00:00Z` must become observation date `2026-08-13`, not `2026-08-12`.

## Required Actions

1. Separate transport/rejection evidence from canonical article bytes. Use full `Response.body()` only for bounded transport validation; define, hash, fixture, and parse the validated selected article container bytes.
2. Rename registry evidence to distinguish full response from canonical article fragment. Add repeat-fetch coverage proving dynamic page-shell variance does not create false source revisions while selected-article drift fails closed.
3. Require `NgayBatDau`, `NgayKetThuc`, and `NgayBanHanh` conversion to `Asia/Ho_Chi_Minh` before civil-date extraction. Add the exact `2026-08-12T17:00:00Z` to `2026-08-13` regression.
4. Re-run plan checks; resubmit for independent review.

## Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/agent/planning-architect.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/implementation_plan_macro_news_v6.md`
- `.ly_state/session/implementation_plan_macro_news_v7.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan_v6_reaudit_20260813.md`
- `.ly_state/session/phase_gates.json`
- `requirements.txt`
- `config/macro_news_sources.json`
- `src/omega/data/macro_pipeline.py`
- `src/omega/data/macro_news_pipeline.py`
- `src/omega/data/macro_news_llm.py`
- `src/omega/core/llm_config.py`
- `tests/test_macro_pipeline.py`
- `tests/test_macro_news_pipeline.py`
- `tests/test_macro_news_llm.py`
- `scripts/sod_gate_enforcer.py`
- `scripts/sod_report_evidence.py`

Existence-only check: `config/sbv_interbank_sources.json` is absent; no content was read.

## Forbidden Path Scan

- Forbidden paths: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.
- Path-access audit: zero forbidden content reads, zero forbidden writes, zero authoritative reliance.
- Repo-local text scan found only explicit policy/evidence mentions in authoritative repo-local instructions, plans, gate metadata, and enforcement scripts. No forbidden path was opened.

## Verdict

`[NEEDS_FIX]`

SBV/Vnstock identities, serializer syntax, and bounded WAF session design pass. Dynamic full-page hashing and SBV FX civil-date ambiguity block approval.
