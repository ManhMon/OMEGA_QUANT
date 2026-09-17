# L2 Fix Report — AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615_FIX1

**Role**: data-scientist (Role 14, OpenCode L2)
**Date**: 2026-06-15T00:00:00+07:00
**Gate**: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615_FIX1
**Responding to**: L3 [NEEDS_FIX] from `.ly_state/session/audit_reports/role20_automated_alpha_discovery_dynamic_20260615.md`

## Repo-Local Sources Read

### Agent spec
- `.agents/agent/data-scientist.md` (role_id: 14, tier: 2)

### Skills (all 9 declared)
1. `.agents/skills/python-patterns/SKILL.md` — framework selection, async patterns, type hints
2. `.agents/skills/clean-code/SKILL.md` — SRP, DRY, KISS, self-check
3. `.agents/skills/testing-patterns/SKILL.md` — AAA, testing pyramid, mocking
4. `.agents/skills/systematic-debugging/SKILL.md` — 4-phase debugging, root cause analysis
5. `.agents/skills/performance-profiling/SKILL.md` — measure-first, bottleneck identification
6. `.agents/skills/quant-research/SKILL.md` — IC/IR, PIT T-1 mandatory, alpha lifecycle
7. `.agents/skills/vietnam-market-data/SKILL.md` — VND_FULL, PIT ingestion, survivorship-free
8. `.agents/skills/backtesting-pit-safety/SKILL.md` — no look-ahead, as_of <= available_at, defense-in-depth
9. `.agents/skills/data-science-workflow/SKILL.md` — EDA, reproducibility, experiment tracking

