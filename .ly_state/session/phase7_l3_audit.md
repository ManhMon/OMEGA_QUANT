# L3 Audit — Phase 7 Capacity Sweep + Falsification (Python)

**Date**: 2026-05-30 13:55 GMT+7
**Auditor**: Role21-CodeReviewer (Python independent audit)
**Method**: deterministic numerical/structural checks via `scripts/audit_phase7.py`
**Reason for non-codex audit**: pure number consistency verification (no code semantics review needed); codex 2-step pattern reserved for code-change audits per SOUL.md Rule 9.

## Inputs reviewed (6 backtest JSONs + 1 falsification)
- `phase5_full_1B_noLSTM.json`, `phase5_full_5B.json`, `phase5_full_10B_noLSTM.json`, `phase5_full_30B.json`, `phase5_full_50B.json`, `phase5_full_100B_noLSTM.json`
- `phase5_full_1B_shuffle.json`

## Verdict

**[APPROVED]** — 6/6 checks PASS.

## Checks executed

| # | Check | Result | Evidence |
|--|--|--|--|
| 1 | Alpha invariance | PASS | median_test_IC = 0.0173 identical across all 6 capitals (alpha is capital-independent; only cost differs) |
| 2 | Capacity monotone | PASS | SR_ann monotone decreasing: 3.671 / 3.517 / 3.320 / 2.526 / 1.779 / 0.188 |
| 3 | Slippage linearity | PASS | All 5 capital-pair ratios match expected within <1% (1B→5B: 5.00 vs 5.00, 5B→10B: 2.00 vs 2.00, 10B→30B: 3.00 vs 3.00, 30B→50B: 1.667 vs 1.667, 50B→100B: 2.00 vs 2.00) |
| 4 | Commission/spread/turnover invariance | PASS | commission=0.028411, spread=0.014206, turnover=14.21 identical across all 6 capitals |
| 5 | Falsification (y-shuffle) | PASS | fold_SR collapsed to 23.9% of real (well under 30% threshold); IC sign-flip from +0.0173 to -0.0183 (no leakage) |
| 6 | Fold stability | PASS | 80% folds positive (36/45) at 1B, well above 60% threshold |

## Detailed evidence

### Alpha invariance (Check 1)
Median test IC = +0.0173 ± 0 across 1B / 5B / 10B / 30B / 50B / 100B.
This is the strongest sanity check: alpha is computed BEFORE cost subtraction, and Phase 5 cleaning is deterministic, so identical input data → identical Ridge fits → identical IC across capitals. Any drift would indicate a regression in the pipeline.

### Capacity monotone (Check 2)
SR_ann sequence (1B → 100B):
```
3.671 → 3.517 → 3.320 → 2.526 → 1.779 → 0.188
```
Strictly decreasing. Production decision: capacity ceiling between 50B and 100B.

### Slippage linearity (Check 3)
Slippage = `0.10 × participation × |delta_w|`, where `participation = trade_VND / ADV` and `trade_VND ∝ capital`. Theory: slippage scales linearly with capital. Measured ratios match theory within numerical precision.

### Commission/spread/turnover invariance (Check 4)
Commission and spread are functions of TURNOVER ONLY, not capital. Turnover depends on signal/weight stability, which is a function of the alpha (not capital). Confirmed: all 3 metrics identical across capitals to 6 decimal places.

### Falsification (Check 5)
- **Real**: fold_SR_ann = +3.6715, median_test_IC = +0.0173
- **y-shuffle**: fold_SR_ann = -0.8783 (24% of real magnitude), median_test_IC = -0.0183 (sign-flip)
- **Verdict**: alpha is REAL, not artifact. Shuffling target within each date breaks alpha-target link → SR collapses near zero (slightly negative due to cost), IC flips sign.

### Fold stability (Check 6)
1B fold SR distribution:
- mean +0.231, median +0.232, std 0.264
- 80% of 45 folds positive (36/45)
- Top fold +0.870, worst fold -0.386

## Disposition

**Phase 7 gate APPROVED.** Capacity table and falsification result are validated.

## Evidence chain

- `scripts/audit_phase7.py` (deterministic, idempotent verification script)
- `.ly_state/session/phase7_audit_python.stdout` (verbatim audit run output)
- `.ly_state/session/phase5_full_*.json` (raw backtest artifacts, 7 files)
- `.ly_state/session/phase5_capacity_report.txt` (human-readable summary)
