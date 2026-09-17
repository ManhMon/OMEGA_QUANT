# L2 Implementation Report — Role 14 (Data Scientist)

## Gate: FORMULAIC_WINNER_SELECTION_GUARD_FIX1_20260614
## Parent Gate: FORMULAIC_WINNER_SELECTION_GUARD_20260614
## Date: 2026-06-14
## Status: [NEEDS_FIX] → [FIX_APPLIED]

---

## Forbidden-Path Wording (Enforcer-Compliant)

> **No authoritative reliance.**
> `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source.
> `.openclaw\skills` is non-authoritative and not used as source.
> `C:\Users\GHC\.agents` is non-authoritative and not used as source.
> `.codex\memories` is non-authoritative and not used as source.

---

## Skill Source Contract

- REPO_AGENT_ROOT = `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`
- REPO_SKILL_ROOT = `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`
- Agent definition read: `REPO_AGENT_ROOT\data-scientist.md`
- Skills declared: python-patterns, clean-code, testing-patterns, systematic-debugging, performance-profiling, quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow

---

## Blockers Resolved

### Blocker 1: L2 report forbidden-path wording not enforcer-compliant

**Resolution:** This report includes the exact enforcer-compliant forbidden-path wording above.

### Blocker 2: Winner guard fallback re-admits non-allowlist legacy alphas when all candidates excluded

**Root cause:** Two methods in `src/omega/quant/alpha/phase35.py` had fallback logic that restored original (non-allowlist) legacy candidates when all candidates were excluded by the guard:

1. `apply_formulaic_winner_guard()` (lines ~1193-1203): When `filtered` was empty and `candidate_alphas` was non-empty, the code set `filtered = list(candidate_alphas)`, re-admitting all non-allowlist legacy alphas into `post_guard_alphas`.

2. `filter_fallback_by_winner_guard()` (lines ~1258-1264): When `filtered` was empty and `fallback_alphas` was non-empty, the code returned `(list(fallback_alphas), [])`, re-admitting all non-allowlist legacy alphas into the fallback pool.

**Evidence:** CPCV12 folds 2/7 showed legacy `post_guard_alphas` appearing in guard-enabled output, violating the contract that guard-enabled pools contain only allowlist members.

---

## Changes Applied

### File: `src/omega/quant/alpha/phase35.py`

#### Fix 1: `apply_formulaic_winner_guard()` — Allowlist-only fallback

**Before (buggy):**
```python
if not filtered and candidate_alphas:
    filtered = list(candidate_alphas)  # BUG: re-admits legacy
    fallback_used = True
```

**After (fixed):**
```python
if not filtered and candidate_alphas:
    # Build allowlist-only fallback ranked by val_ic
    allowlist_with_ic = []
    for al in self.formulaic_winner_allowlist:
        ic_val = val_ics.get(al, None)
        if ic_val is not None and ic_val >= self.formulaic_winner_min_val_ic:
            allowlist_with_ic.append((al, ic_val))
    allowlist_with_ic.sort(key=lambda x: abs(x[1]), reverse=True)
    allowlist_fallback = [al for al, _ in allowlist_with_ic]

    if allowlist_fallback:
        filtered = allowlist_fallback
        fallback_used = True
    else:
        filtered = []
        no_guard_candidates = True
        fallback_used = False
```

**Semantics:**
- Guard-enabled `post_guard_alphas` NEVER contains non-allowlist legacy alphas.
- If all candidates excluded, uses allowlist-only fallback ranked by current-fold validation IC.
- If no allowlist members have qualifying val_ic, returns empty list and marks `no_guard_candidates = True`.
- Evidence dict now includes `no_guard_candidates` key.

#### Fix 2: `filter_fallback_by_winner_guard()` — Empty fallback (no legacy re-admission)

**Before (buggy):**
```python
if not filtered and fallback_alphas:
    return list(fallback_alphas), []  # BUG: re-admits legacy
```

**After (fixed):**
```python
if not filtered and fallback_alphas:
    return [], list(fallback_alphas)  # Empty filtered, all in excluded
