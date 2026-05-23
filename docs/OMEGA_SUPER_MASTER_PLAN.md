# OMEGA+++ QUANT AI — SUPER MASTER PLAN
**Version**: v1.0  
**Status**: Implementation-Ready  
**Last Updated**: 2026-05-09  
**Audience**: Engineering Team, Ly (Orchestrator), OpenCode (Coder), Codex (Auditor)

---

## EXECUTIVE SUMMARY

OMEGA+++ is an **Institutional Grade Quant AI System** designed to achieve:
- **Alpha Generation**: Self-evolving, microstructure-aware alpha discovery
- **Risk Management**: PIT-safe, leakage-free portfolio optimization
- **Execution Excellence**: VWAP/TWAP-aware order routing with circuit breakers
- **Observability**: Real-time monitoring, audit trails, and recovery mechanisms
- **Scalability**: From individual traders (2B-5B VND) to institutional portfolios (100B+)

**Core Principles**:
1. **Verification-first**: No module ships without tests and acceptance criteria
2. **Contract-first**: All boundaries are explicit and versioned
3. **No leakage**: PIT safety with explicit `as_of` and `available_at` timestamps, T-1 lag, chronological splitting enforced
4. **Recovery by design**: Checkpoint, retry, rollback, restore built-in
5. **Observability by default**: Every action logged, traced, audited

---

## VISION & STRATEGIC GOALS

### Long-term Vision (12-24 months)
Build the **most transparent, auditable, and performant Quant AI system** in Southeast Asia, with:
- Proprietary alpha discovery engine (Self-Evolution)
- Institutional-grade risk management (PIT-safe, no leakage)
- Production-ready execution (live trading, paper trading, backtesting)
- Full observability (dashboards, audit trails, SRE tooling)

### Strategic Goals
1. **Alpha Superiority**: Achieve IC > 0.15 on walk-forward tests (T+3, T+5 horizons with non-overlapping label windows)
2. **Risk Excellence**: Sharpe > 2.0, max drawdown < 15%, Sortino > 3.0
3. **Execution Efficiency**: Slippage < 2 bps, fill rate > 98%
4. **System Reliability**: 99.9% uptime, <100ms latency for risk checks
5. **Auditability**: 100% of decisions traceable to data, model, and policy

**Leakage Control for Multi-Horizon Alphas**:
- **T+3 labels**: Predict return from T+1 to T+3 (label available at T+4)
- **T+5 labels**: Predict return from T+1 to T+5 (label available at T+6)
- **Non-overlapping validation**: T+3 and T+5 models validated on separate, non-overlapping time windows
- **Promotion gate (UNIFIED)**: Models promoted only after strict embargo period: `validation_start_date >= train_end_date + max_horizon + 1`
  - For T+3 models: embargo = train_end + 4 days (T+3 label available at T+4)
  - For T+5 models: embargo = train_end + 6 days (T+5 label available at T+6)
  - This ensures NO premature validation/promotion for any horizon

---

## ROADMAP: 16-WEEK PHASED DEPLOYMENT

### Phase 1: Foundation & Core Runtime (Weeks 1-2)
**Goal**: Establish task scheduler, event bus, and core runtime infrastructure.

**Status**: ✅ **PARTIAL COMPLETE** (Data Infrastructure - Holiday Calendar)

**Deliverables**:
- Task State Machine (CREATED → QUEUED → PLANNED → DISPATCHED → RUNNING → VERIFYING → APPROVED → DEPLOYED)
- Scheduler with priority queue, dependency resolution, timeout enforcement
- Event bus with versioning, replay, and idempotency
- Worker lifecycle management (BOOT → LOAD_CONTEXT → EXECUTE → VERIFY → REPORT → UNLOAD)
- Checkpoint/restore mechanism
- ✅ **VN Holiday Calendar (2015-2027)**: JSON-based config with provenance tracking (Option A selected)
  - Config: `OMEGA_QUANT/config/vn_holidays.json` (v1.0.0)
  - Implementation: `OMEGA_QUANT/packages/data/src/omega/data/calendar.py` (refactored)
  - Tests: `OMEGA_QUANT/packages/data/tests/test_calendar.py` (20 tests, 100% pass)
  - Audit: `docs/CALENDAR_JSON_AUDIT_R2.md` (L3 approved)

