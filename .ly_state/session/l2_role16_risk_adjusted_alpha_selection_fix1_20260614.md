# L2 Fix1 Report — Risk-Adjusted Alpha Selection

**Gate**: RISK_ADJUSTED_ALPHA_SELECTION_FIX1_20260614
**Prior Gate**: RISK_ADJUSTED_ALPHA_SELECTION_20260614
**Role**: machine-learning-engineer (Role 16, OpenCode L2)
**Date**: 2026-06-14
**Status**: FIX_COMPLETE — submitted to Tier 3 audit

---

## Repo-Local Sources Read

### Agent Definition
- `.agents/agent/machine-learning-engineer.md` — role_id: 16, tier: 2, platform: OpenCode

### Skills (from `.agents/skills/` only)
1. `python-patterns/SKILL.md`
2. `clean-code/SKILL.md`
3. `testing-patterns/SKILL.md`
4. `performance-profiling/SKILL.md`
5. `systematic-debugging/SKILL.md`
6. `ml-dl-rl/SKILL.md`
7. `backtesting-pit-safety/SKILL.md`
8. `vietnam-market-data/SKILL.md`

### Forbidden Path Scan
- `C:\Users\GHC\.agents` — EXISTS but NOT used as source (non-authoritative).
- Antigravity scratch / OpenClaw / Codex memory — NOT accessed.
- All skills loaded exclusively from `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\`.

### L3 Audit Report
- `.ly_state/session/audit_reports/role20_risk_adjusted_alpha_selection_20260614.md` — verdict: [NEEDS_FIX]

---

## L3 Findings Addressed

### Finding 1 (BLOCKING): Enabled run does not persist risk-adjusted selection evidence

**Root Cause**: `ra_result` (RiskAdjustedSelectionResult) was computed but only `selected_alphas` was extracted. The full result was dropped. `FoldMetrics` had no field for evidence. The saved JSON only recorded `config.risk_adjusted_alpha_selection` (boolean).

**Fix Applied**:

1. **`FoldMetrics`** (`src/omega/quant/alpha/phase35.py:135`):
   - Added `risk_adjusted_evidence: Optional[Dict[str, any]]` field.

2. **`run_fold()` single-horizon path** (`phase35.py:~1767`):
   - Initialized `ra_result = None` before the multi-horizon/single-horizon branch.
   - Single-horizon path sets `ra_result` from `risk_adjusted_select()`.
   - At `FoldMetrics` construction: evidence extracted from `ra_result.to_dict()` (single-horizon) or `gate_metadata['risk_adjusted_evidence']` (multi-horizon).

3. **`_compute_horizon_signal()` multi-horizon path** (`phase35.py:~1382`):
   - Captured `_horizon_ra_result` from `risk_adjusted_select()`.
   - Added `risk_adjusted_evidence` key to `gate_metadata` dict.

4. **`risk_adjusted_select()`** (`phase35.py:~775`):
   - Populated `result.config` with selection parameters (top_n, min_composite_score, require_positive_val_ic, max_overfit_gap, return_col).

5. **`serialize_fold_details()`** (`scripts/run_phase35_backtest.py:76`):
   - Added `risk_adjusted_alpha_selection` key to fold dict when `risk_adjusted_evidence` is present.

### Finding 2 (BLOCKING): `to_dict()` omits `raw_expected_sharpe`

**Root Cause**: `RiskAdjustedSelectionResult.to_dict()` serialized `raw_max_drawdown` but omitted `raw_expected_sharpe` from score breakdowns.

**Fix Applied**:

- **`risk_adjusted_alpha_score.py:120`**: Added `"raw_expected_sharpe": round(bd.raw_expected_sharpe, 6)` to the score_breakdowns serialization in `to_dict()`.

---

## Regression Tests Added

### `tests/test_risk_adjusted_alpha_score.py`

**Test class 12: `TestRawExpectedSharpeSerialization`** (3 tests)
- `test_raw_expected_sharpe_present_in_to_dict`: verifies key exists and value is correct when sharpe is available.
- `test_raw_expected_sharpe_zero_when_unavailable`: verifies safe fallback (0.0) when sharpe is None.
- `test_raw_expected_sharpe_in_json_roundtrip`: verifies value survives JSON serialize/deserialize.

**Test class 13: `TestEvidencePersistence`** (6 tests)
- `test_evidence_has_selected_alphas`: verifies selected_alphas list present and populated.
- `test_evidence_has_rejected_alphas_with_reasons`: verifies rejected list and rejection_reason strings.
- `test_evidence_has_paper_trading_gate`: verifies gate PASS/FAIL and reasons list.
- `test_evidence_has_score_breakdowns`: verifies all 6 component scores + all raw values including `raw_expected_sharpe`.
- `test_evidence_has_config`: verifies config dict is present.
- `test_evidence_saved_to_file`: verifies `save_evidence()` writes complete JSON with all required fields.

---

## Commands and Results

### 1. Unit Tests
```
python -m pytest tests/test_risk_adjusted_alpha_score.py -q
```
**Result**: 50 passed, 3 warnings (41 original + 9 new regression tests).

### 2. Phase 3.5 Quick — Disabled (default)
```
python scripts/run_phase35_backtest.py --quick-mode --no-xgboost
```
**Result**: PASS. Config logged `Risk-Adjusted Alpha Selection: False`. No `[RiskAdj]` logs. Saved JSON has NO `risk_adjusted_alpha_selection` key in fold_details.

### 3. Phase 3.5 Quick — Enabled
```
python scripts/run_phase35_backtest.py --quick-mode --no-xgboost --risk-adjusted-alpha-selection
```
**Result**: PASS. Config logged `Risk-Adjusted Alpha Selection: True`. Observed:
- Fold 1: `[RiskAdj] Selected 1/7 alphas: gate=PASS`
- Fold 2: `[RiskAdj] Selected 4/7 alphas: gate=PASS`

### 4. Evidence Verification (enabled JSON)
Saved JSON `data/phase35_results/phase35_backtest_results_baseline.json` contains per-fold:
- `risk_adjusted_alpha_selection.selected_alphas` — list of selected alpha names
- `risk_adjusted_alpha_selection.rejected_alphas` — list of rejected alpha names
- `risk_adjusted_alpha_selection.paper_trading_gate` — "PASS"
- `risk_adjusted_alpha_selection.paper_trading_reasons` — list of reason strings
- `risk_adjusted_alpha_selection.config` — dict with top_n, min_composite_score, etc.
- `risk_adjusted_alpha_selection.score_breakdowns` — per-alpha dict with all 6 component scores, all raw values including `raw_expected_sharpe`, `selected` flag, and `rejection_reason`

Disabled JSON: fold_details contains NO `risk_adjusted_alpha_selection` key.

---

## PIT Safety Verification

- Selection data derived only from `train_actual` / `val_actual` (embargoed `train_df_clean` split).
- No test-set data passed to `risk_adjusted_select()`.
- Evidence stored on `FoldMetrics` after fold completes; only train/val-derived data serialized.
- Embargo: last `h` rows per symbol dropped from train IC computation before selection.

## Opt-In / Default-Off Verification

- Constructor: `risk_adjusted_alpha_selection: bool = False` (phase35.py:197).
- CLI: `action="store_true"` (default False).
- Without flag: `ra_result` stays `None`, no evidence persisted.

## Live Trading Boundary

- Feature is paper-trading-only.
- No order routing, execution, or live trading paths modified.
- Only affects alpha selection within the walk-forward backtest engine.

---

## Files Modified

| File | Change |
|------|--------|
| `src/omega/quant/walk_forward/risk_adjusted_alpha_score.py` | Added `raw_expected_sharpe` to `to_dict()` serialization |
| `src/omega/quant/alpha/phase35.py` | Added `risk_adjusted_evidence` to `FoldMetrics`; persist evidence in both single-horizon and multi-horizon paths; populate `result.config` |
| `scripts/run_phase35_backtest.py` | Serialize `risk_adjusted_alpha_selection` evidence in `fold_details` |
| `tests/test_risk_adjusted_alpha_score.py` | Added 9 regression tests (raw_expected_sharpe serialization + evidence persistence) |

---

## SOD Boundary

- Implementation only. No self-approval.
- Submitted to Tier 3: Code Reviewer (role 21), QA Engineer (role 17), Performance Tester (role 23).
