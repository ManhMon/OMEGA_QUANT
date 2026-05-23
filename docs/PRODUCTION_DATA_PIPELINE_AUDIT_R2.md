# PRODUCTION_DATA_PIPELINE Re-Audit R2

- Role: Code Reviewer (Role 21, Codex L3)
- Scope: `V21_QUANT/src/v21_system/data_pipeline/production_data_pipeline.py`
- session_id: 019e1d6a-998b-7150-ab9e-160a7d3ba83f
- session_key: R2-bc0b591337d7
- l3_session_id: 019e1d6a-998b-7150-ab9e-160a7d3ba83f
- l3_session_key: R2-bc0b591337d7
- audit_report_path: `OMEGA_QUANT/docs/PRODUCTION_DATA_PIPELINE_AUDIT_R2.md`
- verdict: `[NEEDS_FIX]`
- final_verdict: `[NEEDS_FIX]`
- PIT Safety: `FAIL`
- Role Compliance: `PASS`

## Verification Results

### 1) Corporate actions wired with `ex_date` filter: FAIL
- Pipeline routes through placeholder only: `_apply_corporate_actions` at line 236.
- Method returns input unchanged and logs no-op.
- No invocation of real adjuster path from L2.

### 2) Neutralization date dimension preserved: PASS
- Neutralized values keyed by `(symbol, date)`.
- Mapping back uses `(symbol, row['timestamp'].date())`.

### 3) Validator schema aligned: FAIL
- `ValidationIssue` has `severity` field but pipeline still stores raw `issue.timestamp`.
- JSON write crashes when `timestamp` is `pd.Timestamp`.

### 4) PIT safety: FAIL
- Corporate actions not wired, so required `ex_date` gating in production path is not enforced.

### 5) No crashes: FAIL
- Full pipeline smoke run crashed at L3 sanitizer with deprecated `fillna(method='ffill')`.
- Quality report persistence crashes with validation issues present.

## Final Verdict
[NEEDS_FIX]

## Required Fixes Before Re-Audit
1. Wire L2 corporate action flow to actual adjuster path and enforce `ex_date <= as_of_time.date()`.
2. Replace deprecated `fillna(method='ffill', ...)` with `ffill()`.
3. Serialize `ValidationIssue.timestamp` to ISO string before `json.dump`.
4. Make `as_of_time` explicit/required for deterministic PIT audit runs.
