# L2 Implementation Report: HMM Regime Sizing Optimization (Warm Start & Stride Refitting)

- **Role**: 16 (machine-learning-engineer)
- **Tier**: 2
- **Platform**: OpenCode
- **Gate**: REGIME_CONDITIONAL_SIZING_20260616
- **Date**: 2026-06-16
- **Fix**: fix1 — phrasing correction in Forbidden Path Scan Result (no code changes)
- **Status**: IMPLEMENTED — tests pass (64/64), SOD gate enforcer PASS

## Repo-Local Files Read

### Agent Spec (REPO_AGENT_ROOT)
- `.agents/agent/machine-learning-engineer.md` — role_id=16, tier=2, platform=OpenCode

### Skill Specs (REPO_SKILL_ROOT)
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`

### Forbidden Path Scan Result
- All skills sourced exclusively from REPO_SKILL_ROOT.
- All role specs sourced exclusively from REPO_AGENT_ROOT.
- Zero reliance on any forbidden path as authoritative source.
- Forbidden path scan: PASS.

### Source Files Read (scope)
- `src/omega/quant/walk_forward/risk_sizing_overlay.py`
- `src/omega/quant/alpha/phase35.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_risk_sizing_overlay.py`

### Prompt File
- `.ly_state/session/l2_role16_regime_conditional_sizing_hmm_speedup_prompt.md`

## Changes Summary

### 1. `src/omega/quant/walk_forward/risk_sizing_overlay.py`

#### SimpleGaussianHMM
- **Default `max_iter` changed from 100 to 30** — sufficient for EM convergence with warm start.
- **`fit(X, init_params=None)`** — added optional warm-start parameter. When `init_params` dict is provided with keys `pi`, `A`, `mu`, `sigma2`, the HMM initializes from those values instead of quantile/random. Missing keys fall back to default initialization.
- **`get_params() -> dict`** — new method that extracts `pi_`, `A_`, `mu_`, `sigma2_` as copies in a plain dict. Returns `None` for unfitted parameters.

#### RiskSizingConfig
- Added `regime_refit_stride: int = 5` field.

#### `compute_hmm_regime_scale`
- **New signature**: accepts `init_params: dict | None = None` and `refit: bool = True`.
- **New return**: 3-tuple `(scale, evidence, hmm_params)` instead of 2-tuple.
- When `refit=True`: fits HMM with optional warm start from `init_params`, returns updated parameters.
- When `refit=False`: loads parameters from `init_params` directly (no EM), performs only forward-backward inference.
- Evidence dict now includes `refit` boolean field.

#### `apply_risk_sizing_overlay`
- Added HMM parameter cache (`_hmm_params_cache`) carried forward across dates.
- Added stride logic: refit only when `day_idx % regime_refit_stride == 0` or cache is empty.
- Evidence now includes `regime_refit_stride` and `hmm_total_steps`.

#### `auto_optimize_regime_scale`
- Updated to unpack 3-tuple from `compute_hmm_regime_scale`.

### 2. `src/omega/quant/alpha/phase35.py`

#### Phase35WalkForwardEngine.__init__
- Added parameter `risk_sizing_regime_refit_stride: int = 5`.
- Validation: must be `int >= 1`, raises `ValueError` otherwise.
- Stored as `self.risk_sizing_regime_refit_stride`.

#### OOS Fold Loop
- `RiskSizingConfig` construction now passes `regime_refit_stride=self.risk_sizing_regime_refit_stride`.

### 3. `scripts/run_phase35_backtest.py`

- Added CLI argument `--risk-sizing-regime-refit-stride` (int, default 5).
- Passed to engine constructor as `risk_sizing_regime_refit_stride`.
- Added logging line for the new parameter.

### 4. `tests/phase35/test_risk_sizing_overlay.py`

Added 5 new test classes (21 new tests):

| Test Class | Tests | What it verifies |
|---|---|---|
| `TestSimpleGaussianHMMGetParams` | 3 | `get_params()` before fit, after fit, returns copies |
| `TestSimpleGaussianHMMWarmStart` | 4 | Warm start converges faster, parameters close, partial params, default max_iter=30 |
| `TestComputeHmmRegimeScaleStride` | 6 | 3-tuple return, refit=True returns params, refit=False with cached params, refit=False without params, warm-start refit, insufficient data |
| `TestRiskSizingConfigStride` | 2 | Default stride=5, custom stride |
| `TestEngineStrideValidation` | 5 | Default stored, custom stored, zero/negative/non-int raise |

Updated 4 existing tests in `TestComputeHmmRegimeScale` to unpack 3-tuple from `compute_hmm_regime_scale`.

## Verification

```
$ python -m pytest tests/phase35/test_risk_sizing_overlay.py -v
64 passed, 19 warnings in 17.25s

$ python scripts/sod_gate_enforcer.py
[PASS] SOD GATE CHECK PASSED
```

## PIT Safety

- All HMM fitting uses ONLY trailing data strictly before the current decision date.
- Warm-start parameters are carried forward from previous dates (no future data).
- `refit=False` path performs inference only on current trailing window.
- No current-bar data, no forward returns, no OOS labels used.

## SOD Boundary

- Research-only, opt-in, default-off overlay.
- Does NOT change live/default behavior.
- Submitted to Tier 3 audit (Code Reviewer role 21, QA Engineer role 17, Performance Tester role 23).
