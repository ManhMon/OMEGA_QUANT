# Compliance Audit Report - HOSE/HNX Data Rebuild Phase 1+2

**Role:** 20 compliance-officer (Codex L3)
**Date:** 2026-06-12T17:32:49+07:00
**Gate:** HOSE_HNX_DATA_REBUILD_PHASE12_AUDIT_20260612
**L2 Session:** l2_role15_hose_hnx_rebuild_phase12_audit_20260612
**L2 Role:** 15 data-engineer
**Verdict:** [NEEDS_FIX]

## SOD Verification

- Writer != auditor: PASS (l2_role_id=15, l3_role_id=20).
- L2 role spec: PASS (`data-engineer`, tier 2, OpenCode).
- L3 role spec: PASS (`compliance-officer`, tier 3, Codex, `sod_boundary` present).
- L3 write boundary: PASS. This audit writes only this report and the target phase gate metadata.
- Canonical overwrite check: PASS. `git status` shows `data/market_2015_now.parquet` is not modified; rebuilt data is a separate untracked parquet.

## Independent Data Validation

Validated `data/market_hose_hnx_2015_now_rebuilt_20260612.parquet` independently with pandas.

| Check | Result |
|---|---:|
| Rows / columns | 3,233,304 / 14 |
| Date range | 2015-01-05 to 2026-06-12 |
| Unique trading dates | 2,855 |
| Rebuilt tickers | 1,444 |
| Canonical tickers | 1,534 |
| Missing vs canonical | 90 |
| Rebuilt-only tickers | 0 |
| Nulls in required columns | 0 |
| Duplicate `(ticker,date)` | 0 |
| OHLC invariant violations | 0 |
| Negative volume rows | 0 |
| Zero-volume rows | 1,018,451 (31.499%) |
| Median close | 9,570 VND |
| Close < 1,000 fraction | 1.7% |
| `available_at - date` | exactly 1 day for all rows |
| Common-sample median rebuilt/canonical close ratio | 1.0 |

Structural quality is mostly sound and the VND_FULL scale claim is supported by the median close and common-sample scale ratio. The rebuilt file is not safe for canonical replacement yet because the unresolved blockers below affect execution, costs, capacity, exchange-specific rules, and universe completeness.

## P1 Findings

1. **Canonical replacement unsafe: exchange is UNKNOWN for most of the dataset.**
   Independent counts: `UNKNOWN` = 1,017 / 1,444 tickers (70.43%) and 2,264,195 / 3,233,304 rows (70.03%). This is not a cosmetic metadata gap. Exchange drives VN-specific costs, price bands, board-lot/execution assumptions, liquidity tiers, and capacity/slippage classification. L2 correctly identifies the VCI listing API outage, but the current proxy map is not authoritative enough for canonical promotion.

2. **Canonical replacement unsafe: price-unit contract is unresolved across ingestion and execution.**
   Data scale is VND_FULL, but active code paths still disagree on units. `src/omega/data/vnstock_adapter.py` and `src/omega/data/vnstock_live.py` pass raw OHLC through without the VND guard, while `src/omega/data/vnstock_vci.py`, `src/omega/data/vnstock_ingest.py`, and `scripts/update_market_data.py` scale to VND. On the consumer side, `src/omega/execution/order_generator.py` documents `current_price` as VND but divides by `(current_price * 1000.0)`, `src/omega/execution/trade_blotter.py` computes `quantity * price * 1000.0`, and `src/omega/quant/monitoring/pnl_monitor.py` defaults `price_scale=1000.0`. Feeding VND_FULL prices into these paths can under-size broker orders, overstate trade notional/PnL, or make execution reports internally inconsistent depending on which module supplies quantity.

3. **Capacity/slippage/ADV assumptions remain materially under-validated.**
   Zero-volume rows are 31.499% of the rebuilt dataset. Combined with 70% UNKNOWN exchange and 90 missing canonical tickers, ADV, slippage, and capacity estimates cannot be treated as production-safe without exchange-aware handling of inactive/delisted/illiquid names and explicit tests for VND price units.

## Other Checks

- Price scale decision matrix: partially correct. Scale-invariant formulas are reasonable; scale-sensitive formulas correctly identify the high-risk execution and notional paths. However, the matrix itself proves replacement is unsafe until those P1 unit contracts are fixed.
- P1 blocker classification: correct to classify listing API outage, exchange UNKNOWN, missing tickers, and unit inconsistency as blocking for canonical replacement.
- VND_FULL canonical decision: safe only as a parallel artifact. Not safe as canonical replacement.
- PIT safety: rebuilt `available_at` is T+1 for all rows; no `available_at <= date` rows found. This validates the rebuilt artifact lineage but does not prove all downstream consumers preserve PIT boundaries.
- Syntax check: PASS. No-write tokenizer-compatible AST/compile check passed 46 scoped Python files. I did not run `python -m py_compile` because it would create `__pycache__` outside the L3 write boundary.
- Secrets scan: no real secrets found in scoped evidence. Broader code search returned mock/session token strings such as `PAPER_SECRET` and generated broker tokens, not credential material.
- Antigravity scratch path scan: scoped L2 artifacts do not contain Antigravity scratch paths. Broader repo has legacy absolute `.openclaw\workspace` references in docs/scripts, but not Antigravity scratch paths in this gate's evidence.

## Required Fixes

1. Resolve authoritative exchange mapping or explicitly exclude/flag UNKNOWN exchange rows from any canonical promotion and exchange-aware consumers.
2. Define one price-unit contract (`VND_FULL`) and enforce it at all ingestion write boundaries with tests.
3. Fix or parameterize execution/PnL paths that hardcode `* 1000.0`; add tests proving order quantity, trade notional, cash, PnL, commission, slippage, and ADV capacity are correct for VND_FULL input.
4. Re-run quality checks after fixes, including ADV/capacity sanity by exchange and zero-volume/inactive ticker treatment.
5. Resubmit for L3 review before replacing `data/market_2015_now.parquet`.

## Final Verdict

[NEEDS_FIX]

Canonical replacement is blocked by P1 data governance and price-unit contract risks. The parallel rebuilt parquet may remain as an audit artifact, but it must not replace `data/market_2015_now.parquet` until the required fixes are complete and re-audited.
