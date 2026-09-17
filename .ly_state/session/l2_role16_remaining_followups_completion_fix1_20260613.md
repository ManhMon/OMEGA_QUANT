# L2 Report: Role 16 (Machine Learning Engineer) - Remaining Follow-ups Completion FIX1

**Date:** 2026-06-13
**Gate:** REMAINING_FOLLOWUPS_COMPLETION_FIX1_20260613
**Parent Gate:** REMAINING_FOLLOWUPS_COMPLETION_20260613
**L3 Verdict on Parent:** [NEEDS_FIX]
**Role:** 16 (machine-learning-engineer), Tier 2, OpenCode
**Session:** l2_role16_remaining_followups_completion_fix1_20260613

---

## Repo-Local Skill Source Contract

### Role file (authoritative)
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent\machine-learning-engineer.md`
- Frontmatter: role_id=16, tier=2, platform=OpenCode, sod_boundary="implementation-only, test required, no self-approval, submit to Tier3"
- Declared skills: python-patterns, clean-code, testing-patterns, performance-profiling, systematic-debugging, ml-dl-rl, backtesting-pit-safety, vietnam-market-data

### Skill files (all authoritative, from REPO_SKILL_ROOT)
| # | Skill | Path | Lines |
|---|-------|------|-------|
| 1 | backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` | 322 |
| 2 | python-patterns | `.agents/skills/python-patterns/SKILL.md` | 442 |

### Forbidden path scan result
- **CLEAN**: No reads from `C:\Users\GHC\.agents`, `C:\Users\GHC\.codex`, Antigravity scratch, or OpenClaw memory paths
- All authoritative files read exclusively from REPO_AGENT_ROOT and REPO_SKILL_ROOT
- No skill loaded from non-authoritative sources

---

## Findings Addressed (from L3 Audit Report)

### BLOCKER 1: Default quick mode fails on Windows (FIXED)
- **Root cause:** `compute_safe_workers()` returned 9 on this Windows machine (12 CPUs * 0.75 = 9). joblib `Parallel(prefer='threads', n_jobs=9)` triggers `[WinError 5] Access is denied` on Windows.
- **Fix:** On Windows, force `n_jobs=1` for both default and explicit `--workers` paths. Log message: `"Windows detected: forcing n_jobs=1 (joblib WinError 5 mitigation)"`

### BLOCKER 2: ZeroDivisionError on empty results (FIXED)
- **Root cause:** Line 278 `100*evo_wins/len(results)` when `results == []` after all seeds/years fail.
- **Fix:** Guard `if not results:` before summary table. Print clear error message distinguishing infrastructure failure from strategy failure. Return exit code 1 (controlled nonzero exit).

### HIGH: Explicit `--workers` uncapped (FIXED)
- **Root cause:** `n_jobs = max(1, args.workers)` accepted arbitrarily large values, bypassing `compute_safe_workers()`.
- **Fix:** Cap explicit `--workers` to `min(requested, compute_safe_workers(), 16)`. On Windows, further degrade to 1 with WARNING log. Updated `--help` text documents capping behavior.

---

## Changes Made

**File: `scripts/backtest_evolution_multiseed.py`**

### Change 1: Worker resolution block (lines 145-180)
Replaced old worker resolution (lines 141-149) with Windows-safe, capped logic:

```python
# --- Worker resolution (Windows-safe, capped) ---
import platform
_IS_WINDOWS = platform.system() == "Windows"
_WORKER_HARD_CAP = 16

if args.workers is not None:
    # Explicit --workers: sanitize and cap
    n_jobs = max(1, args.workers)
    _ceiling = compute_safe_workers()  # or _WORKER_HARD_CAP on ImportError
    n_jobs = min(n_jobs, _ceiling, _WORKER_HARD_CAP)
    if _IS_WINDOWS and n_jobs > 1:
        logger.warning("Degrading --workers %d -> 1.", n_jobs)
        n_jobs = 1
else:
    if _IS_WINDOWS:
        n_jobs = 1  # force serial on Windows
    else:
        n_jobs = compute_safe_workers()  # or 1 on ImportError
```

