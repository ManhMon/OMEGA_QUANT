# QA Audit Report

**Role**: QA Engineer (Role 17, L3 Codex)
**Date**: 2026-06-13T09:06:00+07:00
**Gate**: CANONICAL_VCI_UPDATER_LEGACY_TRACKING_20260613
**L2 Session**: l2_role15_canonical_vci_updater_legacy_tracking_20260613
**Tier 2 Engineer**: data-engineer (Role 15)
**Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read

- `.agents/agent/qa-engineer.md`
- `.agents/skills/webapp-testing/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/verify-changes/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`

## SOD Checks

- Writer != auditor: PASS (15 != 17)
- L3 boundary: PASS. No production source edits performed.
- Forbidden path scan: PASS. No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`. Mentions in L2 report are scan evidence only.
- L2 report repo-local skill evidence: PASS. Report lists `.agents/agent/data-engineer.md` and repo-local skill files under `.agents/skills/*/SKILL.md`.

## Validation Results

- `python -m py_compile scripts/update_market_data.py scripts/vci_full_hsx_hnx_download_20260613.py scripts/vci_full_hsx_hnx_validate_20260613.py`: PASS.
- Pre-update `python scripts/sod_gate_enforcer.py`: PASS. 116 phases verified; strict repo-local skill loading checks pass; target gate not yet registered.
- Canonical read-only probe: PASS. Shape `(1771261, 14)`, 703 tickers, date range `2015-01-05` to `2026-06-12`, exchanges `HNX/HOSE`, source `vnstock_vci`, price scale `VND`, duplicate `(ticker,date)` rows `0`, OHLCV nulls `0`, non-positive OHLC `0`, negative volume `0`, pre-2015 rows `0`, PIT violations `0`, close median `10700.0`.
- Dry-run no-write branch: PASS via direct `run_updater(..., dry_run=True)` with in-memory VCI fetch stub. Result `status=dry_run`, `dry_run=True`, `combined_valid=True`, canonical file size/mtime unchanged.
- Live VCI dry-run attempt: BLOCKED by local proxy/environment (`127.0.0.1:9` refused; vnstock environment permission denied under `C:\Users\GHC\.vnstock\id\environment.json`). Canonical file size/mtime unchanged.

## Requirement Coverage

- Full HSX/HNX universe active path: PASS. `update_market_data.py` loads `.ly_state/session/vci_universe_hsx_hnx.json` and maps HSX to canonical `HOSE`; no active hardcoded VN30 path found.
- Symbols subset for testing: PASS. `--symbols` parsed and passed as `symbol_filter`.
- Incremental/backfill logic: PASS. Default start uses canonical max date + 1; explicit `--start/--end` supported; hard lower bound clamps to `2015-01-01`.
- Canonical schema and PIT fields: PASS. 14-column schema constant, `source='vnstock_vci'`, `available_at=date+1`, `date >= 2015-01-01`, VND label with VND_FULL compatibility note.
- Legacy inventory: PASS. JSON and markdown inventory exist and track obsolete/legacy files without deletion.
- Atomic write + backup implementation: PRESENT. `atomic_write_with_backup()` creates `.parquet.bak`, writes temp parquet in target dir, then replaces target.

## Blocking Defect

1. `scripts/update_market_data.py` does not block writes when combined canonical validation fails.

   Evidence: after `combined_valid, combined_errors = validate_dataframe(combined, "combined")`, the code only logs warnings and continues to `atomic_write_with_backup(combined, target_path)`. A no-write spy test forced `validate_dataframe(..., "combined")` to return `False`; `atomic_write_with_backup` was still called, and the result reported `status='written'`, `combined_valid=False`.

   Impact: violates the requirement to validate before write. Future bad merged data, existing canonical corruption, PIT/schema violations, duplicate rows, invalid exchanges, or OHLCV defects can still be written to the canonical parquet.

   Required fix: if `combined_valid` is false, return `{"status": "validation_failed", "errors": combined_errors}` before any write when `dry_run` is false. Dry-run may return the invalid summary without writing.

## Verdict

[NEEDS_FIX]

The implementation is close, and current canonical data passes read-only quality checks, but the canonical writer must fail closed on combined validation errors before approval.
