# Task: Implement HMM Regime Sizing Optimization (Warm Start & Stride Refitting)

Implement the optimizations for Hướng 3 (Regime-Conditional Sizing with Custom 3-state HMM) to speed up walk-forward backtesting.

## Scope
- `src/omega/quant/walk_forward/risk_sizing_overlay.py`
- `src/omega/quant/alpha/phase35.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_risk_sizing_overlay.py`

## Requirements

### 1. `src/omega/quant/walk_forward/risk_sizing_overlay.py`
- Update `SimpleGaussianHMM`:
  - Allow `fit(X, init_params: dict = None)` to support warm starting. If `init_params` is provided, initialize `pi_`, `A_`, `mu_`, `sigma2_` from it instead of randomly/quantiles.
  - Set default `max_iter = 30`.
  - Add `get_params(self) -> dict` to extract `pi_`, `A_`, `mu_`, and `sigma2_` as a dict.
- Extend `RiskSizingConfig` to include:
  - `regime_refit_stride: int = 5`
- Update `compute_hmm_regime_scale`:
  - Change signature to:
    ```python
    def compute_hmm_regime_scale(
        close_wide: pd.DataFrame,
        dt,
        regime_window: int = 200,
        regime_scale: float = 0.5,
        init_params: dict = None,
        refit: bool = True,
    ) -> tuple[float, dict, dict]:
    ```
    where it returns `(scale, evidence, hmm_params)`.
  - If `refit` is True, fit HMM (using `init_params` for warm start if available) and return updated parameters.
  - If `refit` is False, use `init_params` (emission means, transition matrix, etc.) to perform only forward-backward (`predict_proba`) and return current scale without retraining.
- Update `apply_risk_sizing_overlay` and `auto_optimize_regime_scale` loops to cache/carry forward HMM parameters and apply stride logic:
  - Maintain a cache of HMM parameters `hmm_params`.
  - Refit only if `day_idx % regime_refit_stride == 0` (or `refit=True`). Otherwise `refit=False`.
  - Carry forward `hmm_params` to the next step.

### 2. `src/omega/quant/alpha/phase35.py`
- In `Phase35WalkForwardEngine.__init__`, add `risk_sizing_regime_refit_stride: int = 5` and validate it (must be >= 1).
- In the OOS fold loop where `apply_risk_sizing_overlay` is called, construct `RiskSizingConfig` passing `regime_refit_stride=self.risk_sizing_regime_refit_stride`.

### 3. `scripts/run_phase35_backtest.py`
- Add CLI argument `--risk-sizing-regime-refit-stride` (int, default 5).
- Pass it to the engine constructor.

### 4. `tests/phase35/test_risk_sizing_overlay.py`
- Add unit tests verifying:
  - HMM warm-start: fit finishes faster and parameters are close when warm started.
  - Stride refitting: verify that `compute_hmm_regime_scale` returns same/similar results with `refit=False` using cached parameters.

## Verification
- Run `python -m pytest tests/phase35/test_risk_sizing_overlay.py` and ensure all tests pass.
- Run `python scripts/sod_gate_enforcer.py` to check compliance.

## Output Report
Write L2 report to `.ly_state/session/l2_role16_regime_conditional_sizing_hmm_speedup_20260616.md` listing the exact repo-local skill and role files read.