**Acceptance Criteria**:
- [ ] Task can transition through all states without deadlock (verified via state machine unit tests, 100% coverage)
- [ ] Scheduler resolves dependencies correctly (tested with 10+ dependency graphs, including cycles)
- [ ] Events are replayable and idempotent (replay test: 1000 events produce identical state)
- [ ] Worker can checkpoint and resume from checkpoint (tested with 5 failure scenarios, 100% recovery rate)
- [ ] 100% test coverage for state machine (measured via pytest-cov)
- [x] **Holiday calendar handles VN market holidays correctly** (verified via 20 unit tests, 100% pass rate, L3 audit approved)

**Estimated Effort**: 40 hours (OpenCode)  
**Risk**: Low (well-defined, no external dependencies)

---

### Phase 2: Data & Storage Layer (Weeks 2-3)
**Goal**: Implement metadata store, time-series store, artifact store, and audit logging.

**Deliverables**:
- Database schema (tasks, task_events, artifacts, datasets, models, experiments, backtests, risk_reports, executions, memory_snapshots, audit_logs)
- Dataset registry with versioning and provenance tracking
- Model registry with version control and promotion workflow
- Artifact store with checksum validation
- Audit log with immutable append-only semantics

**Acceptance Criteria**:
- [ ] All tables created and indexed (verified via schema migration tests)
- [ ] Dataset versioning works (create, retrieve, promote) - tested with 100+ datasets
- [ ] Model registry supports rollback (tested with 10 rollback scenarios, 100% success rate)
- [ ] Audit logs are immutable and queryable (tested: 10,000 log entries, zero modifications, query latency <100ms)
- [ ] Checksum validation prevents corruption (tested: 50 corrupted files detected, 0 false negatives)

**Estimated Effort**: 35 hours (OpenCode)  
**Risk**: Medium (schema design impacts downstream systems)

---

### Phase 3: Quant Math Engine (Weeks 3-5)
**Goal**: Implement factor computation, alpha generation, and portfolio optimization.

**Deliverables**:
- Factor factory (technical, fundamental, alternative data factors) with explicit `as_of` timestamps
- Alpha discovery engine (linear, tree-based, neural models) with `available_at` boundaries
- Feature engineering pipeline (normalization, winsorization, PCA) with T-1 lag enforcement
- Portfolio optimizer (mean-variance, risk parity, hierarchical risk parity)
- Walk-forward backtester with PIT safety checks (`as_of` <= `available_at` validation)

**Acceptance Criteria**:
- [ ] All factors compute without look-ahead bias (validated via `as_of` <= `available_at` checks)
- [ ] Alpha models train on walk-forward windows with explicit temporal boundaries
- [ ] Portfolio weights respect constraints (leverage, concentration, liquidity)
- [ ] Backtest results match manual calculations
- [ ] PIT safety audit passes (no T+0 leakage, all data has `as_of` and `available_at` timestamps)

**Estimated Effort**: 60 hours (OpenCode + Codex audit)  
**Risk**: High (PIT safety critical, easy to introduce leakage)

---

### Phase 4: Execution Engine (Weeks 5-7)
**Goal**: Implement order routing, execution simulation, and broker integration.

**Deliverables**:
- Order router (VWAP, TWAP, POV, Implementation Shortfall)
- Execution simulator (market impact, slippage, partial fills)
- Broker gateway (SSI, VNDirect, Vietstock integration)
- Order state machine (PENDING → SUBMITTED → FILLED → SETTLED)
- Trade blotter and execution analytics

