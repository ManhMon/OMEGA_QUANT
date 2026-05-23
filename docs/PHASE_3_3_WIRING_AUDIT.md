# Phase 3.3 Wiring Audit Report

**Audit Date:** 2026-05-10T14:10:56Z  
**Auditor Role:** Code Reviewer (Role 21)  
**Scope:**  
- `OMEGA_QUANT/packages/quant/src/omega/quant/trading_engine.py`
- `OMEGA_QUANT/packages/quant/src/omega/quant/execution_sim.py`
- `OMEGA_QUANT/tests/phase3/test_trading_engine.py`
**Test Suite:** `pytest OMEGA_QUANT/tests/phase3/test_trading_engine.py -v`

---

## Audit Result

| Field | Value |
| :--- | :--- |
| **Role** | Code Reviewer |
| **Verdict** | **[NEEDS_FIX]** |
| **PIT Safety** | **FAIL** |
| **Role Compliance** | **PASS** |

Phase 3.3 wiring is not ready for approval. Core reasons:

1. `TradingEngine.generate_trading_signal()` does not enforce T-1 inside wrapper and does not use `AlphaDiscoveryEngine`; it accepts caller-supplied panel as-is and then generates random placeholder alpha/metrics (`trading_engine.py:136-152`, `330-381`).
2. When promotion/embargo gates are relaxed enough for success path, signal generation crashes on miswired portfolio metrics call: `PortfolioOptimizer.calculate_portfolio_metrics()` does not accept `covariance_matrix=` (`trading_engine.py:196-200`; `portfolio_optimizer.py:254-308`).
3. Claimed execution coverage is misleading: on 2026-05-10 pytest reported `10 passed, 3 skipped`, but all three skipped tests are exact execution-path tests, so broken wiring remains untested (`test_trading_engine.py:184-220`, `256-257`).

---

## Findings

### 1. Critical: wrapper does not enforce T-1 lag or real alpha pipeline

**Files:** `trading_engine.py:113-152`, `330-381`  
**Checks failed:** `(1) T-1 lag enforced`, `(2) no look-ahead bias in alpha/portfolio/promotion pipeline`

`generate_trading_signal()` documents that it should operate on T-1 data, but code never slices `market_data` by `timestamp - 1 day`. It trusts caller input and forwards full panel into `_discover_alpha()` / `_evaluate_alpha()`.

Relevant path:

```python
def generate_trading_signal(..., market_data, timestamp, ...):
    ...
    if alpha_id is None:
        alpha_result = self._discover_alpha(market_data)
```

Problems:

- No in-function filter like `market_data[index_timestamp <= timestamp - 1 day]`
- `self.alpha_engine = AlphaDiscoveryEngine()` is instantiated but never used
- `_discover_alpha()` and `_calculate_alpha_metrics()` produce random placeholder outputs, so real PIT-safe alpha discovery path is bypassed
- Test named `test_generate_signal_enforces_pit_safety` asserts only `signal.timestamp == timestamp`; it does not verify data truncation or leakage prevention (`test_trading_engine.py:129-142`)

Impact:

- Wrapper can consume same-day or future rows if caller passes them
- Claimed no-look-ahead guarantee is not enforced by implementation
- Integration claim "Alpha Discovery -> Portfolio -> Promotion" is not true in current code path

---

### 2. High: successful signal path crashes on portfolio metrics call

**Files:** `trading_engine.py:196-200`, `portfolio_optimizer.py:254-308`  
**Checks failed:** `(2) integration correctness`

`TradingEngine` calls:

```python
portfolio_metrics = self.portfolio_optimizer.calculate_portfolio_metrics(
    weights=target_weights,
    returns=alpha_scores,
    covariance_matrix=None
)
```

But `PortfolioOptimizer.calculate_portfolio_metrics()` signature is:

```python
def calculate_portfolio_metrics(
    self,
    weights: pd.Series,
    returns: pd.DataFrame,
    risk_free_rate: float = 0.0
) -> PortfolioMetrics:
```

