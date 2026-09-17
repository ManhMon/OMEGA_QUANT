# Macro News Pipeline v8 Plan Re-Audit

- Verdict: `[NEEDS_FIX]`
- Date: `2026-08-13T23:58:21+07:00`
- Scope: `.ly_state/session/implementation_plan_macro_news_v8.md`
- L2 Session: `.ly_state/session/implementation_plan_macro_news_v8.md`
- L2 Role: `26 planning-architect`
- L3 Session ID: `role21_macro_news_pipeline_plan_v8_reaudit_20260813`
- L3 Session Key: `role21_macro_news_pipeline_plan_v8_reaudit_20260813`
- L3 Role: `21 code-reviewer`
- Submission SHA-256: `A5CEB6DA0B6343F58882975ABECF335EF5C5A22FA7900A459AC5D550FC6C1CAA`
- REPO_AGENT_ROOT: `.agents/agent`
- REPO_SKILL_ROOT: `.agents/skills`

## Audit Evidence Checklist

1. **Writer/auditor separation - PASS.** `l2_role_id=26` differs from `l3_role_id=21`. Role 26 is planning-only; role 21 is independent audit-only.
2. **Approved scope - PASS.** The v7-to-v8 revision is limited to the two v7 audit blockers: canonical article-fragment identity and Vietnam civil-date normalization. This audit writes only this report and the `MACRO_NEWS_PIPELINE_plan` gate entry. Unrelated worktree changes remain untouched.
3. **All tests - PASS.** `python -m pytest` completed with `3261 passed, 3 skipped, 864 warnings` in `195.57s`, exit `0`.
4. **PIT safety - PASS.** The plan requires source-invariant revision identity, immutable first receipt, strictly following tradable-session availability, local cutoff application, raw-before-LLM persistence, and `Asia/Ho_Chi_Minh` civil-date normalization before `.date()`.
5. **SOD boundaries - PASS.** Role 26 authored only the plan. Role 21 modifies only this audit report and target gate metadata. No production or test file is modified.
6. **L2 repo-local skill evidence - PASS.** `.ly_state/session/implementation_plan_macro_news_v8.md:453` lists `.agents/agent/planning-architect.md` and all four declared skills under `.agents/skills`; `.ly_state/session/implementation_plan_macro_news_v8.md:472` records the forbidden-path scan and exclusive repo-local authority.

## Contract Verification

- **SBV interest identification - PASS.** Exact official SBV article/PDF, publication date `2026-08-05`, observation period `2026-07-27..2026-07-31`, overnight measure, selected-fragment identity, and PDF identity are specified. No invented daily rows or source substitution.
- **SBV exchange-rate identification - PASS.** Exact SBV bootstrap/API, structure `137473`, parameters `page`, `pageSize=100`, `sort=datePublished:desc`, and numeric authority `TyGiaSo` are specified. Yahoo/Vietcombank substitution is forbidden.
- **Vnstock parameters - PASS.** Pinned `vnstock==4.0.4` VCI exposes `news(self) -> DataFrame`. The plan correctly requires one zero-argument `.news()` call per ticker, then deterministic local filtering, sorting, dedupe, and caps.
- **Serializer syntax - PASS.** Executable self-check confirms `separators=(',', ':')`, `ensure_ascii=False`, UTF-8 encoding, exact-byte SHA-256, and dispatch of the same `body_bytes` object.
- **Article hashing - PASS.** Full navigation bytes are transport evidence only. Exact one-match selected-container `outerHTML`, UTF-8 encoded once, supplies canonical hash, parser input, fixture identity, and revision evidence.
- **Civil-date normalization - PASS.** Offset-bearing values convert through `ZoneInfo('Asia/Ho_Chi_Minh')` before `.date()`. Regression confirms `2026-08-12T17:00:00Z` becomes `2026-08-13`.
- **WAF transport - NEEDS_FIX.** Both exact same-context request paths returned WAF rejection HTML instead of required PDF/JSON payloads.

## Blocking Finding

1. **P1 - The binding SBV WAF transport is not viable.** `.ly_state/session/implementation_plan_macro_news_v8.md:126`, `.ly_state/session/implementation_plan_macro_news_v8.md:167`, `.ly_state/session/implementation_plan_macro_news_v8.md:334`, `.ly_state/session/implementation_plan_macro_news_v8.md:335`, and `.ly_state/session/implementation_plan_macro_news_v8.md:433` require `BrowserContext.request.get(...)` in the article/bootstrap context and prohibit another acquisition path. A bounded live check navigated the exact interest article with HTTP `200`, received `533458` full-body bytes, found exactly one declared fragment, and reproduced fragment bytes/hash `53401` / `578222ef0273085312816f57a45c4a84834dea0abd4f829897502037ba9e8234`. The exact PDF request then returned HTTP `200`, MIME `text/html`, `246` bytes, and `Request Rejected`, not the registered `215439`-byte PDF. A separate bounded check navigated the exact FX bootstrap with HTTP `200`; the exact API request with `page=1`, `pageSize=100`, `sort=datePublished:desc`, same context, `Referer`, and JSON `Accept` likewise returned HTTP `200`, MIME `text/html; charset=utf-8`, `246` bytes, and `Request Rejected`. The mandated path cannot satisfy PDF signature/hash or JSON envelope validation and would emit zero rows for both official SBV sources.

## Required Actions

1. Replace the binding PDF and structured-content request contracts with acquisition paths empirically proven to return the exact official PDF bytes and JSON envelope under the stated clean, bounded runtime conditions.
2. Specify every required browser action, cookie/token/header dependency, redirect rule, and source-identity check. Retain exact official URLs, fail-closed behavior, bounded resources, and no unreviewed mirror/substitution.
3. Add fixture tests for the revised transport contract plus a bounded live acceptance smoke that verifies PDF MIME/signature/hash and FX JSON MIME/envelope before implementation approval.
4. Re-run plan checks and resubmit for independent review.

## Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/agent/planning-architect.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/implementation_plan_macro_news_v7.md`
- `.ly_state/session/implementation_plan_macro_news_v8.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan_v7_reaudit_20260813.md`
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
- `tests/quant_test_infinite_evolution.py`
- `scripts/sod_gate_enforcer.py`

## Forbidden Path Scan

- Forbidden paths: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.
- Result: zero forbidden filesystem content reads, zero forbidden authoritative reliance, zero forbidden writes.
- Repo-local text matches are explicit policy/evidence mentions only. No Antigravity scratch, OpenClaw skill, user-level `.agents`, or Codex memory content was opened or used.

## Verdict

`[NEEDS_FIX]`

Source identification, Vnstock parameters, serializer syntax, canonical article hashing, civil-date normalization, PIT rules, tests, and SOD checks pass. The exact binding WAF transport fails against both official SBV payload endpoints and blocks approval.
