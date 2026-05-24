# OMEGA_QUANT: PERSONAL SIGNAL ORACLE PLAN
**Date**: 2026-05-24
**Version**: 1.1 (Spec-Aligned Personal Pivot)
**Status**: APPROVED

## OVERVIEW
Pivot from Enterprise Live Trading to Personal Signal Oracle.
Goal: AI runs EOD. Calculates alpha. Sends daily trade signals to Telegram. User executes manually. 

**Core Spec Alignment (OMEGA_SUPER_MASTER_PLAN_v2.md)**:
- Core Quant Math (Phase 3), ML Engine (Phase 13), Memory (Phase 6), Risk (Phase 5) remain 100% active.
- Enterprise features (Kubernetes, Live API Brokers, OAuth, Multi-tenancy) are **DISABLED VIA FEATURE FLAGS**, not deleted. Codebase remains structurally intact for future enterprise scaling.

## PHASES

### Phase A: Signal Aggregation & Telegram Batching (P1)
**Task**: Refactor `run_stage5_shadow_live.py` and `telegram_bot.py`.
**Action**: Batch individual orders into 1 single Daily Signal Summary message. 
**Format**: `[BUY/SELL] [SYMBOL] [QTY] [NOTIONAL]`.
**Enterprise Switch**: Disable SSI Live Gateway flag. Force `TradingMode.PAPER` for signaling.
**SOD Role**: [L2-Impl:Role09-Backend] code. [L3-Audit:Role21-Review] audit message length & flag toggles.

### Phase B: Automated Daily Ingestion (P1)
**Task**: Automate data pull.
**Action**: Create `scripts/update_market_data.py` using VNStock to append new EOD daily data to `market_2015_now.parquet`. 
**Enterprise Switch**: Disable tick-level websocket pullers.
**SOD Role**: [L2-Impl:Role08-Data] code. [L3-Audit:Role21-Review] audit data schema consistency.

### Phase C: Unattended Daily Cronjob (P2)
**Task**: Fully automate pipeline.
**Action**: Create `scripts/run_daily_oracle.py`. 
**Workflow**: 
1. (15:30) Run Data Update (Phase B).
2. (16:00) Run Continuous Learning (Phase 6) -> Train XGBoost.
3. (16:15) Run Signal Generation -> Send Telegram.
**Enterprise Switch**: Bypass complex DAG Scheduler/Airflow. Use flat sequential execution.
**SOD Role**: [L2-Impl:Role11-DevOps] code. [L3-Audit:Role21-Review] audit execution dependencies.

### Phase D: Storage Retention (P3)
**Task**: Disk cleanup.
**Action**: Create `scripts/clean_retention.py`. Delete `.ly_state` and `mlflow.db` data > 30 days. Keep `data/`.
**Enterprise Switch**: Local cleanup only. Bypass MinIO/S3 sync modules.
**SOD Role**: [L2-Impl:Role11-DevOps] code. [L3-Audit:Role21-Review] audit strict path deletion to prevent data loss.