There is no `covariance_matrix` parameter. Manual reproduction on 2026-05-10, after relaxing gate thresholds, raised:

```text
TypeError: PortfolioOptimizer.calculate_portfolio_metrics() got an unexpected keyword argument 'covariance_matrix'
```

Impact:

- First non-rejected signal crashes before returning `TradingSignal`
- Execution path is not functionally wired end-to-end

---

### 3. High: default wiring makes execution path effectively unreachable in tests

**Files:** `trading_engine.py:180-190`, `test_trading_engine.py:184-220`, `278-313`  
**Checks failed:** `(5) test coverage adequate`

Embargo logic in wrapper sets:

```python
model_date = timestamp - datetime.timedelta(days=1)
embargo_ok = self.promotion_gate.apply_embargo(
    model_date=model_date,
    current_date=timestamp,
    horizon=self.config.embargo_horizon
)
```

With test config `embargo_horizon=1`, `apply_embargo()` requires `current_date >= model_date + 2 days`. For same rebalance timestamp, this blocks all freshly discovered models. Result:

- `generate_trading_signal()` returns `None` even when other steps pass
- execution tests skip instead of asserting real behavior
- `run_backtest()` can return empty frame and still pass (`test_trading_engine.py:290-296`)

Manual reproduction on 2026-05-10:

```text
signal -> None
backtest_rows -> 0
```

Impact:

- 3 skipped tests do not represent harmless optional coverage
- execution wiring and downstream metrics are not validated

---

### 4. Medium: vectorization requirement is not met

**Files:** `trading_engine.py:287-326`, `execution_sim.py:140-155`, `158`, `325-327`  
**Checks failed:** `(3) vectorized operations (no loops)`

Explicit loops remain in audited scope:

- `for timestamp in timestamps:` in `run_backtest()`
- `for symbol in trade_symbols:` in `execute_trades()`
- `sum(abs(t.trade_size) for t in trades)` in aggregate cost calc
- list comprehension over trade sizes in `estimate_execution_cost()`

These are not purely vectorized NumPy/Pandas paths.

Impact:

- Fails stated "no loops" requirement
- Scale/perf characteristics differ from requirement

---

### 5. Medium: execution realism is partial, not fully integrated

**Files:** `execution_sim.py:163-178`, `214-246`; `trading_engine.py:215-262`  
**Checks:** `(4) execution simulator realistic`

Strengths:

- commission modeled
- slippage modeled with base + square-root impact + random component
- latency value reported

Gaps:

- latency does not affect price selection; it is metadata only
- `execute_signal()` accepts `market_data` but does not use it
- no time-shifted fill price, spread, volume cap, or partial-fill logic

Assessment:

- simulator is directionally realistic for cost accounting
- wiring does not integrate latency into actual fill formation

---

## Test Run

Command run on 2026-05-10:

```text
pytest OMEGA_QUANT/tests/phase3/test_trading_engine.py -v
```

Observed result:

```text
collected 13 items
10 passed, 3 skipped, 1 warning in 0.82s
```

Skipped tests:

- `TestSignalExecution::test_execute_signal_success`
- `TestSignalExecution::test_execute_signal_calculates_costs`
- `TestSignalExecution::test_execute_signal_updates_weights`

Warning:

- `PytestCacheWarning` for existing `.pytest_cache\v\cache` path

Interpretation:

- Numeric threshold `10 passed, 3 skipped` was observed
- Coverage is still not adequate because all skipped cases are execution-path tests, exactly where wiring is broken

---

## Conclusion

**VERDICT: [NEEDS_FIX]**

Phase 3.3 wiring fails approval on PIT enforcement and end-to-end integration correctness. Main blocker is not style; it is behavior:

1. wrapper does not enforce T-1 internally
2. wrapper bypasses real alpha engine with random placeholders
3. first successful signal path crashes on portfolio metrics call
4. tests skip broken execution path and allow empty backtests

Until these are fixed and execution-path tests are converted from permissive/skip-heavy checks into deterministic assertions, approval is not warranted.
