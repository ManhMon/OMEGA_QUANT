# L3 Audit Report: LightGBM Implementation
**Audit ID**: role21_lightgbm_impl_audit_20260523  
**Auditor**: L3-Audit:Role21-Review  
**Date**: 2026-05-23T12:09:51Z  
**Evidence**: .ly_state/session/l2_lightgbm_impl_20260523.md  
**Code Reviewed**:
- `packages/quant/src/omega/quant/ml/ml_engine.py`
- `packages/quant/tests/test_lightgbm_engine.py`

---

## Verdict

# [APPROVED]

All four audit criteria are satisfied. No blocking issues found. Two minor observations noted below (non-blocking).

---

## Audit Criteria Results

### 1. LightGBM Implementation Mirrors XGBoost PIT-Safety — PASS

**Method**: `train_lightgbm()` (line 503) vs `train_xgboost()` (line 408)

Structural parity confirmed point-by-point:

| Concern | XGBoost | LightGBM | Parity |
|---|---|---|---|
| Signature | `model_id, X_train, y_train, X_val, y_val, config, pit_safe=True` | Identical | ✅ |
| Default `pit_safe` | `True` | `True` | ✅ |
| `_validate_chronological_split()` call | Line 434 | Line 532 | ✅ |
| `_attach_pit_metrics()` on train | Line 481 | Line 582 | ✅ |
| `_attach_pit_metrics()` on val | Line 485 | Line 586 | ✅ |
| `val_metrics` fallback to `train_metrics` when no val | Yes | Yes | ✅ |
| `model_type` stamp on return | `MLModelType.XGBOOST` | `MLModelType.LIGHTGBM` | ✅ |
| `ImportError` mock fallback | Yes | Yes | ✅ |
| `feature_importance` populated | `get_score(importance_type="gain")` | `feature_importance(importance_type="gain")` | ✅ |
| Return type | `TrainedModel` | `TrainedModel` | ✅ |

`_attach_pit_metrics()` is the shared helper (line 301) — both paths call it identically. PIT lag=1 is enforced via `AlphaMetrics.with_pit_safety(predictions, actuals, lag=1)`. No divergence.

`train_lightgbm_with_walk_forward()` (line 604) mirrors `train_xgboost_with_walk_forward()` (line 355) with identical fold-iteration logic, champion training, and `_aggregate_walk_forward_metrics()` delegation.

**`TrainedModel.predict()` dispatch** (lines 237–242): LightGBM booster is correctly identified via `isinstance(self.model_artifact, lgb.Booster)` inside a `try/except ImportError` guard. XGBoost dispatch is checked first (no guard needed as it is already imported at that point). Order is correct — no cross-dispatch risk.

---

### 2. Chronological Splitting Enforced — PASS

`_validate_chronological_split()` (line 286) is called as the **first substantive operation** in `train_lightgbm()` (line 532), before any LightGBM import or dataset construction. This matches the XGBoost path exactly.

The guard logic:
```python
if X_train.index.max() >= X_val.index.min():
    raise ValueError("Chronological split violation: X_train must end before X_val begins")
```

This enforces strict non-overlap: the last training date must be strictly before the first validation date. Edge case (equality) correctly raises — a train row dated the same day as the first val row would be a look-ahead violation.

Early returns for `X_val is None`, `X_train.empty`, `X_val.empty` are appropriate — no val set means no split to validate.

Walk-forward path: fold boundaries are derived from `WalkForwardEnsemble.run()` which owns chronological ordering. The fold loop passes `X_train`/`X_val` slices that are already time-ordered by construction. `_validate_chronological_split()` is called again inside each `train_lightgbm()` fold call, providing a second layer of enforcement.

---

### 3. Tests Pass — PASS

**Run**: `python -m pytest tests/test_lightgbm_engine.py -v`  
**Result**: **18/18 passed** (1.07s)

**Run**: `python -m pytest tests/test_ml_engine.py tests/test_ml_gate_validator.py -v`  
**Result**: **26/26 passed** (1.04s, zero regressions)

**Total**: 44/44 passing.

Warnings observed (33 total) are all `RuntimeWarning: invalid value encountered in divide` and `ConstantInputWarning` from numpy/pandas correlation on zero-variance mock data. These are expected artifacts of the `_FakeLGBBooster` returning constant zeros — not indicative of production bugs.

Test class coverage assessment:

