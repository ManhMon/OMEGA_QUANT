# L2 Plan Report: Hybrid Alpha Real Market Integration Plan
**Role**: machine-learning-engineer (Role 16)
**Date**: 2026-07-20
**Scope**: implementation_plan.md

## Repo-Local Files Read
- .agents/agent/machine-learning-engineer.md
- .agents/AGENTS.md
- .agents/skills/python-patterns/SKILL.md
- .agents/skills/clean-code/SKILL.md
- .agents/skills/testing-patterns/SKILL.md
- .agents/skills/performance-profiling/SKILL.md
- .agents/skills/systematic-debugging/SKILL.md
- .agents/skills/ml-dl-rl/SKILL.md
- .agents/skills/backtesting-pit-safety/SKILL.md
- .agents/skills/vietnam-market-data/SKILL.md

## Forbidden Path Scan Result
No authoritative reliance on forbidden paths (.gemini/antigravity-ide/scratch/ag-kit, .openclaw/skills, C:\Users\GHC\.agents, .codex/memories). All references are non-authoritative.

## Plan Description
Tích hợp LLM Hybrid Alpha Miner vào bộ dữ liệu thị trường Việt Nam thực tế (`data/market_2015_now.parquet`) với nhãn Forward Returns T+5 thực tế, walk-forward 3 tầng (Train/Validate/Test), và ngưỡng thăng cấp chuẩn quant (IC >= 0.01, signal_pnl_score >= 0.08, DSR >= 0.5).
