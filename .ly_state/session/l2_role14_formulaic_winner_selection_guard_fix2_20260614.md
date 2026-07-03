# L2 Implementation Report — Role 14 (Data Scientist)

## Gate: FORMULAIC_WINNER_SELECTION_GUARD_FIX2_20260614
## Parent Gate: FORMULAIC_WINNER_SELECTION_GUARD_FIX1_20260614
## Date: 2026-06-14
## Status: [NEEDS_FIX] → [FIX_APPLIED]
## Fix Type: Report-only (no source/tests/data edits)

---

## Forbidden-Path Wording (Enforcer-Compliant)

> **No authoritative reliance.**
> `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source.
> `.openclaw\skills` is non-authoritative and not used as source.
> `C:\Users\GHC\.agents` is non-authoritative and not used as source.
> `.codex\memories` is non-authoritative and not used as source.

---

## L3 Blocker Resolved

### Blocker: L2 report lacks exact `.agents/skills/<skill>/SKILL.md` paths

**L3 audit reference:** `.ly_state/session/audit_reports/role20_formulaic_winner_selection_guard_fix1_20260614.md`

**Finding:** `scripts.sod_gate_enforcer.check_l2_report_skill_sources('l2_role14_formulaic_winner_selection_guard_fix1_20260614', 14, 'data-scientist')` returned:

```text
(False, "L2 report 'l2_role14_formulaic_winner_selection_guard_fix1_20260614.md' skill source validation failed: no exact .agents/skills/<skill>/SKILL.md path found in report")
```

**Root cause:** The fix1 report listed `REPO_AGENT_ROOT`, `REPO_SKILL_ROOT`, the role file, and declared skill names, but did not enumerate exact repo-local skill file paths in `.agents/skills/<skill>/SKILL.md` form.

**Resolution:** This fix2 report explicitly lists every exact repo-local file read, including all 9 skill SKILL.md paths and the role agent definition, in the "Files Read (Exact Repo-Local Paths)" section below.

---

## Skill Source Contract

- REPO_AGENT_ROOT = `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`
- REPO_SKILL_ROOT = `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`
- Agent definition read: `REPO_AGENT_ROOT\data-scientist.md`
- Skills declared in `data-scientist.md`: python-patterns, clean-code, testing-patterns, systematic-debugging, performance-profiling, quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow
- All 9 skill SKILL.md files verified present on disk under `REPO_SKILL_ROOT`

---

## Files Read (Exact Repo-Local Paths)

### Agent Definition

1. `.agents/agent/data-scientist.md`

### Skill Definitions (all declared in data-scientist.md)

2. `.agents/skills/python-patterns/SKILL.md`
3. `.agents/skills/clean-code/SKILL.md`
4. `.agents/skills/testing-patterns/SKILL.md`
5. `.agents/skills/systematic-debugging/SKILL.md`
6. `.agents/skills/performance-profiling/SKILL.md`
7. `.agents/skills/quant-research/SKILL.md`
8. `.agents/skills/vietnam-market-data/SKILL.md`
9. `.agents/skills/backtesting-pit-safety/SKILL.md`
10. `.agents/skills/data-science-workflow/SKILL.md`

### Source and Test Files (from fix1 implementation)

11. `src/omega/quant/alpha/phase35.py`
12. `tests/phase35/test_formulaic_winner_selection_guard.py`

### Prior Reports and Audit Evidence

13. `.ly_state/session/l2_role14_formulaic_winner_selection_guard_fix1_20260614.md`
14. `.ly_state/session/audit_reports/role20_formulaic_winner_selection_guard_fix1_20260614.md`
15. `.ly_state/session/audit_reports/role20_formulaic_winner_selection_guard_20260614.md`

---

## Files Modified (Exact List)

None. This is a report-only fix. No source, test, or data files were edited.

---

## Files Created (Exact List)

1. `.ly_state/session/l2_role14_formulaic_winner_selection_guard_fix2_20260614.md` (this report)

---

## Preserved Fix1 Implementation Evidence

All implementation changes from fix1 remain in place and are unchanged. The following is a verbatim preservation of the fix1 implementation record.

### Blocker 1 (from fix1): Forbidden-path wording — Already resolved in fix1, preserved here.

### Blocker 2 (from fix1): Winner guard fallback re-admits non-allowlist legacy alphas — Already resolved in fix1, preserved here.

**Root cause:** Two methods in `src/omega/quant/alpha/phase35.py` had fallback logic that restored original (non-allowlist) legacy candidates when all candidates were excluded by the guard:

1. `apply_formulaic_winner_guard()` (lines ~1193-1203): When `filtered` was empty and `candidate_alphas` was non-empty, the code set `filtered = list(candidate_alphas)`, re-admitting all non-allowlist legacy alphas into `post_guard_alphas`.

2. `filter_fallback_by_winner_guard()` (lines ~1258-1264): When `filtered` was empty and `fallback_alphas` was non-empty, the code returned `(list(fallback_alphas), [])`, re-admitting all non-allowlist legacy alphas into the fallback pool.

**Evidence:** CPCV12 folds 2/7 showed legacy `post_guard_alphas` appearing in guard-enabled output, violating the contract that guard-enabled pools contain only allowlist members.

---

### Fix1 Change 1: `apply_formulaic_winner_guard()` — Allowlist-only fallback

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

### Fix1 Change 2: `filter_fallback_by_winner_guard()` — Empty fallback (no legacy re-admission)

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

### Fix1 Change 3: `run_fold()` — Evidence capture for fallback filter

Updated the post-gate fallback filter block to record `fallback_no_guard_candidates = True` in evidence when all gated_alphas are excluded by the fallback filter.

### Fix1 Test Updates

**Updated Tests (fixing assertions for old buggy behavior):**

1. **`test_graceful_fallback_when_all_excluded`** — Now asserts:
   - No non-allowlist alpha in filtered result
   - Legacy candidates NOT restored

2. **`test_fallback_filter_graceful_when_all_excluded`** — Now asserts:
   - `filtered == []` (empty, not originals)
   - `set(excluded) == set(fallback)` (all legacy excluded)

**New Contract Tests (Section 10: FIX1 Contract):**

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

### Fix1 Test Results (Preserved)

```
61 passed, 3 warnings in 6.57s
```

All 61 tests pass (52 existing + 9 new FIX1 contract tests).

---

## CPCV12 Evidence (Preserved from Fix1)

Output-tag: `cpcv12_v3_winner_guard_fix1`

CPCV12 regeneration requires full backtest pipeline execution with real market data and is not feasible within this L2 targeted-fix scope. The guard contract is enforced by 9 new automated tests that cover all exclusion/fallback paths, including the specific fold 2/7 scenario where legacy alphas were previously re-admitted.

---

## Scope Compliance

- Implementation-only role (no self-approval, no audit).
- This fix2 is report-only: no source, test, or data files were edited.
- All fix1 implementation changes remain in place and unchanged in `src/omega/quant/alpha/phase35.py` and `tests/phase35/test_formulaic_winner_selection_guard.py`.
- PIT safety preserved: all guard logic uses only current-fold validation IC.
- No live/default behavior change when `formulaic_winner_guard=False`.
- Submit to Tier 3 (Code Reviewer role 21, QA Engineer role 17) for re-audit.

---

## Summary of Fix2 Delta vs Fix1

| Aspect | Fix1 | Fix2 |
|--------|------|------|
| Forbidden-path wording | Present | Present (preserved) |
| Code changes (phase35.py) | Applied | Unchanged (preserved) |
| Test changes | Applied | Unchanged (preserved) |
| Test results | 61 passed | 61 passed (preserved) |
| Exact `.agents/agent/data-scientist.md` path | Listed | Listed (preserved) |
| Exact `.agents/skills/<skill>/SKILL.md` paths (x9) | **Missing (L3 blocker)** | **Listed explicitly** |
| Source/test/data edits | Yes | No (report-only) |