| Class | Tests | Verdict |
|---|---|---|
| `TestLightGBMTrainContract` | 5 | Adequate — covers return shape, metrics, feature importance, val vs train metrics, config stamp |
| `TestLightGBMPITSafety` | 3 | Strong — covers enabled/disabled and manual computation match |
| `TestLightGBMChronologicalSplit` | 2 | Adequate — overlap raises, valid split passes |
| `TestLightGBMMockFallback` | 2 | Adequate — fallback type and determinism |
| `TestLightGBMEnsembleCompatibility` | 2 | Adequate — store+ensemble, mixed XGB+LGB |
| `TestLightGBMWalkForward` | 2 | Adequate — champion returned, empty fold skipped |
| `TestLightGBMPredict` | 2 | Adequate — booster dispatch, engine.predict() interface |

---

### 4. No Feature Leakage — PASS

Leakage analysis across all data paths:

**Training data construction**: `X_train` and `y_train` are passed in by the caller. The engine does not construct or modify feature sets internally — no future data can be injected at this layer.

**`lgb.Dataset(X_train, label=y_train, free_raw_data=False)`**: Standard LightGBM dataset construction. `free_raw_data=False` retains the raw data for potential re-use but does not introduce leakage.

**Validation reference**: `lgb.Dataset(X_val, label=y_val, reference=dtrain, free_raw_data=False)` — `reference=dtrain` is the correct LightGBM pattern for sharing bin boundaries from train to val. This does NOT leak val labels or features into training; it only aligns feature binning. This is the standard and correct usage.

**Metrics computation**: `train_pred = model.predict(X_train)` and `val_pred = model.predict(X_val)` are computed after training completes. Predictions on training data are used only for `train_metrics` (not returned as `model.metrics`). `model.metrics` is set to `val_metrics` when a val set is provided — correct.

**PIT metrics**: `_attach_pit_metrics()` applies a lag-1 shift to predictions before computing `pit_ic`/`pit_rank_ic`. This is an evaluation-only operation on already-generated predictions — no training data contamination.

**Walk-forward**: Fold boundaries are set by `WalkForwardEnsemble` before any model training. The fold loop slices `walk_forward_data` by date masks derived from `fold.train_end` / `fold.val_start`. Train and val windows are non-overlapping by construction. The champion is trained on the full `X[feature_names]` / `y` — this is correct; the champion is the production model, not a fold model.

**`_build_walk_forward_frame()`**: Adds `forward_return` (= `y.values`) and a constant `symbol` column. No future-looking transformations applied.

No leakage vectors identified.

---

## Minor Observations (Non-Blocking)

### OBS-1: `n_estimators` passed as both param and `num_boost_round`

In `train_lightgbm()`:
```python
params = {
    ...
    "n_estimators": config.n_estimators,  # line ~547
    ...
}
model = lgb.train(
    params,
    dtrain,
    num_boost_round=config.n_estimators,  # line ~567
    ...
)
```

`n_estimators` is not a valid LightGBM `lgb.train()` param key — it is silently ignored by LightGBM (which uses `num_boost_round` from the function argument). The effective value is correct (`num_boost_round` wins), but the redundant key in `params` is misleading. This is a cosmetic issue with no functional impact. Recommend removing `"n_estimators"` from the `params` dict in a follow-up cleanup.

### OBS-2: `test_pit_metrics_populated` does not assert non-zero values

`TestLightGBMPITSafety::test_pit_metrics_populated` asserts only `isinstance(model.metrics.pit_ic, float)`. Since `_FakeLGBBooster.predict()` returns constant zeros, `pit_ic` will be `0.0` (correlation of a constant series is undefined → falls back to `0.0`). The test passes but does not distinguish between "PIT computed and happened to be zero" vs "PIT not computed". `test_pit_metrics_match_manual_computation` (which uses `_CapturingBooster` with a non-constant signal) provides the stronger coverage. Net: coverage is adequate, but `test_pit_metrics_populated` is a weaker assertion than its name implies. Non-blocking.

---

## Summary

| Criterion | Result |
|---|---|
| LightGBM mirrors XGBoost PIT-safety | ✅ PASS |
| Chronological splitting enforced | ✅ PASS |
| Tests pass (18 LGB + 26 regression) | ✅ PASS |
| No feature leakage | ✅ PASS |

**Verdict: [APPROVED]**

Implementation is production-ready. OBS-1 (`n_estimators` in params dict) is recommended for cleanup in a follow-up PR but does not block approval.
