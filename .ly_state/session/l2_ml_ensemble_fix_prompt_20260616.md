# L2 Fix Scope: ML Ensemble Report Wording Fix

## Role
- Role ID: 16
- Role Name: machine-learning-engineer
- Tier: 2
- Platform: OpenCode
- SOD Boundary: implementation-only, test required, no self-approval, submit to Tier3

## Scope
- .ly_state/session/l2_role16_ml_ensemble_fix_20260616.md

## Required Fixes

1. **Forbidden Path Scan Wording Fix**:
   - In `.ly_state/session/l2_role16_ml_ensemble_fix_20260616.md` (around the Forbidden Path Scan section), format the forbidden path scan table/list so each forbidden path is listed separately and is explicitly marked `non-authoritative` and `not used as source`.
   - Specifically, list `C:\Users\GHC\.agents` and `.codex\memories` as separate items.
   - Example wording to use:
     - `C:\Users\GHC\.agents` is non-authoritative and not used as source.
     - `.codex\memories` is non-authoritative and not used as source.
     - `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source.
     - `.openclaw\skills` is non-authoritative and not used as source.

## Verification
- Run: `python scripts/sod_gate_enforcer.py` (should not report forbidden path wording violations for `l2_role16_ml_ensemble_fix_20260616.md`).

## Output
- Update the report `.ly_state/session/l2_role16_ml_ensemble_fix_20260616.md` directly.
