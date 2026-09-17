## Gate

`GP_WEEKLY_EVOLUTION_PREPARED_DATA_DEBUG`

## Scope

Inspected `scripts/run_weekly_evolution.py` lines `66-129`, `215-226`, `277-453`.
Ran a diagnostic reproduction on the full dataset loaded by `load_market_data()`.

## Executive finding

The collapse from `1,776,743` raw rows to `2,781` prepared rows is **not primarily caused by float32 downcast** and **not primarily caused by the general idea of dropping rows with any NaN across many columns**.

The dominant root cause is a **feature construction bug in `compute_mfi()`**:

- `scripts/run_weekly_evolution.py:222-223`
- `pd.Series(pos_mf)` and `pd.Series(neg_mf)` are created with a fresh `RangeIndex`
- those series are then assigned back into each per-ticker `group` at `prepare_features()` line `329`
- pandas aligns by index labels on assignment
- only the first ticker group (`AAA`) has index labels overlapping the new `RangeIndex`
- almost every other ticker receives `NaN` for `mfi_14`
- `mfi_14` is included in `FEATURE_COLUMNS` and therefore in the final all-columns validity mask at `scripts/run_weekly_evolution.py:446-450`

This single poisoned feature explains why only one ticker survives.

## Evidence

Diagnostic reproduction on full dataset:

- Raw rows: `1,776,743`
- Final survivors with current logic: `2,781`
- Tickers total: `703`
- Tickers with any surviving rows: `1`
- Surviving ticker: `AAA` only
- `AAA` rows: `2,859`
- `AAA` surviving rows: `2,781`

Key NaN counts across required columns:

- `mfi_14`: `1,773,885` NaNs
- `alt_body_ratio`: `491,036` NaNs
- `alt_upper_shadow`: `491,036` NaNs
- `alt_lower_shadow`: `491,036` NaNs
- `alt_clv`: `491,036` NaNs
- `ma_ratio_10_50`: `35,125` NaNs
- `roc_20`: `14,763` NaNs
- `realized_vol_20`: `14,763` NaNs

Critical contrast:

- Survivors requiring all base features + targets: `2,799`
- Survivors requiring all alt features only: `1,228,056`
- Rows valid on base features/targets but invalid on alt features: `18`

Interpretation:

- The base feature set is the bottleneck.
- Alternative features contribute a tiny additional loss (`18` rows), not the main collapse.
- `mfi_14` dominates the collapse.

## Requested questions

### 1. What columns are in `FEATURE_COLUMNS`?

`FEATURE_COLUMNS` is defined at `scripts/run_weekly_evolution.py:66-105`.

It contains `114` base feature columns:

`open`, `high`, `low`, `close`, `volume`, `returns_1d`, `returns_5d`, `returns_10d`, `returns_3d`, `vol_ratio`, `vol_trend_5_20`, `hl_range`, `oc_range`, `rsi_14`, `rsi_5`, `rsi_21`, `ma_ratio_5_20`, `vol_std_10`, `close_range_ratio`, `macd_line`, `macd_signal`, `macd_hist`, `roc_10`, `roc_20`, `realized_vol_20`, `bollinger_w_20`, `williams_r_14`, `mfi_14`, `cci_14`, `obv_norm`, `force_index_13`, `ma_ratio_10_50`, `close_to_ema_10`, `close_to_ema_20`, `vn_vol_shock_5d`, `vn_ceil_limit_proximity`, `vn_floor_limit_proximity`, `vn_hit_ceil`, `vn_hit_floor`, `vn_atc_vol_ratio`, `vn_liquidity_concentration`, `vn_price_continuity`, `vn_intraday_reversal`, `vn_gap_fill_ratio`, `vn_amihud_liq_reversal`, `vn_volume_shock_reversal`, `vn_turnover_exhaustion`, `vn_trapped_inventory_2d`, `vn_cash_release_t3`, `vn_freeze_ratio_20`, `vn_sector_rel_momentum_20`, `vn_sector_rel_momentum_60`, `vn_mom_5_20`, `vn_mom_20_60`, `vn_mom_60_120`, `vn_acceleration_index`, `vn_smart_money_proxy`, `vn_retail_panic_proxy`, `vn_accumulation_dist`, `vn_volume_weighted_return`, `vn_obv_change_20`, `vn_whale_net_flow`, `vn_rsi_7`, `vn_rsi_28`, `vn_rsi_crossover_5_20`, `vn_rsi_crossover_20_120`, `vn_rsi_crossover_60_120`, `vn_bb_dist_10`, `vn_bb_dist_20`, `vn_bb_dist_40`, `vn_bb_dist_60`, `vn_bb_dist_120`, `vn_macd_crossover`, `vn_bollinger_snapback`, `vn_kyle_lambda_20`, `vn_liquidity_provision_ratio_10`, `vn_tick_signed_volume_imbalance_5`, `vn_volume_clock_acceleration_10`, `vn_price_impact`, `vn_atr_14_norm`, `vn_yang_zhang_vol_20`, `vn_wick_ratio`, `vn_market_correlation`, `vn_pair_correlation`, `vn_stock_sector_corr`, `vn_market_regime`, `vn_leverage_proxy`, `vn_squeeze_signal`, `vn_expiry_effect`, `vn_sector_neutral_residual_reversion`, `vn_sentiment_vibert_1d`, `vn_sentiment_vibert_5d_decay`, `vn_sentiment_vibert_20d_ma`, `vn_news_volume_shock`, `vn_atc_vol_ratio_v2`, `vn_morning_gap_v2`, `vn_vol_trend_shock_v2`, `vn_intraday_vol_morning`, `vn_foreign_net_flow_5d`, `vn_retail_sentiment_proxy`, `vn_pe_ratio_pit`, `vn_pb_ratio_pit`, `vn_ev_ebitda_pit`, `vn_roe_pit`, `vn_debt_equity_pit`, `vn_roa_pit`, `vn_earnings_growth_yoy`, `vn_earnings_growth_qoq`, `vn_ps_ratio_pit`, `vn_dividend_yield_pit`, `vn_asset_turnover_pit`, `vn_current_ratio_pit`, `vn_accruals_quality`, `vn_market_fundamental_drift`.

