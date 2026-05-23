# PHASE 1-2 Re-Audit R3

- Role: Code Reviewer (Role 21)
- Scope: `OMEGA_QUANT/scripts/batch_market_loader.py`, `OMEGA_QUANT/scripts/batch_market_loader_resume.py`
- Audit Date: 2026-05-12
- Verdict: `[NEEDS_FIX]`
- PIT Safety: `FAIL`
- Role Compliance: `PASS`

## Findings (Severity Ordered)

1. **HIGH - PIT no-now violation remains in batch loader CLI date resolution**  
   - Evidence: wall-clock usage in `OMEGA_QUANT/scripts/batch_market_loader.py:291` and `OMEGA_QUANT/scripts/batch_market_loader.py:298`:
     - `end_date = pd.Timestamp.now()`
   - Impact: run output depends on execution time, not explicit as-of boundary; violates strict PIT no-now policy.
   - Required fix: remove runtime-now fallback; require explicit `--end-date` (and optional explicit `--as-of-time`) similar to resume loader contract.

## Validation Matrix (Requested Checks)

1. **PIT no-now**: **FAIL**  
   - `batch_market_loader.py` uses `pd.Timestamp.now()` at lines 291, 298.  
   - `batch_market_loader_resume.py` enforces explicit `--as-of-time` and `--end-date` (`lines 326-343`), no `now()` calls.

2. **Strict date window `start<=date<=end` in batch + resumed existing parquet clamp**: **PASS**  
   - Batch filter in `batch_market_loader.py:138-140` applies both bounds.  
   - Resume batch filter in `batch_market_loader_resume.py:153-155` applies both bounds.  
   - Existing parquet clamp in resume path at `batch_market_loader_resume.py:198-202`.

3. **Checkpoint in `.ly_state/session` with atomic write where applicable**: **PASS**  
   - Checkpoint path centralized at `.ly_state/session` in `batch_market_loader_resume.py:64-67`.  
   - Atomic write via temp + replace in `batch_market_loader_resume.py:85-90`.

4. **Vectorized transforms**: **PASS**  
   - Batch script vectorized DataFrame transforms at `batch_market_loader.py:126-143`.  
   - Resume script vectorized transforms at `batch_market_loader_resume.py:143-158`.  
   - Per-symbol loop remains API I/O loop; transform stage remains vectorized.

## Gate Contract

- l3_session_id: `codex-role21-2026-05-12-r3`
- l3_session_key: `local-cli-session`
- audit_report_path: `docs/PHASE1-2_AUDIT_R3.md`
- final_verdict: `[NEEDS_FIX]`