Key behaviors:
- **Default on Windows:** `n_jobs=1` (INFO log)
- **Default on Linux/macOS:** `compute_safe_workers()` (as before)
- **Explicit `--workers N` on Windows:** capped, then degraded to 1 with WARNING
- **Explicit `--workers N` on Linux/macOS:** capped to `min(N, compute_safe_workers(), 16)`
- **ImportError fallback:** 1 (not -1 as before)

### Change 2: Zero results guard (lines 296-303)
Added guard before summary table:
```python
if not results:
    print("ERROR: No yearly results produced. All seeds/years failed.")
    print("This typically indicates a data or infrastructure issue, not a strategy failure.")
    return 1
```

### Change 3: `--workers` help text (lines 121-125)
Updated to document capping:
```
"Capped to compute_safe_workers() ceiling and hard cap 16.
 On Windows, forced to 1 (joblib WinError 5 mitigation)."
```

### Change 4: Safe division in summary (line 317-318)
Replaced `len(results)` with local `n_years` variable for clarity.

---

## PIT Safety Preservation

- **No changes to data loading** (`load_and_prepare_data()` unchanged)
- **No changes to feature computation** (T-1 shift on all FEATURE_COLS preserved)
- **No changes to forward returns** (`fwd_ret_5 = shift(-5)` unchanged)
- **No changes to chronological splits** (yearly train/test split preserved)
- **No changes to cross-sectional ranking** (per-date rank preserved)
- Workers fix only affects joblib parallelism, not data correctness

---

## Test Results

| # | Command | Result | Key Evidence |
|---|---------|--------|--------------|
| 1 | `python scripts/run_backtest.py evolution-multiseed --quick` | **PASS** | n_jobs=1 forced, 10/10 years, win rate 5/10 |
| 2 | `python scripts/run_backtest.py evolution-multiseed --quick --workers 1` | **PASS** | n_jobs=1, 10/10 years, win rate 5/10 |
| 3 | `python scripts/run_backtest.py evolution-multiseed --quick --workers 2` | **PASS** | WARNING logged "Degrading --workers 2 -> 1", then succeeds |
| 4 | `python -m pytest tests/test_feature_adapter_nonnumeric.py -q` | **9 passed** | No regressions |
| 5 | `python -m pytest tests/test_dashboard_data_control_integration.py -q` | **106 passed** | No regressions |
| 6 | `python scripts/run_backtest.py full-pipeline` | **PASS** | Sharpe=1.6795, MaxDD=-4.55%, 0.602s |
| 7 | `python scripts/sod_gate_enforcer.py informational` | **Informational** | Shows parent gate as [NEEDS_FIX] (expected pre-fix) |

### Critical verification: `--quick` default
- Log output: `INFO:multiseed_backtest:Windows detected: forcing n_jobs=1 (joblib WinError 5 mitigation)`
- Log output: `INFO:multiseed_backtest:GP n_jobs=1`
- All 10 years (2017-2026) completed successfully
- No WinError 5, no ZeroDivisionError

### Critical verification: `--workers 2` degradation
- Log output: `WARNING:multiseed_backtest:Windows detected: joblib parallel evaluation is unreliable (WinError 5). Degrading --workers 2 -> 1.`
- Then proceeds to complete successfully with `GP n_jobs=1`

---

## SOD Compliance

- **Writer:** Role 16 (machine-learning-engineer), Tier 2, OpenCode
- **Auditor:** Role 23 (performance-tester), Tier 3, Codex (expected)
- **Writer != Auditor:** 16 != 23
- **No self-approval:** This report does NOT approve anything for production
- **Gate contract:** Submitted to Tier 3 for independent re-audit

---

## Artifacts

| Artifact | Path |
|----------|------|
| L2 Report (this) | `.ly_state/session/l2_role16_remaining_followups_completion_fix1_20260613.md` |
| Parent L2 Report | `.ly_state/session/l2_role16_remaining_followups_completion_20260613.md` |
| L3 Audit Report | `.ly_state/session/audit_reports/role23_remaining_followups_completion_20260613.md` |
| Modified script | `scripts/backtest_evolution_multiseed.py` |
| Multiseed Quick Results | `data/backtest/multiseed_backtest_results.json` |

---

*This is an L2 implementation report. No audit or approval is claimed. Work submitted to Tier 3 (Role 23, Performance Tester) for independent re-verification.*
