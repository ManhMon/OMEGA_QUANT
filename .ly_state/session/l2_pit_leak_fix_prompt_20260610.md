# L2 PIT Leak Fix Prompt

**Role**: Backend Engineer (Role 9)
**Gate**: TIER2_PIPELINE_CONSOLIDATION_20260610
**Verdict**: [NEEDS_FIX]

## Context
L3 Codex audit phát hiện 2 P1 PIT (point-in-time) leaks trong overlay system. Cần fix trước khi re-submit audit.

## P1 Findings to Fix

### Finding 1: SmartMoney/Sentiment PIT Leak
**Problem**: Overlays compute same-date OHLCV-derived scores, then `pipeline_v2.py` realizes same-date returns via `returns_pivot`/`apply_realistic_tc`.

**Locations**:
- `src/omega/quant/pipeline/overlays/smart_money.py:17`
- `src/omega/quant/pipeline/overlays/sentiment.py:17`
- `src/omega/quant/pipeline_v2.py:363` (returns_pivot)
- `src/omega/quant/pipeline_v2.py:390` (apply_realistic_tc)

**Required Fix**: 
- Ensure overlays use T-1 lagged OHLCV data for scoring
- Or shift overlay scores by 1 day before applying to returns
- Verify no future data leakage

### Finding 2: AdaptiveSizingOverlay Future Leak
**Problem**: Uses full-panel per-symbol `adv_vnd.mean()` before applying weights, includes future ADV in calculation.

**Location**:
- `src/omega/quant/pipeline/overlays/adaptive_sizing.py:18`
- `src/omega/quant/pipeline/overlays/adaptive_sizing.py:19`

**Required Fix**:
- Compute `adv_vnd` statistics using only historical data up to current date
- Use expanding window or rolling window that doesn't include future dates
- Ensure ADV calculation respects temporal ordering

## Verification Requirements

1. **pycodestyle**: 0 violations (max-line-length=120)
2. **compileall**: PASS
3. **pytest**: 349 passed, 0 failed
4. **PIT Safety**: No look-ahead bias in any overlay

## Deliverables

Write report to: `.ly_state/session/l2_pit_leak_fix_tier2_20260610.md`

Include:
- Files modified
- Specific fixes applied (line numbers, before/after)
- Verification results (pycodestyle, pytest, compileall)
- PIT safety validation approach

**Do NOT commit/push**. Surgical fixes only.
