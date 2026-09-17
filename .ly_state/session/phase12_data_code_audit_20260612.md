# Phase 1+2 Data Code Audit — 2026-06-12

**Role:** 15 Data Engineer (L2 OpenCode)
**Task:** HOSE_HNX_DATA_REBUILD_PHASE12_AUDIT_20260612
**Date:** 2026-06-12

---

## 1. Scoped Files Searched/Read

### Data Ingestion (Phase 1+2 Core)

| # | File | Lines | Role |
|---|------|-------|------|
| 1 | `src/omega/data/vnstock_adapter.py` | 131 | VCI fetch adapter (no VND scaling) |
| 2 | `src/omega/data/vnstock_ingest.py` | 64 | Bulk ingest + median-based VND normalization |
| 3 | `src/omega/data/vnstock_vci.py` | 132 | Per-row VND normalization (×1000 if <1000) |
| 4 | `src/omega/data/vnstock_live.py` | 500 | Live data provider (no VND scaling) |
| 5 | `src/omega/data/vci_bridge.py` | 203 | VCI bridge (mock guard, PIT safety) |
| 6 | `src/omega/data/validator.py` | 480 | Comprehensive data validation (12 rules) |
| 7 | `src/omega/data/sanitizer.py` | 506 | Data sanitization (dedup, ffill, outlier clip, PIT) |
| 8 | `src/omega/data/__init__.py` | 102 | Package init (18 submodule imports) |

### Data Loader Scripts

| # | File | Lines | Role |
|---|------|-------|------|
| 9 | `scripts/update_market_data.py` | 199 | Incremental updater (VND scaling, writes canonical) |
| 10 | `scripts/batch_market_loader_resume.py` | 499 | Full batch loader with checkpoint/resume |
| 11 | `scripts/real_data_loader.py` | 53 | Simple parquet reader (consumer) |
| 12 | `scripts/prepare_full_dataset.py` | 67 | Feature preparation (reads canonical, computes ADV) |

### Backtest Engine & Execution

| # | File | Lines | Role |
|---|------|-------|------|
| 13 | `src/omega/backtest/engine.py` | 146 | Simplified backtest engine (scalar cost model) |
| 14 | `src/omega/backtest/vectorized_backtest.py` | 171 | Vectorized backtest (hardcoded dummy ADV) |
| 15 | `src/omega/backtest/walk_forward_engine.py` | 474 | Walk-forward validation |
| 16 | `src/omega/backtest/liquidity_stress.py` | 87 | Liquidity stress testing (ADV-based exit days) |
| 17 | `src/omega/backtest/liquidation.py` | 54 | Delisting liquidation |
| 18 | `src/omega/backtest/oos_validator.py` | 313 | Out-of-sample validation |
| 19 | `src/omega/backtest/regime_aware_walk_forward.py` | 294 | Regime-aware walk-forward |
| 20 | `src/omega/execution/cost_estimator.py` | 32 | Round-trip cost estimator |
| 21 | `src/omega/execution/market_impact.py` | 136 | Almgren-Chriss market impact |
| 22 | `src/omega/execution/vn_transaction_cost_model.py` | 313 | VN-specific cost model (exchange-aware) |
| 23 | `src/omega/execution/tca.py` | 75 | Transaction cost analysis |
| 24 | `src/omega/execution/execution_engine.py` | 542 | Execution engine with PIT safety |

### Features, Signals, Labels

| # | File | Lines | Role |
|---|------|-------|------|
| 25 | `src/features/signal_module.py` | 52 | Core signals (mean reversion, momentum, trend) |
| 26 | `src/features/signal_sanitizer.py` | 92 | Signal T-1 lag enforcement |
| 27 | `src/features/pit_guard.py` | 48 | PIT safety guard |
| 28 | `src/omega/core/structure_features.py` | 261 | Structural features (price buckets, market cap) |
| 29 | `src/indicators/alpha_discovery.py` | 63 | RSI, MACD indicators |
| 30 | `src/evolution/genetic_alpha.py` | 225 | GP tree alpha search |
| 31 | `src/evolution/fitness.py` | 128 | Fitness evaluator |
| 32 | `scripts/run_backtest.py` | 83 | Backtest runner |
| 33 | `scripts/backtest_v30_full.py` | 360 | Full backtest v30 |
| 34 | `scripts/backtest_v31_unified.py` | 356 | Unified backtest v31 |
| 35 | `scripts/backtest_v32_ml_system.py` | 376 | ML system backtest v32 |
| 36 | `scripts/backtest_advanced_features.py` | 194 | Advanced features backtest |
| 37 | `scripts/run_full_pipeline_backtest.py` | 122 | Full pipeline backtest |

