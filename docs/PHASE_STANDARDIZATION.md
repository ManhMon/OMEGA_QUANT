# PHASE STANDARDIZATION - Master Plan Alignment
**Date**: 2026-05-13 08:06 GMT+7  
**Action**: Rename all sub-phases to match Master Plan (Phase 1-10 only)

---

## RENAMING RULES

### Before (Current - Inconsistent)
```
Phase 3.1 (Alpha Discovery)
Phase 3.2 (Portfolio Optimizer) ← vừa APPROVED
Phase 3.4 (Genetic Alpha)
Phase 3.3 (Portfolio Construction) ← TODO
```

### After (Master Plan - Standardized)
```
Phase 3: Quant Math Engine
  ├─ 3.1: Alpha Discovery Baseline
  ├─ 3.2: Portfolio Optimization (Mean-Variance, Risk Parity, Black-Litterman)
  ├─ 3.3: Portfolio Construction & Risk-Targeting
  └─ 3.4: Self-Evolution Alpha Discovery (Genetic Programming)
```

---

## FILE UPDATES REQUIRED

### 1. `.ly_state/session/phase_gates.json`
**Current**:
```json
"PHASE_3_2_PORTFOLIO_OPTIMIZATION": { "status": "APPROVED", ... }
```

**After**:
```json
"PHASE_3_QUANT_MATH_ENGINE": {
  "status": "in_progress",
  "sub_phases": {
    "3.1": { "status": "APPROVED", "commit": "e4d5900" },
    "3.2": { "status": "APPROVED", "commit": "97027cf" },
    "3.3": { "status": "pending", "commit": null },
    "3.4": { "status": "APPROVED", "commit": "pending" }
  }
}
```

### 2. `.ly_state/session/active_tasks.json`
**Current**:
```json
"phase": "3.4"
```

**After**:
```json
"phase": "3",
"current_step": "3.2",
"next_step": "3.3"
```

### 3. `HEARTBEAT.md`
**Current**:
```
- [x] Phase 3.1 Alpha Discovery (APPROVED)
- [ ] Phase 3.2: Portfolio Optimization (P1)
- [ ] Phase 3.4: Self-Evolution Alpha Discovery
```

**After**:
```
- [x] Phase 3: Quant Math Engine (In Progress)
  - [x] 3.1: Alpha Discovery Baseline (APPROVED)
  - [x] 3.2: Portfolio Optimization (APPROVED)
  - [ ] 3.3: Portfolio Construction & Risk-Targeting (TODO)
  - [x] 3.4: Self-Evolution Alpha Discovery (APPROVED)
```

### 4. `OMEGA_QUANT/docs/OMEGA_SUPER_MASTER_PLAN.md`
**Add clarification**:
```markdown
### Phase 3: Quant Math Engine (Weeks 3-5)

**Sub-phases** (for tracking):
- 3.1: Alpha Discovery Baseline
- 3.2: Portfolio Optimization (P1)
- 3.3: Portfolio Construction & Risk-Targeting (P2)
- 3.4: Self-Evolution Alpha Discovery (Genetic Programming)

All sub-phases must complete before Phase 3 is marked APPROVED.
```

---

## GATE STRUCTURE (Standardized)

```json
{
  "PHASE_1_FOUNDATION": {
    "status": "PARTIAL",
    "completion": "10%",
    "sub_gates": {
      "1.1_task_scheduler": "NOT_STARTED",
      "1.2_event_bus": "NOT_STARTED",
      "1.3_holiday_calendar": "APPROVED"
    }
  },
  "PHASE_2_DATA_STORAGE": {
    "status": "PARTIAL",
    "completion": "60%",
    "sub_gates": {
      "2.1_dataloader": "APPROVED",
      "2.2_model_registry": "NOT_STARTED",
      "2.3_artifact_store": "NOT_STARTED"
    }
  },
  "PHASE_3_QUANT_MATH_ENGINE": {
    "status": "IN_PROGRESS",
    "completion": "75%",
    "sub_gates": {
      "3.1_alpha_discovery": "APPROVED",
      "3.2_portfolio_optimization": "APPROVED",
      "3.3_portfolio_construction": "PENDING",
      "3.4_genetic_alpha": "APPROVED"
    }
  },
  "PHASE_4_EXECUTION_ENGINE": {
    "status": "NOT_STARTED",
    "completion": "0%"
  },
  "PHASE_5_RISK_MANAGEMENT": {
    "status": "APPROVED",
    "completion": "100%"
  },
  "PHASE_6_MEMORY_EVOLUTION": {
    "status": "APPROVED",
    "completion": "100%"
  },
  "PHASE_7_OBSERVABILITY": {
    "status": "APPROVED",
    "completion": "100%"
  },
  "PHASE_8_SECURITY_GOVERNANCE": {
    "status": "APPROVED",
    "completion": "100%"
  },
  "PHASE_9_INTEGRATION_TESTING": {
    "status": "NOT_STARTED",
    "completion": "0%"
  },
  "PHASE_10_DEPLOYMENT_GOLIVE": {
    "status": "NOT_STARTED",
    "completion": "0%"
  }
}
```

---

## ACTION ITEMS

- [ ] Update `phase_gates.json` structure (hierarchical sub-phases)
- [ ] Update `active_tasks.json` (phase=3, current_step=3.2)
- [ ] Update `HEARTBEAT.md` (Phase 3 with sub-phases)
- [ ] Update `OMEGA_SUPER_MASTER_PLAN.md` (add sub-phase clarification)
- [ ] Rename all audit reports to use `PHASE_3_*` prefix (not `PHASE_3_2_*`)
- [ ] Commit: "Standardize phase naming to Master Plan (Phase 1-10)"

---

**Status**: Ready for implementation  
**Owner**: Ly (L1)  
**Timeline**: 30 minutes to update all files
