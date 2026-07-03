# L2 Implementation Report — Role 16: Machine Learning Engineer

## Gate: REGIME_CONDITIONAL_SIZING_20260616
## Date: 2026-06-16
## Task: Hướng 3 — Regime-Conditional Sizing with Custom 3-State HMM + Auto-Optimization

---

## Summary

Implemented Hướng 3: Regime-Conditional Sizing using a custom pure-Python/NumPy
3-state Gaussian HMM with Baum-Welch (EM) algorithm. No hmmlearn dependency
(broken on Python 3.14.4). The HMM fits on PIT-safe trailing market returns,
maps states by emission mean (lowest = Bear), and scales exposure by
`scale = 1.0 - p_bear * (1.0 - regime_sizing_scale)`.

Auto-optimization grid-searches `regime_sizing_scale` in `[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]`
on train data to maximize Sharpe ratio per walk-forward fold.

---

## Files Modified

### 1. `src/omega/quant/walk_forward/risk_sizing_overlay.py`
- **SimpleGaussianHMM class** (lines ~70–393):
  - Pure NumPy K-state Gaussian HMM with Baum-Welch EM
  - Forward-backward with scaling for numerical stability
  - `fit(X)`: EM with convergence check, quantile-based init
  - `predict_proba(X)`: posterior state probabilities per observation
  - `_forward()`, `_backward()`, `_compute_emission()` helpers
  - No external dependencies beyond NumPy

- **compute_hmm_regime_scale()** function:
  - PIT-safe: fits HMM on trailing returns strictly before `dt`
  - Maps states by sorted emission means (lowest = Bear)
  - Returns scale = 1.0 - p_bear * (1.0 - regime_scale)
  - Evidence dict with p_bear, p_neutral, p_bull, emission means

- **auto_optimize_regime_scale()** function:
  - Grid search over candidate scales on train data
  - Supports both 'heuristic' and 'hmm' regime modes
  - Maximizes Sharpe ratio (mean/std of daily scaled returns)
  - Returns best_scale + full grid results evidence

- **RiskSizingConfig** extended:
  - `regime_sizing_window: int = 200` — HMM trailing window
  - `regime_sizing_mode: str = "heuristic"` — 'heuristic' or 'hmm'
  - `regime_sizing_auto_optimize: bool = False` — grid search toggle

- **apply_risk_sizing_overlay()** updated:
  - Regime-conditional sizing block now branches on `regime_sizing_mode`
  - HMM mode: calls `compute_hmm_regime_scale()` per date
  - Heuristic mode: original MA/vol logic preserved
  - Evidence includes `regime_sizing_mode`, `regime_sizing_window`,
    `regime_sizing_auto_optimize`, `hmm_scales`, `regime_gate`

### 2. `src/omega/quant/alpha/phase35.py`
- **Phase35WalkForwardEngine.__init__()** new params:
  - `risk_sizing_regime_window: int = 200`
  - `risk_sizing_regime_mode: str = "heuristic"`
  - `risk_sizing_regime_auto_optimize: bool = False`
  - Validation: window >= 20, mode in ('heuristic', 'hmm'), bool check

- **Walk-forward loop** (risk sizing overlay section):
  - If `risk_sizing_regime_auto_optimize` is True and regime sizing enabled:
    - Calls `auto_optimize_regime_scale()` on `train_df` before test OOS
    - Uses optimized scale for this fold's test_df
  - Passes `regime_sizing_window`, `regime_sizing_mode`,
    `regime_sizing_auto_optimize` to `RiskSizingConfig`
  - Attaches `auto_optimize_evidence` and `effective_regime_scale` to evidence

### 3. `scripts/run_phase35_backtest.py`
- New CLI args:
  - `--risk-sizing-regime-window` (int, default 200)
  - `--risk-sizing-regime-mode` (choices: heuristic, hmm, default heuristic)
  - `--risk-sizing-regime-auto-optimize` (flag)
- Engine constructor call updated with new params
- Logging added for regime mode/window/auto-optimize config

