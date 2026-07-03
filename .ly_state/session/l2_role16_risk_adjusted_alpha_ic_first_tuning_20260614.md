# L2 Implementation Report: IC-First Guarded Risk-Adjusted Alpha Selection Tuning

| Field | Value |
|---|---|
| **Role** | 16 — Machine Learning Engineer (Tier 2) |
| **Gate** | `RISK_ADJUSTED_ALPHA_IC_FIRST_TUNING_20260614` |
| **Date** | 2026-06-14 |
| **Status** | `[IMPLEMENTED]` — awaiting Tier 3 audit |
| **Boundary** | Paper-trading-ready / no live trading / no execution changes |

---

## 1. Agent & Skill Source Contract

### Repo-local files read

| File | Path |
|---|---|
| Agent definition | `.agents/agent/machine-learning-engineer.md` |
| python-patterns | `.agents/skills/python-patterns/SKILL.md` |
| clean-code | `.agents/skills/clean-code/SKILL.md` |
| testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| performance-profiling | `.agents/skills/performance-profiling/SKILL.md` |
| systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` |
| ml-dl-rl | `.agents/skills/ml-dl-rl/SKILL.md` |
| backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` |

### Forbidden path scan

**Result: CLEAN** — Forbidden path scan confirms: `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source. All 8 skills sourced exclusively from `REPO_SKILL_ROOT = .agents/skills/`.

---

## 2. Context: A/B Baseline Failure Analysis

Full A/B report: `risk_adjusted_ab_report.md` (session 74b0ccc4)

| Variant | Portfolio IC | Sharpe | MaxDD | Pass? |
|---|---:|---:|---:|---|
| baseline (no RA selection) | 0.0091 | 0.8837 | -7.58% | Yes |
| balanced | -0.0065 | 0.6124 | -6.52% | No |
| alpha_recovery | -0.0075 | 0.6124 | -6.52% | No |
| drawdown_guarded | -0.0046 | 0.6124 | -6.52% | No |

**Root cause**: All existing presets overweight risk penalties (drawdown 25%, turnover 20% in drawdown_guarded). When expected_sharpe/drawdown are unavailable, weights redistribute to active components, inflating risk penalty influence. This causes the composite to select alphas with safer risk profiles but negative IC, producing worse out-of-sample performance than simple IC-based selection.

**Recommendation from A/B**: Tune weights so validation IC is preserved while drawdown penalty serves only as tie-breaker or soft cap.

---

## 3. Implementation: `ic_first_guarded` Preset

### 3.1 Design Rationale

The `ic_first_guarded` preset allocates weights in two tiers:

| Tier | Components | Combined Weight | Role |
|---|---|---:|---|
| **Primary rank** | validation_ic, ic_stability, expected_sharpe | 80% | Drive the ranking |
| **Soft penalty** | turnover_penalty, drawdown_penalty, overfit_gap | 20% | Tie-breakers only |

| Component | Weight | Tier |
|---|---:|---|
| validation_ic | 0.35 | Primary rank |
| ic_stability | 0.30 | Primary rank |
| expected_sharpe | 0.15 | Primary rank |
| turnover_penalty | 0.08 | Soft penalty |
| drawdown_penalty | 0.05 | Soft penalty |
| overfit_gap | 0.07 | Soft penalty |
| **Total** | **1.00** | |

### 3.2 Weight Redistribution Analysis

When expected_sharpe and drawdown are unavailable (common case):

| Preset | IC weight (normalized) | Risk penalty weight (normalized) |
|---|---:|---:|
| balanced | 60.0% | 40.0% |
| alpha_recovery | 73.7% | 26.3% |
| drawdown_guarded | 42.9% | 57.1% |
| **ic_first_guarded** | **81.3%** | **18.8%** |

`ic_first_guarded` ensures IC components dominate even after redistribution.

### 3.3 Rank Component Classification

Persisted in evidence config for Tier 3 audit:

- `primary_rank_components`: `["validation_ic", "ic_stability", "expected_sharpe"]`
- `soft_penalty_components`: `["turnover_penalty", "drawdown_penalty", "overfit_gap"]`

### 3.4 Opt-in / Default Preservation

- `--risk-adjusted-alpha-selection`: opt-in flag, **default disabled** (unchanged)
- `--risk-adjusted-preset`: default `balanced` (unchanged, backward-compatible)
- `DEFAULT_PRESET = "balanced"` (unchanged)

---

## 4. Files Modified

| File | Change |
|---|---|
| `src/omega/quant/walk_forward/risk_adjusted_alpha_score.py` | Added `ic_first_guarded` preset to `PRESETS`; added `IC_FIRST_PRIMARY_COMPONENTS` and `IC_FIRST_SOFT_PENALTY_COMPONENTS` constants; added `get_preset_rank_components()` function; updated module docstring |
| `src/omega/quant/alpha/phase35.py` | Updated `risk_adjusted_select()` to import `get_preset_rank_components` and include `primary_rank_components` / `soft_penalty_components` in evidence config; updated docstring |
| `scripts/run_phase35_backtest.py` | Added `ic_first_guarded` to `--risk-adjusted-preset` choices list and help text |
| `tests/test_risk_adjusted_alpha_score.py` | Added `TestICFirstGuardedPreset` class with 21 new deterministic tests |

### Files NOT modified (no changes needed)

- `src/omega/quant/walk_forward/alpha_selector.py` — mixin delegates to scoring module; preset logic handled by engine

---

## 5. Test Results

### Command

```
python -m pytest tests/test_risk_adjusted_alpha_score.py -q
```

### Result

```
101 passed, 3 warnings in 7.74s
```

All 101 tests pass (80 existing + 21 new for `ic_first_guarded`).

### New Test Coverage (TestICFirstGuardedPreset — 21 tests)

| Test | Verifies |
|---|---|
| `test_ic_first_guarded_exists_in_presets` | Preset registered |
| `test_ic_first_guarded_weights_sum_to_one` | Weights valid |
| `test_ic_first_guarded_all_components_present` | All 6 components |
| `test_ic_first_guarded_all_weights_non_negative` | No negative weights |
| `test_ic_first_guarded_in_list_presets` | Listed in `list_presets()` |
| `test_get_preset_weights_returns_valid` | Weight resolution works |
| `test_ic_weight_dominates_risk_weights` | IC > risk penalties |
| `test_ic_weight_at_least_60_percent` | IC >= 60% |
| `test_risk_penalties_at_most_25_percent` | Risk <= 25% |
| `test_positive_ic_outranks_negative_ic_with_better_drawdown` | **Key: IC-first ranking** |
| `test_positive_ic_outranks_zero_ic_with_perfect_drawdown` | IC > 0 beats IC = 0 |
| `test_drawdown_breaks_ties_when_ic_close` | Tie-breaker: drawdown |
| `test_turnover_breaks_ties_when_ic_close` | Tie-breaker: turnover |
| `test_evidence_config_has_rank_components` | Evidence includes rank meta |
| `test_evidence_json_roundtrip_with_rank_components` | JSON round-trip |
| `test_get_preset_rank_components_ic_first` | Metadata function |
| `test_get_preset_rank_components_balanced` | Non-IC-first fallback |
| `test_get_preset_rank_components_alpha_recovery` | Non-IC-first fallback |
| `test_ic_first_differs_from_balanced` | Score differs from balanced |
| `test_ic_first_less_sensitive_to_drawdown_than_guarded` | Lower DD sensitivity |
| `test_score_breakdown_has_raw_values_for_rank_audit` | Raw values preserved |
| `test_score_breakdown_serialization_includes_all_raw` | Serialization complete |

---

## 6. PIT Safety Verification

| Check | Status |
|---|---|
| No test-set data used in scoring | PASS — all inputs from train/validation/embargoed data |
| No look-ahead bias introduced | PASS — preset only changes weight allocation, not data flow |
| No live trading changes | PASS — paper-trading-only boundary preserved |
| No execution path changes | PASS — no order routing or live execution code modified |
| Opt-in default disabled | PASS — `risk_adjusted_alpha_selection=False` default |
| Backward compatibility | PASS — `DEFAULT_PRESET="balanced"`, `DEFAULT_WEIGHTS` unchanged |

---

## 7. Evidence Persistence

The per-fold evidence config for `ic_first_guarded` now includes:

```json
{
  "risk_adjusted_alpha_selection": true,
  "preset": "ic_first_guarded",
  "weights": {
    "validation_ic": 0.35,
    "ic_stability": 0.30,
    "expected_sharpe": 0.15,
    "turnover_penalty": 0.08,
    "drawdown_penalty": 0.05,
    "overfit_gap": 0.07
  },
  "primary_rank_components": ["validation_ic", "ic_stability", "expected_sharpe"],
  "soft_penalty_components": ["turnover_penalty", "drawdown_penalty", "overfit_gap"],
  "top_n": 5,
  "min_composite_score": 0.35,
  "require_positive_val_ic": true,
  "max_overfit_gap": 0.15,
  "return_col": "fwd_ret_5"
}
```

Each alpha's score breakdown includes raw values (`raw_validation_ic`, `raw_ic_sharpe`, `raw_turnover`, `raw_max_drawdown`, `raw_overfit_gap`) for audit reconstruction of ranking decisions.

---

## 8. SOD / Tier 3 Submission

This implementation is **Tier 2 only** (implementation + test). Submitted to:

- **Code Reviewer (role 21)**: Code quality, preset design, naming
- **QA Engineer (role 17)**: Test coverage, edge cases, determinism
- **Performance Tester (role 23)**: No performance impact (weight lookup is O(1))

**Cannot self-approve.** Awaiting Tier 3 audit.

---

## 9. Commands & Results

```
> python -m pytest tests/test_risk_adjusted_alpha_score.py -q
101 passed, 3 warnings in 7.74s
```
