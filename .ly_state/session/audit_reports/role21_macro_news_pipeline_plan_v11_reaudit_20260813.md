# Macro News Pipeline v11 Plan Re-Audit

- Verdict: `[NEEDS_FIX]`
- Date: `2026-08-13`
- Scope/L2 session: `.ly_state/session/implementation_plan_macro_news_v11.md`
- L2 role: `26 planning-architect`
- L3 session: `role21_macro_news_pipeline_plan_v11_reaudit_20260813`
- L3 role: `21 code-reviewer`
- Submission SHA-256: `F1B37BEF0AA10BEE35325CB720AC3768800ED68E1DCFE4063FEC6E4E8424139D`
- Authoritative roots: `.agents/agent`, `.agents/skills`

## Audit Evidence Checklist

1. **Writer/auditor separation - PASS.** `l2_role_id=26 != l3_role_id=21`; role 26 is planning-only and non-audit, while role 21 independently reviews.
2. **Approved scope - PASS.** The v10-to-v11 no-index diff contains only the v11 identity/audit-reference refresh, the two requested `source='VCI'` corrections, and matching evidence wording. No production source or test file was changed by role 26. Existing unrelated worktree changes remain outside this audit.
3. **All tests - PASS.** `python -m pytest -q` reached `100%` and exited `0`; three tests were skipped. Existing warnings do not fail the suite.
4. **PIT safety - PASS.** The plan excludes receipt/ingestion time from revision identity, preserves immutable first receipt, forbids invented publication time and synthesized daily rows, normalizes SBV civil dates through `Asia/Ho_Chi_Minh`, and delays availability until the strictly following tradable session.
5. **SOD boundaries - PASS.** Role 26 authored only `.ly_state/session/implementation_plan_macro_news_v11.md`. Role 21 modifies only this audit report and the named phase-gate entry; no production code, tests, or plan content is edited.
6. **L2 repo-local skill evidence - PASS.** The plan lists `.agents/agent/planning-architect.md` and all four declared repo-local skill files under `.agents/skills`, plus a forbidden-path scan showing no authoritative reliance.

## Contract Verification

- **SBV interest rates - NEEDS_FIX.** The official article URL, exact PDF URL, publication/observation period, overnight-only value contract, canonical fragment/PDF hashes, fail-closed transport, and PIT rules are specified. However, the binding source tenor at `.ly_state/session/implementation_plan_macro_news_v11.md:106` is mojibake, with code points `U+00C4 U+2018 U+00C3 U+00AA`, instead of the exact UTF-8 label bytes `51 75 61 20 C4 91 C3 AA 6D` (`Qua` + `U+0111` + `U+00EA` + `m`). An implementer following the literal cannot perform exact source-label identification reliably.
- **SBV exchange rates - PASS.** The plan binds the official SBV bootstrap and structured-content endpoint, `contentStructureId=137473`, exact `page`, `pageSize=100`, `sort=datePublished:desc`, required provider/item identifiers, numeric `TyGiaSo`, and Vietnam civil-date normalization. Yahoo and Vietcombank substitution is forbidden.
- **Vnstock parameters - PASS.** `requirements.txt` pins `vnstock==4.0.4`; installed metadata reports `4.0.4`; `Company` accepts a string `source`. Binding lines 89 and 290 and the acceptance contract at line 406 use quoted `source='VCI'`; the plan contains zero `source=VCI` matches and requires one argument-free `.news()` call per ticker.
- **Exact source identification - NEEDS_FIX.** SBV article-fragment/PDF identity, SBV FX stable provider/item identity, and per-ticker VCI provenance are exact. The corrupted SBV overnight tenor literal prevents complete exact identification for the interest source.

## Blocking Finding

1. **P1 - Corrupted binding SBV tenor label.** `.ly_state/session/implementation_plan_macro_news_v11.md:106` contains mojibake code points instead of the exact Vietnamese source label. This violates the requested exact source identification and can cause a parser or fixture contract to bind the wrong label.

## Required Action

1. Replace the line-106 tenor literal with exact UTF-8 bytes `51 75 61 20 C4 91 C3 AA 6D` (`Qua` + `U+0111` + `U+00EA` + `m`); retain the existing overnight-only fixture/table agreement contract. Resubmit the plan for independent review.

## Explicit Repo-Local Files Read

- `.agents/agent/code-reviewer.md`
- `.agents/AGENTS.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/agent/planning-architect.md`
- `.ly_state/session/implementation_plan_macro_news_v11.md`
- `.ly_state/session/implementation_plan_macro_news_v10.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan_v10_reaudit_20260813.md`
- `.ly_state/session/phase_gates.json`
- `requirements.txt`
- `scripts/sod_gate_enforcer.py`

The repository-root `AGENTS.md` redirect was supplied in task context and was not reopened from disk. Installed `vnstock` metadata was inspected only to verify the pinned API; it supplied no role, skill, or business-source authority. Test execution imports are not counted as explicit audit content reads.

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: absent; content reads `0`; writes `0`; authoritative reliance `0`.
- `C:\Users\GHC\.openclaw\skills`: exists; content reads `0`; writes `0`; authoritative reliance `0`.
- `C:\Users\GHC\.agents`: exists; content reads `0`; writes `0`; authoritative reliance `0`.
- `C:\Users\GHC\.codex\memories`: exists; content reads `0`; writes `0`; authoritative reliance `0`.
- Result: **PASS.** No forbidden path content was opened, used, or modified. Only repo-local role and skill sources were authoritative.

## Verdict

`[NEEDS_FIX]`

VCI quoting, Vnstock call parameters, SBV FX parameters, PIT safety, tests, scope, SOD, and repo-local source evidence pass. Correct the mojibake SBV overnight tenor before approval.
