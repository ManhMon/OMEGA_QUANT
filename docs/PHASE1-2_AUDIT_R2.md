# PHASE 1-2 Re-Audit R2

- Role: Code Reviewer (Role 21)
- Scope: `OMEGA_QUANT/scripts/batch_market_loader_resume.py`
- Audit Date: 2026-05-12
- Verdict: `[NEEDS_FIX]`
- PIT Safety: `FAIL`
- Role Compliance: `PASS`

## Findings (Severity Ordered)

1. **HIGH - End-date boundary not enforced at DataFrame level (PIT/date-window leak risk)**  
   - Evidence: only lower bound filter applied: `df = df[df['date'] >= start_dt]` at line 154.  
   - Missing: explicit upper bound `date <= end_date` in same function.  
   - Impact: if provider returns rows beyond requested `end_date`, output may contain out-of-window data.

2. **MEDIUM - Existing parquet data loaded without re-filter to requested date window**  
   - Evidence: existing file loaded at lines 194-196, then concatenated/saved repeatedly at lines 231-233, with no clamp to `[start_date, end_date]`.  
   - Impact: resumed runs can preserve/propagate stale out-of-range rows from prior executions.

## Checklist Results

- PIT Safety (`no now()`): **FAIL (overall)**  
  - No usage of `datetime.now()`, `pd.Timestamp.now()`, `utcnow()`, or equivalent in file scope.  
  - `--as-of-time` mandatory and validated (lines 318-326).  
  - Checkpoint timestamp uses injected `as_of_time` (line 242), not wall-clock now.
  - However, PIT still fails due to missing upper-bound date clamp (`<= end_date`) in batch filter.

- State Persistence (`.ly_state/session/`): **PASS**  
  - Checkpoint path centralized to `.ly_state/session` (lines 64-67).  
  - Directory auto-created before writes (line 65).  
  - Atomic checkpoint write via temp + replace (lines 85-90).

- Vectorization: **PASS (with caveat)**  
  - Bulk DataFrame transforms used (`rename`, datetime conversion, boolean filtering, column projection) at lines 147-157.  
  - Per-symbol fetch loop remains I/O-bound by API design (lines 123-137), acceptable for this loader shape.

- Date Filter: **FAIL**  
  - Lower bound exists (line 154).  
  - Upper bound filter absent in `load_batch`.  
  - Resume path does not re-clamp previously persisted rows.

## Required Fix Before APPROVED

1. Add explicit upper bound filter in `load_batch`:

```python
end_dt = pd.to_datetime(end_date)
df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
```

2. After loading existing parquet, clamp `df_existing` to `[start_date, end_date]` before concat/save.

## Gate Contract Notes

- l3_session_id: `codex-role21-2026-05-12`
- l3_session_key: `local-cli-session`
- audit_report_path: `docs/PHASE1-2_AUDIT_R2.md`
- final_verdict: `[NEEDS_FIX]`
