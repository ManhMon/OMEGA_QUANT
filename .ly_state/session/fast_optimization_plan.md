# Revised Implementation Plan - OMEGA_QUANT Fast Optimization

Goal: Optimize Sharpe and transaction costs (TC) on OMEGA_QUANT's Hybrid Regime pipeline safely and fast by caching invariant features/predictions and parameterizing overlays.

## Proposed Changes

### 1. Invariant Cache and Overlay Sweep Harness
#### [NEW] [cached_overlay_sweeper.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/cached_overlay_sweeper.py)
Instead of subsetting folds (which adds variance/noise), cache the model predictions (`composite_signal`) and GMM regime probabilities to disk/memory for the full 45 CPCV folds.
* **Why**: Model training & feature gen consume >90% of execution time. Once cached, running the portfolio overlay stack (TailControl, RiskSizing, TCost) on the full 45 folds takes seconds per run.
* **Sweep**: Execute Optuna Bayesian search over cached predictions to sweep overlay parameters.

### 2. Parameterize Portfolio Overlays
#### [MODIFY] [backtest_hybrid_regime.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/backtest_hybrid_regime.py)
Add and thread CLI arguments into `build_overlay_stack`:
* `--target-vol-ann` (default: 0.20)
* `--gmm-bear-damp` (default: 0.45)
* `--gmm-bull-boost` (default: 1.25)
* `--ablate` (`none`, `gmm`, `vol`, `cost`, `conv`)
* `--downside-vol-target` (boolean flag to enable downside-only semi-deviation target)

### 3. Safe Downside Volatility Targeting
#### [MODIFY] [tail_controls.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/portfolio/tail_controls.py)
* Implement `downside_only` leverage scaling.
* **Unit correction**: Set target downside-vol as `target_vol_ann / sqrt(2)` to match symmetric normal volatility scaling, avoiding artificial leverage spikes.
* **Stability guard**: Fallback to standard deviation if the number of negative returns in the lookback window drops below 15.

---

## Verification Plan

### Step 0: Pre-Flight Proxy Parity Check
Verify Spearman rank-correlation (Spearman $\rho$) of Sharpe/turnover on a small 5-point parameter grid between Ridge and LightGBM. If $\rho < 0.7$, disable Ridge proxies and run solely on cached LightGBM predictions.

### Step 1: Cache Generation Run
Generate and cache prediction arrays for all 45 folds.
```powershell
python scripts/backtest_hybrid_regime.py --folds 10 --n-test-folds 2 --workers 8 --output-tag cache_gen
```

### Step 2: Bayesian Sweep via Cached Overlay Sweeper
Run Optuna optimization sweep on cached outputs to find the Pareto frontier for Sharpe vs. MaxDD vs. Turnover.
