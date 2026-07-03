# L2 Implementation Report — Risk-Adjusted Alpha Selection

**GATE:** `RISK_ADJUSTED_ALPHA_SELECTION_20260614`
**Role:** 16 (Machine Learning Engineer, Tier 2)
**KPI:** C (risk-adjusted composite)
**Boundary:** paper-trading-ready / no live trading
**Date:** 2026-06-14
**Status:** SUBMITTED FOR TIER 3 AUDIT

---

## 1. Role / Skill Source Audit

### Repo-local files read

| Type | Path | Status |
|------|------|--------|
| Role | `.agents/agent/machine-learning-engineer.md` | OK |
| Skill | `.agents/skills/python-patterns/SKILL.md` | OK |
| Skill | `.agents/skills/clean-code/SKILL.md` | OK |
| Skill | `.agents/skills/testing-patterns/SKILL.md` | OK |
| Skill | `.agents/skills/performance-profiling/SKILL.md` | OK |
| Skill | `.agents/skills/systematic-debugging/SKILL.md` | OK |
| Skill | `.agents/skills/ml-dl-rl/SKILL.md` | OK |
| Skill | `.agents/skills/backtesting-pit-safety/SKILL.md` | OK |
| Skill | `.agents/skills/vietnam-market-data/SKILL.md` | OK |

### Forbidden path scan

- Antigravity scratch / OpenClaw: **NOT accessed**
- `C:\Users\GHC\.agents` / Codex memory: **NOT accessed**
- All skill/role files sourced exclusively from `C:\Users\GHC\repos\OMEGA_QUANT\.agents\`
- **FORBIDDEN_PATH_SCAN: PASS**

### Frontmatter parsed

```yaml
name: machine-learning-engineer
role_id: 16
tier: 2
skills: [python-patterns, clean-code, testing-patterns, performance-profiling,
         systematic-debugging, ml-dl-rl, backtesting-pit-safety, vietnam-market-data]