**Acceptance Criteria**:
- [ ] Orders route to correct broker based on liquidity (tested with 100+ routing scenarios, 100% accuracy)
- [ ] Execution simulator matches historical fills (backtested on 1 year data, mean absolute error <1%)
- [ ] Broker gateway handles connection failures gracefully (tested with 20 failure scenarios, 100% recovery rate)
- [ ] Trade blotter reconciles with broker statements (tested on 1000+ trades, 100% match rate)
- [ ] Slippage analysis shows realistic costs (validated against 6 months historical data, error <2 bps)

**Estimated Effort**: 50 hours (OpenCode)  
**Risk**: Medium (broker API changes, network failures)

---

### Phase 5: Risk Management (Weeks 7-9)
**Goal**: Implement circuit breakers, position limits, and real-time risk monitoring.

**Deliverables**:
- Advanced circuit breaker (volatility-based, correlation-based, liquidity-based)
- Position limit engine (notional, leverage, concentration, sector, style)
- Real-time risk monitor (Greeks, VaR, stress tests)
- Risk dashboard (live positions, P&L, Greeks, alerts)
- Risk escalation and kill switch

**Acceptance Criteria**:
- [ ] Circuit breaker triggers on volatility spike (tested with 50 volatility events, 100% trigger rate when threshold exceeded)
- [ ] Position limits enforced before order submission (tested with 100+ limit violations, 100% rejection rate)
- [ ] Risk monitor updates in <100ms (measured via latency tests, p99 <100ms over 10,000 updates)
- [ ] Dashboard shows live P&L and Greeks (verified with real-time data feed, update frequency 1Hz, accuracy 100%)
- [ ] Kill switch stops all trading immediately (tested with 10 emergency scenarios, mean stop time <500ms, 100% success rate)

**Estimated Effort**: 45 hours (OpenCode + Codex audit)  
**Risk**: High (safety-critical, must be bulletproof)

---

### Phase 6: Memory & Evolution Engine (Weeks 9-11)
**Goal**: Implement memory compression, retrieval, and self-evolution.

**Deliverables**:
- Memory compression (lossy/lossless, semantic hashing)
- Memory retrieval (similarity search, ranking)
- Memory archive (cold storage, retention policies)
- Evolution engine (hypothesis generation, A/B testing, promotion with leakage guards)
- Continuous learning loop (data → model → backtest → promote) with strict `as_of`/`available_at` enforcement

**Acceptance Criteria**:
- [ ] Memory compression reduces size by 80%+ without losing critical information
- [ ] Retrieval latency <50ms for 1M records
- [ ] Evolution engine discovers new alphas weekly with IC > baseline + 0.02
- [ ] A/B tests show statistical significance (p < 0.05, minimum 30 days)
- [ ] Promoted models outperform baseline on out-of-sample data (validation period >= 60 days, non-overlapping with training)
- [ ] Model promotion enforces UNIFIED strict embargo period: validation_start_date >= train_end_date + max_horizon + 1 (machine-verifiable gate, applies to ALL models regardless of horizon)

**Estimated Effort**: 55 hours (OpenCode)  
**Risk**: High (evolution logic complex, easy to overfit)

---

### Phase 7: Observability & SRE (Weeks 11-13)
**Goal**: Implement logging, metrics, tracing, and alerting.

**Deliverables**:
- Structured logging (JSON, correlation IDs, trace IDs)
- Metrics collection (Prometheus-compatible)
- Distributed tracing (OpenTelemetry)
- Alert rules (latency, error rate, risk limits)
- SRE dashboard (system health, resource usage, incident tracking)

**Acceptance Criteria**:
- [ ] All events logged with correlation IDs (verified via log analysis, 100% of events have correlation_id)
- [ ] Metrics queryable in real-time (tested with Prometheus queries, query latency <50ms, 10,000+ metrics)
- [ ] Traces show full request path (tested with 100+ requests, 100% trace completeness)
- [ ] Alerts trigger within 1 minute of anomaly (tested with 50 anomaly scenarios, mean trigger time <30s, 100% detection rate)
- [ ] Dashboard shows system health at a glance (verified with 10 users, 100% can identify critical issues within 5 seconds)

**Estimated Effort**: 40 hours (OpenCode)  
**Risk**: Low (standard observability patterns)

---

