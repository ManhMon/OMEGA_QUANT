# GP Evolution V3 Improvement Plan - 2026-07-03

## Inspection Summary

### A. `scripts/genetic_alpha_evolution_v3.py`

Current GP terminal features are hard-coded in `FEATURE_COLS`:

- Raw OHLC: `open`, `high`, `low`, `close`
- Raw liquidity: `volume`
- Returns/liquidity transforms: `returns_1d`, `returns_5d`, `vol_ratio`
- Range transforms: `hl_range`, `oc_range`

Evidence:

- `FEATURE_COLS` includes raw OHLC at lines 36-47.
- `hl_range = (high - low) / close`, `oc_range = (close - open) / close` at lines 78-79.
- All `FEATURE_COLS` are shifted by ticker at line 80, so V3 script features are T-1 lagged.
- `features_train` and `features_test` are built only from `FEATURE_COLS` at lines 168 and 171.
- `features_train["__date__"]` is added at line 169; `features_test` does not include `__date__`.

Test IC is computed as one pooled Spearman correlation over all test rows:

- Execute evolved tree on `features_test`: line 214.
- Replace NaN/Inf with 0: line 215.
- Reject constant signal: lines 216-217.
- `ic, _ = spearmanr(signal, target_test)`: line 218.
- `hit = sign(signal) == sign(target_test)`: line 219.

There is no size or sector neutralization in the V3 script. The only "orthogonalization" is a training-time penalty against raw `open/high/low/close/volume`:

- `ORTHO_BASELINE_COLS = ["open", "high", "low", "close", "volume"]`: line 48.
- `ortho_baseline_set` built from these columns at line 173.
- Passed into `GPConfig` at lines 197-199.

This is not neutralization. It does not regress out `log_market_cap` or sector dummies, and it does not residualize `fwd_ret_5`.

Liquidity filtering exists only indirectly in `Phase35DataLoader`:

- V3 calls `load_and_prepare(... top_n_symbols=15 ...)` at lines 67-72.
- Loader selects top symbols at `scripts/phase35_data_loader.py:785-787`.
- Loader `get_top_symbols` filters by ADTV >= 5B VND and avg close >= 5000 VND at lines 231-249, with fallback at lines 252-258.

There is no row-level `avg_volume > threshold` filter in V3 evaluation.

### B. `src/omega/quant/evolution/genetic_engine.py`

Current fitness flow:

1. Execute GP tree: line 331.
2. Reject constant alpha: lines 339-343.
3. Winsorize 1 percent to 99 percent: lines 345-348.
4. Global z-score normalize: lines 350-354.
5. Check pooled observations against `min_observations`: lines 356-362.
6. Compute IC via `_compute_combined_ic`: line 365.
7. `ic_score = ic * valid_fraction`: line 377.
8. Turnover penalty = sign changes in flattened row order, not per ticker/date turnover: lines 379-384.
9. Complexity penalty: lines 386-394.
10. Diversity penalty against HoF alpha correlations: lines 396-425.
11. Orthogonalization penalty against configured baseline signals: lines 427-457.
12. Final fitness = `ic_score - complexity - diversity - turnover - orthogonalization`: lines 459-466.

Current evaluation window structure:

- `GPConfig.use_icir` defaults false, `icir_window=20`: lines 267-268.
- V3 enables `use_icir=True`, `icir_window=20` at `scripts/genetic_alpha_evolution_v3.py:195-196`.
- `_precompute_date_chunks` groups `__date__` into contiguous chunks of `icir_window` unique dates: `genetic_engine.py:780-788`.
- `_compute_combined_ic` computes Spearman IC per 20-date chunk and returns `mean(chunk_ics) / std(chunk_ics)` when `use_icir=True`: lines 496-515 and fast path lines 518-565.
- If no ICIR path, it computes one pooled Spearman IC: lines 489-494 and 601.
- Multi-target mode exists, but only weighted pooled Spearman per horizon: lines 603-626.
- `evolve` randomly samples 100,000 rows per generation when target length is large: lines 975-985. Because this sampling is row-random, any date chunks after sampling can lose chronological density and should not be used for final fold IR.

There is no K=3 chronological train-fold IR. Existing ICIR is 20-date chunk IR, not the requested train split into 3 contiguous time folds.

### C. `src/omega/quant/evolution/feature_adapter.py`

The file exists. It is not imported by `scripts/genetic_alpha_evolution_v3.py`.

Feature preparation:

