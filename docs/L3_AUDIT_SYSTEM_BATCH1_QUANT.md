# L3 Audit Report: System Batch 1 — Quant Math, Alphas & Neutralization

| Field | Value |
|:------|:------|
| **Audit Date** | 2026-05-28 |
| **Auditor Role** | Code Reviewer (Role 21) |
| **Platform** | Codex (L3) |
| **Scope** | src/omega/quant/ (alpha_discovery.py, alpha_factory.py, alpha_preprocessing.py, neutralization.py, neutralization_engine.py, lightweight_neutralization.py, phase35_walk_forward.py, model_module.py, core_alphas.py) |
| **Verdict** | **[APPROVED]** |
| **PIT Safety** | PASS |
| **l3_session_id** | codex-batch1-quant-20260528T140200Z |
| **l3_session_key** | codex:role21:batch1-quant:20260528T140200Z |

---

## 1. Look-Ahead Bias (shift without embargo)

| File | Finding | Status |
|:-----|:--------|:-------|
| `core_alphas.py` | All alphas use `groupby(symbol_col).shift(1)` — T-1 lag enforced | PASS |
| `alpha_factory.py` | `close_lagged = df.groupby(symbol_col)["close"].shift(1)` | PASS |
| `alpha_discovery.py:565` | `grouped.shift(-horizon)` used ONLY in `compute_future_returns()` for TARGET label generation, not feature computation | PASS (acceptable) |
| `alpha_discovery.py:1085` | `df.groupby('ticker')[feature_cols].shift(1)` — features shifted T-1 before use | PASS |
| `phase35_walk_forward.py` | Embargo logic drops last `h` rows per symbol from train before IC computation | PASS |
| `model_module.py` | Train/eval split by timestamp (chronological, no shuffle). Neutralization fit on train only, applied to eval | PASS |

**Verdict**: No look-ahead bias detected. `shift(-horizon)` is used exclusively for target label computation (forward returns), never for feature generation.

---

## 2. Vectorization (iterrows/itertuples anti-patterns)

| File | Finding | Status |
|:-----|:--------|:-------|
| `alpha_discovery.py:985` | `for idx, row in decayed.iterrows()` — used for I/O side-effect (reject_feature call), not numeric computation | P2 (acceptable, non-blocking) |
| `model_module.py:437-442` | Gradient descent loop over train samples — inherent to algorithm, not vectorizable without matrix refactor | P2 (acceptable) |
| All other files | 100% vectorized via Pandas/NumPy groupby, rolling, matrix operations | PASS |

**Verdict**: No critical vectorization violations. Two P2 observations are non-blocking (I/O side-effect loop and gradient descent training loop).

---

## 3. Division-by-Zero Guards & NaN Handling

| File | Pattern | Status |
|:-----|:--------|:-------|
| `core_alphas.py` | `_safe_divide()` replaces 0 with `np.nan`, returns `fill_value=0.0` | PASS |
| `neutralization.py:83` | `(series - mean) / (std + epsilon)` with `epsilon=1e-9` | PASS |
| `neutralization_engine.py:83` | Same pattern `(std + epsilon)` | PASS |
| `lightweight_neutralization.py:72` | Same pattern `(std + epsilon)` | PASS |
| `neutralization.py:299` | `r2 = 1.0 - (ss_res / ss_tot)` guarded by `if ss_tot > 1e-10` | PASS |
| `model_module.py:299-301` | `if std_p == 0 or std_a == 0: return 0.0` before IC division | PASS |
| `model_module.py:311` | `if std_r == 0: return 0.0` before Sharpe division | PASS |
| `model_module.py:327` | `if peak > 0` before drawdown division | PASS |
| `phase35_walk_forward.py:498` | `if std_return == 0 or np.isnan(std_return): return 0.0` | PASS |

**Verdict**: All division operations are properly guarded against zero denominators and NaN propagation.

---

## 4. OLS/Ridge Regression Soundness (Neutralization)

| Check | Status | Evidence |
|:------|:-------|:---------|
| OLS formula correct | PASS | `beta = (X'X)^-1 X'y` at `neutralization.py:288` |
| Regularization for numerical stability | PASS | `XtX += np.eye(XtX.shape[0]) * 1e-8` prevents singular matrix |
| Fallback to pseudo-inverse | PASS | `np.linalg.lstsq(X_with_intercept, y, rcond=None)[0]` on `LinAlgError` |
| Intercept included | PASS | `X_with_intercept = np.column_stack([np.ones(len(X)), X])` |
| Intercept excluded from betas | PASS | `return beta[1:], r2` skips intercept coefficient |
| R² computation | PASS | `1.0 - (ss_res / ss_tot)` with `ss_tot > 1e-10` guard |
| Ridge in model_module | PASS | L2 gradient: `2.0 * cfg.l2_lambda * weights[k]` added to weight gradient |
| Split-aware neutralization | PASS | `_neutralize_split()` fits on train, applies betas to eval — no data leakage |

**Verdict**: OLS and Ridge implementations are mathematically sound with proper regularization and fallback mechanisms.

---

## 5. Test Results

| Metric | Value |
|:-------|:------|
| Total Tests | 280 |
| Passed | 280 |
| Failed | 0 |
| Warnings | 147 (non-blocking deprecation + ConstantInputWarning on synthetic data) |

---

## 6. P2 Observations (Non-Blocking)

| ID | File | Description | Recommendation |
|:---|:-----|:------------|:---------------|
| P2-1 | `alpha_discovery.py:985` | `iterrows` used for `reject_feature()` I/O side-effect | Consider `apply()` for cleaner style |
| P2-2 | `model_module.py:437` | Python-loop gradient descent | Acceptable for small feature sets; consider NumPy matrix ops for >100 features |

---

## 7. Final Verdict

**[APPROVED]**

All 9 target files pass PIT safety, division-by-zero, NaN handling, and regression soundness checks. No critical look-ahead bias or vectorization violations found. 280/280 tests pass cleanly.

---

*Signed-off by: L3 Code Reviewer (Role 21) | Codex | 2026-05-28*
