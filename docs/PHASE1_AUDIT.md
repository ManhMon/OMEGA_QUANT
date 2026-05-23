# PHASE 1 DATA INFRASTRUCTURE AUDIT REPORT

**Audit ID**: `L3-AUDIT-P1-20260511`
**Role**: Code Reviewer (Role 21)
**Platform**: Codex (L3)
**Date**: 2026-05-11T17:00:00+07:00
**Commit**: 444ef5f
**Scope**: `packages/data/src/omega/data/` (12 modules), `tests/phase1/` (88 tests)

---

## FINAL VERDICT: [NEEDS_FIX]

---

## 1. VECTORIZATION AUDIT

**Requirement**: 100% Pandas/NumPy vectorized operations. No Python `for`/`while` loops on data rows.

**Result**: `FAIL` — 18 Python loop violations found across 8 modules.

### Critical Violations (data-path loops on rows)

| File | Line | Pattern | Severity |
|:-----|:-----|:--------|:---------|
| `vnstock_vci.py` | 71 | `for _, row in df.iterrows()` — row-by-row OHLCV extraction | HIGH |
| `vnstock_vci.py` | 101 | `for sym in symbols` — sequential symbol fetch in `get_ohlcv()` | MEDIUM |
| `vnstock_adapter.py` | 84 | `for _, row in df.iterrows()` — row-by-row OHLCV extraction | HIGH |
| `market_flow.py` | 64 | `for _, row in df.iterrows()` — row-by-row foreign flow extraction | HIGH |
| `market_flow.py` | 111 | `for _, row in df.iterrows()` — row-by-row prop flow extraction | HIGH |
| `market_flow.py` | 141 | `for symbol in symbols` — sequential symbol fetch | MEDIUM |
| `vci_bridge.py` | 83 | `for i, date in enumerate(dates)` — row-by-row mock OHLCV generation | HIGH |
| `vci_bridge.py` | 133 | `for i in range(n_features)` — sequential feature generation | MEDIUM |
| `vci_bridge.py` | 272 | `for metrics in self.quality_history` — loop over quality history | LOW |
| `corporate_action.py` | 203-240 | Nested `for` loops for price adjustment across rows | HIGH |
| `live_ingestor.py` | 129 | `for symbol in symbols` — sequential live fetch | MEDIUM |
| `validator.py` | 51 | `for i in range(1, len(rows))` — row-by-row price move validation | HIGH |
| `validator.py` | 71 | `for i in range(self.adv_lookback, ...)` — row-by-row volume check | HIGH |
| `validator.py` | 90,116 | `for r in rows` — row-by-row gap and OHLC checks | HIGH |
| `sanitizer.py` | 100,107 | `for symbol / for col` — nested symbol×column loop in `fit()` | MEDIUM |
| `sanitizer.py` | 307,337,380 | `for symbol` — nested loops in `_clip_outliers_fitted()` | MEDIUM |
| `calendar.py` | 102 | `for ts in timestamps` — row-by-row timestamp validation | MEDIUM |
| `loader.py` | 228 | `for col in df_filtered.columns` — column-level loop for outlier detection | LOW |

### Recommended Fixes

- **`iterrows()` → vectorized**: Replace `df.iterrows()` with `df.rename(columns=...).to_dict('records')` or direct column assignment.
- **`corporate_action.py`**: Use `np.where` / boolean masking for backward price adjustment instead of nested index loops.
- **`validator.py`**: Convert row-by-row validation to vectorized DataFrame operations (`df['high'] < df['low']`, `df['close'].pct_change()`).
- **`sanitizer.py` `fit()`**: Use `groupby().agg()` instead of per-symbol per-column loops.

---

## 2. PIT SAFETY AUDIT

**Requirement**: Mandatory `as_of_time` parameters everywhere. No `datetime.now()` in production paths.

**Result**: `FAIL` — 5 `datetime.now()` / `Timestamp.now()` violations found.

### Violations

| File | Line | Code | Risk |
|:-----|:-----|:-----|:-----|
| `vnstock_vci.py` | 97 | `end_date = datetime.now()` in `get_ohlcv()` | HIGH — uses wall-clock time as data boundary |
| `vci_bridge.py` | 25 | `timestamp: datetime = field(default_factory=datetime.now)` | MEDIUM — default metric timestamp |
| `vci_bridge.py` | 66 | `as_of_date = self.config.as_of_date or datetime.now()` | HIGH — fallback to wall-clock in data fetch |
| `vci_bridge.py` | 180 | `timestamp=datetime.now()` in `validate_data_quality()` | MEDIUM — quality metric timestamp |
| `sanitizer.py` | 421 | `df['as_of'] = pd.Timestamp.now()` in `_enforce_pit_safety()` | CRITICAL — stamps `as_of` with wall-clock time, defeating PIT safety |

### Positive Findings

- `loader.py`: `load_prices()` correctly enforces mandatory `as_of_time` parameter and raises `ValueError` if `None`.
- `loader.py`: `load_market_data()` also enforces mandatory `as_of_time`.
- `datasource_config.py`: PIT validation logic (embargo, lag, no-lookahead) is correct and well-structured.
- `loader.py`: `_enforce_pit_safety()` correctly validates `as_of <= available_at`.

### Recommended Fixes

- All `datetime.now()` calls MUST be replaced with explicit `as_of_time` parameter passed from caller.
- `sanitizer.py:421` is the most critical: `_enforce_pit_safety()` ironically introduces PIT violation by using `Timestamp.now()`.

---

## 3. MOCK DATA AUDIT

**Requirement**: No synthetic/mock OHLCV data in production code paths.

