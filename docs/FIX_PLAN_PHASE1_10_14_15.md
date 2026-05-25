# FIX_PLAN_PHASE1_10_14_15.md
**Role:** L1 Orchestrator
**Target:** Phase 1-10, 14, 15 Fix Plan

## Goal
Resolve `[NEEDS_FIX]` from L3 Codex Audit for Phase 1-10, 14, 15.

## L2 Action Items (Opencode)
1. **Fix Phase 10 Pandas Compatibility (P1):**
   - File: `tests/phase10/test_performance.py`
   - Issue: `AttributeError: 'SeriesGroupBy' object has no attribute 'kurt'` under Pandas 2.3.3.
   - Fix: Replace `.agg(['mean', 'std', 'skew', 'kurt'])` with a Pandas 2.x compatible lambda or apply function for kurtosis.

2. **Fix `verify_phase_gaps.py` Mapping (P1):**
   - File: `scripts/verify_phase_gaps.py`
   - Issue: Mapping logic is unreliable, allowing false completion signals (e.g., Phase 1 marked complete from Phase 11/16 keys).
   - Fix: Ensure `verify_phase_gaps.py` maps strictly 1:1 to correct `phase_gates.json` keys for Phase 1-10, 14, 15.

3. **Wire Gate Evidence (P2):**
   - File: `.ly_state/session/phase_gates.json`
   - Issue: Missing/Pending keys.
   - Fix: Ensure keys `OMEGA_GAP_PHASE1_FOUNDATION` through `10`, `14`, `15` exist. Set them to `PENDING_AUDIT` so L3 can cleanly overwrite them upon passing.

## Verification
- Run: `python -m pytest tests/phase10/test_performance.py -k test_vectorization_compliance`
- Run: `python scripts/verify_phase_gaps.py`

L2, please execute this plan. Do not approve gates yourself. L3 will verify.