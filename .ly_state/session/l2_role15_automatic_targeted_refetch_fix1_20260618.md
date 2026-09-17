# L2 Implementation Report — Stage 1 Boundary Validation Fix

| Field | Value |
|---|---|
| **Session** | `l2_role15_automatic_targeted_refetch_fix1_20260618` |
| **Role** | 15 — Data Engineer (Tier 2) |
| **Gate** | `AUTOMATIC_TARGETED_REFETCH_20260618` |
| **Date** | 2026-06-18 |
| **Status** | IMPLEMENTED — Submitted for Tier 3 Audit |
| **Trigger** | L3 Audit `[NEEDS_FIX]` — Stage 1 boundary validation in `run_targeted_refetch()` |

---

## 1. AG Kit Compliance

### Files Read (repo-local)
| File | Purpose |
|---|---|
| `.agents/agent/data-engineer.md` | Role 15 frontmatter: `role_id: 15`, `tier: 2`, `sod_boundary: implementation-only` |
| `.agents/skills/systematic-debugging/SKILL.md` | 4-phase debugging methodology |
| `.agents/skills/testing-patterns/SKILL.md` | AAA pattern, mocking strategies |
| `.agents/skills/python-patterns/SKILL.md` | Python implementation principles |

### Forbidden Path Scan
- No access outside `REPO_ROOT` (`C:\Users\GHC\repos\OMEGA_QUANT`)
- All paths are repo-relative
- **Result: PASS** — No forbidden paths accessed

---

## 2. Bug Root Cause Analysis (4-Phase Debugging)

### Phase 1: Reproduce
In `run_targeted_refetch()` (line 754), Stage 1 boundary validation used:
```python
ref_first_close = float(df.sort_values("date").iloc[0]["close"])
```
This takes the close price at `iloc[0]` — the **earliest date in the 90-day lookback window** (e.g., `end_date - 90 days`), NOT the canonical boundary date.

### Phase 2: Isolate
The bug is in `scripts/update_market_data.py`, function `run_targeted_refetch()`, Stage 1 block (lines 753–756).

### Phase 3: Root Cause (5 Whys)
1. **Why** wrong comparison? → Uses `iloc[0]` of re-fetched data (earliest lookback date)
2. **Why** is this wrong? → The boundary should be at `canonical_max_date + 1`, not the lookback start
3. **Why** does it matter? → A symbol could have normal prices at the boundary but very different prices 90 days ago (or vice versa)
4. **What's the impact?** → Two failure modes:
   - **False rejection**: Price 90 days ago differs from canonical → flagged "still_anomalous" even though boundary is fine
   - **False acceptance**: Price 90 days ago matches canonical → accepted even though boundary is anomalous
5. **Root cause**: Stage 1 validation doesn't locate the correct boundary date

### Phase 4: Fix & Verify
- Fix implemented (see §3)
- 5 new regression tests added (see §4)
- All 42 tests pass

---

## 3. Implementation — Fix Applied

### File: `scripts/update_market_data.py`

**BEFORE (buggy):**
```python
# Stage 1: Validate re-fetched data at boundary
ref_first_close = float(df.sort_values("date").iloc[0]["close"])
canon_close = anomaly["canon_close"]
new_ret = abs((ref_first_close - canon_close) / canon_close) if canon_close > 0 else 1.0
```

**AFTER (fixed):**
```python
# Stage 1: Validate re-fetched data at boundary
# Compare close at the first trading day AFTER canonical max date
# (the boundary), NOT iloc[0] of the full lookback window.
canon_max_ts = pd.Timestamp(anomaly["canon_date"])
sorted_df = df.sort_values("date")
boundary_mask = sorted_df["date"] > canon_max_ts
if boundary_mask.any():
    boundary_row = sorted_df.loc[boundary_mask].iloc[0]
    ref_boundary_close = float(boundary_row["close"])
else:
    ref_boundary_close = None

canon_close = anomaly["canon_close"]
new_ret = (
    abs((ref_boundary_close - canon_close) / canon_close)
    if ref_boundary_close is not None and canon_close > 0
    else 1.0
)
```

### Key Changes
| Aspect | Before | After |
|---|---|---|
| **Price source** | `iloc[0]` (earliest lookback date) | First row where `date > canon_max_date` |
| **No boundary data** | N/A (always had iloc[0]) | `ref_boundary_close = None` → `new_ret = 1.0` → rejected |
| **Semantic correctness** | Compared wrong date | Compares actual boundary date |

---

## 4. Regression Tests Added

### File: `tests/test_targeted_refetch.py`

| Test Class | Test Name | Scenario |
|---|---|---|
| `TestStage1BoundaryValidationFix` | `test_false_rejection_prevented_boundary_ok_lookback_different` | iloc[0]=30000 (old bug rejects), boundary=49000 (fix accepts). Uses 3-zone data. |
| `TestStage1BoundaryValidationFix` | `test_false_acceptance_prevented_boundary_anomalous_lookback_ok` | iloc[0]=49000 (old bug accepts), boundary=10000 (fix rejects) |
| `TestStage1BoundaryValidationFix` | `test_no_rows_after_canonical_max_date` | No post-boundary rows → rejected as still_anomalous |
| `TestStage1BoundaryValidationFix` | `test_boundary_close_exactly_at_threshold` | 25% exactly → rejected (`>=` threshold) |
| `TestStage1BoundaryValidationFix` | `test_boundary_close_just_below_threshold_passes` | 24% → passes Stage 1 |

### Test Helpers Added
| Helper | Purpose |
|---|---|
| `_make_ohlcv_varying()` | 2-zone price data (before/after boundary) |
| `_make_ohlcv_three_zone()` | 3-zone price data (pre-canonical / overlap / post-canonical) |

### Existing Tests Updated
- Added `canon_date` key to all anomaly dicts in existing tests (required by fix)
- Updated `test_refetch_overlap_trims_all_rows`: now expects `still_anomalous` (Stage 1 intercepts when no post-boundary rows exist)

---

## 5. Test Results

```
42 passed, 0 failed (32.86s)
```

All existing tests + 5 new regression tests pass.

---

## 6. Scope & Constraints

| Constraint | Status |
|---|---|
| Implementation-only (no audit/approve) | ✅ Compliant |
| Repo-relative paths only | ✅ Compliant |
| Test required | ✅ 5 regression tests added |
| No self-approval | ✅ Submitted for Tier 3 |

---

## 7. Tier 3 Audit Submission

Submitted to:
- **Code Reviewer (Role 21)**: Pipeline code quality — `scripts/update_market_data.py`
- **QA Engineer (Role 17)**: Data quality validation — regression test coverage
- **Performance Tester (Role 23)**: No performance impact (same O(n) sort + single filter)

### Files Changed
| File | Lines Changed | Type |
|---|---|---|
| `scripts/update_market_data.py` | ~20 lines modified | Bug fix |
| `tests/test_targeted_refetch.py` | ~280 lines added/modified | Regression tests + existing test updates |
