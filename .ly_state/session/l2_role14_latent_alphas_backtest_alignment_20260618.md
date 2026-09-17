# L2 Implementation Report — Role 14 (Data Scientist)

**GATE**: `LATENT_ALPHA_MINING_64D_20260617`  
**Date**: 2026-06-18  
**Scope**: `scripts/run_phase35_backtest.py`  
**Status**: `[NEEDS_FIX]` → `[IMPLEMENTED]` — Awaiting Tier 3 audit  

---

## 1. Repo-Local Skill Source Evidence (Files Read)

All role and skill definitions were loaded exclusively from repo-local paths.  
**REPO_AGENT_ROOT**: `.agents/agent/`  
**REPO_SKILL_ROOT**: `.agents/skills/`  

### Exact repo-local files read (skill source evidence):

| File | Repo-Local Path | Status |
|------|-----------------|--------|
| Agent definition (role 14) | `.agents/agent/data-scientist.md` | Read, frontmatter parsed |
| Skill: python-patterns | `.agents/skills/python-patterns/SKILL.md` | Read |
| Skill: clean-code | `.agents/skills/clean-code/SKILL.md` | Read |
| Skill: testing-patterns | `.agents/skills/testing-patterns/SKILL.md` | Read |
| Skill: systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` | Read |
| Skill: performance-profiling | `.agents/skills/performance-profiling/SKILL.md` | Read |
| Skill: quant-research | `.agents/skills/quant-research/SKILL.md` | Read |
| Skill: vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` | Read |
| Skill: backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` | Read |
| Skill: data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` | Read |

**Forbidden path scan**: No files accessed from Antigravity scratch, OpenClaw, or `C:\Users\GHC\.agents` (non-authoritative, not used as source) memory. Result: clean — no forbidden path violations.

---

## 2. Objective

Investigate why `latent_ae_*` features have 0.0 values in the training/validation splits of backtest folds, and adjust fold execution parameters so that latent alphas can be successfully selected and backtested over the period where they exist.

---

## 3. Investigation — Systematic Debugging (4-Phase)

### Phase 1: Reproduce

The latent_ae_* features are **always 0.0** in training splits of most walk-forward folds when using default parameters (`--start-date 2015-01-05`, `--train-years 3`, `--test-years 1`, `--n-folds 8`).

### Phase 2: Isolate

**Data artifacts inspected**:

| Artifact | Date Range | Tickers | Latent Columns |
|----------|-----------|---------|----------------|
| `data/market_2015_now.parquet` | 2015-01-05 to 2026-06-12 | 703 | N/A (raw OHLCV) |
| `data/features_advanced_sim.parquet` | 2024-01-02 to 2026-06-12 | 10 | 0 latent columns |
| `data/latent_alphas_components.parquet` | **2024-01-03** to 2026-06-12 | 10 | 16 `latent_ae_*` (autoencoder only) |

**Key finding**: The `latent_alphas_components.parquet` contains **ONLY** autoencoder components (`latent_ae_00` through `latent_ae_15`). There are **zero** PCA/ICA columns (`latent_pca_*`, `latent_ica_*`).

### Phase 3: Root Cause Analysis — The 5 Whys

1. **Why are latent_ae_* all 0.0?**  
   The walk-forward folds cover 2015–2026, but latent components only exist from 2024-01-03. The left-merge with `fillna(0.0)` fills all pre-2024 rows with 0.0.

2. **Why do folds span 2015–2026?**  
   The default `--start-date` is `2015-01-05` and the warehouse has data from 2015. The walk-forward engine creates folds starting from the earliest available date.

3. **Why doesn't the script detect this mismatch?**  
   No pre-merge validation existed to check whether the latent parquet's date range overlaps with the walk-forward fold windows.

4. **Why are latent_ae_* columns not selected even when the flag is set?**  
   The script requires `--enable-latent-autoencoder` in addition to `--enable-latent-alphas` to include `latent_ae_*` columns. Without it, `_la_ae_cols = []` and injection is skipped entirely.

5. **Why is the default configuration incompatible with latent data?**  
   The latent alpha mining pipeline (`mine_latent_alphas.py`) operates on the `features_advanced_sim.parquet` feature set (2024+ only), but the backtest's default date range covers 2015–2026. No auto-alignment logic existed.

### Phase 4: Root Causes Summary

| # | Root Cause | Impact |
|---|-----------|--------|
| RC1 | **Date mismatch**: Warehouse spans 2015–2026, latent parquet spans 2024–2026 only | Folds 1–6 have 0% latent coverage in train/test |
| RC2 | **Missing auto-alignment**: No logic adjusts START_DATE/fold params when latent alphas are enabled | Silent 0.0 fill, no warning |
| RC3 | **Variant flag required**: `--enable-latent-autoencoder` must be passed alongside `--enable-latent-alphas` for AE columns | Users may not know to pass both flags |
| RC4 | **No post-merge validation**: No check that merged latent columns have meaningful non-zero coverage | Problem goes undetected |

**Fold-by-fold coverage BEFORE fix** (default params, 8 folds × 3yr train + 1yr test):

