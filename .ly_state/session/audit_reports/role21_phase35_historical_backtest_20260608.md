# L3 Audit Report: OMEGA_PHASE35_HISTORICAL_BACKTEST_20260608

## Metadata
- Session ID: 019ea5c7-ee9d-7db0-9837-128dc9550b0f
- Session Key: bc76147e-82d7-4328-8122-99838fcaffc9
- L2 Session ID: l2-ly-direct-20260607-dashboard

VERDICT: [APPROVED]

## Audit Details
1. **Validation Split Upgrade**:
   - Split `train_df_clean` into `train_actual` (2 years) and `val_actual` (1 year).
   - Alpha IC evaluation, selection, and XGBoost training are PIT-safe and only trained on `train_actual`.
   - ML Gate / Research Gate runs exclusively on `val_actual`, eliminating selection bias.
   - Refactored validation split fallback to dynamically scale with training data length.

2. **Dynamic Portfolio Selection**:
   - `get_top_symbols` upgraded to select liquid universe (ADTV > 5B VND and average close > 5k VND).
   - Prevents look-ahead leak while dynamically adjusting the size of the investable universe.

3. **Backtest Execution Output**:
   - Quick Mode successfully completed and verified data loading.
   - Baseline Backtest Sharpe: **1.2514** (Max DD: -69.09%).
   - XGBoost Backtest Sharpe: **1.9320** (Max DD: -65.00%).
   - Results correctly saved to `data/phase35_results/`.

4. **Wiring of Advanced Features (Drawdown Control)**:
   - Verified that `drawdown_control` and `drawdown_threshold` are correctly routed from the CLI `scripts/run_phase35_backtest.py` to `Phase35WalkForwardEngine`.
   - Verified integration in the Streamlit UI dashboard and backend subprocess executor service (`backtest_executor.py`).
   - Confirmed that running with drawdown control active successfully limits Max DD to **-17.70%** (during verification run) protecting portfolio capital.
   - Executed full test suite: **91/91 PASS** in `tests/phase35/`.

5. **L3 Codex CLI Audit & SRE Corrections**:
   - Resolved P0 label/feature corruption in `scripts/run_weekly_evolution.py` by switching from positional index assignments to explicit joins on `['ticker', 'date']`.
   - Fixed P1 module-level import execution side effects in `src/omega/quant/phase35_walk_forward.py`.
   - Corrected P1 prediction order drift in `phase35_walk_forward.py` by aligning `raw_preds` with `test_df` via explicit `['date', 'ticker']` key merging.
   - Resolved P1 stochastic genetic programming reproduction issues by introducing deterministic random state generator seed routing in `genetic_engine.py`.

---

## L3 Codex CLI Audit: IC Fix Surgical Changes (2026-06-08)

### Scope
4 surgical fixes to `src/omega/quant/phase35_walk_forward.py` to address low IC (0.0070 baseline).

### Fixes Audited

1. **`compute_daily_cs_ic()` method** (lines 229-277):
   - Computes Spearman IC per date cross-sectionally, returns mean of daily ICs
   - Min cross-section threshold (5), NaN handling
   - **PIT Safety**: PASS - uses only test_df data

2. **Cold-start fix** (lines 759-785):
   - Prepends last 30 rows per symbol from train_df to test_df for alpha computation
   - Uses `_is_test` marker to strip warmup rows back after computation
   - **PIT Safety**: PASS - prepends already-embargoed train data only

3. **Raw signal IC tracking** (lines 924-948):
   - Computes `raw_signal_ic` (pooled) and `raw_signal_daily_cs_ic` before Stage 2
   - Z-score normalization applied per-date cross-sectionally
   - **PIT Safety**: PASS - no look-ahead

4. **Metric aggregation** (lines 1041-1042, 1094-1096, 1106-1107):
   - `FoldMetrics` stores `raw_signal_ic`, `raw_signal_daily_cs_ic`
   - `WalkForwardResult` aggregates averages correctly
   - `summary()` displays both metrics

### Backtest Results (8 folds, drawdown control active)
| Metric | Value |
|--------|-------|
| Avg Portfolio IC (post Stage 2) | -0.0063 |
| Avg Raw Signal IC (pre Stage 2) | 0.0038 |
| Avg Raw Signal Daily CS IC | 0.0045 |
| Avg Sharpe | 0.9042 |
| Avg Max DD | -17.72% |

### Test Suite
- **91/91 PASS** in `tests/phase35/`

### VERDICT: [APPROVED] (Round 2)
- PIT Safety: PASS
- Role Compliance: PASS
- Vectorization: PASS (groupby.apply, no nested loops)
- Z-score: PASS (per-alpha BEFORE blend, manual probe verified)
- All surgical fixes correctly implemented, no scope creep

### Codex L3 Re-Audit (Round 2, 2026-06-08T14:09Z)
- Fixed P1: Z-score normalization moved to per-alpha BEFORE `alpha_matrix @ weights`
- Fixed P2: `compute_daily_cs_ic` and `validate_alpha_with_research_gate` vectorized via `groupby.apply()`
- Manual probes: `zscore_blend_allclose=True`, `daily_cs_loop_match=True`
- Tests: 91/91 PASS
