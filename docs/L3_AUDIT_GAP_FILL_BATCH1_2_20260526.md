# L3 Audit Report: Gap Fill Batch 1+2
**Date**: 2026-05-26
**Role**: Code Reviewer (Role 21)
**Scope**: `src/omega/quant/strategy/*.py` + `src/omega/quant/performance_tracker.py` + `src/omega/quant/portfolio.py` + `src/omega/governance/online_model_updater.py` + `src/omega/governance/validate_ly_state.py` + `src/omega/data/production_data_pipeline.py` + `src/omega/data/vnstock_live.py` + `src/omega/quant/quant_engine.py`
**Verdict**: `[NEEDS_FIX]`

---

## Executive Summary

| Check | Result |
|---|---|
| `py_compile` | PASS on 20/20 requested files |
| `v21_system` grep in audited scope | PASS: 0 hits |
| `v21_system` grep repo-wide imports | FAIL: 7 live imports remain in `src/omega/backtest/*` |
| `iterrows(` grep in audited scope | PASS: 0 hits |
| PIT safety | FAIL |
| Role compliance | PASS |

**Why verdict is not approved**
- `omega.quant.quant_engine` is not importable because audited modules export/import mismatched symbols.
- `PurgedTimeSeriesSplit` trains on samples after test fold, which is forward leakage.
- `QuantEngine._train_models()` trains on full sample then predicts same full sample before signal generation.
- `ProductionDataPipeline` requires `as_of_time` but never filters dataset to `<= as_of_time`.

---

## Evidence Collected

### 1. Syntax check
Command:
```powershell
$files = @(Get-ChildItem -Path 'src/omega/quant/strategy' -Filter '*.py' | ForEach-Object { $_.FullName })
$files += @(
  (Resolve-Path 'src/omega/quant/performance_tracker.py').Path,
  (Resolve-Path 'src/omega/quant/portfolio.py').Path,
  (Resolve-Path 'src/omega/governance/online_model_updater.py').Path,
  (Resolve-Path 'src/omega/governance/validate_ly_state.py').Path,
  (Resolve-Path 'src/omega/data/production_data_pipeline.py').Path,
  (Resolve-Path 'src/omega/data/vnstock_live.py').Path,
  (Resolve-Path 'src/omega/quant/quant_engine.py').Path
)
python -m py_compile @files
```
Result: no errors.

### 2. `v21_system` grep
Audited scope:
```powershell
rg -n "\bv21_system\b" src/omega/quant/strategy src/omega/quant/performance_tracker.py src/omega/quant/portfolio.py src/omega/governance/online_model_updater.py src/omega/governance/validate_ly_state.py src/omega/data/production_data_pipeline.py src/omega/data/vnstock_live.py src/omega/quant/quant_engine.py
```
Result: no hits.

Repo-wide live imports:
```powershell
rg -n "^\s*(from|import)\s+.*v21_system" src
```
Hits:
- `src/omega/backtest/regime_aware_walk_forward.py:28`
- `src/omega/backtest/regime_aware_walk_forward.py:35`
- `src/omega/backtest/walk_forward_engine.py:26`
- `src/omega/backtest/walk_forward_engine.py:27`
- `src/omega/backtest/walk_forward_engine.py:31`
- `src/omega/backtest/walk_forward_engine.py:35`
- `src/omega/backtest/walk_forward_engine.py:36`

### 3. `iterrows(` grep
Command:
```powershell
rg -n "iterrows\(" src/omega/quant/strategy src/omega/quant/performance_tracker.py src/omega/quant/portfolio.py src/omega/governance/online_model_updater.py src/omega/governance/validate_ly_state.py src/omega/data/production_data_pipeline.py src/omega/data/vnstock_live.py src/omega/quant/quant_engine.py
```
Result: no hits.

### 4. Runtime import repro
Command:
```powershell
python -c "import sys; sys.path.insert(0, 'src'); import omega.quant.quant_engine"
```
Observed failure:
```text
ImportError: cannot import name 'HyperoptConfig' from 'omega.quant.strategy.ml_hyperopt'
```

---

## Findings

### P0: Broken import/export surface makes quant package unusable
**Files**
- `src/omega/quant/strategy/__init__.py:9`
- `src/omega/quant/strategy/__init__.py:10`
- `src/omega/quant/strategy/__init__.py:11`
- `src/omega/quant/strategy/__init__.py:14`
- `src/omega/quant/strategy/__init__.py:16`
- `src/omega/quant/quant_engine.py:55`
- `src/omega/quant/quant_engine.py:56`
- `src/omega/quant/quant_engine.py:59`
- `src/omega/quant/quant_engine.py:61`
- `src/omega/quant/quant_engine.py:66`
- `src/omega/quant/quant_engine.py:68`
- `src/omega/quant/quant_engine.py:71`
- `src/omega/quant/strategy/ml_hyperopt.py:22`
- `src/omega/quant/strategy/ml_models.py:27`
- `src/omega/quant/strategy/model_trainer.py:24`
- `src/omega/quant/strategy/purged_cv.py:24`
- `src/omega/quant/strategy/rl_agent.py:23`
- `src/omega/quant/portfolio.py:8`
- `src/omega/governance/validate_ly_state.py:6`
- `src/omega/data/vnstock_live.py:87`

**Issue**
- `strategy/__init__.py` imports names not defined by audited modules:
  - `HyperoptConfig`, `run_hyperopt` not in `ml_hyperopt.py`
  - `XGBModel`, `LGBModel` not in `ml_models.py` (`XGBEstimator`, `LGBEstimator` exist)
  - `ModelTrainer` not in `model_trainer.py` (`WalkForwardOptunaTrainer` exists)
  - `PurgedTimeSeriesCV` not in `purged_cv.py` (`PurgedTimeSeriesSplit` exists)
  - `RLAgent` not in `rl_agent.py` (`RLPortfolioAgent` exists)
