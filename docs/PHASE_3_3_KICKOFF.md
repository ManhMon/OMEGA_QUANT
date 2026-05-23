# Phase 3.3 Kickoff — Wiring & Paper Trading

**Goal:** Connect Alpha Discovery → Portfolio Optimizer → Promotion Gate → Mock Execution.

**Modules to Wire:**
1. `alpha_discovery.py`: Generates alpha signals (vectorized, T-1).
2. `portfolio_optimizer.py`: Converts signals to weights (constraints: leverage, concentration).
3. `promotion.py`: Evaluates performance and handles state (Shadow/Production).
4. `execution_sim.py` (New): Mock SSI/Broker gateway for PnL tracking.

**Tasks:**
1. Create `trading_engine.py` (Orchestrator for Quant modules).
2. Create `execution_sim.py` (Latency & slippage model).
3. Integration tests (Full loop).

**Roles:**
- **Ly (L1)**: Coordination.
- **Role 9 (L2 - Backend Engineer)**: Implementation.
- **Role 21 (L3 - Code Reviewer)**: Audit.

**SOD Flow:**
Ly spawn L2 → Impl artifacts → Ly verify → Ly spawn L3 → Audit verdict → Ly gate.
