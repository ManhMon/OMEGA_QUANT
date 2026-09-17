# L2 Fix Report: VCI Full HSX/HNX Date Scope Fix

- **Role**: Data Engineer (Role 15, L2)
- **Gate**: VCI_FULL_HSX_HNX_2015_NOW_20260613
- **Session ID**: l2_role15_vci_full_hsx_hnx_2015_now_fix1_20260613
- **Date**: 2026-06-13
- **Trigger**: Role 17 (QA Engineer) L3 audit returned [NEEDS_FIX]

---

## Repo-Local Role/Skill Source Evidence

### REPO_AGENT_ROOT files read
- `REPO_AGENT_ROOT=C:/Users/GHC/repos/OMEGA_QUANT/.agents/agent`
- `.agents/agent/data-engineer.md` (role_id: 15, tier: 2, platform: OpenCode)

### REPO_SKILL_ROOT files read
- `REPO_SKILL_ROOT=C:/Users/GHC/repos/OMEGA_QUANT/.agents/skills`
- `.agents/skills/python-patterns/SKILL.md` - Python development principles, async patterns, type hints
- `.agents/skills/database-design/SKILL.md` - Database design principles, schema design, indexing
- `.agents/skills/clean-code/SKILL.md` - Pragmatic coding standards, SRP/DRY/KISS
- `.agents/skills/testing-patterns/SKILL.md` - Testing pyramid, AAA pattern, mocking strategies
- `.agents/skills/systematic-debugging/SKILL.md` - 4-phase debugging: reproduce, isolate, understand, fix
- `.agents/skills/performance-profiling/SKILL.md` - Measure, analyze, optimize workflow

### Project files read (repo-local)
- `scripts/vci_full_hsx_hnx_download_20260613.py` (282 lines)
- `scripts/vci_full_hsx_hnx_validate_20260613.py` (294 lines)
- `scripts/sod_gate_enforcer.py` (1189 lines)
- `.ly_state/session/vci_full_hsx_hnx_validation.json` (308 lines)
- `.ly_state/session/vci_full_hsx_hnx_stats.json` (20 lines)
- `data/market_vci_hsx_hnx_2015_now_20260613.parquet` (21.7 MB)

---

## Forbidden Path Scan Evidence

Forbidden paths scanned. Every mention below is non-authoritative / forbidden-path scan evidence only:

- `.gemini\antigravity-ide\scratch\ag-kit` -- non-authoritative, not used as source, forbidden-path scan evidence: clean
- `.openclaw\skills` -- non-authoritative, not used as source, forbidden-path scan evidence: clean
- `C:\Users\GHC\.agents` -- non-authoritative, not used as source, forbidden-path scan evidence: clean
- `.codex\memories` -- non-authoritative, not used as source, forbidden-path scan evidence: clean

No authoritative reliance on any forbidden path. All skill/role sources loaded exclusively from REPO_AGENT_ROOT and REPO_SKILL_ROOT within the repo.

---

## L3 Finding (Root Cause)

**Role 17 audit**: File `data/market_vci_hsx_hnx_20260613.parquet` contained pre-2015 rows:
- Min date: 2011-03-15
- Pre-2015 rows: 82,280 (years 2011: 100, 2012: 680, 2013: 7,702, 2014: 73,798)
- User requested 2015-now scope

**Root cause (5 Whys)**:
1. Why pre-2015 rows? -- VCI API returned data before the requested start_date for some tickers
2. Why wasn't it filtered? -- Download script trusted API to honor start_date parameter
3. Why no post-fetch filter? -- No defense-in-depth date filter in `fetch_one_symbol()`
4. Why did validator pass? -- Validator check `min_date_covers_2015` used `date_min <= 2015-12-31` (weak check)
5. Why weak check? -- Original check verified data "reaches back to 2015" not "starts at 2015"

---

## Fixes Applied

### 1. Parquet data fix (immediate)
- **File**: `data/market_vci_hsx_hnx_2015_now_20260613.parquet`
- **Action**: Filtered all rows where `date < 2015-01-01`, saved in place
- **Rows before**: 1,853,541
- **Rows after**: 1,771,261 (removed 82,280 pre-2015 rows)
- **Tickers before**: 703
- **Tickers after**: 703 (all preserved, 0 tickers became empty)

### 2. Download script hardening
- **File**: `scripts/vci_full_hsx_hnx_download_20260613.py`
- **Change 1**: Added post-fetch date filter in `fetch_one_symbol()` after `pd.to_datetime()`:
  ```python
  pre_filter = len(df)
  df = df[df["date"] >= pd.Timestamp(START_DATE)].copy()
  ```
