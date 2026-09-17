# L2 Session Report: TURNOVER_REDUCTION_ADR_FIRST_ROW_FIX

- **Role**: 7 (Tech Lead)
- **Tier**: 2
- **Gate**: TURNOVER_REDUCTION_ADR_20260620
- **Date**: 2026-06-20
- **Status**: [SUBMIT_TO_TIER3]
- **Previous session**: l2_role7_turnover_reduction_adr_20260620 [NEEDS_FIX]

---

## Repo-Local Source Evidence (Gate: TURNOVER_REDUCTION_ADR_20260620)

> All role definitions and skill files were loaded exclusively from repo-local paths
> under `REPO_ROOT = C:\Users\GHC\repos\OMEGA_QUANT`. No external or forbidden
> paths were used as authoritative sources.

### 1. Role File Read (REPO_AGENT_ROOT)

| # | Repo-Relative Path | Frontmatter Fields |
|---|-------------------|-------------------|
| 1 | `.agents/agent/tech-lead.md` | `name: tech-lead`, `role_id: 7`, `tier: 2`, `platform: OpenCode`, `skills: [clean-code, code-review-checklist, plan-writing, testing-patterns, verify-changes, systematic-debugging]`, `sod_boundary: "implementation-only, test required, no self-approval, submit to Tier3"` |

### 2. Skill Files Read (REPO_SKILL_ROOT)

All 6 skills declared in the tech-lead frontmatter were read from repo-local `REPO_SKILL_ROOT`:

| # | Skill Name | Repo-Relative Path | Status |
|---|-----------|-------------------|--------|
| 1 | `clean-code` | `.agents/skills/clean-code/SKILL.md` | READ - authoritative |
| 2 | `code-review-checklist` | `.agents/skills/code-review-checklist/SKILL.md` | READ - authoritative |
| 3 | `plan-writing` | `.agents/skills/plan-writing/SKILL.md` | READ - authoritative |
| 4 | `testing-patterns` | `.agents/skills/testing-patterns/SKILL.md` | READ - authoritative |
| 5 | `verify-changes` | `.agents/skills/verify-changes/SKILL.md` | READ - authoritative |
| 6 | `systematic-debugging` | `.agents/skills/systematic-debugging/SKILL.md` | READ - authoritative |

### 3. Forbidden-Path Scan Result

The following paths were scanned and confirmed as **non-authoritative / not used as source** for this session:

| # | Forbidden Path | Exists on Disk | Used as Source | Verdict |
|---|---------------|---------------|----------------|---------|
| 1 | `Antigravity` (any variant) | N/A | **NOT USED** | Non-authoritative |
| 2 | `scratch` (any scratch workspace) | N/A | **NOT USED** | Non-authoritative |
| 3 | `OpenClaw` (any variant) | N/A | **NOT USED** | Non-authoritative |
| 4 | `C:\Users\GHC\.agents` (user-home agents, outside REPO_ROOT) | YES | **NOT USED** | Non-authoritative |
| 5 | `Codex memory` (any external memory store) | N/A | **NOT USED** | Non-authoritative |

**Statement:** Antigravity is non-authoritative and not used as source. Scratch is non-authoritative and not used as source. OpenClaw is non-authoritative and not used as source. `C:\Users\GHC\.agents` is non-authoritative and not used as source. Codex memory is non-authoritative and not used as source. No content from any of these paths was loaded, referenced, or used as an authoritative source for this implementation session. All role and skill definitions were sourced exclusively from repo-local paths under `REPO_ROOT\.agents`.

---

## Finding from Role 21 / Role 17

In `src/omega/quant/pipeline_v2.py`, `_apply_rebalance_controls`: when the first
output row (i=0) is a non-rebalance day (e.g. weekly Monday rebalance but run
starts Tuesday), the implementation ignored persisted `state['last_weights']`
and allowed trading immediately. The guard condition was:

```python
if not is_rebalance_day and i > 0:
```

This meant `i == 0` non-rebalance rows fell through to the throttle block,
which at best capped the delta but still permitted the first row to deviate
from persisted weights.

## Root Cause

The `i > 0` guard excluded the first row from the carry-forward logic. On a
non-rebalance first row, the raw signal weights (or throttle-capped weights)
were used instead of carrying forward `state['last_weights']`.

## Fix Applied

**File**: `src/omega/quant/pipeline_v2.py` (line ~490)

Changed the condition from:
```python
if not is_rebalance_day and i > 0:
    result.loc[dt] = result.iloc[i - 1]
    continue
```

To:
```python
if not is_rebalance_day:
    if i == 0:
        # First row, non-rebalance day: carry persisted
        # last_weights unchanged (no trading).
        # PIT-safe: uses only persisted prior-run weights.
        for col in result.columns:
            result.loc[dt, col] = float(prev_w_dict.get(col, 0.0))
    else:
        result.loc[dt] = result.iloc[i - 1]
    prev_w_dict = result.loc[dt].to_dict()
    continue
```

### PIT Safety Verification

The fix uses only:
1. Calendar info (day-of-week / day-of-month) -- PIT safe
2. Persisted `state['last_weights']` from prior run -- PIT safe
3. No future prices, signals, or returns are accessed

## Tests Added

**File**: `tests/test_pipeline_v2.py`

| Test Name | Scenario |
|-----------|----------|
| `test_weekly_first_row_non_rebalance_carries_last_weights` | Weekly Mon rebalance, run starts Tue. First row = persisted weights. throttle=0.02. |
| `test_monthly_first_row_non_rebalance_carries_last_weights` | Monthly day-1 rebalance, run starts day 2. First row = persisted weights. throttle=0.02. |
| `test_weekly_first_row_non_rebalance_throttle_zero` | Weekly Mon rebalance, run starts Tue. throttle=0.0. Proves frequency guard alone blocks trading. |
| `test_monthly_first_row_non_rebalance_throttle_zero` | Monthly day-1 rebalance, run starts day 2. throttle=0.0. Proves frequency guard alone blocks trading. |
| `test_weekly_first_row_non_rebalance_no_persisted_state` | No persisted state, run starts Tue. First row = 0.0 (no trading). |

## Test Results

```
New tests (5):               5/5 PASSED
Existing turnover tests (16): 16/16 PASSED
Full suite (52):              52/52 PASSED
```

## Files Modified

| File | Change |
|------|--------|
| `src/omega/quant/pipeline_v2.py` | Fixed `_apply_rebalance_controls` first-row non-rebalance guard |
| `tests/test_pipeline_v2.py` | Added 5 focused tests for first-row non-rebalance scenarios |

## Scope

- Implementation: DONE
- Testing: DONE (52/52 pass)
- Audit/Approval: NOT DONE (submit to Tier 3)
