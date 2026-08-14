# L2 Report: gp_diverse_evolution_oom_fix_plan_review

Date: 2026-07-15
Role: 16 machine-learning-engineer
Scope: src/omega/quant/evolution/diverse_alpha_evolution.py
Gate: gp_diverse_evolution_oom_fix_plan_review

## Summary

Proposed optimization plan to fix OOM during large population (4000) GP Alpha Evolution on WSL.

## Proposed Changes

1. **float32 conversion**: Downcast core numeric feature arrays in `_build_standard_features()` from float64 to float32 to reduce memory footprint by 50%.
2. **Payload & Signature Invariants**: Redesign worker signatures to remove all DataFrame and features arguments: `def _evaluate_genome_job(genome, genome_idx, fold_idx)`. Added assertions in worker to verify arg payload size is under 10 KB. Set `pre_dispatch="2*n_jobs"` to bound parallel queue overhead.
3. **Memory Sharing**: Use memory-mapped NumPy arrays (`np.memmap`) loaded into global read-only variables `GLOBAL_TRAIN_FEATURES` and `GLOBAL_VAL_FEATURES` by worker initializers. For nested caches, flat indices are mapped to shared memmap, and neutralization cache is capped under 100 MB per worker.
4. **Graceful Headroom Guard**:
   - Order cgroup v2 and v1 limit minus usage discovery with fallback to `/proc/meminfo`.
   - Calculate workers dynamically using realistic formula: `n_jobs = min(n_workers_config, floor((M_avail - 1.5GB) / M_worker_est), floor((12.0GB - M_parent) / M_worker_est))` where `M_worker_est = 1.0 GB` (the expected post-optimized worker memory). This allows 8 workers to run when system resource is sufficient, while child process ceiling limit is monitored independently at **3.5 GB**.
   - Implement a background daemon thread checking system memory, process-tree RSS, and child RSS every 0.5s. Set soft limits: total RSS < 11.0 GB, child RSS < 3.2 GB, headroom < max(1.5, 0.3 * n_jobs) GB. Trigger graceful shutdown by sending `SIGINT` to main process to let Parallel context manager safely reap workers and clean memmaps before exiting.

## Memory & Parity Acceptance Criteria

- **Measurement**: Use a Python-based monitor (`scripts/monitor_memory.py`) sampling RSS, PSS, and USS at a **1-second interval**.
- **Peak RSS**: Total Peak RSS (parent and children) must be under **12 GB** total when running with 8 workers; Peak RSS of each child process must be under **3.5 GB**. RSS, PSS, and USS reported separately as supplementary diagnostics.
- **Runs**: Require **3 consecutive successful 8-worker runs** with population 4000 without OOM or crash.
- **Parity**: IC discrepancy between float32 and float64 must be under **1e-6**.

## Repo-Local Files Read

- .agents/AGENTS.md
- .agents/agent/machine-learning-engineer.md
- .agents/skills/python-patterns/SKILL.md
- .agents/skills/clean-code/SKILL.md
- .agents/skills/testing-patterns/SKILL.md
- .agents/skills/performance-profiling/SKILL.md
- .agents/skills/systematic-debugging/SKILL.md
- .agents/skills/ml-dl-rl/SKILL.md
- .agents/skills/backtesting-pit-safety/SKILL.md
- .agents/skills/vietnam-market-data/SKILL.md
- src/omega/quant/evolution/diverse_alpha_evolution.py

## Forbidden Path Scan

PASS: No forbidden path (.gemini\\antigravity-ide\\scratch\\ag-kit, .openclaw\\skills, C:\\Users\\GHC\\.agents, .codex\\memories) was read or relied upon authoritatively.