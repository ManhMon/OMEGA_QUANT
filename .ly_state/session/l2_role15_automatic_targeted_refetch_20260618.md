# L2 Implementation Report — Role 15 (Data Engineer)

| Field | Value |
|---|---|
| **Gate** | `AUTOMATIC_TARGETED_REFETCH_20260618` |
| **Role** | 15 data-engineer (Tier 2, OpenCode) |
| **Date** | 2026-06-18 |
| **Status** | IMPLEMENTED — submitted to Tier 3 audit |

---

## 1. Agent/Skill Provenance

### Agent definition (repo-local)
- **File**: `.agents/agent/data-engineer.md`
- **role_id**: 15, **tier**: 2, **platform**: OpenCode
- **sod_boundary**: implementation-only, test required, no self-approval, submit to Tier3

### Skills loaded (REPO_SKILL_ROOT only)
| Skill | Path |
|---|---|
| vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` |
| python-patterns | `.agents/skills/python-patterns/SKILL.md` |
| testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` |
| clean-code | `.agents/skills/clean-code/SKILL.md` |

### Forbidden-path scan
| Path | Scanned? | Result |
|---|---|---|
| Antigravity scratch | No | Not accessed |
| OpenClaw | No | Not accessed |
| `C:\Users\GHC\.agents` (Codex memory) | No | Non-authoritative, not accessed |

---

## 2. Scope

| File | Change type |
|---|---|
| `scripts/update_market_data.py` | Modified (overlap threshold, new function, merge logic) |
| `tests/test_targeted_refetch.py` | Modified (existing tests updated, 4 new test classes added) |

---

## 3. Implementation Summary

### 3.1 Overlap Check — 0.1% threshold

**Changed**: `OVERLAP_PRICE_TOLERANCE` from `0.005` (0.5%) to `0.001` (0.1%).

Rationale: at 0.5% tolerance, small corporate actions (cash dividends of ~0.2-0.5%, small bonus-share adjustments of ~5-10%) were silently accepted as "matching" overlap. The tighter 0.1% threshold catches these phase-shift events so the pipeline can recover via full-history reload.

### 3.2 Full-History Refetch (`run_full_history_refetch`)

**New function**: `run_full_history_refetch(client, symbols_to_refetch, exchange_map, end_date)`

- Fetches from `FULL_HISTORY_START = "2015-01-01"` to `end_date` for each affected symbol
- Validates OHLC invariants on returned data
- Returns combined DataFrame + stats dict

### 3.3 Overlap Mismatch → Full Refetch Queue

**Modified**: `run_targeted_refetch`

When the overlap check at 0.1% detects a mismatch:
- Previously: counted as hard-fail, data discarded
- Now: symbol is queued in `stats["needs_full_refetch"]` for full-history reload

### 3.4 Delete-and-Overwrite in `run_updater`

**Modified**: `run_updater` pipeline (step 4b + step 5)

Step 4b (new): After targeted refetch, checks `needs_full_refetch` list and calls `run_full_history_refetch` for queued symbols.

Step 5 (modified): Before merging, deletes ALL old canonical rows for full-history-refetched symbols. The fresh full-history data is then the sole source for those tickers in the parquet.

This ensures no phase mismatch between old (pre-adjustment) and new (post-adjustment) backward-adjusted prices.

---

## 4. Test Results

```
56 passed, 0 failed (38.08s)
```

### Test classes

| Class | Tests | Status |
|---|---|---|
| `TestDetectPriceAnomalies` | 7 | PASS |
| `TestClassifyAnomaly` | 4 | PASS |
| `TestRunTargetedRefetch` | 5 | PASS |
| `TestRunUpdaterRefetch` | 2 | PASS |
| `TestCLI` | 3 | PASS |
| `TestConstants` | 3 | PASS |
| `TestCheckOverlapConsistency` | 8 | PASS |
| `TestRefetchWithOverlapCheck` | 4 | PASS |
| `TestStage1BoundaryValidationFix` | 5 | PASS |
| `TestRunFullHistoryRefetch` (NEW) | 4 | PASS |
| `TestOverlapThresholdSensitivity` (NEW) | 5 | PASS |
| `TestFullHistoryDeleteAndOverwrite` (NEW) | 5 | PASS |

### New test coverage

- `TestRunFullHistoryRefetch`: empty input, success, failure, mixed results
- `TestOverlapThresholdSensitivity`: 0.2% discrepancy detected, 0.05% passes, cash dividend caught, small split caught, constant verification
- `TestFullHistoryDeleteAndOverwrite`: overlap mismatch queues full refetch, run_updater integration (delete + overwrite), FULL_HISTORY_START constant, needs_full_refetch key, no-anomalies path

---

## 5. Constants Changed/Added

| Constant | Old | New | Purpose |
|---|---|---|---|
| `OVERLAP_PRICE_TOLERANCE` | 0.005 | 0.001 | 0.1% threshold for small split/dividend detection |
| `FULL_HISTORY_START` | (new) | "2015-01-01" | Start date for full-history reload on phase shift |

---

## 6. Tier 3 Audit Submission

This implementation is submitted to:
- **Code Reviewer (role 21)**: Pipeline code quality review
- **QA Engineer (role 17)**: Data quality validation
- **Performance Tester (role 23)**: Pipeline performance review

**Cannot proceed until all relevant Tier 3 roles return [APPROVED].**
