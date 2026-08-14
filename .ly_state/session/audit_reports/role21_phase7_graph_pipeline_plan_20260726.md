# Phase 7 Graph Pipeline Plan Audit

**Role**: Code Reviewer (Role 21, Codex L3)
**Gate**: `phase7_graph_pipeline_plan`
**Date**: 2026-07-26
**Scope**: Plan review only; no production source modified.

## Verdict

[NEEDS_FIX]

## Blocking Findings

1. `implementation_plan.md:37`: Dedup by `_symbol` collapses valid multi-row officers, subsidiaries, ownership, and shareholders. Define per-entity natural keys plus `_symbol`; retain latest eligible row by `observed_at <= as_of_date`.
2. `implementation_plan.md:46-48`: Raw schemas do not satisfy `build_graph()`. Per-symbol files use `_symbol`; builder expects `ticker`/`symbol`. Subsidiaries use `name`/`ownership_percent`; ownership uses `owner_type`/`ownership_percentage`; officers use `name`. Define canonical normalization before graph construction.
3. `implementation_plan.md:49,69-72,94-97`: Snapshots cover only 2026-07-25 and 2026-07-26. One feature date cannot produce time-series `mean_IC`, `std_IC`, IR, or meaningful t-stat. Permit only schema/coverage checks and one-date cross-sectional IC after the forward horizon matures, or define repeated historical PIT materialization.
4. `implementation_plan.md:54-60`: Pipeline hook is premature. No proven feature schema, uniqueness key, historical availability, fallback, evaluation threshold, or approved contract exists. Remove the pipeline hook from this iteration.
5. `implementation_plan.md:70,106`: `daily_ic` and `industry_sector` are not price columns. Keep `peer_mean_ic = NaN`, coverage zero, excluded from ranking. Do not fabricate either input.
6. PIT contract must require `observed_at <= signal_date`, entity-natural-key latest selection, forward returns used only as labels, no future snapshot/membership/sector data in features, and exclusion of incomplete forward horizons.
7. `implementation_plan.md:115`: `quant-researcher (role ?)` is unresolved SoD metadata. L1 must resolve an exact repo-local role before dispatch.

## Required Revised Scope

- Repair loader globbing and entity-specific PIT dedup.
- Normalize raw entity schemas into builder inputs.
- Build graph and materialize dated features with `ticker + signal_date` uniqueness.
- Keep `peer_mean_ic` as `NaN`.
- Run offline schema, coverage, graph sanity, and feasible IC checks.
- Define an approval threshold; request new L3 approval before any pipeline hook.

## Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `src/omega/quant/graph/snapshot.py`
- `src/omega/quant/graph/builder.py`
- `src/omega/quant/graph/features.py`
- `src/omega/quant/graph/integration.py`
- `src/omega/quant/pipeline_v2.py`
- `.ly_state/graph_snapshots/**` parquet metadata/schema evidence

## External File Read

- `C:\Users\GHC\.gemini\antigravity-ide\brain\3d6d7760-071e-42d2-a99e-b9922376d700\implementation_plan.md`

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit` non-authoritative scan evidence only; no reliance.
- `.openclaw\skills` non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents` non-authoritative scan evidence only; no reliance.
- `.codex\memories` non-authoritative scan evidence only; no reliance.

**Final Verdict**: [NEEDS_FIX]