```

**Semantics:**
- Fallback pool NEVER contains non-allowlist legacy alphas.
- If all fallback alphas excluded, returns empty filtered list.
- Caller (`run_fold`) assigns `gated_alphas = _fb_filtered` (empty), which downstream pipeline handles gracefully.

#### Fix 3: `run_fold()` — Evidence capture for fallback filter

Updated the post-gate fallback filter block to record `fallback_no_guard_candidates = True` in evidence when all gated_alphas are excluded by the fallback filter.

### File: `tests/phase35/test_formulaic_winner_selection_guard.py`

#### Updated Tests (fixing assertions for old buggy behavior):

1. **`test_graceful_fallback_when_all_excluded`** — Now asserts:
   - No non-allowlist alpha in filtered result
   - Legacy candidates NOT restored

2. **`test_fallback_filter_graceful_when_all_excluded`** — Now asserts:
   - `filtered == []` (empty, not originals)
   - `set(excluded) == set(fallback)` (all legacy excluded)

#### New Contract Tests (Section 10: FIX1 Contract):

| Test | Contract |
|------|----------|
| `test_post_guard_pool_only_allowlist` | Every alpha in post_guard_alphas is on allowlist |
| `test_all_excluded_allowlist_only_fallback_ranked_by_ic` | Allowlist fallback ranked by abs(val_ic) desc |
| `test_all_excluded_no_allowlist_ic_empty_result` | Empty list + no_guard_candidates=True |
| `test_fallback_filter_never_returns_non_allowlist` | Fallback pool only has allowlist members |
| `test_fallback_filter_all_excluded_returns_empty` | Empty filtered when all excluded |
| `test_evidence_has_no_guard_candidates_key` | Evidence includes no_guard_candidates |
| `test_guard_off_no_guard_candidates_false` | no_guard_candidates=False when guard off |
| `test_min_val_ic_filter_on_allowlist_fallback` | min_val_ic threshold respected in fallback |
| `test_contract_no_legacy_in_any_guard_enabled_pool` | Comprehensive multi-scenario contract |

---

## Test Results

```
61 passed, 3 warnings in 6.57s
```

All 61 tests pass (52 existing + 9 new FIX1 contract tests).

---

## Files Read (Exact List)

1. `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent\data-scientist.md`
2. `C:\Users\GHC\repos\OMEGA_QUANT\src\omega\quant\alpha\phase35.py`
3. `C:\Users\GHC\repos\OMEGA_QUANT\tests\phase35\test_formulaic_winner_selection_guard.py`

## Files Modified (Exact List)

1. `C:\Users\GHC\repos\OMEGA_QUANT\src\omega\quant\alpha\phase35.py` — 4 edits (fallback fix in 2 methods, evidence init, run_fold evidence capture, docstrings)
2. `C:\Users\GHC\repos\OMEGA_QUANT\tests\phase35\test_formulaic_winner_selection_guard.py` — 3 edits (2 test fixes, 9 new contract tests)

## Files Created (Exact List)

1. `C:\Users\GHC\repos\OMEGA_QUANT\.ly_state\session\l2_role14_formulaic_winner_selection_guard_fix1_20260614.md` (this report)

---

## Scope Compliance

- Implementation-only role (no self-approval, no audit).
- All changes confined to declared scope: `src/omega/quant/alpha/phase35.py`, `tests/phase35/test_formulaic_winner_selection_guard.py`.
- PIT safety preserved: all guard logic uses only current-fold validation IC.
- No live/default behavior change when `formulaic_winner_guard=False`.
- Submit to Tier 3 (Code Reviewer role 21, QA Engineer role 17) for audit.

---

## CPCV12 Evidence

Output-tag: `cpcv12_v3_winner_guard_fix1`

CPCV12 regeneration requires full backtest pipeline execution with real market data and is not feasible within this L2 targeted-fix scope. The guard contract is now enforced by 9 new automated tests that cover all exclusion/fallback paths, including the specific fold 2/7 scenario where legacy alphas were previously re-admitted.
