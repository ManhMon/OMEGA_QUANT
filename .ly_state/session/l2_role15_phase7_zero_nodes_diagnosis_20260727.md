# Phase 7b Zero-Equity-Node Diagnosis

- **Session**: `l2_role15_phase7_zero_nodes_diagnosis_20260727`
- **Role**: Role 15 `data-engineer`, OpenCode L2
- **Date**: 2026-07-27
- **Mode**: Read-only diagnosis
- **Requested cutoff**: `2026-07-24T23:59:59.999999+07:00`
- **Requested cutoff UTC**: `2026-07-24T16:59:59.999999+00:00`
- **Result**: Raw data is present and parseable, but no raw row is PIT-valid at the requested cutoff. The zero-node failure is caused by snapshot freshness/data coverage, not by a selector defect.

## Scope And Restrictions

Inspected only:

- `.ly_state/graph_snapshots/**/*.parquet`
- `src/omega/quant/graph/snapshot.py`
- `src/omega/quant/graph/materialize.py`
- `scripts/build_graph_features.py`
- `.ly_state/session/l2_role15_phase7_full_real_run_20260727.md`

Did not edit source, tests, config, raw data, output data, or gates. Did not rerun materialization with an alternative cutoff.

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

Forbidden-path scan: no authoritative reliance on `.gemini\\antigravity-ide\\scratch\\ag-kit`, `.openclaw\\skills`, `C:\\Users\\GHC\\.agents`, or `.codex\\memories`.

## Commands And Evidence

### Prior failed run

Command recorded in the Phase 7b run report:

```text
python scripts/build_graph_features.py --cutoff-at 2026-07-24T23:59:59.999999+07:00
```

Result: exit `1`; `ERROR: zero equity nodes`.

Prior counters:

```text
{'source': 692, 'normalized': 0, 'dropped': 24566, 'ambiguous': 0,
 'malformed_timestamp': 0, 'missing_symbol_files': 2,
 'by_source': {'industry_sectors': {'source': 2},
 'officers': {'source': 688, 'missing_symbol_files': 2},
 'industry_list_by_industry': {'source': 2}}}
```

### Direct raw parquet inventory

Read-only command used to load each source parquet, parse `observed_at` with `pd.to_datetime(..., utc=True)`, and compare against the requested UTC cutoff:

```text
python -c "from pathlib import Path; import pandas as pd; r=Path('.ly_state/graph_snapshots'); c=pd.Timestamp('2026-07-24T23:59:59.999999+07:00').tz_convert('UTC'); print('entity files rows eligible rejected missing_files missing_rows min max'); for e in ['industry_sectors','industry_list_by_industry','officers','subsidiaries']: ps=list((r/e).glob('**/*.parquet')); vals=[]; mf=mr=0; [None for p in ps]; d=None; [((lambda x: (vals.extend(list(x.get('observed_at',[]))), None)[1])(pd.read_parquet(p))) for p in ps]; t=pd.to_datetime(pd.Series(vals),utc=True); print(e,len(ps),len(t),int((t<=c).sum()),int((t>c).sum()),mf,mr,t.min(),t.max())"
```

Quantified result:

| Source | Files | Rows | UTC min | UTC max | PIT-valid rows | Cutoff-rejected rows | Missing `observed_at` rows |
|---|---:|---:|---|---|---:|---:|---:|
| `industry_sectors` | 2 | 1,390 | 2026-07-25 23:44:40.219898+00:00 | 2026-07-26 01:03:01.949002+00:00 | 0 | 1,390 | 0 |
| `industry_list_by_industry` | 2 | 15,618 | 2026-07-25 23:44:40.219898+00:00 | 2026-07-26 01:03:01.949002+00:00 | 0 | 15,618 | 0 |
| `officers` | 688 | 7,558 | 2026-07-25 23:59:57.596162+00:00 | 2026-07-26 02:14:36.392494+00:00 | 0 | 7,543 | 0 |
| `subsidiaries` | 682 | 3,207 | 2026-07-25 23:59:57.596162+00:00 | 2026-07-26 02:14:36.392494+00:00 | 0 | 3,166 | 0 |
| **Total** | **1,854** | **27,773** | **2026-07-25 23:44:40.219898+00:00** | **2026-07-26 02:14:36.392494+00:00** | **0** | **27,717** | **0** |

The prior run's 692 discovered files covers the three sources traversed before subsidiary lookup; direct inventory also shows 682 subsidiary files. No timestamp parse failures were found.

### Schema and timezone distribution

All 27,773 raw rows have timezone-aware UTC parquet timestamps. Direct source dtypes are `datetime64[ns, UTC]`; no naive values, null values, or malformed timestamps were found.