### Additional Label/Target Files (Found via Search)

| # | File | Lines | Role |
|---|------|-------|------|
| 38 | `src/omega/quant/backtest/label_engine.py` | 160 | Forward return labels |
| 39 | `src/omega/quant/backtest/multi_horizon_labels.py` | 84 | Settlement-aware multi-horizon targets |
| 40 | `src/omega/quant/backtest/target_module.py` | 175 | V21 core target (PIT validated) |
| 41 | `src/omega/core/feature_factory.py` | 419 | Institutional feature factory |
| 42 | `src/omega/quant/evolution/alternative_features.py` | 115 | 25 alternative derived features |
| 43 | `src/omega/quant/evolution/feature_adapter.py` | 178 | GP feature adapter |

### Documentation & Config

| # | File | Role |
|---|------|------|
| 44 | `SOUL.md` | Canonical rule: vnstock prices × 1000 → VND |
| 45 | `config/development.yaml` | Dev config (VCI source, HOSE+HNX universe) |
| 46 | `config/production.yaml` | Prod config (PIT strict, 252-day min) |
| 47 | `docs/PHASE1-2_AUDIT_R4.md` | Prior Phase 1-2 audit (APPROVED) |
| 48 | `docs/L3_AUDIT_SYSTEM_BATCH2_DATA.md` | Data module L3 audit |
| 49 | `docs/L3_AUDIT_SYSTEM_BATCH2_DATA_V2.md` | Data module L3 audit V2 |
| 50 | `.ly_state/session/l2_role15_data_refresh_audit_20260612.md` | Prior refresh audit |
| 51 | `.ly_state/session/data_code_audit_20260612.md` | Prior code audit |
| 52 | `.ly_state/session/data_refresh_quality_20260612.json` | Prior quality check |
| 53 | `.ly_state/session/data_refresh_plan_20260612.json` | Rebuild plan |

---

## 2. Data Flow Map

```
                    vnstock VCI API (prices in THOUSANDS)
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
   vnstock_adapter.py   vnstock_vci.py      vnstock_ingest.py
   (NO scaling)       (per-row ×1000)     (median ×1000)
         │                    │                    │
         │              ┌─────┘                    │
         │              │                          │
   vnstock_live.py   batch_market_loader    update_market_data.py
   (NO scaling)      _resume.py             (row-mask ×1000)
                      (writes canonical)     (appends canonical)
         │                    │                    │
         │                    ▼                    ▼
         │              ┌──────────────────────────────┐
         │              │ data/market_2015_now.parquet  │
         │              │ (VND scale, 3.39M rows)      │
         │              └──────────────────────────────┘
         │                    │
         ▼                    ▼
   Consumers: real_data_loader.py, prepare_full_dataset.py,
   backtest_v30/31/32, feature_factory, label_engine, etc.
   (ALL assume VND scale — no further scaling)
```

## 3. Critical Findings

### 3.1 Price Scale Inconsistency (P1)

The codebase has **inconsistent VND scaling** across ingestion paths:
- `vnstock_adapter.py` and `vnstock_live.py`: **NO** VND scaling
- `vnstock_vci.py`, `vnstock_ingest.py`, `update_market_data.py`: **DO** scale ×1000

If any code path uses the unscaling adapters to write to the canonical warehouse, a 1000× price inconsistency occurs.

### 3.2 DataValidator Disconnected (P2)

`src/omega/data/validator.py` has 12 comprehensive validation rules but is **NOT** wired into `update_market_data.py` or `batch_market_loader_resume.py`.

### 3.3 Schema Drift (P2)

- `symbol` vs `ticker` column naming across files
- Dead `time` column (99.9% null) in canonical
- Inconsistent `as_of`/`available_at` presence

### 3.4 Execution Module Scale Split (P1)

Some execution modules assume VND (e.g., `vn_transaction_cost_model.py` with `liquid_adv_threshold_vnd = 50e9`), while others assume thousands (e.g., `order_generator.py` with `current_price * 1000.0`).

---

## 4. py_compile Results

All 37 scoped Python files passed `py_compile` with zero errors.

---

## 5. Status

**AWAITING L3 REVIEW** — This is an L2 implementation audit. No self-approval. Submit to Tier 3 (Code Reviewer role 21, QA Engineer role 17, Performance Tester role 23).
