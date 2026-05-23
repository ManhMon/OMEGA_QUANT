#!/usr/bin/env python3
"""
SOV V2.4 Reasoning Engine - Phase 3.4 v2 Planning
Gọi SOV để lập kế hoạch chi tiết cho Alpha Discovery Engine (T+3/T+5)
"""

import json
import sys
from pathlib import Path

# Load task definition
task_file = Path(".ly_state/session/phase3_4_v2_task.json")
with open(task_file) as f:
    task = json.load(f)

# SOV Reasoning Prompt
sov_prompt = f"""
You are SOV V2.4 - Stealth Orchestration Reasoning Engine for V21_QUANT.
Your role: Provide detailed reasoning, audit logic, and institutional strategy.

TASK: {task['task']}
OBJECTIVE: {task['objective']}

REQUIREMENTS:
{chr(10).join(f"- {req}" for req in task['requirements'])}

CONTEXT: {task['context']}

---

PHASE 3.4 v2 PLANNING REQUEST:

Provide a detailed, step-by-step implementation plan for Alpha Discovery Engine (T+3/T+5).

Structure your response as:

## 1. ARCHITECTURE OVERVIEW
- Layer structure (which layers involved)
- Data flow (input -> processing -> output)
- Integration points with existing modules

## 2. ALPHA DISCOVERY STRATEGY
- What makes a "T+3 alpha" vs "T+5 alpha"?
- Signal types (momentum, mean-reversion, microstructure, etc.)
- Feature engineering approach (PIT-safe, T-1 lag)
- Scoring/ranking methodology

## 3. IMPLEMENTATION ROADMAP
- Step 1: Core Alpha Discovery Module
- Step 2: T+3/T+5 Signal Generators
- Step 3: Feature Factory Integration
- Step 4: Backtesting & Validation
- Step 5: Paper Trading Integration

## 4. PIT SAFETY CHECKLIST
- Look-ahead bias prevention
- T-1 lag enforcement
- Temporal data splitting
- Leakage detection

## 5. TESTING STRATEGY
- Unit tests (signal generators)
- Integration tests (with HighAlphaFilter + RiskGuard)
- Walk-forward validation
- Paper trading verification

## 6. RISKS & MITIGATIONS
- Overfitting risk
- Liquidity constraints
- Execution slippage
- Market regime changes

## 7. SUCCESS CRITERIA
- Measurable IC (Information Coefficient)
- Sharpe ratio targets
- Max drawdown limits
- Turnover constraints

Provide reasoning, not just a checklist. Think like a Renaissance/Two Sigma quant.
"""

# Output reasoning plan
plan = {
    "task_id": "phase3_4_v2_planning",
    "agent": "SOV_V2.4",
    "mode": "REASONING_ONLY",
    "prompt": sov_prompt,
    "timestamp": "2026-05-09T06:20:00Z",
    "status": "ready_for_sov_input"
}

output_file = Path(".ly_state/session/sov_phase3_4_v2_reasoning_request.json")
with open(output_file, "w") as f:
    json.dump(plan, f, indent=2)

print(f"SOV Reasoning Request prepared: {output_file}")
print(f"\nPrompt for SOV:")
print("=" * 80)
print(sov_prompt)
print("=" * 80)
