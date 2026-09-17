# L2 Role 15 Phase7 Graph Materialization Fix

- Session: `l2_role15_phase7_graph_materialization_fix1_20260726`
- Role: `15 data-engineer` / OpenCode L2
- Status: implementation complete; no audit or gate changes
- Scope: `src/omega/quant/graph/materialize.py`, `tests/phase7/test_graph_materialize.py`
- Unchanged scoped files: `src/omega/quant/graph/snapshot.py`, `scripts/build_graph_features.py`

## Root Causes

1. Fixture observations were later than the valid UTC cutoff (`2026-07-26T04:00:00Z`), so all industry rows were correctly excluded and materialization raised `zero equity nodes`.
2. Subsidiary counterparties were emitted as equity nodes without contributor timestamps, causing a `KeyError` during output row construction.
3. The atomic-write test resolved the package export instead of the materialization module. It now imports the actual module and patches its `os.replace` dependency.

## Changes

- Made fixture timestamps plan-compliant and retained a future-dated row to verify cutoff exclusion.
- Recorded subsidiary counterparties as contributors at their observed timestamp.
- Patched `materialize_module.os.replace` in the atomic failure test; previous target remains untouched.
- Updated expected PIT timestamp to the valid cutoff boundary.
- Built `peer_mean_ic` as an explicit Arrow `float64` array from a NumPy float64 buffer in `write_atomic`; this prevents pandas NaN-to-Arrow-null conversion.
- Added a physical Parquet round-trip test asserting `peer_mean_ic.null_count == 0` and every value is IEEE-754 NaN.

## Verification

Command: `python -m pytest tests/phase7 -q`

Result: `14 passed`.

Command: `python -m py_compile src/omega/quant/graph/materialize.py src/omega/quant/graph/snapshot.py scripts/build_graph_features.py tests/phase7/test_graph_materialize.py`

Result: exit `0`.

Command: `python scripts/build_graph_features.py --cutoff-at 2026-07-26T11:00:00+07:00 --snapshot-root .ly_state/graph_snapshots --output-root .ly_state/graph_features`

Result: exit `0`; target `.ly_state\graph_features\graph_features_20260726.parquet`.

Command: `python scripts/build_graph_features.py --cutoff-at 2026-07-26T11:00:00 --snapshot-root .ly_state/graph_snapshots --output-root .ly_state/graph_features`

Result: exit `1`; stderr `ERROR: cutoff-at must be timezone-aware`.

Command: `python -c "import pyarrow.parquet as pq; t=pq.read_table('.ly_state/graph_features/graph_features_20260726.parquet'); c=t['peer_mean_ic']; import math; assert c.null_count == 0; assert all(math.isnan(x) for x in c.to_pylist()); print({'type': str(c.type), 'null_count': c.null_count, 'rows': len(c)})"`

Result: `{'type': 'double', 'null_count': 0, 'rows': 705}`; all physical values are IEEE-754 NaN.

## Canonical Report Correction

The original L2 report `.ly_state/session/l2_role15_phase7_graph_materialization_20260726.md` incorrectly listed `.agents/skills/lint-and-validate/SKILL.md` as loaded evidence. `lint-and-validate` is not declared by `data-engineer`; the original evidence was therefore undeclared and is removed. This report retains only declared repo-local role/skill sources. No source, test, audit, or gate scope was broadened.

## Repo-Local Files Read

`REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`

`REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`

- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\AGENTS.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent\data-engineer.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\python-patterns\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\database-design\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\clean-code\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\testing-patterns\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\systematic-debugging\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\performance-profiling\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\vietnam-market-data\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\data-science-workflow\SKILL.md`
- `src/omega/quant/graph/materialize.py`
- `src/omega/quant/graph/snapshot.py`
- `scripts/build_graph_features.py`
- `tests/phase7/test_graph_materialize.py`

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: non-authoritative scan evidence only; no reliance.
- `.codex\memories`: non-authoritative scan evidence only; no reliance.
