# L2 Report: role14 data-scientist

- Session: `l2_role14_conformal_backtest_integration_and_sharpe_verification_fix2_20260702`
- Gate: `CONFORMAL_BACKTEST_INTEGRATION_AND_SHARPE_VERIFICATION_20260702`
- Scope: `scripts/backtest_hybrid_regime.py`, `scripts/precompute_all_features.py`, `scripts/genetic_alpha_evolution_v3.py`
- Role boundary: implementation + test only. No audit/approval.

## Repo-Local Role/Skill Files Read

- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent\data-scientist.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\python-patterns\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\clean-code\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\testing-patterns\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\systematic-debugging\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\performance-profiling\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\quant-research\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\vietnam-market-data\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\backtesting-pit-safety\SKILL.md`
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\data-science-workflow\SKILL.md`

## Forbidden Path Scan Result

- Repo scratch scan: no files found under `.gemini/antigravity-ide/scratch/ag-kit/**`
- Repo scratch scan: no files found under `.openclaw/skills/**`
- Repo scratch scan: no files found under `.codex/memories/**`
- Global path check: `C:\Users\GHC\.agents` exists but was not used as an authoritative source
- Result: no authoritative reliance on forbidden paths

## Changes

### `scripts/genetic_alpha_evolution_v3.py`

- Added stable artifact target `data/stable/`
- Dual-write genetic outputs to stable + legacy `data/phase35_results/`
- Persisted both human-readable `expression` and parseable `serialized_tree=repr(ind.tree)`
- Kept legacy CSV shape compatible enough for current consumers

### `scripts/precompute_all_features.py`

- Switched GP results lookup to prefer `data/stable/genetic_alpha_v3_results.csv`, fallback to legacy path
- Added parser fallback for legacy/truncated GP payloads
- Fallback behavior: recover a terminal feature like `vol_ratio`/`open` when full tree payload is not parseable
- Regenerated `data/precomputed_alpha_features.parquet`

### `scripts/backtest_hybrid_regime.py`

- Hardened per-fold conformal refit against train-row underflow
- Logic now ranks available feature cols by non-null coverage, drops lowest-coverage cols until both train/calib splits remain viable
- Preserves PIT behavior: only in-fold rows, no future leakage
- Added JSON result mirroring from legacy output root to `data/stable/`

## Verification

### Command

```powershell
python scripts/precompute_all_features.py
```

### Result

- Passed
- Regenerated parquet: `data/precomputed_alpha_features.parquet`
- Snapshot:

```text
{'path': 'data\\precomputed_alpha_features.parquet', 'exists': True, 'rows': 274224, 'symbols': 104, 'alpha_gp_non_null': {'alpha_gp_00': 274224, 'alpha_gp_01': 274224, 'alpha_gp_02': 274224}}
```

- Notable runtime evidence:
  - `alpha_gp_00` loaded directly from parseable payload
  - legacy/truncated payloads for ranks 2/3 recovered via terminal fallback (`vol_ratio`)

### Command

```powershell
pytest tests/test_conformal_backtest.py
```

### Result

- Passed: `15 passed, 5 warnings in 6.37s`
- Warnings were pre-existing/dependency-level (`vnai` update notice, SQLAlchemy deprecation, pytest cache path, precision-loss warning in statistical test)

## Files Materialized/Updated During Verification

- `data/precomputed_alpha_features.parquet`
- `data/stable/genetic_alpha_v3_results.csv`
- `data/stable/best_evolved_alpha_v3.json`

## Notes

- Stable-folder migration implemented minimally as prefer-stable + dual-write/mirror, not broad repo-wide path rewrite.
- GP fallback intentionally degrades to a terminal feature when only legacy truncated payload exists. Upgrade path: rerun `scripts/genetic_alpha_evolution_v3.py` to repopulate `serialized_tree` for exact tree reconstruction.