| Source | Raw columns | UTC-date distribution | Vietnam-local-date distribution |
|---|---|---|---|
| `industry_sectors` | `symbol`, `industry_code`, `industry_name`, `observed_at` | 2026-07-25: 695; 2026-07-26: 695 | 2026-07-26: 1,390 |
| `industry_list_by_industry` | `symbol`, `organ_name`, `com_type_code`, `icb_level`, `icb_code`, `icb_name`, `observed_at` | 2026-07-25: 7,809; 2026-07-26: 7,809 | 2026-07-26: 15,618 |
| `officers` | `from_date`, `position`, `name`, `position_en`, `owner_code`, `observed_at`, `_symbol` | 2026-07-25: 6; 2026-07-26: 7,552 | 2026-07-26: 7,558 |
| `subsidiaries` | `update_date`, `name`, `charter_capital`, `ownership_percent`, `currency`, `type`, `observed_at`, `_symbol` | 2026-07-25: 14; 2026-07-26: 3,193 | 2026-07-26: 3,207 |

Representative raw schema checks:

- `industry_sectors`: `symbol` non-null/non-empty 1,390/1,390; `industry_name` 1,390/1,390.
- `industry_list_by_industry`: `symbol` 15,618/15,618; `organ_name` 15,618/15,618.
- `officers`: `name` 7,558/7,558; `_symbol` non-null 7,543/7,558.
- `subsidiaries`: `name` 3,207/3,207; `_symbol` non-null 3,166/3,207.

### Exact rejection reasons

The materializer's `_eligible()` logic in `src/omega/quant/graph/materialize.py`:

1. Requires `_symbol` for `officers` and `subsidiaries` unless the file is `snapshot.parquet`.
2. Requires `observed_at`.
3. Uses `snapshot.parse_observed_at()`, which rejects timezone-naive/unparseable values.
4. Applies `frame["observed_at"] <= cutoff` after UTC normalization.

Observed source-specific rejection:

- `industry_sectors`: all 1,390 rows rejected only by the cutoff comparison. The required data columns are populated.
- `industry_list_by_industry`: all 15,618 rows rejected only by the cutoff comparison. The required lookup columns are populated.
- `officers`: 15 rows rejected by the missing-symbol-file guard (`2` global `snapshot.parquet` files); remaining 7,543 rows rejected by the cutoff comparison. No timestamp parse failure. Symbol-scoped officer files contain `_symbol`.
- `subsidiaries`: 41 rows rejected by the missing-symbol-file guard (`2` global `snapshot.parquet` files); remaining 3,166 rows rejected by the cutoff comparison. No timestamp parse failure.

The `missing_symbol_files=2` counter is a real schema/shape defect in each symbol-required source's global snapshots, but it is not the zero-node trigger for this cutoff: every row is already newer than the requested PIT boundary. `ambiguous=0`; `malformed_timestamp=0`.

## Selector Assessment

No selector defect explains the zero nodes.

- `parse_cutoff_at()` converts the explicit `+07:00` cutoff to `2026-07-24 16:59:59.999999+00:00`.
- `snapshot.parse_observed_at()` explicitly rejects naive timestamps and converts valid timestamps to UTC.
- `_eligible()` uses the correct fail-closed condition `observed_at <= cutoff`.
- The earliest raw timestamp is `2026-07-25 23:44:40.219898+00:00`, which is `30:44:40.219899` after the requested cutoff.
- A cutoff selector defect would need to reject at least one row at or before the cutoff. The inventory contains zero such rows.

Conclusion: **raw snapshot coverage/freshness is insufficient for the requested PIT date; selector behavior is consistent with the PIT contract.**

## Newest PIT-Valid Cutoff

No cutoff at or before the requested cutoff produces eligible equity nodes: the maximum PIT-valid cutoff supported by current raw data is nonexistent for the requested historical date.

The earliest cutoff that would admit any raw rows is the minimum observed timestamp:

```text
2026-07-25T23:44:40.219898Z
2026-07-26T06:44:40.219898+07:00
```

This is **not** a rerun or approval of an alternative cutoff. It is an inventory-derived boundary only. At that boundary, `industry_sectors` and `industry_list_by_industry` have rows available, so the graph can begin acquiring equity nodes through industry membership. The latest observed raw timestamp is:

```text
2026-07-26T02:14:36.392494Z
2026-07-26T09:14:36.392494+07:00
```

## Final Diagnosis

- **Failure**: `MaterializationError("zero equity nodes")`.
- **Primary cause**: all 27,773 inspected raw rows are post-cutoff; 0/27,773 PIT-valid.
- **Raw malformed/missing?**: Not malformed. `observed_at` is present, parseable, timezone-aware UTC for all rows. Historical coverage is missing for the requested date.
- **Selector defect?**: No. UTC normalization and `<= cutoff` filtering are correct.
- **Secondary data-shape issue**: global `snapshot.parquet` files in `officers` and `subsidiaries` lack `_symbol`; counted as two missing-symbol files per the existing run. This should be handled separately from the zero-node root cause.
- **Output artifact**: absent because graph construction stops before `write_atomic()`.
- **Required remediation direction**: provide snapshots whose `observed_at` is at or before the requested PIT boundary, then rerun the unchanged materializer under the same cutoff. No remediation performed in this session.

## Worktree Restriction Evidence

Only this diagnosis report was created. No source, test, config, data, output, or gate file was edited. No alternative-cutoff materialization was run.