sod_boundary: "implementation-only, test required, no self-approval, submit to Tier3"
```

---

## 2. Implementation Summary

### New files

| File | Purpose |
|------|---------|
| `src/omega/quant/walk_forward/risk_adjusted_alpha_score.py` | Composite risk-adjusted scoring engine |
| `tests/test_risk_adjusted_alpha_score.py` | 41 deterministic unit tests |

### Modified files

| File | Change |
|------|--------|
| `src/omega/quant/walk_forward/__init__.py` | Export new symbols |
| `src/omega/quant/walk_forward/alpha_selector.py` | Add `risk_adjusted_select()` method |
| `src/omega/quant/alpha/phase35.py` | Add `risk_adjusted_alpha_selection` parameter + `risk_adjusted_select()` method + 2 integration points |
| `scripts/run_phase35_backtest.py` | Add `--risk-adjusted-alpha-selection` CLI flag |

---

## 3. Composite Score Design

The composite score is a weighted sum of 6 risk-adjusted components, each normalized to [0, 1]:

| Component | Weight | Source | Mapping |
|-----------|--------|--------|---------|
| Validation IC | 0.25 | Spearman IC on embargoed val set | `(ic + 1) / 2` |
| IC Stability | 0.20 | IC Sharpe = mean/std of daily IC | Sigmoid: `1/(1+exp(-2*x))` |
| Expected Sharpe | 0.15 | If safely available | Sigmoid: `1/(1+exp(-x))` |
| Turnover Penalty | 0.15 | Day-over-day rank churn | `1 - turnover` |
| Drawdown Penalty | 0.10 | If safely available | `1 + max_dd` (clamped) |
| Overfit Gap | 0.15 | `|train_IC - val_IC|` | `1 - |gap|` |

**Unavailable components** (Sharpe, drawdown) use neutral fallback `_NEUTRAL_SCORE = 0.5` and weights are renormalized.

### Selection criteria

- Minimum composite score: 0.35
- Require positive validation IC
- Maximum overfit gap: 0.15
- Top-N selection (configurable)

### PIT Safety

- **All data inputs are from train/validation periods only**
- No test-set data is accessed at any point
- Daily IC series computed on embargoed validation set
- Turnover estimated on embargoed training set
- Overfit gap uses train IC (embargoed) vs validation IC (embargoed)

### Paper-trading boundary

- This module **never** touches live execution paths or order routing
- `RiskAdjustedSelectionResult` includes `paper_trading_gate: PASS|FAIL`
- Gate reasons documented for audit trail

---

## 4. Opt-in Design (Default Disabled)

- `risk_adjusted_alpha_selection=False` in engine constructor (default)
- CLI flag `--risk-adjusted-alpha-selection` is opt-in
- When disabled, the existing IC-based selection pipeline runs unchanged
- Fallback: if risk-adjusted selection yields 0 alphas, falls back to default path

---

## 5. Test Results

### Unit tests: 41/41 PASSED

```
python -m pytest tests/test_risk_adjusted_alpha_score.py -v
41 passed, 3 warnings in 6.93s
```

**Test matrix covered:**

| # | Category | Tests | Status |
|---|----------|-------|--------|
| 1 | Stable positive IC vs noisy | 3 | PASS |
| 2 | High turnover penalty | 4 | PASS |
| 3 | Overfit gap penalty | 3 | PASS |
| 4 | NaN safety | 7 | PASS |
| 5 | Default disabled path | 4 | PASS |
| 6 | Selection + paper-trading gate | 5 | PASS |
| 7 | Batch scoring | 2 | PASS |
| 8 | Serialization | 3 | PASS |
| 9 | Helper mapping functions | 3 | PASS |
| 10 | Validation IC computation | 5 | PASS |
| 11 | Drawdown penalty | 2 | PASS |

### Smoke tests: Phase 3.5 Backtest

**Command 1 — Default (disabled):**
```
python scripts/run_phase35_backtest.py --quick-mode --no-xgboost
```
- Result: Completed successfully
- `risk_adjusted_alpha_selection: False` in output JSON
- No `[RiskAdj]` log messages

**Command 2 — Enabled:**
```
python scripts/run_phase35_backtest.py --quick-mode --no-xgboost --risk-adjusted-alpha-selection
```
- Result: Completed successfully
- `risk_adjusted_alpha_selection: True` in output JSON
- `[RiskAdj] Selected 1/7 alphas: gate=PASS` (fold 1)
- `[RiskAdj] Selected 4/7 alphas: gate=PASS` (fold 2)

### Module import verification

```
from omega.quant.walk_forward.risk_adjusted_alpha_score import ...  OK
from omega.quant.walk_forward import AlphaScoreBreakdown ...        OK
from omega.quant.walk_forward.alpha_selector import ...             OK
AlphaSelectionMixin.risk_adjusted_select exists: True
```

---

## 6. Evidence / JSON Summary

The `RiskAdjustedSelectionResult.to_dict()` output includes:
- `selected_alphas`: list of selected alpha names
- `rejected_alphas`: list of rejected alpha names with reasons
- `score_breakdowns`: per-alpha composite score + all 6 component scores + raw values
- `paper_trading_gate`: "PASS" or "FAIL"
- `paper_trading_reasons`: human-readable gate evaluation reasons
- `config`: scoring parameters used

---

## 7. Boundary Compliance

| Boundary | Status |
|----------|--------|
| Paper-trading-ready | PASS — no live execution paths touched |
| No live trading | PASS — module is selection-only |
| PIT safety | PASS — only embargoed train/val data used |
| Opt-in default-off | PASS — `risk_adjusted_alpha_selection=False` default |
| SOD: implementation-only | PASS — submitted to Tier 3 for audit |
| SOD: no self-approval | PASS — cannot approve own work |
| Tests required | PASS — 41 unit tests all passing |

---

## 8. Tier 3 Audit Submission

Submitted to:
- **Code Reviewer** (role 21): Code quality, patterns, ML best practices
- **QA Engineer** (role 17): Test coverage, validation logic, edge cases
- **Performance Tester** (role 23): Computational efficiency of composite scoring

**Cannot proceed until all Tier 3 roles return [APPROVED].**

---

## 9. Exact Commands

```bash
# Unit tests
python -m pytest tests/test_risk_adjusted_alpha_score.py -v

# Phase 3.5 backtest — default (disabled)
python scripts/run_phase35_backtest.py --quick-mode --no-xgboost

# Phase 3.5 backtest — risk-adjusted enabled
python scripts/run_phase35_backtest.py --quick-mode --no-xgboost --risk-adjusted-alpha-selection

# CLI help
python scripts/run_phase35_backtest.py --help
```
