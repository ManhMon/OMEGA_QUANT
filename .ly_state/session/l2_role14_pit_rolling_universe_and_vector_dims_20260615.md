# L2 Implementation Report: PIT Rolling Universe & Expanded Alpha Vector Dimensions

**Gate**: `PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615`
**Role**: 14 (data-scientist) — L2 Implementation
**Date**: 2026-06-15
**Platform**: OpenCode L2
**SOD Boundary**: Implementation only, test required, no self-approval, submit to Tier 3

---

## 1. Agent & Skill Files Read

### Agent File
- **Path**: `.agents/agent/data-scientist.md`
- **Frontmatter**: name=data-scientist, role_id=14, tier=2, platform=OpenCode
- **Skills declared**: [python-patterns, clean-code, testing-patterns, systematic-debugging, performance-profiling, quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow]

### Skill Files (All from `REPO_SKILL_ROOT = .agents/skills/`)
| # | Skill | Path | Status |
|---|-------|------|--------|
| 1 | python-patterns | `.agents/skills/python-patterns/SKILL.md` | Read |
| 2 | clean-code | `.agents/skills/clean-code/SKILL.md` | Read |
| 3 | testing-patterns | `.agents/skills/testing-patterns/SKILL.md` | Read |
| 4 | systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` | Read |
| 5 | performance-profiling | `.agents/skills/performance-profiling/SKILL.md` | Read |
| 6 | quant-research | `.agents/skills/quant-research/SKILL.md` | Read |
| 7 | vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` | Read |
| 8 | backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` | Read |
| 9 | data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` | Read |

### Forbidden Path Scan Result
No authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

---

## 2. Implementation Summary

### 2.1 PIT-Safe Rolling Universe (phase35_data_loader.py)

**GATE**: `PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615`

Added three new methods to `Phase35DataLoader`:

| Method | Purpose |
|--------|---------|
| `select_rolling_universe(train_df, top_n)` | Selects top N symbols from train_df ONLY using ADTV>=5B, avg_close>=5000, min_history filters. Returns (symbols, evidence_dict). |
| `apply_rolling_universe_to_splits(splits, top_n)` | Applies per-fold rolling selection, filters both train and test. Returns list of (train, test, evidence) tuples. |
| `get_rolling_universe_evidence()` | Returns per-fold evidence list (JSON-serializable). |

**PIT Safety Guarantee**: Universe selection uses ONLY `train_df` data. No test data is ever accessed for symbol selection. `test_symbols_subset_of_train` is verified per fold.

**Default**: DISABLED — static universe behavior preserved. Opt-in via `--rolling-universe` CLI flag.

### 2.2 CLI Wiring (run_phase35_backtest.py)

- Added `--rolling-universe` flag (action=store_true, default=False)
- Added rolling universe config logging
- Wired rolling universe application after split creation
- Persisted `rolling_universe_evidence` in results JSON
- Added `rolling_universe_enabled` to config section

### 2.3 Expanded Alpha Vector Dimensions (analyze_alpha_vector_space.py)

**Expanded from ~9D to 40D scalar features per alpha.**

New features added (all deterministic):

| Category | Features |
|----------|----------|
| **IC Distribution** | min_ic, max_ic, ic_range, ic_median, ic_skew, fold_ic_kurtosis, ic_stability, ic_coefficient_of_variation |
| **Fold Analysis** | worst_fold_ic, best_fold_ic, n_folds_available, quarter_mean_1..4 |
| **Directional** | downside_ic_mean, upside_ic_mean, negative_fold_rate, positive_ic_rate_above_threshold, ic_win_loss_ratio, ic_consistency_score |
| **Temporal** | ic_momentum, fold_ic_autocorr, regime_bull_proxy_mean_ic, regime_bear_proxy_mean_ic |
| **Cross-Alpha** | mean_abs_corr, redundancy_count, cluster_centrality, cross_alpha_mean_ic_deviation |
| **Association** | sharpe_association, drawdown_association, return_association |

Added helpers: `_safe_median`, `_safe_skew`, `_safe_kurtosis`, `_safe_autocorr_lag1`, `_count_scalar_features`, `extract_fold_sharpes`, `extract_fold_max_dds`, `extract_fold_total_returns`, `extract_rolling_universe_metadata`.

---

## 3. Test Results

### 3.1 Focused Tests

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/phase35/test_phase35_rolling_universe.py` | 18 | ALL PASSED |
| `tests/test_analyze_alpha_vector_space.py` | 81 | ALL PASSED |

### 3.2 Regression Tests

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/phase35/test_regime_routing.py` | 43 | ALL PASSED |
| `tests/phase35/test_drawdown_control_default_on_cli.py` | 29 | ALL PASSED |
| `tests/phase35/test_xgboost_default_off_cli.py` | 18 | ALL PASSED |

