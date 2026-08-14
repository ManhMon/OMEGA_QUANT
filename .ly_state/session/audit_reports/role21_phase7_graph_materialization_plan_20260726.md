# Phase 7 Graph Materialization Plan Audit

**Role**: `21 code-reviewer` (Codex L3)
**Gate**: `phase7_graph_materialization_plan`
**Date**: `2026-07-26`
**Reviewed plan**: `C:\Users\GHC\.gemini\antigravity-ide\brain\3d6d7760-071e-42d2-a99e-b9922376d700\implementation_plan.md`

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
- `src/omega/quant/graph/fetcher.py`
- `scripts/run_graph_bootstrap.py`
- `tests/phase7/test_graph_bootstrap.py`

## Findings

1. **BLOCKING — raw-to-canonical normalization remains undefined.** The plan names canonical columns but does not specify deterministic mappings from observed raw schemas. Required mappings include `subsidiaries.name -> subsidiary`, `subsidiaries.ownership_percent -> ownership_pct`, `officers.name -> officer`, and industry source selection/mapping from `industry_sectors` or `industry_list_by_industry`. Most critically, observed ownership snapshots contain `owner_type`, `ownership_percentage`, `shares_owned`, and `update_date`, but no raw company/person identity that can satisfy canonical `target`. The proposed natural key `(ticker, target)` is therefore not implementable without an explicit target derivation rule or an explicit decision to exclude unsupported ownership rows.

2. **CLOSED — multi-row relationship preservation.** Latest eligible snapshot selection is scoped per source-file symbol/entity; deduplication uses entity natural keys rather than `_symbol` alone. Tests require multiple officer, subsidiary, and ownership rows for one symbol to survive.

3. **CLOSED — PIT boundary.** Input eligibility and output contract explicitly require `observed_at <= signal_date`; tests and smoke assertions cover future-row exclusion.

4. **CLOSED — unavailable historical evaluation.** The plan states snapshots exist only for `2026-07-25` and `2026-07-26`, prohibits time-series IC/IR claims, and defers historical evaluation to a separately approved gate.

5. **CLOSED — `peer_mean_ic`.** The output contract and tests require the column to remain entirely `NaN`; ranking and evaluation usage is excluded.

6. **CLOSED — pipeline scope.** `pipeline_v2.py`, alpha scoring, ranking, and pipeline integration are explicitly excluded. Integration requires a future plan and L3 approval.

7. **CLOSED — exact L2 role.** Implementation is assigned to `15 data-engineer`; audit remains `21 code-reviewer`.

## Required Fix

- Add a raw-to-canonical mapping table for every entity using the actual snapshot directory and column names. Define null/invalid-row handling. Resolve ownership `target` provenance explicitly; if unavailable, exclude ownership materialization and define `ownership_concentration` behavior rather than inventing identity from `owner_type`.

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit` — non-authoritative scan evidence only; no reliance.
- `.openclaw\skills` — non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents` — non-authoritative scan evidence only; no reliance.
- `.codex\memories` — non-authoritative scan evidence only; no reliance.

## Verdict

[NEEDS_FIX]
