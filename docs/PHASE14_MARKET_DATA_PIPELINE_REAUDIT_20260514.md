# Phase 14 Market Data Pipeline Re-Audit (Role 21)

- Timestamp: 2026-05-14T21:10:32+07:00
- Role: 21 - Code Reviewer (L3-Audit)
- Scope:
  - `OMEGA_QUANT/scripts/batch_market_loader_resume.py`
  - `OMEGA_QUANT/packages/data/src/omega/data/vnstock_vci.py`
  - `.ly_state/session/market_2015_now_checkpoint.json`
  - `OMEGA_QUANT/data/market_2015_now.parquet`
  - `OMEGA_QUANT/fetch_resume_v2.log`
- Commit: `5fe7472`

## Final Verdict

`[NEEDS_FIX]`

## Requested Checks

1. CW Filter (len <= 3): **PASS (code + artifact)**
   - Code filter exists: `len(s) <= 3` in `batch_market_loader_resume.py:145`.
   - Artifact check: `tickers_gt3 = 0` in `market_2015_now.parquet`.

2. Parallel Thread Safety (5 threads + RateLimiter): **PASS (code + probe)**
   - 5-thread executor configured: `ThreadPoolExecutor(max_workers=self.max_workers)` at `:192`; CLI default `--max-workers 5` at `:431-434`.
   - Shared lock in limiter: `threading.Lock()` and guarded `acquire()` at `:50-63`.
   - Probe result: 6 concurrent acquires => min observed interval `1.000s`, no burst violations.

3. Data Cleaning (OHLC invalid + close <= 0): **FAIL (artifact), code path PASS**
   - Cleaning logic exists in code at `:232-240`.
   - Runtime artifact currently violates requirement:
     - `invalid_ohlc = 61,998`
     - `close <= 0 = 6,570`
     - file: `OMEGA_QUANT/data/market_2015_now.parquet`.
   - Interpretation: current production parquet was not produced by cleaned path (or is stale/legacy).

4. PIT Safety (`as_of` + `available_at` T+1): **FAIL (artifact), code path PASS**
   - Code writes PIT columns at `:245-247` and enforces CLI `--as-of-time`/`--end-date` at `:440-457`.
   - Current artifact missing required PIT columns entirely (`as_of`, `available_at` absent).
   - file: `OMEGA_QUANT/data/market_2015_now.parquet`.

5. Checkpoint Integrity: **PARTIAL**
   - Positive:
     - Centralized checkpoint path `.ly_state/session` at `:98-105`.
     - Atomic write (temp + replace) at `:120-132`.
     - Current checkpoint JSON parse OK, no duplicate `loaded_symbols`, no missing referenced batch files.
   - Gap:
     - Current checkpoint schema lacks `batch_files` lineage field in persisted artifact (`keys=loaded_symbols,total_rows,batches_completed,last_updated`), reducing end-to-end provenance verifiability.

6. Batch cleanup after consolidation: **PARTIAL / FAIL-IN-PIPELINE**
   - Main pipeline consolidate path (`batch_market_loader_resume.py:345-386`) does not remove batch files/dir.
   - Cleanup exists only in separate helper script `OMEGA_QUANT/scripts/consolidate_batches.py:33-35`.
   - Current filesystem has no batch dir (`OMEGA_QUANT/data/market_2015_now_batches` absent), but cleanup is not guaranteed by primary pipeline.

## Additional Blocking Observation

- Active Phase 14 run shows repeated symbol failures: `name 'logger' is not defined` in `OMEGA_QUANT/fetch_resume_v2.log` (e.g., lines 24, 38, 52, 66, 80, 94). This can prevent batch progress and contaminates reliability claims.

## PIT Safety

`FAIL` at artifact level (required PIT columns absent in produced parquet).

## Role Compliance

`PASS` (audit-only; no implementation changes).
