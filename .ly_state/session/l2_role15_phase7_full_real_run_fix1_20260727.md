# L2 Role 15 Phase 7b Real-Data Materialization Retry

- **Session**: `l2_role15_phase7_full_real_run_fix1_20260727`
- **Role**: Role 15 `data-engineer`, OpenCode L2
- **Run date**: 2026-07-27
- **Scope**: `.ly_state/graph_features/graph_features_20260726.parquet`, this report
- **Status**: Real-data materialization succeeded
- **Root cause context**: Prior cutoff preceded all valid snapshots. No source/data repair performed.
- **Backtest/ranking/integration**: Not run
- **Atomic replacement authorization**: Received; existing target atomically replaced

## Repo-Local Files Read

- `.agents/agent/data-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`
- `scripts/build_graph_features.py`
- `src/omega/quant/graph/materialize.py`
- `.ly_state/session/l2_role15_phase7_zero_nodes_diagnosis_20260727.md`

Forbidden-path scan: no authoritative reliance on `.gemini\\antigravity-ide\\scratch\\ag-kit`, `.openclaw\\skills`, `C:\\Users\\GHC\\.agents`, or `.codex\\memories`.

## Authorized Run

Exact command:

```text
python scripts/build_graph_features.py --cutoff-at 2026-07-26T23:59:59.999999+07:00
```

Exit status: `0`

Exact counters:

```text
{'source': 1374, 'normalized': 8236, 'dropped': 3222, 'ambiguous': 3166, 'malformed_timestamp': 0, 'missing_symbol_files': 4, 'by_source': {'industry_sectors': {'source': 2}, 'industry': {'normalized': 695}, 'officers': {'source': 688, 'missing_symbol_files': 2, 'normalized': 7541}, 'subsidiaries': {'source': 682, 'missing_symbol_files': 2}, 'industry_list_by_industry': {'source': 2}}}
```

Target reported by CLI: `.ly_state\\graph_features\\graph_features_20260726.parquet`

## Artifact Evidence

- **Target path**: `.ly_state/graph_features/graph_features_20260726.parquet`
- **Row count**: `705`
- **Physical schema/order**:

```text
signal_date: date32[day]
ticker: string
observed_at: timestamp[us, tz=UTC]
degree_centrality: double
subsidiary_count: int64
officer_overlap_count: int64
ownership_concentration: double
peer_mean_ic: double
```

- **Column order**: `['signal_date', 'ticker', 'observed_at', 'degree_centrality', 'subsidiary_count', 'officer_overlap_count', 'ownership_concentration', 'peer_mean_ic']`
- **Output max `observed_at`**: `2026-07-26 02:14:36.392494+00:00`
- **Cutoff UTC**: `2026-07-26 16:59:59.999999+00:00`
- **Max observed_at versus cutoff**: max is `14:45:23.607505` before cutoff; `0` rows exceed cutoff
- **PIT check**: `PASS`; all `705/705` output rows satisfy `observed_at <= cutoff`; null `observed_at` rows: `0`
- **Uniqueness check**: `PASS`; `(ticker, signal_date)` duplicate count: `0`; unique keys: `705`
- **SHA-256**: `49d0fc3742cb303a892bbf6f41cd0abbc249a2089c3393251273536448177ef4`

## Restricted-Change Evidence

- No source, tests, config, secrets, or gates modified.
- Only the authorized graph feature target was replaced atomically and this session report was added.
- No backtest, ranking, or integration command was run.
- No failure was fixed; retry used the unchanged materializer with the authorized later cutoff.

## Result

Phase 7b real-data graph materialization retry completed successfully. Artifact and validation evidence are persisted for Tier 3 audit. L2 does not self-approve.
