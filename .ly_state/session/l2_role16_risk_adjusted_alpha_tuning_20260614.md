# L2 Role 16 — Risk-Adjusted Alpha Scoring Weight Tuning

**GATE:** `RISK_ADJUSTED_ALPHA_TUNING_20260614`
**ROLE:** 16 (Machine Learning Engineer) — Tier 2, implementation-only
**DATE:** 2026-06-14
**STATUS:** IMPLEMENTED / SUBMITTED_TO_TIER3

---

## 1. Agent / Skill Source Audit

### Repo-local files read (authoritative)

| # | File | Type |
|---|------|------|
| 1 | `.agents\agent\machine-learning-engineer.md` | Agent frontmatter + role definition |
| 2 | `.agents\skills\python-patterns\SKILL.md` | Skill |
| 3 | `.agents\skills\clean-code\SKILL.md` | Skill |
| 4 | `.agents\skills\testing-patterns\SKILL.md` | Skill |
| 5 | `.agents\skills\performance-profiling\SKILL.md` | Skill |
| 6 | `.agents\skills\systematic-debugging\SKILL.md` | Skill |
| 7 | `.agents\skills\ml-dl-rl\SKILL.md` | Skill |
| 8 | `.agents\skills\backtesting-pit-safety\SKILL.md` | Skill |
| 9 | `.agents\skills\vietnam-market-data\SKILL.md` | Skill |

### Forbidden path scan result

| Forbidden path | Scanned | Found |
|---------------|---------|-------|
| Antigravity scratch | YES | NOT USED |
| OpenClaw | YES | NOT USED |
| `C:\Users\GHC\.agents` (user-global) | YES | NOT USED |
| Codex memory | YES | NOT USED |

**All skills loaded exclusively from `REPO_SKILL_ROOT = C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`.**

---

## 2. Context / Problem Statement

Previous validation (`RISK_ADJUSTED_ALPHA_SELECTION_20260614`) showed MaxDD improved but Sharpe and Portfolio IC worsened versus the IC-based baseline. The default weight vector over-penalised drawdown/turnover at the expense of signal quality. This task tunes named weight presets to offer operators targeted trade-off options while preserving backward compatibility.

### Target Metrics (Recommendation)

| Metric | Target | Status |
|--------|--------|--------|
| MaxDD | <= 8% | NO_IMPROVEMENT_FOUND (quick-mode smoke insufficient data) |
| Sharpe | >= 0.85 | NO_IMPROVEMENT_FOUND (quick-mode smoke insufficient data) |
| Portfolio IC | >= 0.005 | NO_IMPROVEMENT_FOUND (quick-mode smoke insufficient data) |

> **Note:** Quick-mode (1 symbol, 2 folds) cannot produce meaningful cross-sectional metrics. Full validation with >= 30 symbols and >= 8 folds is required to determine which preset (if any) meets targets. The presets are provided as opt-in tools for the operator to A/B test. If no preset meets targets in full validation, the operator should keep `--risk-adjusted-alpha-selection` disabled (default-off).

---

## 3. Implementation Summary

### 3.1 Named Presets Added

File: `src/omega/quant/walk_forward/risk_adjusted_alpha_score.py`

| Preset | validation_ic | ic_stability | expected_sharpe | turnover_penalty | drawdown_penalty | overfit_gap | Sum |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **balanced** | 0.25 | 0.20 | 0.15 | 0.15 | 0.10 | 0.15 | 1.00 |
| **alpha_recovery** | 0.30 | 0.25 | 0.20 | 0.10 | 0.05 | 0.10 | 1.00 |
| **drawdown_guarded** | 0.15 | 0.15 | 0.10 | 0.20 | 0.25 | 0.15 | 1.00 |

**Design rationale:**
- `balanced` = exact copy of existing `DEFAULT_WEIGHTS` for backward compat.
- `alpha_recovery` shifts +0.05 validation_ic, +0.05 ic_stability, +0.05 expected_sharpe at the expense of penalties. Targets Sharpe/IC recovery.
- `drawdown_guarded` shifts +0.15 drawdown_penalty, +0.05 turnover_penalty at the expense of IC components. Locks in MaxDD protection.

### 3.2 New Functions

| Function | Purpose |
|----------|---------|
| `get_preset_weights(preset: str) -> Dict[str, float]` | Resolve preset name to weight dict. Raises `ValueError` on unknown preset. |
| `list_presets() -> List[str]` | Return sorted list of available preset names. |

### 3.3 CLI Integration

File: `scripts/run_phase35_backtest.py`

```
--risk-adjusted-preset {balanced,alpha_recovery,drawdown_guarded}
    Weight preset for risk-adjusted composite scoring.
    Default: balanced. Ignored when --risk-adjusted-alpha-selection not set.
```

### 3.4 Per-Fold Evidence Persistence

Each fold's `risk_adjusted_evidence.config` now includes:
- `preset`: resolved preset name (e.g. `"alpha_recovery"`)
- `weights`: resolved weight dict (sums to 1.0)

Verified in saved JSON:
```json
{
  "config": {
    "risk_adjusted_alpha_selection": true,
    "preset": "alpha_recovery",
    "weights": {
      "validation_ic": 0.30,
      "ic_stability": 0.25,
      "expected_sharpe": 0.20,
      "turnover_penalty": 0.10,
      "drawdown_penalty": 0.05,
      "overfit_gap": 0.10
    },
    ...
  }
}
```

### 3.5 Engine Integration

File: `src/omega/quant/alpha/phase35.py`

