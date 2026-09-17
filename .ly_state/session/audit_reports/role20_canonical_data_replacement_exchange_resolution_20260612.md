# Compliance Audit Report

**Role**: 20 compliance-officer (Codex L3)
**Date**: 2026-06-12T19:55:00+07:00
**Gate**: CANONICAL_DATA_REPLACEMENT_EXCHANGE_RESOLUTION_20260612
**L2 Session**: l2_role15_canonical_data_replacement_exchange_resolution_20260612
**L2 Role**: 15 data-engineer
**Verdict**: [APPROVED]

## SOD Verification

- Writer != auditor: PASS (L2 role_id 15 != L3 role_id 20)
- L2 role spec: PASS (`data-engineer`, tier 2, OpenCode)
- L3 role spec: PASS (`compliance-officer`, tier 3, Codex, sod_boundary defined)
- L3 write boundary: PASS (audit report + one phase gate entry only)
- Scratch path check in scoped artifacts: PASS (no Antigravity scratch path references found)
- Secret scan in scoped artifacts: PASS (no key/secret/token/private-key patterns found)

## Artifact Integrity

- Canonical `data/market_2015_now.parquet` SHA-256: `e9b0b4f1754db11378aa7be6cc46b4a28ccfe2dc5c47612893ae1cccda8cab5f`
- Backup `data/market_2015_now.backup_20260612.parquet` SHA-256: `e9b0b4f1754db11378aa7be6cc46b4a28ccfe2dc5c47612893ae1cccda8cab5f`
- Backup matches canonical: PASS
- Candidate `data/market_hose_hnx_2015_now_canonical_candidate_20260612.parquet` SHA-256: `206196b1889b1a308b302b5278cd7de0a55d30cad1a2003db22f4034e2514285`
- Canonical not overwritten: PASS (candidate is separate; canonical hash matches backup)

## Independent Candidate Validation

- Shape: PASS (1,687,749 rows x 14 columns)
- Tickers: PASS (666 total; HOSE 380, HNX 286)
- Date range: PASS (2015-01-05 to 2026-06-12)
- Exchange domain: PASS (`HOSE` 953,440 rows; `HNX` 734,309 rows only)
- UNKNOWN rows: PASS (0)
- UPCOM rows: PASS (0)
- `EXCLUDE_*` rows: PASS (0)
- Duplicate ticker-date pairs: PASS (0)
- OHLCV nulls: PASS (0)
- Total nulls all columns: PASS (0)
- OHLC invariant violations: PASS (0)
- Non-positive price rows: PASS (0)
- Negative volume rows: PASS (0)
- Price scale: PASS (`VND` for all rows)
- Adjusted flag: PASS (`backward_adjusted` for all rows)
- PIT availability: PASS (`available_at > date` for all 1,687,749 rows; 0 leaks)

## KBS Exchange Resolution Audit

- KBS source availability: PASS (3,249 rows from `symbols_by_exchange(get_all=True)`)
- Non-stock exclusion: PASS (candidate overlap with KBS non-stock symbols = 0)
- UPCOM/non-target stock exclusion: PASS (candidate overlap with KBS UPCOM/non-target stock symbols = 0)
- Conflict count: PASS (10 conflicts reported, 10 resolved with KBS precedence)
- Conflict behavior in candidate: PASS
  - Included as HOSE: BSR, LCG, MCH, MSN, SHB, VGC
  - Excluded because KBS maps to UPCOM/non-target: HBC, POM, PVX, SBS
- Still-UNKNOWN rebuilt tickers: PASS (DMS, DTE, IHK, SHG, TKC, TNV excluded from candidate)

## Verification Commands

- Syntax compile without bytecode writes: PASS for 6/6 scoped files.
- Scoped pytest: PASS (`python -B -m pytest tests/data_test_vnd_full_exchange_fix.py -q -p no:cacheprovider` => 39 passed, 0 failed).
- Full `tests/` pytest: ATTEMPTED, blocked by sandbox/temp ACL permissions on `C:\tmp` and user temp directories. Failures were permission errors in unrelated temp-writing tests, not candidate validation failures.

## Residual Notes

- Existing `.ly_state/session/exchange_map_20260612.json` still contains old conflict values; the canonical candidate itself was generated from the KBS-resolved authoritative map and independently validates clean. For future rebuild governance, L2 should persist the KBS-resolved authoritative map as a named artifact before any later rebuild cycle.
- This audit approves the current candidate artifact for canonical replacement, not blanket approval for future exchange resolver rebuilds.

## Verdict

[APPROVED]

L1 may replace `data/market_2015_now.parquet` with `data/market_hose_hnx_2015_now_canonical_candidate_20260612.parquet` after running `python scripts/sod_gate_enforcer.py` successfully and retaining `data/market_2015_now.backup_20260612.parquet`.
