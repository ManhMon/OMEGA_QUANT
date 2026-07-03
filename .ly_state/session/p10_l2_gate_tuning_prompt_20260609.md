# [L2-Impl:Role9-BackendEngineer] P10 Research Gate Tuning Knobs

You are L2 implementation only. Do not audit/approve.

## Goal
Add opt-in P10 Research Gate tuning knobs so P10 can be tested with relaxed gate policies without changing default strict behavior.

## Scope
Allowed files only:
- `src/omega/quant/phase35_walk_forward.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_p10_multi_horizon_blend.py`
- `.ly_state/session/l2_p10_gate_tuning_report_20260609.md`

Do not modify unrelated files. Do not commit/push.

## Context
Strict matrix results: all P10 horizon configs had `Fallbacks=8/8`, `NonEmptyHorizonFolds=0`. Research Gate excludes all horizons, so P10 blend rarely runs.

Current approved P10 constraints must remain:
- default strict behavior unchanged
- P10 remains default-off
- relaxed gate must be explicit opt-in
- negative/zero final-objective quality gets zero weight
- no abs(IC), no equal-weight fallback
- all invalid/non-positive horizons fallback T+5 baseline
- PIT safe: use train/validation only

## Required implementation

### 1) Engine params
Add constructor params with defaults preserving current behavior:
- `p10_gate_mode: str = "strict"`
  - valid: `strict`, `relaxed`
- `p10_gate_min_pass: int = 1`
  - minimum true gate passes required for a horizon
- `p10_gate_allow_fallback_candidates: bool = False`
  - strict default false for P10 horizon eligibility
  - relaxed mode may allow candidates selected by top_alphas only if their final-objective selected quality is positive later

Validate values.

### 2) Horizon gate eligibility
In `_compute_horizon_signal()`:
- strict mode: current robust pass count logic unchanged.
- relaxed mode: allow horizon to proceed if either:
  - robust pass count >= `p10_gate_min_pass`, OR
  - `p10_gate_allow_fallback_candidates=True` and `top_alphas` non-empty.
- Even in relaxed mode, include diagnostics:
  - gate_mode
  - gate_passed_count
  - gate_required_passes
  - used_fallback_candidates bool
- Do not mark failed gate verdicts as passed; just allow candidate continuation when explicitly configured.
- Blend quality guard later must still reject non-positive final-objective IC.

### 3) CLI flags
Add to `scripts/run_phase35_backtest.py`:
- `--p10-gate-mode strict|relaxed`, default `strict`
- `--p10-gate-min-pass`, int default `1`
- `--p10-gate-allow-fallback-candidates`, action store_true default false

Pass to engine. Persist in JSON config.

### 4) Tests
Add tests proving:
- default strict behavior unchanged: FAIL string horizon excluded.
- relaxed mode without fallback candidates still excludes all FAIL if min pass unmet.
- relaxed + allow fallback candidates lets horizon compute a signal if candidates exist.
- relaxed admitted horizon with negative/zero final-objective quality still gets zero weight / fallback.
- invalid gate mode raises.
- CLI args parse/persist if there are existing CLI tests; otherwise unit-test engine only.

### 5) Verification
Run:
```powershell
python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q
python -m pytest tests/phase35/ -q
python scripts/run_phase35_backtest.py --quick-mode --multi-horizon-blend --blend-horizons 1,3,5 --p10-gate-mode relaxed --p10-gate-allow-fallback-candidates
```

### 6) Report
Write `.ly_state/session/l2_p10_gate_tuning_report_20260609.md` with:
- files changed
- knobs added
- defaults unchanged proof
- tests/results
- residual risks

Do not commit/push.
