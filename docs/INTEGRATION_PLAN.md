# KẾ HOẠCH ĐẤU NỐI TOÀN BỘ MODULES VÀO HỆ THỐNG OMEGA_QUANT

**Ngày**: 2026-05-28
**Tác giả**: Ly (L1 Orchestrator)
**Status**: PENDING IMPLEMENTATION
**Baseline**: Sharpe 1.93, 8 modules wired, 21 modules unwired

---

## TỔNG QUAN

21 modules tồn tại trong codebase nhưng chưa kết nối vào pipeline live.
Kế hoạch chia thành 5 Sprint, ưu tiên theo impact lên Sharpe và production safety.

---

## SPRINT 1: ALPHA EXPANSION (Nâng Sharpe 1.93 → 2.5+)
**Timeline**: 2 ngày | **Priority**: P1

### Modules cần wire:
| # | Module | Wire vào | Expected Impact |
|:--|:-------|:---------|:----------------|
| 1 | `quant.regime_detector_hmm` | E2E backtest + oracle | Position sizing theo regime (bull/bear/sideways) |
| 2 | `quant.macro_alphas` | phase_3_alpha_generation | Macro factor alpha (VN-Index momentum, yield curve) |
| 3 | `quant.macro_context` | phase_4_portfolio_construction | Regime-aware weight adjustment |
| 4 | `quant.sentiment.cii_engine` | phase_3_alpha_generation | Composite Investor Index sentiment |
| 5 | `quant.sentiment.vsi_engine` | phase_3_alpha_generation | Volatility Sentiment Index |

### Deliverables:
1. Wire regime_detector_hmm vào backtest (reduce exposure in bear regime)
2. Add macro_alphas as alpha source (IC filter applies)
3. Add CII + VSI sentiment as alpha sources
4. Re-run E2E backtest with expanded alpha set
5. L3 audit

### Success Criteria:
- Sharpe >= 2.0 (target 2.5)
- At least 2 new alphas survive train+val gate
- No PIT violations

---

## SPRINT 2: PRODUCTION SAFETY (Alerting + Reconciliation)
**Timeline**: 2 ngày | **Priority**: P2

### Modules cần wire:
| # | Module | Wire vào | Purpose |
|:--|:-------|:---------|:--------|
| 6 | `observability.alerting` | run_daily_oracle.py | Telegram alert on pipeline failure |
| 7 | `execution.reconciliation` | run_daily_oracle.py (step 4) | Verify positions match expected |
| 8 | `quant.stress_testing` | Weekly cron job | Stress test portfolio weekly |
| 9 | `quant.contagion_detector` | circuit_breaker | Contagion risk early warning |

### Deliverables:
1. Telegram alert khi oracle fail (via alerting module)
2. Position reconciliation step after signal generation
3. Weekly stress test cron (Saturday 10:00)
4. Contagion detector wired into circuit breaker
5. L3 audit

### Success Criteria:
- Oracle failures trigger Telegram notification within 1 min
- Reconciliation catches position drift > 5%
- Stress test runs weekly without manual intervention

---

## SPRINT 3: LIVE EXECUTION (Real Broker)
**Timeline**: 3 ngày | **Priority**: P2

### Modules cần wire:
| # | Module | Wire vào | Purpose |
|:--|:-------|:---------|:--------|
| 10 | `execution.live_trading_pipeline` | run_daily_oracle.py (step 4) | Real order execution |
| 11 | `execution.ssi_broker_gateway` | live_trading_pipeline | SSI broker API |
| 12 | `execution.tca` | Post-trade step 5 | Transaction cost analysis |
| 13 | `execution.order_state_machine` | live_trading_pipeline | Order lifecycle tracking |
| 14 | `execution.partial_fill_handler` | live_trading_pipeline | Handle partial fills |

### Deliverables:
1. SSI broker gateway with API key from vault
2. Live trading pipeline: signal → order → fill → reconcile
3. TCA report after each trading session
4. Order state machine tracking (PENDING → FILLED → SETTLED)
5. L3 audit

### Prerequisites:
- SSI API credentials (anh cung cấp)
- Paper trading mode first (1 week)
- Kill-switch tested in paper mode

---

## SPRINT 4: DATA ENRICHMENT (News + Live Tick)
**Timeline**: 2 ngày | **Priority**: P2

### Modules cần wire:
| # | Module | Wire vào | Purpose |
|:--|:-------|:---------|:--------|
| 15 | `data.news_aggregator` | Alpha pipeline | News sentiment feed |
| 16 | `data.live_ingestor` | Real-time signal | Intraday tick data |
| 17 | `quant.thompson_sampling` | Alpha selection | Dynamic alpha weight via bandit |
| 18 | `quant.sentiment.contagion_detector` | Risk guard | Cross-asset contagion |

### Deliverables:
1. News aggregator pulling VN financial news
2. Live ingestor for intraday signals (optional)
3. Thompson sampling for dynamic alpha blending
4. L3 audit

---

## SPRINT 5: GOVERNANCE & INFRASTRUCTURE (Enterprise)
**Timeline**: 2 ngày | **Priority**: P3

### Modules cần wire:
| # | Module | Wire vào | Purpose |
|:--|:-------|:---------|:--------|
| 19 | `governance.audit_trail` | All pipeline steps | Immutable audit log |
| 20 | `governance.compliance` | Pre-trade | Regulatory compliance |
| 21 | `security.vault` | Broker credentials | Secret management |
| 22 | `observability.production_monitor` | Dashboard | Real-time monitoring |
| 23 | `memory.episodic_memory` | Oracle pipeline | Learn from past decisions |
| 24 | `memory.failure_memory` | Error handling | Remember past failures |
| 25 | `infra.worker_pool` | Parallel execution | Multi-process scaling |

### Deliverables:
1. Audit trail for every trade decision
2. Compliance pre-trade checks (position limits, sector caps)
3. Vault for SSI API keys (no plaintext)
4. Production monitoring dashboard
5. L3 audit

---

## TIMELINE TỔNG THỂ

```
Sprint 1 (29-30/05): Alpha Expansion → Sharpe 2.5+
Sprint 2 (31/05-01/06): Production Safety → Alerts + Reconciliation
Sprint 3 (02-04/06): Live Execution → Real broker (paper first)
Sprint 4 (05-06/06): Data Enrichment → News + Live tick
Sprint 5 (07-08/06): Governance → Enterprise features
```

---

## METRICS MỤC TIÊU SAU 5 SPRINTS

| Metric | Hiện tại | After Sprint 1 | After All |
|:-------|:---------|:---------------|:----------|
| Sharpe | 1.93 | 2.5+ | 2.5+ |
| Modules Wired | 8 | 13 | 25+ |
| Alphas Active | 3 | 5-7 | 7-10 |
| Alerts | None | Telegram | Full |
| Broker | None | None | SSI Live |
| Monitoring | None | Basic | Dashboard |

---

*Generated by Ly (L1 Orchestrator) - OMEGA_QUANT Protocol v2.4*
