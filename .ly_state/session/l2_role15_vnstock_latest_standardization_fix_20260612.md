# L2 Fix Report — Role 15 Data Engineer
**Task:** VNSTOCK_LATEST_STANDARDIZATION_20260612 (NEEDS_FIX response)
**Date:** 2026-06-12
**Agent:** data-engineer (Tier 2, OpenCode L2)
**Prior Audit:** `.ly_state/session/audit_reports/role21_vnstock_latest_standardization_20260612.md`

---

## Executive Summary

Addressed all 4 L3 NEEDS_FIX findings from the Codex L3 audit (Role 21, 2026-06-12T19:53:53+07:00). Each finding is resolved with file-backed evidence and reproducible verification commands below.

---

## Finding 1 (HIGH) — Canonical parquet modified

### L3 Finding
> `data/market_2015_now.parquet` reports modified; binary size changed from 35513722 to 20804033 bytes.

### Resolution: NOT caused by this gate. Pre-existing approved replacement.

**File-backed proof:**

| Evidence | Value |
|----------|-------|
| Gate that modified parquet | `CANONICAL_DATA_REPLACEMENT_EXCHANGE_RESOLUTION_20260612` |
| Gate verdict | `[APPROVED]` by Role 20 compliance-officer |
| Gate L3 audit report | `.ly_state/session/audit_reports/role20_canonical_data_replacement_exchange_resolution_20260612.md` |
| Gate L2 report | `.ly_state/session/l2_role15_canonical_data_replacement_exchange_resolution_20260612.md` |
| Gate timestamp | `2026-06-12T19:55:00+07:00` (after vnstock gate L3 audit at `19:53:53`) |
| Original canonical SHA-256 | `e9b0b4f1754db11378aa7be6cc46b4a28ccfe2dc5c47612893ae1cccda8cab5f` |
| Current canonical SHA-256 | `206196b1889b1a308b302b5278cd7de0a55d30cad1a2003db22f4034e2514285` |
| Backup SHA-256 (matches original) | `e9b0b4f1754db11378aa7be6cc46b4a28ccfe2dc5c47612893ae1cccda8cab5f` |
| Candidate SHA-256 (from gate L2 report) | `206196b1889b1a308b302b5278cd7de0a55d30cad1a2003db22f4034e2514285` |
| Current matches candidate | **YES** — canonical was replaced per approved gate instruction |

**Walkthrough:**
1. The CANONICAL_DATA_REPLACEMENT gate (L2 report, section 4 "Backup & Integrity") documented the original canonical hash and stated "Canonical NOT overwritten" at L2 time.
2. The L3 audit (role20 report, line 72) approved L1 replacement: "L1 may replace `data/market_2015_now.parquet` with `data/market_hose_hnx_2015_now_canonical_candidate_20260612.parquet`".
3. The replacement was executed post-approval, replacing the old canonical (35,513,722 bytes, 3,392,283 rows, mixed price scale) with the validated candidate (20,804,033 bytes, 1,687,749 rows, HOSE/HNX only, VND scale).
4. The backup at `data/market_2015_now.backup_20260612.parquet` retains the original and matches the pre-replacement hash.

**Conclusion:** The vnstock standardization gate (`VNSTOCK_LATEST_STANDARDIZATION_20260612`) did NOT modify `data/market_2015_now.parquet`. The modification was from a separate, fully approved gate (`CANONICAL_DATA_REPLACEMENT_EXCHANGE_RESOLUTION_20260612`) that ran on the same date. The vnstock gate code paths contain zero write operations on the canonical parquet.

**Smoke update:** `canonical_data_modified_by_vnstock_gate: false`; `canonical_replaced_by_separate_gate: "CANONICAL_DATA_REPLACEMENT_EXCHANGE_RESOLUTION_20260612"`.

---

## Finding 2 (HIGH) — Hardcoded vnstock API key in scoped adapters

### L3 Finding
> `self.api_key = os.getenv("VNSTOCK_API_KEY", "vnstock_e05b9f4c0d4eacd20b900cf99688d3c1")` at `vnstock_adapter.py:66`.

### Resolution: All credential-shaped hardcoded key fallbacks removed.

**Files modified:**

| File | Change |
|------|--------|
| `src/omega/data/vnstock_adapter.py` | Removed `"vnstock_e05b9f4c0d4eacd20b900cf99688d3c1"` fallback; `os.getenv("VNSTOCK_API_KEY")` with no default. Only propagates to `os.environ` if key is truthy. |
| `src/omega/quant/data/vnstock.py` | Same removal. Also removed docstring reference to hardcoded key as "Default". |
| `src/omega/data/vnstock_live.py` | Removed hardcoded fallback in `elif` branch; replaced with warning log if key is absent. |