### Phase 8: Security & Governance (Weeks 13-14)
**Goal**: Implement secrets management, access control, and audit trails.

**Deliverables**:
- Secrets vault (encrypted storage, rotation)
- Access control (RBAC, API keys, OAuth)
- Audit trails (immutable logs of all actions)
- Compliance checks (PIT safety, data retention, regulatory)
- Security scanning (dependency vulnerabilities, code analysis)

**Acceptance Criteria**:
- [ ] Secrets never logged or exposed (verified via log scanning, 0 secrets found in 100,000+ log entries)
- [ ] Access control enforced on all APIs (tested with 100+ unauthorized requests, 100% rejection rate)
- [ ] Audit trails show who did what when (verified with 1000+ actions, 100% traceability)
- [ ] Compliance checks pass (PIT safety: 100% pass rate on 50+ datasets, data retention: 100% compliance)
- [ ] Security scan finds no critical issues (tested with OWASP ZAP, Bandit, Safety - 0 critical vulnerabilities)

**Estimated Effort**: 35 hours (OpenCode + Codex audit)  
**Risk**: Medium (security is ongoing, not one-time)

---

### Phase 9: Integration & Testing (Weeks 14-15)
**Goal**: Integrate all components, run end-to-end tests, and validate system behavior.

**Deliverables**:
- End-to-end test suite (happy path, error cases, edge cases)
- Integration tests (component interactions)
- Performance tests (latency, throughput, resource usage)
- Stress tests (high load, network failures, data corruption)
- Acceptance test suite (business requirements)

**Acceptance Criteria**:
- [ ] All tests pass (unit, integration, e2e, performance, stress) - 100% pass rate, 0 flaky tests
- [ ] Code coverage >90% (measured via pytest-cov, all critical paths covered)
- [ ] Performance meets SLOs (latency p99 <100ms for risk checks, throughput >1000 orders/day)
- [ ] System recovers from failures (tested with 20 failure scenarios: network, disk, memory - 100% recovery rate, MTTR <5 minutes)
- [ ] Business requirements validated (tested with 50+ user scenarios, 100% acceptance rate)

**Estimated Effort**: 50 hours (OpenCode + Codex)  
**Risk**: Medium (integration issues common)

---

### Phase 10: Deployment & Go-Live (Week 16)
**Goal**: Deploy to production, monitor, and support.

**Deliverables**:
- Deployment automation (CI/CD, blue-green, canary)
- Production monitoring (dashboards, alerts, on-call)
- Runbooks (incident response, troubleshooting)
- Documentation (user guides, API docs, architecture)
- Support process (bug reports, feature requests, escalation)

**Acceptance Criteria**:
- [ ] Deployment is automated and repeatable (tested with 10 deployments, 100% success rate, mean deployment time <10 minutes)
- [ ] Monitoring shows system health (verified with 24-hour monitoring, 100% uptime visibility, alert coverage >95%)
- [ ] Runbooks cover common issues (tested with 15 incident scenarios, 100% resolution via runbook)
- [ ] Documentation is complete and accurate (verified by 3 independent reviewers, 100% API coverage, 0 broken links)
- [ ] Support process is defined (SLA: response time <1 hour for critical issues, resolution time <4 hours)

**Estimated Effort**: 30 hours (OpenCode + Codex)  
**Risk**: Medium (production surprises common)

---

## RESOURCE & TOKEN BUDGET STRATEGY

### Team Composition
- **Ly (L1)**: Orchestrator, decision-maker, 20% time
- **OpenCode (L2)**: Senior coder, 80% time
- **Codex (L3)**: Auditor, 60% time
- **SOV V2.4**: Reasoning engine, 40% time (guidance, not execution)

