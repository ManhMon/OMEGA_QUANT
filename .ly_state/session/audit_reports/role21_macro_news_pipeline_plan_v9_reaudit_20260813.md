# Macro News Pipeline v9 Plan Re-Audit

- Verdict: `[NEEDS_FIX]`
- Date: `2026-08-13T18:52:17Z`
- Scope/L2 session: `.ly_state/session/implementation_plan_macro_news_v9.md`
- L2 role: `26 planning-architect`
- L3 session: `role21_macro_news_pipeline_plan_v9_reaudit_20260813`
- L3 role: `21 code-reviewer`
- Submission SHA-256: `7B4DC2B8C3812998387696FC3FFB3E1416C6509DA53A6F69C2BDED7BDF4E075B`
- Skill roots: `.agents/agent`, `.agents/skills`

## Audit Evidence Checklist

1. **Writer/auditor separation - PASS.** `l2_role_id=26 != l3_role_id=21`. Role 26 is planning-only/non-audit; role 21 is independent audit-only.
2. **Approved scope - PASS.** The v8-to-v9 revision addresses the approved WAF transport blocker. This audit changes only this report and the `MACRO_NEWS_PIPELINE_plan` gate entry. Unrelated worktree changes remain untouched.
3. **All tests - PASS.** `python -m pytest`: `3261 passed, 3 skipped, 864 warnings in 195.87s`, exit `0`. The existing `.pytest_cache` creation warning was non-fatal.
4. **PIT safety - PASS.** Receipt time is excluded from revision identity; reruns retain immutable first receipt; availability begins on the strictly following tradable session after delay; raw persistence precedes LLM work; SBV timestamps convert through `Asia/Ho_Chi_Minh` before `.date()`.
5. **SOD boundaries - PASS.** Role 26 authored only the plan. Role 21 changes only audit metadata/artifacts. Writer and auditor remain separated.
6. **L2 repo-local skill evidence - PASS.** The L2 report lists `.agents/agent/planning-architect.md` and its four declared skills under `.agents/skills`, plus exclusive repo-local authority and forbidden-path scan evidence.

## Contract Verification

- **SBV interest identification - PASS.** Exact official article/PDF URLs, publication date `2026-08-05`, period `2026-07-27..2026-07-31`, overnight-only measure, selected-fragment identity, and exact PDF identity are specified. No substitution or invented daily rows.
- **SBV interest WAF transport - PASS.** Live Chromium `151.0.7922.34` returned article HTTP `200`; the unique fragment was `53401` bytes, SHA-256 `578222ef0273085312816f57a45c4a84834dea0abd4f829897502037ba9e8234`. Response-stage CDP `Fetch` captured the clicked PDF: HTTP `200`, `application/pdf`, `215439` bytes, `%PDF-1.5`, SHA-256 `b003b92e4795cbd70da5d7eb8ae4a089b1436e2df14c575765f1fb442380f475`.
- **SBV exchange-rate identification - PASS.** Exact bootstrap/API, structure `137473`, parameters `page`, `pageSize=100`, `sort=datePublished:desc`, and numeric authority `TyGiaSo` are explicit. Yahoo/Vietcombank substitution is forbidden.
- **SBV exchange-rate WAF transport - NEEDS_FIX.** Exact `page.expect_response` captured HTTP `200`, `application/json`, method `GET`, resource type `fetch`. With the required no-JavaScript-body-consumption path, Playwright `Response.body()` timed out after the full `30`-second contract deadline. Adding only renderer `await response.arrayBuffer()` made Playwright `Response.body()` return the exact `366668` bytes. The plan requires both no renderer body consumption and successful Playwright body capture; the pinned runtime cannot satisfy both.
- **Vnstock parameters - PASS.** Installed `vnstock==4.0.4` accepts `Company(symbol=ticker, source='VCI')`. The plan requires one `.news()` call without arguments per ticker, then deterministic local filtering, sorting, dedupe, and caps.
- **Exact source identity - PASS.** Canonical fragment/PDF hashes identify interest data; stable SBV provider/item fields identify FX revisions; per-ticker VCI provenance remains physical identity; URL-only identity is forbidden.

## Blocking Finding

1. **P1 - The binding FX body-capture contract deadlocks before canonical bytes exist.** `.ly_state/session/implementation_plan_macro_news_v9.md:177` and `.ly_state/session/implementation_plan_macro_news_v9.md:178` require same-origin renderer `fetch`, `page.expect_response`, and canonical bytes from Playwright `Response.body()` within one `30`-second deadline. `.ly_state/session/implementation_plan_macro_news_v9.md:386` additionally forbids JavaScript body consumption. A bounded live reproduction on the pinned browser reached bootstrap HTTP `200`, renderer HTTP `200`, captured HTTP `200`, resource type `fetch`, and JSON MIME, then `Response.body()` timed out after `30` seconds. A control run adding only `await response.arrayBuffer()` in the renderer completed; Playwright then returned the body. The v9 fake/spy enforces the non-working behavior, so the mandatory live smoke cannot pass as specified.

## Required Actions

1. Permit and specify a renderer-side drain such as `await response.arrayBuffer()` while retaining Playwright `Response.body()` as the sole canonical Python payload, or replace FX body acquisition with another empirically proven exact-byte interception contract.
2. Update the FX fake/spy to verify the drain, exact `page.expect_response` match, canonical Playwright bytes, timeout, cleanup, and no JavaScript-returned JSON/byte payload.
3. Run the mandatory live pages `1` and `2` smoke with the exact production sequence; both bodies and envelopes must complete inside the declared deadline.
4. Resubmit the corrected plan for independent review.

## Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/agent/planning-architect.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/implementation_plan_macro_news_v8.md`
- `.ly_state/session/implementation_plan_macro_news_v9.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan_v8_reaudit_20260813.md`
- `.ly_state/session/phase_gates.json`
- `requirements.txt`

The repository-root `AGENTS.md` redirect was supplied in the task context and was not reopened from disk. Installed `vnstock` and Playwright metadata/runtime are outside the repository and were used only to validate declared pinned APIs and transport behavior.

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: absent; content reads `0`; writes `0`; authoritative reliance `0`.
- `C:\Users\GHC\.openclaw\skills`: exists; content reads `0`; writes `0`; authoritative reliance `0`.
- `C:\Users\GHC\.agents`: exists; content reads `0`; writes `0`; authoritative reliance `0`.
- `C:\Users\GHC\.codex\memories`: exists; content reads `0`; writes `0`; authoritative reliance `0`.
- Result: **PASS.** Only repo-local role and skill sources were authoritative. No forbidden content was opened, used, or modified.

## Verdict

`[NEEDS_FIX]`

Source identification, SBV interest CDP transport, Vnstock parameters, PIT rules, tests, scope, and SOD checks pass. The exact binding SBV FX `page.expect_response`/`Response.body()` contract is contradictory and times out on the pinned runtime.