- Loads alpha arsenals best effort: ultimate, phase34, vn_specific at lines 72-120.
- Adds all produced alpha columns at lines 169-202.
- Adds raw base OHLCV `["open", "high", "low", "close", "volume"]` at lines 204-208.
- Computes engineered `ret_1d`, `ret_5d`, `vol_ratio`, `hl_range`, `oc_range` at lines 210-221.
- Applies variance filter and converts numeric arrays to float64 at lines 225-244.
- Keeps top-N by standard deviation at lines 248-252.

Issues:

- Raw OHLC are passed through.
- Engineered features are not shifted inside the adapter; `pct_change`, rolling volume, `hl_range`, and `oc_range` are same-row features unless caller pre-lags the input.
- There is no size or sector neutralization.
- There are no `cs_zscore(hl_range)` or `cs_zscore(oc_range)` terminal features.

## Implementation Plan

### 1. Remove raw OHLC terminals and add stationary range terminals

File: `scripts/genetic_alpha_evolution_v3.py`

Change:

- Replace `FEATURE_COLS` with:
  - `volume`
  - `returns_1d`
  - `returns_5d`
  - `vol_ratio`
  - `hl_range`
  - `oc_range`
  - `hl_range_cs_z`
  - `oc_range_cs_z`
- Remove `open/high/low/close` from `FEATURE_COLS`.
- Replace `ORTHO_BASELINE_COLS` with either `["volume", "vol_ratio"]` or remove it entirely. Do not penalize against raw OHLC if raw OHLC are no longer valid terminals.
- Add helper:
  - `_cs_zscore_by_date(df, col) -> pd.Series`
  - Implementation: `df.groupby("date")[col].transform(lambda s: (s - s.mean()) / (s.std(ddof=0) + 1e-9))`
- In `load_dataset()`:
  - Keep raw OHLC in `df` for computing features and target only.
  - Compute:
    - `hl_range = (high - low) / close.clip(lower=1e-9)`
    - `oc_range = (close - open) / close.clip(lower=1e-9)`
    - `hl_range_cs_z = cs_zscore_by_date(hl_range)`
    - `oc_range_cs_z = cs_zscore_by_date(oc_range)`
  - Shift only `FEATURE_COLS` by ticker exactly once after these calculations.

Verification:

- Add a test that imports `scripts.genetic_alpha_evolution_v3.FEATURE_COLS` and asserts `{"open", "high", "low", "close"}` are absent.
- Assert `{"hl_range", "oc_range", "hl_range_cs_z", "oc_range_cs_z"}` are present.

File: `src/omega/quant/evolution/feature_adapter.py`

Change:

- Replace `base_features = ["open", "high", "low", "close", "volume"]` with `base_features = ["volume"]`.
- Add `hl_range_cs_z` and `oc_range_cs_z`.
- Shift adapter base/engineered features by ticker before appending:
  - `eng[engineered_cols] = eng.groupby("ticker")[engineered_cols].shift(1)`
- Keep external alpha arsenal outputs unchanged because their own modules own PIT safety.

Verification:

- Extend `tests/test_feature_adapter_nonnumeric.py`:
  - Assert raw OHLC keys do not appear in `compute_all()`.
  - Assert range and cs-z range keys appear when `top_n_features` is large enough.
  - Assert output arrays are finite float64.

### 2. Add size and sector neutralization before IC

File: `scripts/genetic_alpha_evolution_v3.py`

Change:

- Load sector mapping from `data/sector_mapping_level2.csv`:
  - `symbol,sector`
  - `df["sector"] = df["ticker"].map(sector_map).fillna("Unknown")`
- Add `log_market_cap`:
  - Preferred if a real `market_cap` column exists: `np.log1p(df["market_cap"])`.
  - Current warehouse path exposes OHLCV; fallback proxy: `np.log1p(df["close"] * df["volume"])`.
  - Shift `log_market_cap` by ticker one day before use in evaluation metadata.
- Add metadata to train/test features:
  - `features_train["__date__"] = train_df["date"].values`
  - `features_train["__sector__"] = train_df["sector"].values`
  - `features_train["__log_market_cap__"] = train_df["log_market_cap"].values`
  - same keys for `features_test`; currently `features_test` lacks `__date__`, which blocks per-date neutralized test IC.

File: `src/omega/quant/evolution/genetic_engine.py`

Change:

- Extend `GPConfig`:
  - `neutralize_size_sector: bool = False`
  - `neutralize_min_cross_section: int = 8`
  - `neutralize_size_key: str = "__log_market_cap__"`
  - `neutralize_sector_key: str = "__sector__"`