- `quant_engine.py` also imports names not exported by audited modules:
  - `Portfolio` vs `PortfolioOptimizer`
  - `validate_ly_state` vs `validate_ly_state_integrity`
  - `VNStockLive` vs `VnStockLiveDataProvider`

**Impact**
- Direct import of `omega.quant.quant_engine` fails before pipeline can run.
- `py_compile` passed because syntax is valid; runtime is still broken.

### P0: Purged CV leaks future samples into training
**Files**
- `src/omega/quant/strategy/purged_cv.py:97`
- `src/omega/quant/strategy/purged_cv.py:98`
- `src/omega/quant/strategy/purged_cv.py:101`
- `src/omega/quant/strategy/purged_cv.py:104`
- `src/omega/quant/strategy/model_trainer.py:112`
- `src/omega/quant/strategy/model_trainer.py:117`

**Issue**
- `PurgedTimeSeriesSplit.split()` concatenates `train_before` and `train_after`.
- `train_after` contains observations strictly after test fold.
- Docstring claims training data always precedes test data, but code violates contract.
- `WalkForwardOptunaTrainer.objective()` uses this splitter for hyperparameter search.

**Impact**
- Hyperparameter tuning and CV scores are contaminated by future information.
- Institutional PIT claim is false in current implementation.

### P1: QuantEngine generates in-sample predictions for downstream signals
**Files**
- `src/omega/quant/quant_engine.py:401`
- `src/omega/quant/quant_engine.py:402`
- `src/omega/quant/quant_engine.py:403`
- `src/omega/quant/quant_engine.py:407`
- `src/omega/quant/quant_engine.py:410`
- `src/omega/quant/quant_engine.py:414`
- `src/omega/quant/quant_engine.py:439`
- `src/omega/quant/quant_engine.py:447`

**Issue**
- Engine trains on full `feature_matrix` and full `target_vector`.
- Immediately predicts same full `feature_matrix`.
- Those in-sample predictions feed `signal_module.transform()` and later weights.

**Impact**
- Model outputs, signal stats, and experiment IC can look inflated.
- Forward-safe deployment path is not enforced.

### P1: `ProductionDataPipeline` does not enforce `as_of_time`
**Files**
- `src/omega/data/production_data_pipeline.py:80`
- `src/omega/data/production_data_pipeline.py:82`
- `src/omega/data/production_data_pipeline.py:94`
- `src/omega/data/production_data_pipeline.py:112`
- `src/omega/data/production_data_pipeline.py:113`
- `src/omega/data/production_data_pipeline.py:116`
- `src/omega/data/production_data_pipeline.py:120`
- `src/omega/data/production_data_pipeline.py:144`

**Issue**
- Constructor requires `as_of_time` for PIT compliance.
- `run()` reads full parquet, fits sanitizer on full dataset, computes features on full dataset, then writes full dataset.
- No `timestamp <= self.as_of_time` filter exists.

**Impact**
- If source parquet contains future rows, future data contaminates fitted stats, fills, features, validation, and saved output.
- Current PIT guarantee depends on caller pre-truncating data externally, which code does not assert.

### P1: `validate_ly_state.py` has import-time side effects and stale protocol assumptions
**Files**
- `src/omega/governance/validate_ly_state.py:11`
- `src/omega/governance/validate_ly_state.py:23`
- `src/omega/governance/validate_ly_state.py:28`

**Issue**
- Module executes validation immediately at import time.
- On failure it calls `sys.exit(1)`.
- Expected directories are `session`, `memory`, `logs`, which do not match current repo protocol in `AGENTS.md` (`checkpoints` exists; `logs` not specified as required root directory).

**Impact**
- Any future correct import from `quant_engine.py` can terminate process during module import.
- Governance validation can fail on valid state layout.

### P2: `vnstock_live.py` docstring overstates vectorization
**Files**
- `src/omega/data/vnstock_live.py:13`
- `src/omega/data/vnstock_live.py:103`
- `src/omega/data/vnstock_live.py:228`
- `src/omega/data/vnstock_live.py:270`
- `src/omega/data/vnstock_live.py:330`

**Issue**
- File claims “no Python loops”.
- Implementation loops over tickers for fetch, ADV, and volatility.

**Impact**
- Not PIT bug.
- Documentation/compliance claim is inaccurate.

---

## PIT Safety Conclusion

**`iterrows`**: no hits in audited scope.

**No-look-ahead**: failed.
- `purged_cv.py` uses post-test observations in train fold.
- `quant_engine.py` scores same data it trained on.
- `production_data_pipeline.py` does not constrain input to `as_of_time`.

Some components appear PIT-aware in isolation:
- `src/omega/governance/online_model_updater.py` applies strict embargo with `< current_date - embargo_days`.
- `src/omega/data/vnstock_live.py` computes `pit_date = reference_date - timedelta(days=self.config.pit_lag_days)`.
- `src/omega/quant/strategy/regime_conditional.py` clearly separates online filtered probabilities from smoothing path.

Those positives do not offset blockers above.

---

## Final Verdict

**VERDICT: `[NEEDS_FIX]`**

Approval blocked by:
1. Runtime import surface broken across audited quant modules.
2. Confirmed forward leakage in `PurgedTimeSeriesSplit`.
3. In-sample prediction leakage in `QuantEngine`.
4. `ProductionDataPipeline` PIT contract not enforced in code.