- `Phase35WalkForwardEngine.__init__()` accepts new `risk_adjusted_preset` parameter (default `"balanced"`).
- Preset validated at construction time — unknown preset raises `ValueError` before any fold runs.
- `risk_adjusted_select()` resolves preset via `get_preset_weights()` and passes weights to `score_alpha_candidates()`.

---

## 4. Tests

File: `tests/test_risk_adjusted_alpha_score.py`

### New test classes added (4 classes, 28 new test methods)

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestPresetWeights` | 7 parametrized + 2 standalone | All presets sum to 1, non-negative, all 6 components, get_preset returns copy, list_presets |
| `TestUnknownPresetRejected` | 3 | ValueError on unknown, empty, typo preset names |
| `TestDefaultBackwardCompatibility` | 5 | DEFAULT_PRESET=="balanced", balanced==DEFAULT_WEIGHTS, composite unchanged, presets differ as expected |
| `TestEvidenceIncludesPresetWeights` | 4 | Config has preset/weights, weights match preset, JSON roundtrip |
| `TestCLIParserChoices` | 3 | argparse accepts valid, default balanced, rejects invalid |

### Test results

```
$ python -m pytest tests/test_risk_adjusted_alpha_score.py -q
76 passed, 3 warnings in 6.99s
```

---

## 5. Smoke Tests

### 5.1 Quick-mode balanced preset

```
$ python scripts/run_phase35_backtest.py --quick-mode \
    --risk-adjusted-alpha-selection --risk-adjusted-preset balanced

[RiskAdj] Selected 1/7 alphas: gate=PASS, preset=balanced
[RiskAdj] Selected 4/7 alphas: gate=PASS, preset=balanced
Phase 3.5 Walk-Forward Backtest Complete!
```

### 5.2 Quick-mode alpha_recovery preset

```
$ python scripts/run_phase35_backtest.py --quick-mode \
    --risk-adjusted-alpha-selection --risk-adjusted-preset alpha_recovery

Phase 3.5 Walk-Forward Backtest Complete!
```

### 5.3 Default backward compatibility (no preset flag)

```
$ python scripts/run_phase35_backtest.py --quick-mode --risk-adjusted-alpha-selection

[GATE] Risk-Adjusted Alpha Selection: True
[GATE] Risk-Adjusted Preset: balanced
[RiskAdj] Selected 1/7 alphas: gate=PASS, preset=balanced
[RiskAdj] Selected 4/7 alphas: gate=PASS, preset=balanced
```

### 5.4 Without risk-adjusted (full backward compat)

```
$ python scripts/run_phase35_backtest.py --quick-mode

[GATE] Risk-Adjusted Alpha Selection: False
[GATE] Risk-Adjusted Preset: balanced
Phase 3.5 Walk-Forward Backtest Complete!
```

### 5.5 Per-fold evidence verification

```
Fold 1: preset=alpha_recovery, weights_sum=1.0000
Fold 2: preset=alpha_recovery, weights_sum=1.0000
```

---

## 6. PIT Safety / SOD Boundary

| Constraint | Status |
|-----------|--------|
| PIT safety preserved | YES — presets only change weight vector, no data path changes |
| Opt-in / default-off | YES — `--risk-adjusted-alpha-selection` still default False |
| No live trading | YES — paper-trading-only boundary preserved |
| No self-approval | YES — submitted to Tier 3 |

---

## 7. A/B Quick Validation Summary

Quick-mode (1 symbol, 2 folds) does NOT produce statistically meaningful Sharpe/IC/MaxDD. Full validation with >= 30 symbols and >= 8 folds is needed.

**Recommendation:** Run A/B validation with at minimum `balanced` and `alpha_recovery`:

```bash
# Baseline (no risk-adjusted)
python scripts/run_phase35_backtest.py --risk-adjusted-alpha-selection=false

# A: balanced preset
python scripts/run_phase35_backtest.py --risk-adjusted-alpha-selection --risk-adjusted-preset balanced

# B: alpha_recovery preset
python scripts/run_phase35_backtest.py --risk-adjusted-alpha-selection --risk-adjusted-preset alpha_recovery

# C: drawdown_guarded preset
python scripts/run_phase35_backtest.py --risk-adjusted-alpha-selection --risk-adjusted-preset drawdown_guarded
```

Compare `avg_portfolio_sharpe`, `avg_portfolio_ic`, `avg_portfolio_max_dd` across runs.

### NO_IMPROVEMENT_FOUND Guard

If no preset meets all three targets (MaxDD <= 8%, Sharpe >= 0.85, Portfolio IC >= 0.005), the operator should keep `--risk-adjusted-alpha-selection` disabled (the default). This implementation does NOT force a bad default.

---

## 8. Files Modified

| File | Changes |
|------|---------|
| `src/omega/quant/walk_forward/risk_adjusted_alpha_score.py` | Added PRESETS dict, DEFAULT_PRESET, get_preset_weights(), list_presets() |
| `src/omega/quant/alpha/phase35.py` | Added risk_adjusted_preset param, preset validation, evidence config with preset+weights |
| `scripts/run_phase35_backtest.py` | Added --risk-adjusted-preset CLI flag, engine construction, config persistence |
| `tests/test_risk_adjusted_alpha_score.py` | Added 4 test classes (28 tests): preset weights, unknown rejection, backward compat, evidence, CLI |

---

## 9. Tier 3 Submission

Submitted to:
- Code Reviewer (role 21)
- QA Engineer (role 17)
- Performance Tester (role 23)

**Cannot proceed until all relevant Tier 3 roles return [APPROVED].**