- **Change 2**: Added defense-in-depth filter in final assembly before dedup:
  ```python
  result = result[result["date"] >= pd.Timestamp(START_DATE)].copy()
  ```

### 3. Validator hardening
- **File**: `scripts/vci_full_hsx_hnx_validate_20260613.py`
- **Change**: Replaced weak check `min_date_covers_2015` (`date_min <= 2015-12-31`) with two hard checks:
  - `min_date_gte_2015`: `date_min >= 2015-01-01` (hard failure if min date is before 2015)
  - `no_pre_2015_rows`: count of rows with `date < 2015-01-01` must be exactly 0

### 4. Stats update
- **File**: `.ly_state/session/vci_full_hsx_hnx_stats.json`
- **Change**: Added `rows_raw`, `rows_post_filter`, `pre_2015_rows_removed`, and `l2_fix_note`

### 5. Canonical file safety
- `data/market_2015_now.parquet` does NOT exist in the repo, confirming no canonical overwrite occurred.

---

## Validation Results (Post-Fix)

Ran `python scripts/vci_full_hsx_hnx_validate_20260613.py` -- **ALL PASS**

| Check | Status | Detail |
|-------|--------|--------|
| file_exists | PASS | data/market_vci_hsx_hnx_2015_now_20260613.parquet |
| file_loads | PASS | 1,771,261 rows, 14 cols |
| schema_all_expected_cols | PASS | 14/14 |
| universe_count_matches | PASS | 703 vs 703 |
| all_universe_tickers_in_data | PASS | Missing: 0 |
| no_extra_tickers | PASS | Extra: 0 |
| zero_errors | PASS | errors=0 |
| zero_empty | PASS | empty=0 |
| only_hose_hnx | PASS | [HNX, HOSE] |
| hose_has_data | PASS | HOSE rows: 1,001,584 |
| hnx_has_data | PASS | HNX rows: 769,677 |
| row_count_positive | PASS | 1,771,261 |
| ticker_count_matches_universe | PASS | 703 vs 703 |
| **min_date_gte_2015** | **PASS** | **Min: 2015-01-05 (>= 2015-01-01)** |
| **no_pre_2015_rows** | **PASS** | **Pre-2015 rows: 0** |
| max_date_current | PASS | Max: 2026-06-12 |
| no_future_dates | PASS | Max <= today |
| no_duplicate_ticker_date | PASS | Duplicates: 0 |
| no_null_open/high/low/close/volume | PASS | 0 nulls each |
| no_nonpositive_open/high/low/close | PASS | 0 each |
| no_negative_volume | PASS | 0 |
| ohlc_invariants_hold | PASS | Violations: 0 |
| price_scale_vnd | PASS | [VND] |
| source_vnstock_vci | PASS | [vnstock_vci] |
| adjusted_backward | PASS | [backward_adjusted] |
| prices_in_vnd_range | PASS | Median close: 10,700 |
| hose_full_coverage | PASS | Missing: 0 |
| hnx_full_coverage | PASS | Missing: 0 |

### Post-fix summary statistics
- **Rows**: 1,771,261
- **Tickers**: 703 (403 HOSE + 300 HNX)
- **Date range**: 2015-01-05 to 2026-06-12
- **Unique dates**: 2,855
- **File size**: 20.9 MB
- **Year distribution**: 2015-2026 (no pre-2015 years)
- **Volume zero rows**: 273,916 (15.46%) -- normal for illiquid tickers

---

## Tickers Now Empty After 2015 Filter

**None.** All 703 tickers in the VCI HSX/HNX universe have at least one row with date >= 2015-01-01.

---

## Files Modified

| File | Change |
|------|--------|
| `data/market_vci_hsx_hnx_2015_now_20260613.parquet` | Filtered 82,280 pre-2015 rows |
| `scripts/vci_full_hsx_hnx_download_20260613.py` | Added hard date filter in fetch + final assembly |
| `scripts/vci_full_hsx_hnx_validate_20260613.py` | Replaced weak date check with 2 hard checks |
| `.ly_state/session/vci_full_hsx_hnx_stats.json` | Updated stats with filter metadata |
| `.ly_state/session/vci_full_hsx_hnx_validation.json` | Re-generated by validator (all pass) |

## Files NOT Modified (as required)

| File | Reason |
|------|--------|
| `data/market_2015_now.parquet` | Does not exist; canonical not overwritten |
