# Macro News Pipeline Plan Audit

Verdict: [NEEDS_FIX]
Gate: `MACRO_NEWS_PIPELINE_plan`
Date: `2026-08-12T15:04:34+07:00`
Auditor: Codex L3 `code-reviewer` (role 21)
L2 Session: `.ly_state/session/implementation_plan_macro_news_v2.md`
Plan author: Codex L3 `planning-architect` (role 26, non-audit)

## Audit Evidence Checklist

1. **Writer/auditor separation - PASS.** `l2_role_id=26 != l3_role_id=21`.
2. **Required scope - PASS.** The plan covers vnstock, VCBS, source expansion, raw-first persistence, shared alpha LLM configuration, versioned extraction, PIT controls, security, tests, rollback, and acceptance criteria.
3. **SoD boundary - PASS.** Repo-local role 26 is tier 3, platform Codex, `planning-only, non-audit, no production code`. The submission is a plan only. Code blocks are permitted and were not treated as a defect.
4. **Role-26 attribution - PASS.** Plan metadata, repo-local role frontmatter, and gate metadata consistently identify Codex L3 role 26. No conflicting repository evidence was found.
5. **Repo-local skill evidence - PASS.** Section 19 lists `.agents/agent/planning-architect.md` and all declared repo-local skills: `plan-writing`, `architecture`, `database-design`, `api-patterns`. All five files exist under `.agents/`.
6. **Architecture standards - NEEDS_FIX.** Blocking data-identity and runtime-input contradictions remain.

## Blocking Findings

1. **P1 - Hidden session-state runtime dependency.** `.ly_state/session/implementation_plan_macro_news_v2.md:224` requires production ingestion to load `.ly_state/session/vci_universe_hsx_hnx.json`, but the file is absent from the implementation file map at `.ly_state/session/implementation_plan_macro_news_v2.md:454` and has no lifecycle, version, refresh, or `as_of` contract. `.ly_state/session/` is workflow state, not a durable pipeline input. Define a repo-owned/versioned universe source or a required CLI input whose hash and effective date are recorded in the manifest.
2. **P1 - vnstock provenance is lost by the stated identity key.** `.ly_state/session/implementation_plan_macro_news_v2.md:231` and `.ly_state/session/implementation_plan_macro_news_v2.md:308` require one raw provenance row per ticker. `.ly_state/session/implementation_plan_macro_news_v2.md:302` prefers provider ID or URL for `article_id`; `.ly_state/session/implementation_plan_macro_news_v2.md:303` deduplicates on `(article_id, content_hash)`. The same provider story returned for multiple tickers therefore collapses to one row, losing `origin_ticker`. Add ticker/provenance to the physical key, store a ticker set, or separate article content from article-ticker provenance.
3. **P1 - LLM cache identity does not match the request identity.** `.ly_state/session/implementation_plan_macro_news_v2.md:362` sends source metadata and publication time, while `.ly_state/session/implementation_plan_macro_news_v2.md:425` caches only by content, schema, prompt, provider, and model. Identical content with different source metadata/time can reuse an extraction produced from a different request. Make the request source-invariant or include canonical `request_sha256` in extraction/cache identity. Also define the one-to-many mapping implied by `.ly_state/session/implementation_plan_macro_news_v2.md:427` instead of retaining one ambiguous `article_id`.

## Exact Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/agent/planning-architect.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/implementation_plan_macro_news_v2.md`
- `.ly_state/session/phase_gates.json`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan_20260812.md`
- `.ly_state/session/audit_reports/role21_macro_news_pipeline_plan_audit_20260812.md`
- `scripts/sod_gate_enforcer.py`
- `requirements.txt`
- `setup.cfg`
- `src/omega/data/macro_news_pipeline.py`
- `scripts/run_hybrid_alpha_evolution.py`
- `tests/test_hybrid_alpha_real_market.py`

Role-26 skill file existence was additionally verified for `.agents/skills/plan-writing/SKILL.md`, `.agents/skills/architecture/SKILL.md`, `.agents/skills/database-design/SKILL.md`, and `.agents/skills/api-patterns/SKILL.md`. `.ly_state/session/vci_universe_hsx_hnx.json` existence and metadata were checked; its content was not used as authority.

## Forbidden Path Scan

- Scope: `.ly_state/session/implementation_plan_macro_news_v2.md`.
- Non-authoritative forbidden-pattern scan evidence: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.
- Result: `PASS`; exact matches `0`; authoritative reliance `none`.
- No forbidden path was read or written during this audit.

## Verdict

[NEEDS_FIX]

Revise the three blocking contracts, then submit a new independent plan audit. L1 must run `python scripts/sod_gate_enforcer.py` after this gate update.