### Forbidden path scan
No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`. Grep confirms zero references in modified source or tests.

---

## L3 Audit Findings Addressed

### Finding #1 (BLOCKING): PIT/global shift leakage in template expressions

**Root cause**: The old templates used `df.groupby('ticker')['close'].shift(1).pct_change(N)`. After `groupby().shift(1)` returns a flat Series, the subsequent `.pct_change(N)` operates *globally* across all rows. In a panel sorted by `[date, ticker]`, this compares row N (ticker A) against row N-k (which may be ticker B), producing cross-ticker artifact values.

**Affected lines (old)**: L62, L63, L64, L65, L87, L89 (momentum/accel templates) and L70, L71, L76, L77 (volume rolling on post-shift flat Series), L87 (vol_std_ratio).

**Fix applied** (src/omega/quant/alpha/automated_alpha_discovery.py):
- All momentum/acceleration templates rewritten to `df.groupby('ticker')['close'].transform(lambda x: x.shift(1).pct_change(N))` — pct_change now executes *inside* the ticker group.
- Volume rolling templates rewritten to `df.groupby('ticker')['volume'].transform(lambda x: x.shift(1).rolling(N).mean())` — rolling inside the ticker group.
- `vol_std_ratio_10_30` rewritten with transform pattern.
- **Evidence**: lines 66–93 (all `_EXPRESSION_TEMPLATES` entries).

**`_compute_rsi_safe` fix** (line 97):
- Old: `close = df.groupby('ticker')['close'].shift(1); delta = close.diff()` — `diff()` was global.
- New: All shift/diff/rolling inside `groupby('ticker')['close'].transform(_rsi_within_group)` — fully ticker-grouped.

### Finding #2 (BLOCKING): Current-bar OHLCV usage while claiming pit_safe: True

**Root cause**: Multiple templates used bare `df['close']`, `df['volume']`, `df['high']`, `df['low']`, `df['open']` — accessing same-row (T=0) data. SOP_PIT_SAFETY requires features at time T to use only data available at T-1 or earlier.

**Affected lines (old)**: L67, L68 (mr_zscore used `df['close']`), L71 (vol_zscore used `df['volume']`), L73 (vol_range_pct used `df['high']`, `df['low']`), L74 (vol_close_loc used `df['close']`, `df['low']`, `df['high']`), L77 (turnover_ratio used `df['volume']`), L79 (body_pct used `df['close']`, `df['open']`), L80–81 (shadows used all OHLC).

**Fix applied**:
- `mr_zscore_10/20`: New helper `_compute_mr_zscore(df, period)` at line 116 — all ops within `groupby().transform()`, shift(1) then rolling.
- `vol_zscore_20`: New helper `_compute_vol_zscore(df, 20)` at line 130 — same pattern.
- `vol_range_pct`: `(df.groupby('ticker')['high'].shift(1) - df.groupby('ticker')['low'].shift(1)) / (df.groupby('ticker')['close'].shift(1) + 1e-9)` at line 77.
- `vol_close_loc`: All columns via `groupby('ticker')[col].shift(1)` at line 78.
- `turnover_ratio`: `df.groupby('ticker')['volume'].shift(1) / (transform rolling + 1e-9)` at line 81.
- `body_pct`: New helper `_compute_body_pct(df)` at line 144 — uses `groupby.shift(1)` for close and open.
- `upper_shadow`: New helper `_compute_upper_shadow(df)` at line 154 — all OHLC via `groupby.shift(1)`.
- `lower_shadow`: New helper `_compute_lower_shadow(df)` at line 163 — all OHLC via `groupby.shift(1)`.
- **Evidence**: lines 64–93 (templates), lines 144–169 (helpers).

---

## Changes Summary

### Source: `src/omega/quant/alpha/automated_alpha_discovery.py`

| Section | Lines (new) | Change |
|---------|-------------|--------|
| `_EXPRESSION_TEMPLATES` | 64–93 | All 19 templates rewritten: ticker-grouped, T-1 lagged |
| `_compute_rsi_safe` | 97–113 | Fully grouped via `transform(_rsi_within_group)` — no global diff |
| `_compute_mr_zscore` (new) | 116–127 | Grouped mean-reversion z-score helper |
| `_compute_vol_zscore` (new) | 130–141 | Grouped volume z-score helper |
| `_compute_body_pct` (new) | 144–151 | T-1 candle body percentage helper |
| `_compute_upper_shadow` (new) | 154–160 | T-1 upper shadow ratio helper |
| `_compute_lower_shadow` (new) | 163–169 | T-1 lower shadow ratio helper |
| `_evaluate_expression` | 639–695 | Added regex dispatch for new helpers; injected body/shadow helpers into eval namespace |

### Tests: `tests/phase35/test_automated_alpha_discovery.py`

| Test class | Tests | Purpose |
|------------|-------|---------|
| `TestCrossTickerLeakageRegression` (new) | 4 | Reproduce and prevent global shift/diff cross-ticker artifact |
| `TestCurrentBarOHLCVRegression` (new) | 4 | Prevent current-bar OHLCV usage and ensure pit_safe evidence is truthful |

**New test details:**

1. `test_no_global_pct_change_after_group_shift` — source inspection: no bare `.shift(N).pct_change(M)` outside `transform(lambda x: ...)`
2. `test_no_global_diff_after_group_shift` — source inspection: `_compute_rsi_safe` uses transform, no bare `close.diff()`
3. `test_momentum_no_cross_ticker_values` — functional: 2-ticker panel, first row of each ticker group must be NaN
4. `test_rsi_no_cross_ticker_values` — functional: RSI on 2-ticker panel, boundary rows must be NaN
5. `test_no_bare_ohlcv_in_templates` — source inspection: no `df['close']` etc. without `groupby('ticker')` prefix
6. `test_no_ungrouped_close_shift_in_templates` — source inspection: no `df['col'].shift()` without groupby
7. `test_pit_safe_evidence_truthful` — source inspection: if bare OHLCV exists, evidence cannot claim `pit_safe: True`
8. `test_helper_functions_all_shift_ohlcv` — source inspection: helpers use `groupby.shift(1)` for all OHLCV

---

## Test Evidence

```
$ python -m pytest tests/phase35/test_automated_alpha_discovery.py -q --tb=line
60 passed, warnings only.

$ python -m pytest tests/phase35/test_nonredundant_alphas.py tests/phase35/test_diversified_basket.py -q --tb=line
119 passed, warnings only.
```

---

## Invariants Preserved

| Invariant | Status | Evidence |
|-----------|--------|---------|
| Default off / disabled | PASS | `enabled: bool = False` at line 208, `enabled=False` at line 263 |
| No live promotion | PASS | `no_live_promotion: True` at line 592, no `promote_to_live` or `deploy` in source |
| Candidate cap default 200 | PASS | `DEFAULT_CANDIDATE_CAP = 200` at line 46 |
| Deterministic generation | PASS | Same templates, same eval, same seed |
| Train-only screening | PASS | `run_discovery(train_df)` only, no test/oos params |
| Correlation filter | PASS | Structural — unchanged |
| PIT-safe evidence | PASS | All templates now strictly T-1 lagged, ticker-grouped |

---

## SOD Boundary

- Writer (L2 role_id=14) != auditor (L3 role_id=20): maintained.
- No self-approval. Submitting to Tier 3 for re-audit.
- No production promotion. Research-only artifacts.
