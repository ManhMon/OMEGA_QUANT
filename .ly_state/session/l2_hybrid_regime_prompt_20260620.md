# L2 Implementation Request: Hybrid Regime Full Backtest Upgrades

You are dispatched as **Role 9: Backend Engineer (Platform: OpenCode, Tier 2)**.
Your task is to upgrade `scripts/backtest_hybrid_regime.py` to support full historical backtesting, walk-forward CPCV folds, and dynamic universe selection.

---

## 1. Source Contract & SOD Compliance
- **First Step**: First run `Set-Location 'C:\Users\GHC\repos\OMEGA_QUANT'`.
- **First Read**: Read `.agents/agent/backend-engineer.md` and parse its frontmatter.
- **Skill Loading**: From the frontmatter, parse `skills` and read only `SKILL.md` from `.agents/skills/<skill_name>/SKILL.md`.
- **Forbidden Paths**: Do NOT read/write any Antigravity scratch paths (`.gemini\antigravity-ide\scratch\ag-kit` etc.), OpenClaw skills, Codex memories, or global agents directories.
- **Reporting**: In your final L2 report (`.ly_state/session/l2_role9_hybrid_regime_full_backtest_20260620.md`), list exact repo-local role and skill files read, and verify no authoritative reliance on forbidden paths.
- **SOD Boundary**: This is implementation-only. Do not audit or self-approve.

---

## 2. Requirements & Specifications for `scripts/backtest_hybrid_regime.py`

### 2.1. CLI Argument Parsing
Add an `argparse.ArgumentParser` to parse the following flags:
- `--start-date` (default: `"2015-01-05"`)
- `--end-date` (default: `"2026-05-14"`)
- `--initial-capital` (default: `2000000000.0`, type `float`)
- `--n-folds` (default: `8`, type `int`)
- `--train-years` (default: `3.0`, type `float`)
- `--test-years` (default: `1.0`, type `float`)
- `--dynamic-universe` (default: `False`, action=`"store_true"`)
- `--top-n-symbols` (default: `30`, type `int`)
- `--quick-mode` (default: `False`, action=`"store_true"`)
- `--output-tag` (default: `None`, type `str`)

If `--quick-mode` is passed, override the parameters:
- `n_folds = 2`
- `top_n_symbols = 5`
- `train_years = 1.0`
- `test_years = 1.0`

### 2.2. Data Loading & Universe Selection
- Use `Phase35DataLoader` to load the market data.
- If `--dynamic-universe` is enabled, build a global dynamic universe schedule.
  - Instantiate `DynamicUniverseSelector` with `lookback_days=252`, `rebalance_days=21`, `top_n=args.top_n_symbols`, and `min_history_days=loader.min_history_days`.
  - Generate the schedule using `selector.build_dynamic_universe_schedule(raw_df)`.
- If `--dynamic-universe` is disabled, get a static set of top tickers using `loader.get_top_symbols(raw_df, top_n=args.top_n_symbols)`.

### 2.3. Walk-Forward CPCV Split Loop
- Generate splits using `loader.create_walk_forward_splits(raw_df, n_folds=n_folds, train_years=train_years, test_years=test_years)`.
- Loop over each fold (index `i`, `(train_df, test_df)`):
  - Identify train and test boundaries.
  - Determine active symbols for this fold:
    - If `--dynamic-universe` is enabled, the active symbols for the fold are all unique symbols selected in the schedule for any date within the fold's date range (from `train_df['date'].min()` to `test_df['date'].max()`).
    - If False, the active symbols are the static set of top symbols.
  - Slicing with Warmup: To avoid NaN values in feature calculation, slice the raw market data to include only the active symbols, starting from `train_start_date - 252 calendar days` (the warmup buffer) to `test_end_date`.
  - Instantiate `UnifiedFeatureAdapter` and generate features on the sliced panel data.
  - Slicing Output: Slice the generated feature dataframe back to the fold's train/test dates.
  - Set up `DatabaseFeatureStoreAdapter` for the fold.
    - Inside the `query_fn(date_start, date_end, tickers=None)`:
      - Filter the feature dataframe by date range.
      - If `tickers` is specified, filter by symbols.
      - If `--dynamic-universe` is enabled, dynamically filter daily data: for each date `t` in the mask, only return rows for symbols that are selected in the rebalance schedule for the latest rebalance date `r <= t`. (You can build a fast lookup dictionary `date -> active_symbols` for all dates in the test period beforehand).
  - Execute `TradingPipelineV2` on the fold's test period for both scenarios:
    - **Scenario 1: "Baseline (No GMM-BOCPD)"** (with `latent_gmm_enabled=False` and `bocpd_enabled=False` in overlays).
    - **Scenario 2: "Hybrid GMM-BOCPD Active"** (with `latent_gmm_enabled=True` and `bocpd_enabled=True` in overlays).
  - Collect metrics (Sharpe, Max DD, Total Return) and elapsed time for each fold.

### 2.4. Results & Aggregation
- Compute average metrics across all executed folds (mean Sharpe, mean Max DD, mean Return).
- Print a comparative Markdown table to stdout.
- Save the results to `data/phase35_results/hybrid_regime_comparison.json`. If `--output-tag` is set, save to `data/phase35_results/hybrid_regime_comparison_{output_tag}.json`.

---

## 3. Verification & Outputs
- Validate changes via `pytest tests/test_pipeline_v2.py`.
- Run a smoke test: `python scripts/run_backtest.py hybrid-regime --quick-mode`.
- Write the final L2 report to `.ly_state/session/l2_role9_hybrid_regime_full_backtest_20260620.md`.