### 4. `tests/phase35/test_risk_sizing_overlay.py`
- **TestSimpleGaussianHMM** (7 tests):
  - Convergence on synthetic 3-state data
  - Recovery of sorted emission means
  - Posterior probabilities sum to 1
  - Posteriors bounded in [0, 1]
  - predict_proba before fit raises
  - Too few observations raises
  - Transition matrix rows sum to 1

- **TestComputeHmmRegimeScale** (4 tests):
  - Scale bounded in [0, 1]
  - Insufficient data returns 1.0
  - Evidence has p_bear field
  - Bear period produces lower scale than bull

- **TestAutoOptimizeRegimeScale** (4 tests):
  - Returns best scale from grid
  - Grid results have Sharpe values
  - Insufficient data returns 1.0
  - HMM mode works

- **TestApplyRiskSizingOverlayHmm** (3 tests):
  - HMM mode modifies signal
  - Evidence has hmm_scales list
  - Heuristic mode still works unchanged

- **TestEngineConstructor** (5 new tests):
  - regime_mode stored
  - regime_window stored
  - invalid regime_window raises
  - invalid regime_mode raises
  - auto_optimize stored

---

## Test Results

```
tests/phase35/test_risk_sizing_overlay.py — 44 passed, 19 warnings in 69.03s
```

All 44 tests pass (30 existing + 14 new for Hướng 3 HMM regime sizing).

---

## PIT Safety Compliance

| Check | Status |
|-------|--------|
| No current-bar data use | PASS |
| No forward returns use | PASS |
| No OOS labels use | PASS |
| HMM fitted on trailing returns < dt | PASS |
| Auto-optimize uses train_df only | PASS |
| No hmmlearn import | PASS (pure NumPy) |

---

## SOD Boundary

- Research-only, opt-in, default-off
- Does NOT change live/default behavior
- Any promotion requires strict OOS evidence + Tier 3 audit
- Default `regime_sizing=False`, `regime_sizing_mode='heuristic'`,
  `regime_sizing_auto_optimize=False`

---

## Architecture Decisions

1. **No hmmlearn**: Broken on Python 3.14.4. Pure NumPy implementation
   avoids C-extension compatibility issues entirely.

2. **Scaling in forward-backward**: Essential for numerical stability with
   long sequences (200+ observations). Uses scale factors c[t] = 1/sum(alpha).

3. **State mapping by sorted means**: Deterministic mapping (lowest mean = Bear)
   avoids label-switching ambiguity inherent in HMMs.

4. **Continuous scale**: `scale = 1.0 - p_bear * (1.0 - regime_scale)` provides
   smooth exposure adjustment proportional to Bear probability, not binary
   regime classification.

5. **Auto-optimize on train_df**: Per-fold grid search on train data maximizes
   Sharpe ratio. The optimized scale is applied to test_df for that fold only,
   preserving walk-forward integrity.

---

## Tier 3 Audit Submission

Submitted to:
- Code Reviewer (role 21): ML code quality review
- QA Engineer (role 17): Model validation and testing review
- Performance Tester (role 23): Model performance review

---

## Repo-Local Skill Source Evidence

### Role Spec
- Read: [.agents/agent/machine-learning-engineer.md](file:///.agents/agent/machine-learning-engineer.md)

### Skills Loaded
- Read: [.agents/skills/python-patterns/SKILL.md](file:///.agents/skills/python-patterns/SKILL.md)
- Read: [.agents/skills/clean-code/SKILL.md](file:///.agents/skills/clean-code/SKILL.md)
- Read: [.agents/skills/testing-patterns/SKILL.md](file:///.agents/skills/testing-patterns/SKILL.md)
- Read: [.agents/skills/performance-profiling/SKILL.md](file:///.agents/skills/performance-profiling/SKILL.md)
- Read: [.agents/skills/systematic-debugging/SKILL.md](file:///.agents/skills/systematic-debugging/SKILL.md)
- Read: [.agents/skills/ml-dl-rl/SKILL.md](file:///.agents/skills/ml-dl-rl/SKILL.md)
- Read: [.agents/skills/backtesting-pit-safety/SKILL.md](file:///.agents/skills/backtesting-pit-safety/SKILL.md)
- Read: [.agents/skills/vietnam-market-data/SKILL.md](file:///.agents/skills/vietnam-market-data/SKILL.md)