### 2. Are feature columns computed per ticker with `groupby.shift`, creating NaN for first row per ticker?

Yes.

- Base features are computed inside the per-ticker loop at `scripts/run_weekly_evolution.py:285-367`.
- Then a T-1 lag is applied to every base feature with `result.groupby("ticker")[col].shift(1)` at `scripts/run_weekly_evolution.py:402-406`.
- Alternative features receive the same per-ticker lag at `scripts/run_weekly_evolution.py:428-431`.
- Targets are computed per ticker at `scripts/run_weekly_evolution.py:433-439`.

This does create expected NaNs:

- first row per ticker from lagged features
- early rows from rolling windows like `20`, `50`, `60`, `120`
- last `3`, `5`, `10` rows per ticker from forward targets

These expected NaNs are normal and should reduce row count somewhat. They do **not** explain collapse to one surviving ticker.

### 3. Is the NaN mask too aggressive, dropping rows where any of 100+ columns is NaN?

Mechanically: yes.

- `drop_cols` is built at `scripts/run_weekly_evolution.py:443-446`
- all required columns are enforced by `_all_notna_mask(result, drop_cols)` at `scripts/run_weekly_evolution.py:448-450`

Semantically: this is **not the primary bug** behind the `2,781` rows.

Why:

- With current code, the base-feature+target requirement already yields only `2,799` rows.
- Adding alternative features reduces that only from `2,799` to `2,781`.

So the all-columns mask is strict, but the catastrophic collapse is already present before alternative features matter.

The strict mask becomes catastrophic because `mfi_14` is broken for almost the whole dataset.

### 4. Should we only drop on essential features and target, not all columns?

For model training robustness: likely yes, especially if some optional feature families are allowed to be sparse.

For this specific incident: changing the drop set alone would **not** fix the main problem unless `mfi_14` were excluded.

Evidence:

- Requiring only targets gives `1,769,010` rows.
- Requiring the first `39` core features + targets gives `2,799` rows.
- Requiring all `114` base features + targets also gives `2,799` rows.

Interpretation:

- The row collapse is already caused inside the core feature set.
- The main offender is `mfi_14`, not the later optional VN-alpha block.

## Exact suspected issues

### Primary issue: `compute_mfi()` loses ticker-local index

`scripts/run_weekly_evolution.py:215-226`

Problem lines:

- `222`: `pos_mf_sum = pd.Series(pos_mf).rolling(window).sum()`
- `223`: `neg_mf_sum = pd.Series(neg_mf).rolling(window).sum()`

Why this is wrong in context:

- inside `prepare_features()`, each `group` preserves the original global row index from the sorted full frame
- `pd.Series(pos_mf)` creates a new `RangeIndex(0..n-1)` instead of reusing `group.index`
- assigning the resulting `mfi` series back via `group["mfi_14"] = compute_mfi(group, 14)` at `scripts/run_weekly_evolution.py:329` triggers label alignment
- for non-first tickers, most or all labels do not match, so assigned values become `NaN`

Why only `AAA` survives:

- after `result.index = pd.RangeIndex(len(result))` at `scripts/run_weekly_evolution.py:281`, first ticker `AAA` occupies index labels starting at `0`
- the temporary `RangeIndex` produced in `compute_mfi()` overlaps only for that first group
- later ticker groups have indices outside `0..len(group)-1`, so overlap disappears

### Secondary issue: all-or-nothing NaN filter amplifies single-feature failures

`scripts/run_weekly_evolution.py:443-450`

Problem lines:

- `446`: `drop_cols = FEATURE_COLUMNS + available_alt + target_cols`
- `449`: `valid_mask = _all_notna_mask(result, drop_cols)`

This means one corrupted column can wipe out almost the whole frame.

### Per-ticker lag / target NaNs are expected, not root cause

`scripts/run_weekly_evolution.py:402-406`, `428-431`, `433-439`

These add predictable warm-up and tail-loss NaNs, but that alone should still leave a very large fraction of `1.77M` rows, not `0.16%`.

## Float32 downcast check

Checked the hypothesis around `scripts/run_weekly_evolution.py:441`.

Targets are computed first at `433-439`, then `_downcast_float64_columns(result)` runs at `441`.

So the specific concern "downcast on `close` before `pct_change`" does **not** happen in this function.

Precision test comparing target computation from `float64` vs `float32` close values:

- `target_h3` max abs diff: `5.95984623874557e-08`
- `target_h5` max abs diff: `1.1559688672946322e-07`
- `target_h10` max abs diff: `2.243939567492248e-07`
- mean abs diffs were all about `2e-08`

Conclusion:

- float32 downcast is negligible here
- not a credible explanation for losing `~99.84%` of rows

## Bottom line

Most likely causal chain:

1. `compute_mfi()` creates misindexed rolling series at `222-223`.
2. `mfi_14` becomes `NaN` for nearly every ticker except the first one.
3. `mfi_14` is included in `FEATURE_COLUMNS`.
4. `_all_notna_mask()` at `449` drops every row with `mfi_14` missing.
5. Result: only `AAA` contributes rows, yielding about `2,781` survivors.

## Recommended next debugging focus

If follow-up work is approved, first verify/fix `compute_mfi()` index preservation before changing global NaN-drop policy. The drop policy may still deserve redesign, but it is secondary for this incident.