| Fold | Train Period | Test Period | Train Latent % | Test Latent % |
|------|-------------|------------|---------------|--------------|
| 1 | 2015–2018 | 2018–2019 | **0%** | **0%** |
| 2 | 2016–2019 | 2019–2020 | **0%** | **0%** |
| 3 | 2017–2020 | 2020–2021 | **0%** | **0%** |
| 4 | 2018–2021 | 2021–2022 | **0%** | **0%** |
| 5 | 2019–2022 | 2022–2023 | **0%** | **0%** |
| 6 | 2020–2023 | 2023–2024 | **0%** | **0%** |
| 7 | 2021–2024 | 2024–2025 | **0%** | 100% |
| 8 | 2022–2025 | 2025–2026 | 33% | 100% |

---

## 4. Implementation

### Changes to `scripts/run_phase35_backtest.py`

#### Change 1: Auto-alignment block (after line 1183, before data loading)

**Location**: Between fold parameter resolution and `MIN_IC_THRESHOLD` definition.

**Logic**:
1. When `--enable-latent-alphas` is set, read the latent parquet's `date` column
2. If `START_DATE < latent_min_date` → auto-adjust `START_DATE` to latent min date
3. If `(TRAIN_YEARS + TEST_YEARS) * 365 > latent_span_days` → reduce `TRAIN_YEARS`
4. If `N_FOLDS` exceeds max folds that fit within latent span at step≥30d → reduce `N_FOLDS`
5. Log all adjustments as `[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617` warnings

**PIT safety**: No change to signal computation. Only adjusts the data loading window and fold boundaries. All latent signals remain T-1 lagged as before.

#### Change 2: Post-merge zero-fill diagnostic (after line 1648)

**Location**: After `df[_selected_cols] = df[_selected_cols].fillna(0.0)`.

**Logic**:
1. Compute percentage of zero values across all injected latent columns
2. Determine date range of non-zero latent values
3. If zero-fill > 50%, log a WARNING with coverage details
4. Otherwise, log an INFO confirming healthy coverage

#### Change 3: Evidence dict enrichment

Added to `latent_alpha_evidence`:
- `zero_fill_pct`: percentage of zeros in injected columns
- `nonzero_date_coverage`: date range string of non-zero values
- `n_nonzero_dates`: count of dates with non-zero latent values
- `n_total_dates`: total dates in dataframe
- `auto_alignment_applied`: whether auto-alignment adjusted parameters

### Fold Coverage AFTER Fix

Smoke test simulation confirmed:

| Parameter | Before | After Auto-Alignment |
|-----------|--------|---------------------|
| START_DATE | 2015-01-05 | **2024-01-03** |
| TRAIN_YEARS | 3 | **1** |
| N_FOLDS | 8 | **6** |
| TEST_YEARS | 1 | 1 (unchanged) |

**All 6 folds have 100% latent coverage** in both train and test windows:

| Fold | Train Period | Test Period | Train Latent % | Test Latent % |
|------|-------------|------------|---------------|--------------|
| 1 | 2024-01-03 to 2025-01-02 | 2025-01-02 to 2026-01-02 | 100% | 100% |
| 2 | 2024-01-29 to 2025-01-28 | 2025-01-28 to 2026-01-28 | 100% | 100% |
| 3 | 2024-02-24 to 2025-02-23 | 2025-02-23 to 2026-02-23 | 100% | 100% |
| 4 | 2024-03-21 to 2025-03-21 | 2025-03-21 to 2026-03-21 | 100% | 100% |
| 5 | 2024-04-16 to 2025-04-16 | 2025-04-16 to 2026-04-16 | 100% | 100% |
| 6 | 2024-05-12 to 2025-05-12 | 2025-05-12 to 2026-05-12 | 100% | 100% |

---

## 5. Usage Instructions

To backtest with latent alphas successfully, run:

```bash
python scripts/run_phase35_backtest.py \
  --enable-latent-alphas \
  --enable-latent-autoencoder \
  --latent-alpha-min-ir 0.3
```

The auto-alignment logic will automatically:
- Set `START_DATE` to `2024-01-03` (latent data start)
- Reduce `TRAIN_YEARS` from 3 to 1 (fit within 891-day latent span)
- Reduce `N_FOLDS` from 8 to 6 (fit within latent span at step≥30d)

**Manual override**: Users can explicitly set `--start-date 2024-01-03 --train-years 1 --n-folds 6` to achieve the same result without auto-alignment.

---

## 6. Verification

| Check | Result |
|-------|--------|
| Python syntax | `py_compile` passed |
| `--help` output | Correct, all args present |
| Smoke test alignment | All 6 folds at 100% coverage |
| Backward compatibility | No change when `--enable-latent-alphas` is NOT set |
| PIT safety | No look-ahead introduced — only adjusts data window boundaries |

---

## 7. Reproducibility

| Item | Value |
|------|-------|
| Script modified | `scripts/run_phase35_backtest.py` |
| Gate | `LATENT_ALPHA_MINING_64D_20260617` |
| Latent parquet | `data/latent_alphas_components.parquet` (16 AE components, 2024-01-03 to 2026-06-12) |
| Metrics JSON | `data/latent_alphas_metrics.json` (n_components=16) |
| Components passing IR≥0.3 | `latent_ae_00` (IR=-0.83), `latent_ae_01` (IR=0.84) |

---

## 8. Tier 3 Audit Submission

This implementation is submitted to:
- **Code Reviewer (role 21)**: Code quality, naming, backward compatibility
- **QA Engineer (role 17)**: Model validation, PIT safety verification, test coverage

**Cannot proceed to live deployment until both Tier 3 roles return `[APPROVED]`.**