### Token Budget (Estimated)
| Phase | Task | Tokens | Notes |
|:------|:-----|:-------|:------|
| 1 | Foundation | 15K | Task scheduler, event bus |
| 2 | Storage | 12K | Database schema, registry |
| 3 | Quant Math | 25K | Factors, alphas, portfolio opt |
| 4 | Execution | 18K | Order routing, broker gateway |
| 5 | Risk | 20K | Circuit breaker, limits, monitor |
| 6 | Memory | 22K | Compression, retrieval, evolution |
| 7 | Observability | 14K | Logging, metrics, tracing |
| 8 | Security | 16K | Secrets, access control, audit |
| 9 | Testing | 20K | E2E, integration, performance |
| 10 | Deployment | 12K | CI/CD, monitoring, runbooks |
| **Total** | | **174K** | ~2-3 weeks of intensive work |

### Token Optimization Strategies
1. **Reuse existing code**: V21_QUANT modules (sanitization, neutralization, risk guard)
2. **Contract-first design**: Minimize rework by getting contracts right upfront
3. **Parallel work**: Ly orchestrates multiple OpenCode tasks simultaneously
4. **Codex spot-checks**: Audit critical paths (PIT safety, risk) rather than every line
5. **Documentation-driven**: Specs reduce back-and-forth clarification

---

## SYSTEM ARCHITECTURE OVERVIEW

### 7-Layer Institutional Grade Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ L7: Monitoring & Observability (Dashboards, Alerts, SRE)   │
├─────────────────────────────────────────────────────────────┤
│ L6: Data Governance & MLOps (Versioning, Lineage, Quality) │
├─────────────────────────────────────────────────────────────┤
│ L5: Portfolio Management (Rebalancing, Constraints, Limits) │
├─────────────────────────────────────────────────────────────┤
│ L4: Risk Management (Circuit Breaker, VaR, Stress Tests)   │
├─────────────────────────────────────────────────────────────┤
│ L3: Execution Engine (Order Routing, VWAP/TWAP, Broker)    │
├─────────────────────────────────────────────────────────────┤
│ L2: Strategy Logic (XGBoost, DL, RL, Walk-Forward)         │
├─────────────────────────────────────────────────────────────┤
│ L1: Core Intelligence (Feature Factory, Alpha Discovery)   │
├─────────────────────────────────────────────────────────────┤
│ L0: Runtime Core (Task Scheduler, Event Bus, Storage)      │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Principles

**1. Task-Driven Execution**
- Every action is a Task with explicit state, dependencies, and constraints
- Tasks flow through state machine: CREATED → QUEUED → PLANNED → DISPATCHED → RUNNING → VERIFYING → APPROVED → DEPLOYED
- Scheduler ensures dependency resolution and resource allocation

**2. Event-Driven Communication**
- Components communicate via versioned events (not direct calls)
- Events are idempotent, replayable, and immutable
- Event bus maintains ordering and causality

**3. Contract-First Design**
- All boundaries are explicit (file, class, function, event, schema)
- Contracts specify inputs, outputs, preconditions, postconditions
- Violations detected early (compile-time or runtime)

**4. PIT Safety by Default**
- No look-ahead bias (T+n data never used for T)
- T-1 lag enforced on all features
- Chronological splitting for train/test/val
- Leakage detection in data pipeline

**5. Checkpoint & Recovery**
- Checkpoints at critical milestones (after planning, after code, after test, after risk, before deploy)
- Checkpoints include task state, context, artifacts, metrics, decisions
- Recovery restores from checkpoint and resumes

**6. Observability by Default**
- Every action logged with correlation ID and trace ID
- Metrics collected for latency, throughput, errors
- Traces show full request path through system
- Audit trails immutable and queryable

---

## CRITICAL SUCCESS FACTORS

### Technical
1. **PIT Safety**: Zero tolerance for look-ahead bias or data leakage
2. **Performance**: <100ms latency for risk checks, <1s for order submission
3. **Reliability**: 99.9% uptime, graceful degradation on failures
4. **Scalability**: Support 1000+ assets, 100+ strategies, 1M+ daily trades

### Organizational
1. **Clear Ownership**: Each component has a clear owner (OpenCode, Codex, Ly)
2. **Transparent Communication**: All decisions logged and traceable
3. **Continuous Improvement**: Weekly reviews, A/B testing, evolution
4. **Risk Discipline**: Risk checks before every decision, kill switch always ready

