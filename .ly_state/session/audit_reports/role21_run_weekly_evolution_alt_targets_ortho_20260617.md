# Code Review Audit Report
**Role**: Code Reviewer (Role 21)
**Date**: 2026-06-17T10:10:14.2173679+07:00
**Submission**: `scripts/run_weekly_evolution.py`
**Scope**: Audit implementation of alternative features, targets, and orthogonalization in `run_weekly_evolution.py`
**l3_session_id**: `772164eb-c6a7-411b-92d9-e46967233a0f`
**l3_session_key**: `role21_run_weekly_evolution_alt_targets_ortho_20260617`
**audit_report_path**: `.ly_state/session/audit_reports/role21_run_weekly_evolution_alt_targets_ortho_20260617.md`
**final_verdict**: `[NEEDS_FIX]`

## Role Load Evidence
- `role_file`: `.agents/agent/code-reviewer.md`
- `role_file_sha256`: `b5c0a539e2aaaea3697f7a32312303897bfc41bc7d99502496e025fa8575cb55`
- `mandatory_skill_sha256`: `.agents/skills/omega-sod/SKILL.md` = `44ab0b9a8462216d3f52ec55e52bf9f9deae9598a25b4ad78fbc4e271f5a7e9a`
- `repo_local_skill_sources`:
  - `.agents/agent/code-reviewer.md`
  - `.agents/skills/code-review-checklist/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/audit-cycle/SKILL.md`
  - `.agents/skills/omega-sod/SKILL.md`
- `forbidden_path_scan`: No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`.

## SOD Boundary Check
- L3 boundary: PASS. Review-only actions taken; no production code edited, no commits made.
- Writer != auditor: NOT VERIFIED. No `l2_session_id`, `l2_role_id`, `l2_role_name`, or gate metadata were provided in the routing prompt, so gate update was intentionally not attempted.

## Validation Performed
- `python -m py_compile scripts/run_weekly_evolution.py` -> PASS
- `pytest tests/quant_test_evolution_modules.py -q` -> PASS
- `pytest tests/test_vn_features_targeted.py -q` -> PASS
- Static/API checks against:
  - `src/omega/quant/evolution/genetic_engine.py`
  - `src/omega/quant/evolution/alternative_features.py`
  - `src/omega/quant/evolution/alternative_data_fetcher.py`
  - `src/omega/quant/evolution/alpha_to_execution_bridge.py`

## Findings
1. **HIGH** - `scripts/run_weekly_evolution.py:497-514`, `scripts/run_weekly_evolution.py:623-667`
   `--orthogonalize promoted` cannot reliably penalize previously promoted alphas once those alphas use the new alternative features. The promoted-baseline builder evaluates formulas with `features_dict` containing only `FEATURE_COLUMNS`, while `run_evolution()` now allows trees to use `ALTERNATIVE_FEATURE_COLUMNS` at `scripts/run_weekly_evolution.py:741-754`. Repro run in this audit: `_evaluate_formula_string('alt_gap', {'open': ..., 'close': ...}) -> None` and `_evaluate_formula_string('(alt_gap + open)', {'open': ..., 'close': ...}) -> [1.0, 2.0, 3.0]`, which degrades to a partial fallback that ignores the alternative term. Result: previously promoted alt-feature alphas are either dropped from the baseline set or converted into incorrect proxies, so the orthogonalization penalty can silently fail to block rediscovery of the same signal family.

2. **MEDIUM** - `scripts/run_weekly_evolution.py:112-126`, `scripts/run_weekly_evolution.py:355-370`, `scripts/run_weekly_evolution.py:743-745`, `scripts/run_weekly_evolution.py:796-805`, `scripts/run_weekly_evolution.py:1044-1053`, `src/omega/quant/evolution/alternative_features.py:104-115`, `src/omega/quant/evolution/alternative_data_fetcher.py:202-209`
   The hard-coded `ALTERNATIVE_FEATURE_COLUMNS` list is incomplete relative to the generators it claims to integrate. Audit repro: generator feature names minus script allowlist = `['alt_focal_stress_score', 'alt_ret_20d', 'alt_ret_5d', 'alt_vsi_score']`. Those columns are generated and merged, but never lagged, never included in GP feature dicts, and never included in the `dropna` contract. The implementation therefore does not fully wire the alternative feature surface it advertises, and downstream logs/metadata undercount available signals.

3. **MEDIUM** - `scripts/run_weekly_evolution.py:866-885`, `scripts/run_weekly_evolution.py:966-996`
   Result metadata is wrong when `--no-alt-features` is used. The CLI explicitly supports disabling alternative features, and `main()` monkey-patches `_generate_alternative_features` off for that mode, but `save_results()` always writes:
   - `"alternative_features": {"enabled": True, ...}`
   This creates a false audit trail in `.ly_state/session/evolved_alphas.json`, making downstream consumers believe alternative features participated in the run even when they were disabled.

## Residual Risks / Gaps
- No targeted tests cover `_build_ortho_baseline_set()`, `_evaluate_formula_string()` with alt-feature formulas, or the `--no-alt-features` metadata branch.
- Gate metadata could not be verified or updated because the routing prompt omitted L2 session and gate identifiers.

## Verdict
[NEEDS_FIX]

## Required Actions
1. Expand promoted-baseline evaluation so it uses the same feature universe available to evolution, including alternative features and any target-horizon dependencies that promoted formulas can reference.
2. Replace the hard-coded alternative feature allowlist with a source-of-truth derived from the generators, or update the list and lag/dropna/feature-dict wiring so every generated alternative feature is handled consistently.
3. Make `save_results()` reflect the actual runtime flag for alternative-feature enablement.
4. Add regression tests for promoted-baseline evaluation with alternative-feature formulas and for the `--no-alt-features` metadata path.
