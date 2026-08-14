# L2 Plan Report: Data Layer & Alpha Layer 3 Blockers Remediation Plan
**Role**: machine-learning-engineer (Role 16)
**Date**: 2026-07-20
**Scope**: implementation_plan.md, src/omega/data/, src/omega/quant/alpha/

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

## Plan Summary
1. PIT-CA-01: Add `available_at` and `announced_at` to `CorporateAction` dataclass. Enforce UTC timezone, `available_at >= announced_at` invariant, fail-closed quarantine with observable warning for missing provenance, and strict `available_at <= as_of_time` filter in `loader.py`.
2. SEC-EXPR-01: Single deterministic rejection flow via `UnsafeExpressionError` -> `CandidateStatus.REJECTED_UNSAFE_EXPRESSION`. Exhaustive expression-only AST allowlist (Expression, BinOp, UnaryOp, Call, Name, Constant, Num, Load, Compare, IfExp, Eq, NotEq, Lt, LtE, Gt, GtE, And, Or, Not, BoolOp, Add, Sub, Mult, Div, USub, UAdd). Exact arity (1-arg: abs, neg, rank, sign, log; 2-arg: add, sub, mul, div, ts_mean, ts_std, ts_min, ts_max, ts_delta, ts_delay; 3-arg: where, correlation). Resource limits (depth <= 10, nodes <= 50, literal bound <= 1e6).
3. SEC-GEN-02: Sanitize symbols with `str.isidentifier() and not keyword.iskeyword() and not dunder`. Pure fixed mapped operations, no eval/exec, no top-level module executable statements.
