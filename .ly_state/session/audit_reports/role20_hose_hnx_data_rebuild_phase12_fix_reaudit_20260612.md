# Compliance Re-Audit Report - HOSE/HNX Data Rebuild Phase 1+2 Fix

**Role:** 20 compliance-officer (Codex L3)
**Date:** 2026-06-12T18:07:11+07:00
**Gate:** HOSE_HNX_DATA_REBUILD_PHASE12_AUDIT_20260612
**L2 Session:** l2_role15_hose_hnx_rebuild_phase12_fix_20260612
**L2 Role:** 15 data-engineer
**Prior Audit:** .ly_state/session/audit_reports/role20_hose_hnx_data_rebuild_phase12_audit_20260612.md [NEEDS_FIX]
**Verdict:** [APPROVED]

## SOD Verification

- Writer != auditor: PASS (l2_role_id=15, l3_role_id=20).
- L2 role spec: PASS (`data-engineer`, role_id 15, tier 2, OpenCode).
- L3 role spec: PASS (`compliance-officer`, role_id 20, tier 3, Codex, `sod_boundary` present).
- L3 boundary: PASS. This re-audit writes only this report and the target `HOSE_HNX_DATA_REBUILD_PHASE12_AUDIT_20260612` gate entry.
- L2 report present: PASS (`.ly_state/session/l2_role15_hose_hnx_rebuild_phase12_fix_20260612.md`).

## Re-Audit Findings

No blocking findings remain for the L2 fix scope.

1. Canonical parquet overwrite check: PASS. `git status --short -- data/market_2015_now.parquet` returned no modification. The rebuilt parquet remains a separate untracked artifact: `data/market_hose_hnx_2015_now_rebuilt_20260612.parquet`.
2. UNKNOWN exchange handling: PASS. `src/omega/data/exchange_resolver.py` resolves invalid/missing exchanges to `UNKNOWN` and `build_promoted_candidate(..., exclude_unknown=True)` drops `UNKNOWN` rows by default. On the actual rebuilt artifact: input 3,233,304 rows / 1,444 tickers; promoted candidate 969,109 rows / 427 tickers; excluded 2,264,195 rows / 1,017 tickers; promoted UNKNOWN rows = 0.
3. VND_FULL contract: PASS. `src/omega/data/vnd_price_contract.py` centralizes `VND_FULL`, `THOUSANDS`, `ensure_vnd_scale()`, `detect_price_unit()`, `price_scale_metadata()`, and `get_price_multiplier()`.
4. Ingestion write boundaries: PASS for scoped paths. Guards are wired into `vnstock_adapter.py`, `vnstock_live.py`, `vnstock_vci.py`, `vnstock_ingest.py`, `live_ingestor.py`, and `scripts/update_market_data.py`; `scripts/batch_market_loader_resume.py` consumes `VnstockVCIDataSource`, which normalizes prices before parquet writes.
5. Execution/PnL unit fixes: PASS. `order_generator.py`, `trade_blotter.py`, and `pnl_monitor.py` default to VND_FULL behavior and preserve THOUSANDS compatibility through `price_unit` / `get_price_multiplier()` instead of unconditional `* 1000.0` on VND_FULL paths.
6. ADV/capacity zero-volume handling: PASS for scoped fix. `OrderGenerator.validate_compliance()` now rejects `adv <= 0`; tests cover zero-volume/inactive behavior and real promoted-manifest stats report 235,567 zero-volume rows and 5 fully inactive promoted tickers.
7. Test coverage: PASS. Tests prove order quantity, compliance notional, trade notional, commission, PnL cash/realized/unrealized, slippage bps, THOUSANDS backward compatibility, UNKNOWN exclusion/flagging, and zero-ADV rejection.
8. PIT safety: PASS for touched logic. PnL monitor keeps monotonic timestamp checks; data rebuild artifact is not promoted to canonical; no look-ahead write was introduced in the fix scope.
9. Antigravity scratch paths: PASS. Scoped scan found no Antigravity scratch paths.

## Verification Run

- AST syntax check: PASS with `PYTHONDONTWRITEBYTECODE=1` and UTF-8-SIG source read across 17 scoped Python files. A plain UTF-8 string parse hits the existing BOM in `src/omega/data/__init__.py`; the BOM-aware parse passes and pytest imports successfully.
- Pytest: PASS. Command: `python -m pytest tests/data_test_vnd_full_exchange_fix.py tests/execution_test_order_generator.py tests/execution_test_trade_blotter.py tests/quant_test_pnl_monitor.py -p no:cacheprovider --tb=short -q`. Result: 54 passed, 2 warnings.
- Secrets scan: WARN, non-blocking for this gate. Scoped files contain pre-existing `VNSTOCK_API_KEY` defaults in `vnstock_adapter.py`, `vnstock_live.py`, `vnstock_vci.py`, and `vnstock_ingest.py`; `git show HEAD` confirms these were not introduced by the L2 fix. They should be removed or documented in a separate credential-hygiene task if they are live credentials.

## Residual Governance Notes

- Canonical replacement remains blocked until external VCI exchange map/universe completeness is resolved. Approval here means the required code/data governance fixes are acceptable, not that `data/market_2015_now.parquet` is safe to replace today.
- The VND_FULL guard uses a median-price heuristic. This is acceptable for the current fix scope and tested source paths, but future ingestion should prefer explicit provider metadata when available to avoid ambiguity for true sub-1000 VND securities.
- The promoted candidate intentionally excludes 70.03% of rows due to UNKNOWN exchange. This is fail-closed behavior, not a complete replacement universe.

## Final Verdict

[APPROVED]

The prior P1 blockers are addressed for the scoped implementation: UNKNOWN exchange rows are excluded/flagged from promotion, VND_FULL is centralized and applied across ingestion and execution/PnL paths, unit-sensitive tests pass, zero-ADV capacity handling fails closed, and the canonical parquet was not overwritten. Canonical replacement still requires external exchange-map/universe completion and a later gate.