- Add helper `_residualize_size_sector(values, features, mask) -> np.ndarray`:
  - Work per date using `features["__date__"]`.
  - Valid rows require finite `values`, finite `__log_market_cap__`, non-null sector, and liquidity mask true if present.
  - For each date:
    - Build design matrix `X = [intercept, log_market_cap, sector_dummies(drop_first=True)]`.
    - If rows < `max(neutralize_min_cross_section, X_cols + 1)`, fallback to date demean.
    - Else solve OLS with `np.linalg.lstsq(X, y, rcond=None)`.
    - Store residuals.
- In `_compute_combined_ic`, before Spearman:
  - Build evaluation mask.
  - If `neutralize_size_sector=True`, residualize both `alpha_series` and target using the same controls.
  - Compute IC on residual alpha vs residual target.
- Apply the same neutralization helper in the ICIR and multi-fold paths.

Why inside engine:

- It keeps training fitness and test scoring consistent.
- It avoids duplicating residualization in script and engine.
- It uses `__` metadata keys, so neutralization controls never become GP terminals because `evolve()` excludes keys starting with `__` at line 955.

Verification:

- Add `tests/quant_test_genetic_engine.py::test_size_sector_neutralization_removes_common_exposure`.
- Synthetic setup:
  - `alpha = true_signal + 3 * log_market_cap + sector_effect`
  - `target = true_signal + 2 * log_market_cap + sector_effect`
  - With neutralization disabled, IC is inflated.
  - With neutralization enabled and `true_signal` removed, IC collapses near zero.
  - With `true_signal` retained in both, IC remains positive after neutralization.

### 3. Implement K=3 chronological multi-fold IR fitness

File: `src/omega/quant/evolution/genetic_engine.py`

Change:

- Extend `GPConfig`:
  - `use_time_fold_ir: bool = False`
  - `time_folds: int = 3`
  - `min_fold_observations: int = 100`
  - `fold_ir_std_floor: float = 1e-9`
- Add helper `_compute_time_fold_ir(alpha_series, target, features, config, mask) -> float`:
  - Require `__date__`.
  - Sort unique dates ascending.
  - Split into `np.array_split(unique_dates, config.time_folds)`.
  - For each fold:
    - Select rows whose date is in fold and pass liquidity mask.
    - Apply size+sector neutralization inside that fold if enabled.
    - Compute Spearman IC for that fold.
  - Require at least 2 valid fold ICs.
  - Return `mean(fold_ics) / (std(fold_ics, ddof=1) + fold_ir_std_floor)`.
  - If std is effectively zero and mean positive, cap to `mean / floor` is too explosive. Use `std = max(std, 0.01)` or return `mean` when std < floor. Recommended: `fitness_ic = mean_ic / max(std_ic, 0.01)` to prevent single stable tiny IC from dominating.
- In `_compute_combined_ic`, make `use_time_fold_ir` take precedence over existing `use_icir`.
- In V3 script, set:
  - `use_time_fold_ir=True`
  - `time_folds=3`
  - `use_icir=False`

Important:

- Existing 100,000-row random generation sample at `genetic_engine.py:975-985` can corrupt chronological fold composition if active.
- For time-fold IR, replace row-random subsample with date-stratified subsample:
  - sample dates or sample rows within each fold after folds are defined.
  - Minimum change: if `use_time_fold_ir=True`, skip random subsampling unless memory forces it.

Verification:

- Add `tests/quant_test_genetic_engine.py::test_time_fold_ir_uses_three_chronological_folds`.
- Synthetic 90 dates, 3 tickers/day:
  - stable alpha positive in all 3 folds gets higher fitness than alpha with one strong fold and two weak/negative folds.
- Assert engine history `best_ic` equals fold IR path when enabled.

### 4. Add avg-volume liquidity filter

File: `scripts/genetic_alpha_evolution_v3.py`

Change:

- Add CLI:
  - `--min-avg-volume`, type float, default `500000.0`
  - `--avg-volume-window`, type int, default `20`
- In `load_dataset(min_avg_volume, avg_volume_window)`:
  - Compute trailing volume:
    - `avg_volume = df.groupby("ticker")["volume"].transform(lambda s: s.rolling(avg_volume_window, min_periods=5).mean())`
    - `avg_volume = avg_volume.groupby(df["ticker"]).shift(1)`
  - Keep `avg_volume` as metadata, not terminal.
  - Define `liquidity_mask = avg_volume > min_avg_volume`.
  - Do not drop rows before calculating returns/ranges; instead filter rows after all shifted features and target exist.
  - Persist rows with `liquidity_mask=True`.
- Add metadata:
  - `features_train["__liquidity_mask__"] = train_df["liquidity_mask"].values`
  - same for test.

File: `src/omega/quant/evolution/genetic_engine.py`

Change:

