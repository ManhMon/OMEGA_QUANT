# Walk-Forward Validation & Expanded Feature Base for Self-Evolution

This implementation plan adds more basic features to the weekly genetic programming self-evolution script, upgrades the validation scheme to a robust walk-forward train-validate-test setup with strict purge/embargo boundaries, and resolves key bugs identified by the L3 Auditor.

## User Review Required

> [!IMPORTANT]
> - **Purge & Embargo**: To prevent look-ahead bias at split boundaries, we will purge/embargo `TARGET_HORIZON = 5` samples at the end of the Train and Validate splits.
> - **Per-Ticker Feature Engineering**: We will rewrite `prepare_features` to compute rolling windows and percent changes strictly per ticker to prevent ticker data bleed.
> - **GP Operator Bug Fix**: Fix the logical checking order in `GeneticEngine._execute_tree` to ensure time-series operators (e.g. `ts_std`, `ts_mean`) are correctly executed.

## Proposed Changes

### [Self-Evolving Engine]

#### [MODIFY] [run_weekly_evolution.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)

1. **Fix Per-Ticker Feature Engineering**: Group by `ticker` (or `symbol`) for all window calculations in `prepare_features()` to avoid boundary cross-contamination:
   ```python
   # Grouped feature engineering
   result["returns_1d"] = result.groupby("ticker")["close"].pct_change(1)
   result["returns_5d"] = result.groupby("ticker")["close"].pct_change(5)
   result["vol_ratio"] = result["volume"] / (result.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean()) + 1e-9)
   result["hl_range"] = (result["high"] - result["low"]) / (result["close"] + 1e-9)
   result["oc_range"] = (result["close"] - result["open"]) / (result["open"] + 1e-9)
   
   # Add new primitive indicators
   result["rsi_14"] = result.groupby("ticker")["close"].transform(compute_rsi, window=14)
   result["rsi_5"] = result.groupby("ticker")["close"].transform(compute_rsi, window=5)
   result["ma_ratio_5_20"] = (
       result.groupby("ticker")["close"].transform(lambda x: x.rolling(5).mean()) /
       (result.groupby("ticker")["close"].transform(lambda x: x.rolling(20).mean()) + 1e-9)
   )
   result["vol_std_10"] = result.groupby("ticker")["volume"].transform(lambda x: x.rolling(10).std()).fillna(0.0)
   ```

2. **Purged Walk-Forward Split**: Define 3-way time-ordered split with purge/embargo gaps at split boundaries:
   ```python
   def walk_forward_split(df: pd.DataFrame, horizon: int = 5):
       """Split data sequentially with purge zones to avoid boundary leakage."""
       n = len(df)
       idx_val = int(n * 0.6)
       idx_test = int(n * 0.8)
       
       # Train split
       train = df.iloc[:idx_val - horizon].copy()
       # Validate split (purging boundary overlap)
       validate = df.iloc[idx_val:idx_test - horizon].copy()
       # Test split
       test = df.iloc[idx_test:].copy()
       
       return train, validate, test
   ```

#### [MODIFY] [genetic_engine.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/genetic_engine.py)

1. **Fix Operator Routing**: In `_execute_tree()`, route time-series operators first before fallback 2-child binary evaluation:
   ```diff
-        elif len(node.children) == 2:
+        elif len(node.children) == 2 and node.operator in ['ts_std', 'ts_mean', 'ts_rank', 'decay_linear']:
+            child_val = self._execute_tree(node.children[0], features)
+            window = int(self._execute_tree(node.children[1], features)[0])
+            window = max(2, min(window, 60))
+            ...
+        elif len(node.children) == 2:
   ```

## Verification Plan

### Automated Tests
- Run `pytest` to ensure all unit tests pass.
- Execute `python scripts/run_weekly_evolution.py` (with fast parameters) to verify the new features, grouping, and split logic.
- Run SOD gate enforcer: `python scripts/sod_gate_enforcer.py --check-before-push`.

### Manual Verification
- Review `evolved_alphas.json` to confirm the successful evaluation.
