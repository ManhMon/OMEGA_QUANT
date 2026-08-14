# Macro News Pipeline v10 Plan Re-Audit

- Verdict: `[NEEDS_FIX]`
- Date: `2026-08-13T19:52:10Z`
- Scope/L2 session: `.ly_state/session/implementation_plan_macro_news_v10.md`
- L2 role: `26 planning-architect`
- L3 session: `role21_macro_news_pipeline_plan_v10_reaudit_20260813`
- L3 role: `21 code-reviewer`
- Submission SHA-256: `D9603EC4D280124E4F627F561E28CBB3DF2D431549CF8E2FF7D8AAE852801A4F`
- Authoritative roots: `.agents/agent`, `.agents/skills`

## Audit Evidence Checklist

1. **Writer/auditor separation - PASS.** `l2_role_id=26 != l3_role_id=21`; planning author and independent reviewer are distinct.
2. **Approved scope - PASS.** v10 changes the approved macro-news plan only, primarily correcting the v9 SBV FX response-drain contract. This audit changes only its report and the `MACRO_NEWS_PIPELINE_plan` gate entry. Unrelated worktree changes remain untouched.
3. **All tests - PASS.** `python -m pytest`: `3261 passed, 3 skipped, 864 warnings in 197.74s`, exit `0`.
4. **PIT safety - PASS.** Revision identity excludes receipt time; first receipt remains immutable; source timestamps normalize through `Asia/Ho_Chi_Minh`; availability begins on the strictly following tradable session after delay; raw evidence precedes LLM work.
5. **SOD boundaries - PASS.** Role 26 authored planning only. Role 21 performed review and writes only audit/gate artifacts. No production implementation was modified.
6. **L2 repo-local skill evidence - PASS.** The plan lists `.agents/agent/planning-architect.md`, its four declared `.agents/skills/*/SKILL.md` files, repo-local authority, and forbidden-path scan evidence.

## Contract Verification

- **SBV interest rates - PASS.** Exact official article/PDF, publication/period/overnight semantics, selected-container identity, PDF identity, and fail-closed parsing are binding. Live evidence captured the `53401`-byte fragment, SHA-256 `578222ef0273085312816f57a45c4a84834dea0abd4f829897502037ba9e8234`, then the exact `215439`-byte PDF through response-stage CDP `Fetch`, SHA-256 `b003b92e4795cbd70da5d7eb8ae4a089b1436e2df14c575765f1fb442380f475`.
- **SBV exchange rates - PASS.** Exact SBV bootstrap/API, `contentStructureId=137473`, `page`, `pageSize=100`, `sort=datePublished:desc`, stable provider/item fields, and numeric `TyGiaSo` authority are binding. Yahoo/Vietcombank substitution is forbidden.
- **SBV FX WAF transport - PASS.** Live pages `1` and `2` completed: pre-registered `page.expect_response`, same-origin renderer fetch, awaited/discarded `response.arrayBuffer()` drain, `null` renderer return, canonical Playwright `Response.body()` bytes. Status, JSON MIME, request method/resource type, query, envelope, and cleanup checks passed.
- **Exact source identification - PASS.** Interest fragment/PDF hashes, stable SBV FX provider/item identity, per-ticker VCI provenance, and source-specific canonical evidence replace URL-only identity.
- **Vnstock parameters - NEEDS_FIX.** The pinned package requires provider string `source='VCI'`; two binding implementation statements instead use undefined bare identifier `source=VCI`.

## Blocking Finding

1. **P1 - Two binding Vnstock constructor specifications are invalid.** `.ly_state/session/implementation_plan_macro_news_v10.md:89` and `.ly_state/session/implementation_plan_macro_news_v10.md:290` require `Company(symbol=ticker, source=VCI)`. Pinned `vnstock==4.0.4` does not export a `VCI` identifier; the supported constructor argument is the string `source='VCI'`. The plan's own fake/spy contract already specifies the correct form at `.ly_state/session/implementation_plan_macro_news_v10.md:406`. An implementer following either binding statement would produce an unresolved name rather than the required provider value.

## Required Actions

1. Replace `source=VCI` with `source='VCI'` at lines `89` and `290`.
2. Keep the already-correct acceptance contract at line `406` unchanged.
3. Resubmit the corrected plan for independent review.

## Explicit Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/agent/planning-architect.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/implementation_plan_macro_news_v9.md`
- `.ly_state/session/implementation_plan_macro_news_v10.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan_v9_reaudit_20260813.md`
- `.ly_state/session/phase_gates.json`
- `requirements.txt`

The repository-root `AGENTS.md` redirect was supplied in task context and was not reopened from disk. Installed `vnstock` and Playwright metadata/runtime were used only to verify the pinned API and live WAF transport; they supplied no authoritative role, skill, or business-source contract. Test-run imports are not counted as explicit audit content reads.

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: absent; content reads `0`; writes `0`; authoritative reliance `0`.
- `C:\Users\GHC\.openclaw\skills`: exists; content reads `0`; writes `0`; authoritative reliance `0`.
- `C:\Users\GHC\.agents`: exists; content reads `0`; writes `0`; authoritative reliance `0`.
- `C:\Users\GHC\.codex\memories`: exists; content reads `0`; writes `0`; authoritative reliance `0`.
- Result: **PASS.** No forbidden path content was opened, used, or modified. Only repo-local role and skill sources were authoritative.

## Verdict

`[NEEDS_FIX]`

SBV interest and FX identification, CDP `Fetch`, `page.expect_response`, renderer `response.arrayBuffer()` drain, canonical Playwright `Response.body()`, PIT safety, full tests, scope, SOD, and repo-local source evidence pass. Correct the two unquoted VCI provider arguments.