### 3.3 Test Coverage Summary

- Rolling disabled default: VERIFIED
- Static behavior preserved: VERIFIED
- Rolling selector uses train window only: VERIFIED
- Test symbols subset of train-selected: VERIFIED (all 12 folds)
- Metadata serializable: VERIFIED (JSON dumps passes)
- Vector dim count increased/deterministic: VERIFIED (40 features, deterministic)

---

## 4. E2E Backtest Results

**Command**: `python scripts/run_phase35_backtest.py --n-folds 12 --train-years 3 --test-years 1 --top-n-symbols 30 --rolling-universe --enable-formulaic-alphas --formulaic-alpha-set v3_pruned --formulaic-winner-guard --output-tag rolling_universe_best_config_20260615`

| Metric | Value |
|--------|-------|
| Folds | 12 (all executed) |
| Avg Portfolio IC | 0.0263 |
| Avg Portfolio Sharpe | 2.8561 |
| Avg Max Drawdown | -12.30% |
| Rolling Universe | ENABLED |
| Universe Growth | 12 → 27 symbols across folds |
| test_subset_of_train | True (all 12 folds) |

### Rolling Universe Per-Fold Stats

| Fold | Symbols Selected | Train Rows | Test Rows |
|------|-----------------|------------|-----------|
| 1 | 12 | 7,329 | 2,978 |
| 2 | 22 | 12,121 | 5,469 |
| 3 | 22 | 13,409 | 5,522 |
| 4 | 23 | 15,527 | 5,773 |
| 5 | 23 | 16,558 | 5,727 |
| 6 | 23 | 17,237 | 5,727 |
| 7 | 26 | 19,512 | 6,500 |
| 8 | 26 | 19,516 | 6,500 |
| 9 | 27 | 20,234 | 6,723 |
| 10 | 27 | 20,187 | 6,722 |
| 11 | 27 | 20,166 | 6,713 |
| 12 | 27 | 20,161 | 6,694 |

---

## 5. Analyzer Results

**Command**: `python scripts/analyze_alpha_vector_space.py --input ... --output-report ... --output-json ...`

| Metric | Value |
|--------|-------|
| Alphas Analyzed | 12 |
| Vector Dims | **40 scalar features** (expanded from ~9) |
| Clusters | 5 |
| Redundant Clusters | 1 |
| Complementary Pairs | 13 |
| Verdict | RESEARCH_ONLY / DO_NOT_PROMOTE |

**Output Files**:
- `.ly_state/session/alpha_vector_space_rolling_universe_report_20260615.md`
- `.ly_state/session/alpha_vector_space_rolling_universe_20260615.json`

---

## 6. Files Modified/Created

| File | Action |
|------|--------|
| `scripts/phase35_data_loader.py` | Modified: Added `select_rolling_universe`, `apply_rolling_universe_to_splits`, `get_rolling_universe_evidence` |
| `scripts/run_phase35_backtest.py` | Modified: Added `--rolling-universe` CLI flag, wiring, evidence persistence |
| `scripts/analyze_alpha_vector_space.py` | Modified: Expanded from ~9D to 40D features, new helpers, updated report/JSON |
| `tests/phase35/test_phase35_rolling_universe.py` | Created: 18 tests for rolling universe |
| `tests/test_analyze_alpha_vector_space.py` | Modified: Added expanded dimension tests (81 total) |
| `.ly_state/session/l2_role14_pit_rolling_universe_and_vector_dims_20260615.md` | Created: This report |
| `.ly_state/session/alpha_vector_space_rolling_universe_report_20260615.md` | Created: Analyzer report |
| `.ly_state/session/alpha_vector_space_rolling_universe_20260615.json` | Created: Analyzer JSON |

---

## 7. Safety & Compliance

- **PIT Safety**: Rolling universe selection uses ONLY train_df. No test data leakage. Verified per-fold with `test_symbols_subset_of_train`.
- **Default Preserved**: Rolling universe is DISABLED by default. Static universe behavior unchanged.
- **RESEARCH_ONLY / DO_NOT_PROMOTE**: No alpha promoted. No OOS winner selected. No live/default behavior altered.
- **Deterministic**: All computations deterministic (no random seeds, no stochastic ops). Same input → same output.
- **JSON-Safe**: All evidence dicts verified JSON-serializable.

---

## 8. Forbidden Path Statement

No authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

---

## 9. SOD Boundary

- **L2 Implementation only** — no self-approval, no audit, no promotion.
- **Submit to Tier 3**: Code Reviewer (role 21) + QA Engineer (role 17) for audit.
- **Do not audit or approve** — implementation-only boundary respected.
