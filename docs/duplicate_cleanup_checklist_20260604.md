# Duplicate Cleanup Checklist — 2026-06-04

## Goal
Dọn duplicate an toàn theo batch nhỏ.

Operating rule hiện tại:
- `src/omega/...` = canonical mặc định cho 70 duplicate modules
- `packages/quant/...` = canonical tạm thời cho 26 package-only active modules

---

## Batch 1 — execution

### Scope
- `packages/quant/src/omega/quant/execution/__init__.py`
- `packages/quant/src/omega/quant/execution/broker_gateway.py`
- `packages/quant/src/omega/quant/execution/order_router.py`
- đối chiếu với:
  - `src/omega/quant/execution/__init__.py`
  - `src/omega/quant/execution/broker_gateway.py`
  - `src/omega/quant/execution/order_router.py`

### Actions
- [ ] Diff nội dung `src` vs `packages`
- [ ] Xác nhận imports trong `scripts/`, `src/`, `tests/`
- [ ] Chốt `src` là source-of-truth
- [ ] Sửa imports còn trỏ nhầm nếu có
- [ ] Archive/xóa duplicate trong `packages` chỉ sau khi tests pass

### Verification
- [ ] grep import paths sạch
- [ ] test execution/router liên quan pass

---

## Batch 2 — risk

### Scope
- `advanced_circuit_breaker.py`
- `contagion_risk_validator.py`
- `individual_risk_guard.py`
- `production_monitor.py`
- `risk_monitor.py`
- `risk_monitor_l07.py`

### Actions
- [ ] Diff `src` vs `packages`
- [ ] Kiểm tra references từ paper trading / live pipeline
- [ ] Chốt `src` canonical
- [ ] Giữ package-only active modules ngoài batch này nguyên trạng
- [ ] Remove/archive duplicate package copies sau verify

### Verification
- [ ] risk-related tests pass
- [ ] paper trading / realtime risk imports không gãy

---

## Batch 3 — features

### Scope
- `basic_indicators.py`
- `cross_sectional.py`
- `neutralization.py`
- `normalization.py`
- `statistical_features.py`
- `factory/discovery_engine.py`

### Actions
- [ ] Diff `src` vs `packages`
- [ ] Kiểm tra upstream import graph
- [ ] Chốt `src` canonical
- [ ] Remove/archive duplicate package copies sau test

### Verification
- [ ] feature tests pass
- [ ] discovery/backtest imports pass

---

## Batch 4 — quant core

### Scope
Representative high-impact duplicates:
- `pipeline.py`
- `phase35_walk_forward.py`
- `live_trading_pipeline.py`
- `realtime_risk_guard.py`
- `rebalancer.py`
- `transaction_cost_optimizer.py`
- `portfolio_optimizer.py`
- `backtest_engine.py`
- `constraint_solver.py`
- `pnl_monitor.py`
- `promotion.py`
- `label_engine.py`
- `feature_module.py`

### Actions
- [ ] Diff each pair
- [ ] Map who imports each path now
- [ ] Freeze `src` canonical list
- [ ] Patch lingering imports/tests/docs
- [ ] Archive package duplicates in one controlled commit

### Verification
- [ ] focused backtest/pipeline tests pass
- [ ] no broken imports from scripts

---

## Do not touch yet
These remain package-canonical tạm thời:
- `packages/quant/src/omega/quant/validation/*`
- `packages/quant/src/omega/quant/universe/*`
- `packages/quant/src/omega/quant/portfolio/execution_sim.py`
- `packages/quant/src/omega/quant/portfolio/tail_controls.py`
- overlay modules in `packages/quant/src/omega/quant/portfolio/`
- `packages/quant/src/omega/quant/models/lstm_alpha.py`
- `packages/quant/src/omega/quant/evolution/feature_adapter.py`
- `packages/quant/src/omega/quant/evolution/pareto_hof.py`

---

## Safe order
1. execution
2. risk
3. features
4. quant core

---

## Exit criteria
- [ ] no duplicate module left in cleaned batches
- [ ] imports point to canonical path only
- [ ] tests green for touched scope
- [ ] docs/state updated after each batch