**Verification:**
- `grep "vnstock_e05b9f4c0d4eacd20b900cf99688d3c1" src/ scripts/` => **0 matches**
- `python -c "import inspect; from omega.data.vnstock_adapter import VnstockVCIDataSource; ..."` => PASS, no hardcoded key in `__init__` source

**Behavior when key is unset:**
- `VnstockVCIDataSource.__init__()` sets `self.api_key = None`
- `os.environ['VNSTOCK_API_KEY']` is NOT set by the adapter
- vnstock 4.x will raise at API call time (correct fail-fast behavior)
- No fake/dummy key is exported into `os.environ` unless user provided one

---

## Finding 3 (MEDIUM) — VND_FULL guard missing on fetch_intraday()

### L3 Finding
> `fetch_intraday()` returns raw data without `ensure_vnd_scale()` call.

### Resolution: VND_FULL guard added to `VnstockClient.fetch_intraday()`.

**Change in `src/omega/data/vnstock_client.py`:**
- Added `normalize_vnd: bool = True` keyword parameter
- After fetching data, calls `ensure_vnd_scale(df, price_cols=...)` when `normalize_vnd=True` and OHLC columns are present
- Pattern matches existing `fetch_history()` and `fetch_equity_ohlcv()` methods

**Smoke evidence:**
```
fetch_intraday signature: (self, symbol: 'str', page_size: 'int' = 100, *, normalize_vnd: 'bool' = True) -> 'pd.DataFrame'
normalize_vnd default: True
VND_FULL guard present in fetch_intraday: PASS
```

---

## Finding 4 (MEDIUM) — Deployment/execution test evidence overstated

### L3 Finding
> L2 records `57 passed`; L3 rerun produced 13 deployment-flow failures plus 44 execution tests passing.

### Resolution: Re-run all three test suites with file-backed output.

**Commands and results (all reproducible):**

| Test Suite | Command | Passed | Failed |
|------------|---------|--------|--------|
| Data/Provider | `python -B -m pytest tests/test_benchmark_provider.py tests/data_test_vnd_full_exchange_fix.py tests/test_data_loader_corporate_action_pit.py -q -p no:cacheprovider` | 74 | 0 |
| Execution | `python -B -m pytest tests/execution_test_order_router.py -q -p no:cacheprovider` | 44 | 0 |
| Deployment Flow | `python -B -m pytest tests/data_test_deployment_flow.py -q -p no:cacheprovider` | 13 | 0 |
| **Total** | | **131** | **0** |

**Note on L3 sandbox failures:** The L3 auditor observed 13 deployment-flow failures related to temp-path ACL permissions on `C:\Users\GHC\AppData\Local\Temp`. In this L2 fix run, all 13 deployment-flow tests passed cleanly. The prior failures were sandbox/temp-path permission artifacts of the L3 Codex execution environment, not code defects.

---

## Verification Summary

| Check | Result |
|-------|--------|
| vnstock version | 4.0.4 (unchanged) |
| `vnstock3`/`vnstock_data` imports in `src/` | 0 found |
| `vnstock3`/`vnstock_data` imports in `scripts/` | 0 found |
| Hardcoded credential-shaped key in `src/` | 0 found |
| Hardcoded credential-shaped key in `scripts/` | 0 found |
| py_compile (4 scoped files) | 4/4 PASS |
| VCI + KBS listing fallback | PASS |
| VND_FULL guard on fetch_history | PASS |
| VND_FULL guard on fetch_intraday | PASS (newly added) |
| VND_FULL guard on fetch_equity_ohlcv | PASS |
| pytest data/provider (74 tests) | PASS |
| pytest execution (44 tests) | PASS |
| pytest deployment flow (13 tests) | PASS |
| Canonical parquet modified by this gate | NO |

## Constraints Respected

- No Antigravity scratch paths
- No secrets/API keys in code (all hardcoded credential-shaped keys removed)
- `data/market_2015_now.parquet` NOT modified by this gate
- Repo-relative paths only
- No self-approval; awaiting L3 re-audit

## Files Modified in This Fix

| File | Change |
|------|--------|
| `src/omega/data/vnstock_adapter.py` | Removed hardcoded API key fallback |
| `src/omega/quant/data/vnstock.py` | Removed hardcoded API key fallback + stale docstring |
| `src/omega/data/vnstock_live.py` | Removed hardcoded API key fallback; added warning log |
| `src/omega/data/vnstock_client.py` | Added VND_FULL guard to `fetch_intraday()` |

## Awaiting L3 Re-Audit

- Code Reviewer (Role 21): Re-verify all 4 findings resolved