### Process
1. **Verification-First**: No code ships without tests and acceptance criteria
2. **Contract-First**: Specs written before code
3. **Audit-First**: Codex reviews before deployment
4. **Documentation-First**: Decisions recorded in MEMORY.md and audit logs

---

## DEPENDENCIES & CONSTRAINTS

### External Dependencies
- **Data**: VNStock, SSI, VNDirect, Vietstock APIs
- **Infrastructure**: Cloud compute (AWS/GCP), database (PostgreSQL), message queue (RabbitMQ/Kafka)
- **Libraries**: Pandas, NumPy, XGBoost, PyTorch, scikit-learn

### Internal Dependencies
- **V21_QUANT**: Reuse sanitization, neutralization, risk guard modules
- **SOV V2.4**: Reasoning engine for guidance and strategy
- **Ly Orchestrator**: Decision-making and resource allocation

### Constraints
- **Token Budget**: 174K tokens for full implementation
- **Timeline**: 16 weeks for MVP
- **Team Size**: 3 agents (Ly, OpenCode, Codex)
- **Capital**: 2B-5B VND for individual scale, 100B+ for institutional

---

## RISK MITIGATION

| Risk | Probability | Impact | Mitigation |
|:-----|:-----------|:-------|:-----------|
| PIT safety violation | High | Critical | Codex audit on all data pipelines, automated leakage detection |
| Performance degradation | Medium | High | Load testing, caching, async processing |
| Broker API changes | Medium | Medium | Abstraction layer, fallback brokers |
| Market regime change | High | Medium | Continuous learning, A/B testing, evolution |
| Data quality issues | Medium | High | Data validation, quality scoring, alerts |
| Execution failures | Low | High | Circuit breaker, kill switch, manual override |

---

## SUCCESS METRICS

### Alpha Quality
- **Information Coefficient (IC)**: > 0.15 on walk-forward tests
- **Sharpe Ratio**: > 2.0 on live trading
- **Sortino Ratio**: > 3.0 on live trading
- **Max Drawdown**: < 15% on live trading

### System Performance
- **Latency**: <100ms for risk checks, <1s for order submission
- **Throughput**: 1000+ orders/day
- **Uptime**: 99.9% (< 43 minutes downtime/month)
- **Error Rate**: < 0.1%

### Operational Excellence
- **Code Coverage**: > 90%
- **Test Pass Rate**: 100%
- **Deployment Frequency**: Daily
- **Mean Time to Recovery**: < 5 minutes

### Business Impact
- **Alpha Generation**: Consistent outperformance vs VN-Index
- **Risk-Adjusted Returns**: Sharpe > 2.0
- **Capital Efficiency**: ROI > 30% annually
- **Scalability**: Support 100B+ AUM

---

## NEXT STEPS

1. **Week 1**: Ly reviews this plan with OpenCode and Codex
2. **Week 1-2**: OpenCode implements Phase 1 (Foundation & Core Runtime)
3. **Week 2-3**: Codex audits Phase 1, OpenCode starts Phase 2
4. **Ongoing**: Weekly reviews, risk checks, evolution
5. **Week 16**: Go-live and production monitoring

---

## APPENDIX: GLOSSARY

- **PIT Safety**: Point-In-Time safety; no look-ahead bias or data leakage
- **IC**: Information Coefficient; correlation between predictions and actuals
- **Sharpe Ratio**: Risk-adjusted return; higher is better
- **Sortino Ratio**: Downside risk-adjusted return; higher is better
- **VWAP**: Volume-Weighted Average Price; execution algorithm
- **TWAP**: Time-Weighted Average Price; execution algorithm
- **Circuit Breaker**: Automatic trading halt on volatility spike
- **Kill Switch**: Emergency stop for all trading
- **Walk-Forward**: Backtesting with rolling train/test windows
- **Leakage**: Unintended information flow from future to past

---

**Document Owner**: OpenCode (L2)  
**Reviewed By**: Codex (L3), Ly (L1)  
**Last Updated**: 2026-05-09  
**Version**: v1.0
