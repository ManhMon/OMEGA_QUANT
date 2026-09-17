# L2 Role 15 Phase 7b Real-Data Run

- **Session**: `l2_role15_phase7_full_real_run_20260727`
- **Role**: Role 15 `data-engineer`, OpenCode L2
- **Run date**: 2026-07-27
- **Scope**: `tests/phase7/`, `scripts/build_graph_features.py`, `.ly_state/graph_features/`, this report
- **Status**: `NEEDS_FIX` / materialization failed; no source fix attempted
- **Backtest/ranking/integration**: Not run
- **Atomic replacement authorization**: Received; target was absent, so no replacement occurred

## Repo-Local Sources Read

- `.agents/agent/data-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `scripts/build_graph_features.py`
- `src/omega/quant/graph/materialize.py`

Forbidden-path scan: no authoritative reliance on `.gemini\\antigravity-ide\\scratch\\ag-kit`, `.openclaw\\skills`, `C:\\Users\\GHC\\.agents`, or `.codex\\memories`.

## Commands

### Phase 7 tests

```text
python -m pytest tests/phase7/ -q
```

Result: exit `0`; `14 passed`.

Observed output:

```text
..............                                                           [100%]
14 passed, warnings only
```

Warnings: vnstock/vnai upgrade notices; deprecated `omega.quant.alpha.discovery`; SQLAlchemy `declarative_base`; pre-existing `.pytest_cache` WinError 183.

### Real-data materialization

```text
python scripts/build_graph_features.py --cutoff-at 2026-07-24T23:59:59.999999+07:00
```

Result: exit `1`.

Exact stderr:

```text
ERROR: zero equity nodes
```

## Diagnostics

- **Input root**: `.ly_state/graph_snapshots`
- **Output root**: `.ly_state/graph_features`
- **Cutoff input**: `2026-07-24T23:59:59.999999+07:00`
- **Cutoff UTC**: `2026-07-24 16:59:59.999999+00:00`
- **Discovered files**: `industry_sectors=2`, `officers=688`, `industry_list_by_industry=2`
- **Eligible rows at cutoff**: `industry_sectors=0`, `officers=0`, `industry_list_by_industry=0`
- **Normalized rows**: `industry=0`, `officers=0`, `subsidiaries=0`
- **Graph nodes**: `0`
- **Equity nodes**: `0`
- **Root cause observed**: all discovered snapshot rows were excluded by the cutoff filter; materializer raised `MaterializationError("zero equity nodes")`

### Counters

```text
{'source': 692, 'normalized': 0, 'dropped': 24566, 'ambiguous': 0, 'malformed_timestamp': 0, 'missing_symbol_files': 2, 'by_source': {'industry_sectors': {'source': 2}, 'officers': {'source': 688, 'missing_symbol_files': 2}, 'industry_list_by_industry': {'source': 2}}}
```

## Artifact Evidence

- **Expected artifact**: `.ly_state/graph_features/graph_features_20260724.parquet`
- **Artifact exists**: `false`
- **Atomic replacement**: not reached
- **Schema**: unavailable because no parquet was written; expected logical schema from `src/omega/quant/graph/materialize.py`:
  - `signal_date: date32`
  - `ticker: string`
  - `observed_at: timestamp[us, tz=UTC]`
  - `degree_centrality: float64`
  - `subsidiary_count: int64`
  - `officer_overlap_count: int64`
  - `ownership_concentration: float64`
  - `peer_mean_ic: float64`
- **Row count**: unavailable; no artifact
- **Output `observed_at` max**: unavailable; no artifact
- **Cutoff comparison**: not applicable; no output rows
- **SHA-256**: unavailable; target artifact absent (`artifact_missing`)

## Restricted-Change Evidence

No source, test, config, secret, or gate modification was made by this run. Existing worktree changes were present before execution and were not altered.

## Handoff

Tests pass. Real-data materialization remains blocked by `zero equity nodes`. Per instruction, no code fix or retry with altered inputs was attempted. Submit this report for Tier 3 audit; L2 does not self-approve.