**Result**: `FAIL` — 1 module contains synthetic OHLCV generation in a production-importable path.

### Violations

| File | Function | Issue |
|:-----|:---------|:------|
| `vci_bridge.py` | `fetch_mock_vci_data()` | Generates synthetic OHLCV with `np.random` — importable from `omega.data.vci_bridge` |
| `vci_bridge.py` | `generate_mock_features()` | Generates random features with `np.random.randn` |
| `sanitizer.py` | `__main__` block (L458-489) | Creates synthetic test data — acceptable (guarded by `if __name__ == '__main__'`) |

### Assessment

- `vci_bridge.py` is the primary concern: `VCIDataIntegration.fetch_mock_vci_data()` is a class method on a production-importable class. Any caller can accidentally use mock data in production.
- The class name `VCIDataIntegration` does not indicate it's mock-only.
- `sanitizer.py` `__main__` block is acceptable — guarded, not importable.

### Recommended Fix

- Move `VCIDataIntegration` to a `tests/` or `fixtures/` directory, or rename to `MockVCIDataIntegration` and add runtime guard (`raise RuntimeError` if not in test mode).

---

## 4. STATE PERSISTENCE AUDIT

**Requirement**: No RAM-only state. All persistent state must be file-backed.

**Result**: `FAIL` — 5 modules store operational state in RAM-only dicts/lists.

### Violations

| File | Attribute | Type | Risk |
|:-----|:----------|:-----|:-----|
| `vnstock_vci.py` | `self._cache` | `Dict[str, List[Dict]]` | MEDIUM — API response cache lost on restart |
| `vnstock_adapter.py` | `self._cache` | `Dict[str, List[Dict]]` | MEDIUM — same pattern |
| `market_flow.py` | `self._cache` | `Dict[str, Any]` | MEDIUM — same pattern |
| `vci_bridge.py` | `self.quality_history` | `List[VCIDataQualityMetrics]` | HIGH — quality audit trail lost on restart |
| `sanitizer.py` | `self._fitted_params` | `Dict` (mean/std/quantiles) | HIGH — fitted model parameters lost on restart |
| `sanitizer.py` | `self.sanitization_stats` | `Dict` | MEDIUM — sanitization stats lost |

### Positive Findings

- `loader.py`: Uses Parquet file-backed cache (`self.cache_dir / f"{cache_key}.parquet"`) — COMPLIANT.
- `datasource_config.py`: Stateless configuration — COMPLIANT.
- `calendar.py`: Class-level holiday cache is acceptable (deterministic, computed from constants).

### Recommended Fixes

- `_cache` dicts should be backed by Parquet/JSON files (or use `loader.py` pattern).
- `sanitizer._fitted_params` should serialize to JSON/pickle file after `fit()` and load on `apply()`.
- `vci_bridge.quality_history` should append to `.ly_state/session/audit_log.jsonl`.

---

## 5. TEST VERIFICATION

**Requirement**: 88/88 tests PASS.

**Result**: `PASS` ✓

```
88 passed, 142 warnings in 0.44s
```

### Test Distribution

| Test File | Tests | Status |
|:----------|:------|:-------|
| `test_event_bus.py` | 27 | ALL PASS |
| `test_scheduler.py` | 19 | ALL PASS |
| `test_state_machine.py` | 19 | ALL PASS |
| `test_vnstock_vci.py` | 13 (+ 10 integration) | ALL PASS |

### Warnings

- 140× `datetime.utcnow()` deprecation warnings from `event_bus.py` — should migrate to `datetime.now(datetime.UTC)`.
- 1× pytest cache warning (benign, filesystem issue).

---

## 6. ADDITIONAL FINDINGS

### 6.1 Code Quality

- `corporate_action.py` `adjust_prices()` uses `copy.deepcopy` on input list — inefficient for large datasets. Should use DataFrame operations.
- `vnstock_ingest.py` swallows exceptions silently (`except Exception: pass`) — should at minimum log errors.
- `live_ingestor.py` `_normalize_price_columns_to_vnd()` logic duplicated from `vnstock_ingest.py`.

### 6.2 Role Compliance

- This audit is READ-ONLY per Role 21 spec. No code changes made. `PASS`.

---

## SUMMARY SCORECARD

| Criterion | Status | Issues |
|:----------|:-------|:-------|
| Vectorization (no Python loops) | `FAIL` | 18 loop violations across 8 modules |
| PIT Safety (as_of_time, no datetime.now) | `FAIL` | 5 datetime.now() violations, 1 CRITICAL |
| No Mock Data in prod | `FAIL` | 1 module (vci_bridge.py) with mock OHLCV |
| State Persistence (file-backed) | `FAIL` | 5 modules with RAM-only state |
| Tests 88/88 PASS | `PASS` | All pass ✓ |
| Role Compliance | `PASS` | Read-only audit |

**Final Verdict**: `[NEEDS_FIX]`

**Blocking Issues** (must fix before APPROVED):
1. `sanitizer.py:421` — `pd.Timestamp.now()` in `_enforce_pit_safety()` (CRITICAL PIT violation)
2. `vnstock_vci.py:97` — `datetime.now()` as data boundary in `get_ohlcv()`
3. `vci_bridge.py:66` — `datetime.now()` fallback in production data fetch
4. `vci_bridge.py` — Mock OHLCV generator on production-importable class

**Non-blocking Issues** (should fix, not gating):
- `iterrows()` loops (performance, not correctness)
- RAM-only caches (acceptable for ephemeral session data if documented)
- `datetime.utcnow()` deprecation warnings in tests

---

*Auditor: Codex L3 — Role 21 (Code Reviewer)*
*Session: L3-AUDIT-P1-20260511*
