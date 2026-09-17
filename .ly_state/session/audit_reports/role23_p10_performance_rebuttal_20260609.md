# P10 Multi-Horizon Blending Performance Rebuttal

Role: Performance Tester / Role 23
Verdict: [NEEDS_FIX]
Performance Safety: FAIL
Role Compliance: PASS

Gate Contract:
  - l3_session_id: b72f813b-ca67-406b-aaff-6bf465fa5179
  - l3_session_key: role23_p10_performance_rebuttal_20260609
  - audit_report_path: .ly_state/session/audit_reports/role23_p10_performance_rebuttal_20260609.md
  - final_verdict: [NEEDS_FIX]

## Rebuttal Summary

P10 is not cleared as a performance improvement. The implementation blends horizons, but current evidence does not prove additive signal versus P9, does not provide comparable official full-backtest metrics, and has weight logic that can assign large positive weight to horizons whose validation IC is negative. The quick smoke all-zero metrics are explainable by a one-symbol universe, but that also means the smoke is not performance evidence.

## Scope

Audited inputs:
- `.ly_state/session/l2_p10_multi_horizon_blend_report_20260609.md`
- `src/omega/quant/phase35_walk_forward.py`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_p10_multi_horizon_blend.py`

Baseline supplied by task:
- P9: IC `0.0091`, Sharpe `0.9854`, MaxDD `-8.12%`

Local checks:
- RAM precheck: `10.4 GB` free of `23.7 GB` total.
- `python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q` -> `12 passed` in `7.7s`.
- No-save quick backtest comparison: baseline `2.749s`, P10 `4.017s`; both all-zero metrics with `top_n_symbols=1`.
- No-save full-ish comparison: `top_n_symbols=30`, `n_folds=8`, `train_years=3`, `test_years=1`.

## Findings

### 1. No proven performance lift versus P9

L2 report provides test pass counts but no comparable full P10 backtest against the stated P9 baseline. My no-save full-ish run did not show a convincing lift:

| Case | Runtime | IC | Raw IC | Daily CS IC | Sharpe | MaxDD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P9 current path, XGBoost flag true | `14.127s` | `-0.00295` | `0.00325` | `0.00604` | `1.6804` | `-67.31%` |
| P10 multi-horizon, XGBoost flag true | `16.928s` | `-0.00104` | `0.01161` | `0.01268` | `1.5681` | `-67.88%` |
| P9 no-XGBoost apples-to-apples | `9.359s` | `0.00024` | `0.01105` | `0.01231` | `1.5726` | `-66.49%` |

P10 raw IC improves slightly versus no-XGBoost, but Sharpe is basically flat and drawdown is worse. Against the supplied P9 baseline, the local run's drawdown regime is not comparable, so this must not be approved without an official full backtest artifact using identical config, data window, universe, costs, Stage2 settings, and target metric definitions.

### 2. P10 metrics are not comparable to default P9 XGBoost path

`scripts/run_phase35_backtest.py` defaults `use_xgboost=True`, and persists that config. But P10 explicitly bypasses XGBoost in `src/omega/quant/phase35_walk_forward.py:1396-1397`; the Stage4 XGBoost branch only exists in the non-P10 path at `src/omega/quant/phase35_walk_forward.py:1475-1539`.

Result: P10 artifacts can say `use_xgboost=true` while the P10 fold path did not use XGBoost. That makes P9/P10 performance claims easy to misread.

Required evidence before approval:
- P9 default XGBoost vs P10 with XGBoost disabled explicitly, clearly labelled; or
- P10 integrated with XGBoost and compared to P9 default path.

### 3. Blend weights can overweight anti-predictive horizons

Weight computation uses absolute quality in `src/omega/quant/phase35_walk_forward.py:1229-1239`, then adds each signal with a positive coefficient at `src/omega/quant/phase35_walk_forward.py:1249-1251`. If a horizon signal has negative validation IC, P10 does not invert it or zero it; it still gives it positive weight.

Captured full-ish P10 fold weights:
- Fold 3: all validation ICs negative; weights were h1 `24.8%`, h3 `25.0%`, h5 `50.2%`.
- Fold 7: h5 validation IC `-0.020287`; assigned h5 weight `88.5%`.

This is not a quality-based blend; it can amplify horizons that validation says are wrong-way for the target.

### 4. Degenerate/equal weights happen in smoke and are not guarded

Quick smoke P10 produced validation IC `0.0000` for h1/h3/h5 and fell back to equal weights `0.3333/0.3333/0.3333`. Baseline smoke also produced all-zero metrics, so this is mainly a quick-universe issue: `top_n_symbols=1` collapses cross-sectional z-scores and ICs.

However, P10 does not surface this as an invalid performance sample. Equal-weight fallback should be flagged in reports and excluded from performance claims unless the universe has enough cross-section.

### 5. Runtime overhead is only acceptable if performance improves, which is unproven

Measured no-save overhead:
- Quick mode: P10 `4.017s` vs baseline `2.749s` -> `+46%`.
- Full-ish XGBoost-flag path: P10 `16.928s` vs current P9 path `14.127s` -> `+20%`.
- P10 versus no-XGBoost apples-to-apples baseline: `16.928s` vs `9.359s` -> `+81%`.

The overhead is structurally expected because P10 computes horizon signal selection/gating three times. It is not justified without a clear Sharpe/drawdown/stability gain.

### 6. `blend_weight_method=train_ic` is a performance config trap

The CLI advertises `validation_ic` or `train_ic` in `scripts/run_phase35_backtest.py:108-114`, but `_compute_horizon_signal()` returns only validation IC at `src/omega/quant/phase35_walk_forward.py:1167-1179`, and `_blend_horizon_signals()` ignores `method` except logging at `src/omega/quant/phase35_walk_forward.py:1181-1255`.

This means experiments labelled `train_ic` silently use validation IC. Any performance report using this switch is unreliable.

### 7. Test suite does not test performance value

`tests/phase35/test_p10_multi_horizon_blend.py` mostly checks construction, non-NaN metrics, and partial fallback. It does not assert:
- P10 improves or at least does not degrade Sharpe/MaxDD versus P9 on a fixed fixture.
- Negative validation IC is zeroed, inverted, or penalized.
- Equal-weight fallback is reported and not used as proof.
- `train_ic` method actually changes weights.
- Runtime overhead remains within a defined budget.

## Required Fixes / Evidence

1. Fix blend weighting policy for negative validation IC: either require positive validation IC, flip the horizon signal when using negative IC intentionally, or make the weight signed and prove downstream Stage2 handles it correctly.
2. Make `blend_weight_method` real or remove it from CLI/config until implemented.
3. Produce official full P9/P10 comparison artifacts with identical config and explicit XGBoost state. Include fold-level IC, raw IC, daily CS IC, Sharpe, MaxDD, turnover/cost, and runtime.
4. Add a performance regression test or benchmark fixture that fails on Sharpe/drawdown degradation and catches degenerate equal-weight fallback.
5. Label quick-mode results as smoke-only and invalid for performance approval when `top_n_symbols < 5`.

## Final Fields

Role: Performance Tester / Role 23
Verdict: [NEEDS_FIX]
Performance Safety: FAIL
Role Compliance: PASS
Rebuttal Summary: P10 currently looks like a noisy multi-horizon average with unsafe absolute-IC weighting, incomplete experiment wiring, non-comparable XGBoost behavior, and no full evidence that it beats P9 after costs/drawdown. Quick zero metrics are due to insufficient one-symbol smoke universe, not proof of success or failure.