- Add helper `_evaluation_mask(alpha_series, target, features)`.
- Include `features.get("__liquidity_mask__", True)` in all IC masks.
- Observation threshold must count rows after liquidity filtering.

Verification:

- Add `tests/quant_test_genetic_engine.py::test_liquidity_mask_excludes_low_volume_rows_from_ic`.
- Synthetic setup:
  - Low-volume rows have misleading perfect alpha.
  - High-volume rows have neutral/weak alpha.
  - With mask enabled, IC reflects only high-volume rows.

### 5. Make test IC match training IC semantics

File: `scripts/genetic_alpha_evolution_v3.py`

Change:

- Replace direct pooled `spearmanr(signal, target_test)` at line 218.
- Add helper:
  - `score_individual(ind, features, target, config) -> tuple[ic_or_ir, hit_rate]`
- Reuse `GPIndividual._compute_combined_ic(signal, target, features, config)` after preprocessing signal the same way as `evaluate()`:
  - finite coverage
  - winsorize
  - z-score
  - neutralization
  - liquidity mask
  - K=3 fold IR if configured
- For hit rate, apply liquidity mask and use neutralized or raw target consistently. Recommended: compute hit on filtered raw target only, report as secondary diagnostic.

Verification:

- Add test or smoke script that scores the same individual through train/test helper and engine helper with matching config.

## Exact File Change Checklist

- `scripts/genetic_alpha_evolution_v3.py`
  - Update `FEATURE_COLS`.
  - Remove raw OHLC from terminal set.
  - Add range cs-z features.
  - Add sector map load.
  - Add `log_market_cap` metadata.
  - Add trailing `avg_volume` liquidity mask and CLI args.
  - Pass `__date__`, `__sector__`, `__log_market_cap__`, `__liquidity_mask__` to train and test features.
  - Configure `GPConfig(neutralize_size_sector=True, use_time_fold_ir=True, time_folds=3, use_icir=False)`.
  - Replace pooled test Spearman with engine-consistent score helper.

- `src/omega/quant/evolution/genetic_engine.py`
  - Add `GPConfig` fields for neutralization, liquidity mask, and time-fold IR.
  - Add evaluation mask helper.
  - Add per-date size+sector residualization helper using `np.linalg.lstsq`.
  - Add K=3 chronological fold IR helper.
  - Route `_compute_combined_ic` through liquidity filter, neutralization, and fold IR.
  - Guard random 100k subsample when `use_time_fold_ir=True`.

- `src/omega/quant/evolution/feature_adapter.py`
  - Remove raw OHLC passthrough.
  - Keep volume if desired, but do not expose raw prices.
  - Add `hl_range_cs_z`, `oc_range_cs_z`.
  - Shift adapter base/engineered features by ticker once.

- Tests
  - `tests/quant_test_genetic_engine.py`
    - Add neutralization test.
    - Add K=3 fold IR stability test.
    - Add liquidity mask test.
  - `tests/test_feature_adapter_nonnumeric.py`
    - Assert raw OHLC absent.
    - Assert cs-z range features present and finite.
  - New `tests/test_genetic_alpha_evolution_v3_config.py`
    - Assert V3 terminal set excludes raw OHLC.
    - Assert V3 config defaults enable neutralized K=3 fold IR.

## Validation Commands

Run targeted tests:

```powershell
python -m pytest tests/quant_test_genetic_engine.py tests/test_feature_adapter_nonnumeric.py tests/test_genetic_alpha_evolution_v3_config.py -q
```

Run a small GP smoke:

```powershell
python scripts/genetic_alpha_evolution_v3.py --rounds 1 --population-size 20 --generations 2 --workers 1 --min-avg-volume 500000
```

Expected smoke evidence:

- Printed features exclude `open`, `high`, `low`, `close`.
- Printed features include `hl_range`, `oc_range`, `hl_range_cs_z`, `oc_range_cs_z`.
- Train/test rows reflect liquidity-filtered universe.
- Results still register to `.ly_state/session/conformal_registry.sqlite`.

## Risk Notes

- `log_market_cap = log1p(close * volume)` is a liquidity/value proxy, not true market cap. If real shares-outstanding or market-cap data exists, use it instead.
- Per-date sector dummies with only top 15 tickers can be rank-deficient. Use `np.linalg.lstsq`, drop-first dummies, and fallback to date demean for small cross-sections.
- Current `use_icir=True` and new `use_time_fold_ir=True` should not both run. V3 should use only K=3 fold IR for training fitness.
- Existing row-random generation subsampling is incompatible with chronological fold IR. Disable it for V3 unless a date-stratified replacement is added.
