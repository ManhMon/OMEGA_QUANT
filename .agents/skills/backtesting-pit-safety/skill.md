---
name: backtesting-pit-safety
description: Backtesting integrity and Point-In-Time (PIT) safety for OMEGA_QUANT. No look-ahead bias, survivorship-free, walk-forward validation, CPCV, corporate action handling, slippage/fee modeling.
when_to_use: "When writing or modifying backtests, evaluating signal performance, implementing cross-validation, handling corporate actions, or validating any time-series analysis that feeds into trading decisions."
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Backtesting & PIT Safety — OMEGA_QUANT Integrity Contract

> The #1 principle: **no backtest result is trustworthy unless PIT-safe, survivorship-free, and cost-adjusted.**
> Every backtest in OMEGA_QUANT must pass these gates before its results can inform live trading.

---

## 1. PIT (Point-In-Time) Safety — Non-Negotiable

### Core PIT Rules

| Rule | Definition | Enforcement |
|------|-----------|-------------|
| **No look-ahead** | Never use data from T+n when computing at time T | T-1 shift on ALL signals |
| **as_of <= available_at** | Data timestamp must precede or equal availability timestamp | Checked at ingestion, raises `PITViolationError` |
| **available_at = T+1 09:00 VN** | EOD data available next trading day at market open | Set in `DataLoader` |
| **T-1 lag mandatory** | ALL features/alphas shifted at least 1 period | `enforce_t_minus_1_lag()` in `pit_guard.py` |
| **Double-shift defense** | Both generator AND evaluator apply T-1 shift | Defense-in-depth in `genetic_alpha.py` + `fitness.py` |

### PIT Implementation Pattern

```python
# CORRECT: Signal generated from T-1 data, applied at T
signal_t = compute_signal(data.shift(1))  # Uses T-1 data
position_t = signal_t  # Trade on T based on T-1 signal

# WRONG: Look-ahead bias
signal_t = compute_signal(data)  # Uses T data (not yet available!)
position_t = signal_t  # Trading on information not yet knowable
```

### PIT Validation Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `enforce_t_minus_1_lag()` | `src/omega/core/pit_guard.py` | Apply mandatory shift |
| `validate_t_minus_1_lag()` | `src/omega/features/signal_sanitizer.py` | Verify first row is NaN after shift |
| `PITViolationError` | `src/omega/data/loader.py` | Custom exception for violations |
| `_validate_chronological_split()` | `src/omega/ml/ml_engine.py` | Block random CV splits on time-series |

### PIT Verification Checklist

- [ ] Every feature column shifted by at least 1 period
- [ ] `signal_sanitizer.validate_t_minus_1_lag()` passes
- [ ] First row after shift is NaN (not forward-filled)
- [ ] No `future_data` or `lead()` operations in feature code
- [ ] Labels use forward returns (T to T+n), features use backward data (T-n to T-1)
- [ ] `as_of <= available_at` invariant holds for all rows
- [ ] Corporate action adjustments applied at `available_at`, not retroactively

---

## 2. Survivorship Bias Prevention

### The Bias

| Scenario | Bias Direction | Magnitude |
|----------|---------------|-----------|
| **Only current stocks** | Upward | 1-3% annualized |
| **Ignore delistings** | Upward | 0.5-2% annualized |
| **Ignore suspensions** | Upward | Variable |

### OMEGA_QUANT Survivorship-Free Protocol

| Step | Action |
|------|--------|
| **1. Full history** | Include all stocks ever listed on HOSE/HNX/UPCOM |
| **2. Point-in-time universe** | At date T, universe = stocks listed and tradeable at T |
| **3. Delisting returns** | Terminal return = -100% (or actual liquidation value) |
| **4. Suspension handling** | Carry last price, mark as non-tradeable |
| **5. Re-listing** | Re-add to universe when trading resumes |

### Verification

- [ ] Universe size changes over time (not static)
- [ ] Delisted stocks present in historical data
- [ ] Backtest engine queries PIT universe, not current listing
- [ ] Delisting events have terminal returns recorded

---

## 3. Walk-Forward Validation

### Standard Protocol

```
|--- Train ---|-- Val --|--- Test ---|
                           |--- Train ---|-- Val --|--- Test ---|
                                              |--- Train ---|-- Val --|--- Test ---|
```

### OMEGA_QUANT Walk-Forward Parameters

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| **Train window** | 252 days (1 year) | Sufficient for model fitting |
| **Validation window** | 63 days (3 months) | Hyperparameter selection |
| **Step size** | 21 days (1 month) | Monthly rebalance cadence |
| **Embargo** | 3 days | Prevent label horizon overlap |
| **Minimum folds** | 12 | At least 1 year of OOS results |

### WalkForwardEnsemble Rules

| Rule | Enforcement |
|------|-------------|
| **Chronological only** | `_validate_chronological_split()` blocks random splits |
| **Embargo between folds** | 3-day gap between train end and test start |
| **IC-based model gating** | Only models with positive OOS IC enter ensemble |
| **Per-fold tracking** | `FoldResult` records IC, Sharpe, max_drawdown per fold |

### Walk-Forward Verification

- [ ] No temporal overlap between train and test windows
- [ ] Embargo period >= label horizon
- [ ] Results reported per-fold (not just aggregate)
- [ ] Model parameters fixed before test window begins
- [ ] No re-optimization on test data

---

## 4. CPCV (Combinatorial Purged Cross-Validation)

### Concept (Lopez de Prado, AFML Ch.7)

| Parameter | OMEGA_QUANT Default | Meaning |
|-----------|-------------------|---------|
| **N** | 10 | Number of groups (time-ordered) |
| **k** | 2 | Number of test groups per fold |
| **Folds** | C(10,2) = 45 | All combinations of 2-from-10 |
| **Purge** | Bidirectional | Remove train samples whose label horizon overlaps test |
| **Embargo** | Configurable (default ~5%) | Drop train within embargo_pct after test blocks |

### Purge and Embargo

```
Train: [======][PURGE]  Embargo  [======][PURGE]
Test:                    [====]                    [====]

Purge removes train samples where label horizon overlaps test period.
Embargo drops train samples immediately after test blocks (prevents information bleed).
```

### CPCV Implementation

| Component | File |
|-----------|------|
| `CombinatorialPurgdKFold` | `src/omega/backtest/cv_splitter.py` |
| **Bidirectional purge** | Removes train samples overlapping test in both directions |
| **Embargo** | Configurable percentage of samples dropped after test |

### CPCV Verification

- [ ] Purge removes ALL overlapping label horizons
- [ ] Embargo applied AFTER test blocks, not before
- [ ] Results aggregated across all 45 folds
- [ ] Sharpe/IC distribution reported (mean, std, min, max)
- [ ] No fold uses data from the future

---

## 5. Corporate Action Handling

### Action Types and PIT-Safe Treatment

| Action | Price Adjustment | Volume Adjustment | available_at |
|--------|-----------------|-------------------|-------------|
| **Stock split (n:1)** | price / n | volume * n | Ex-date + 1 trading day 09:00 |
| **Bonus shares (n:m)** | price * m/(m+n) | volume * (m+n)/m | Ex-date + 1 trading day 09:00 |
| **Cash dividend** | price - dividend | No change | Ex-date + 1 trading day 09:00 |
| **Rights issue** | Theoretical ex-rights price | Adjusted | Ex-date + 1 trading day 09:00 |
| **Merger** | Mark delisted | Zero volume | Last trading day + 1 |

### CRITICAL: Adjust at available_at, NOT Retroactively

| Wrong | Right |
|-------|-------|
| Rewrite all historical prices on split | Apply adjustment from available_at forward |
| Adjust prices before they're knowable | Adjust at T+1 09:00 VN (when split is effective) |
| Use adjusted prices for PIT signal calc | Use raw prices → apply T-1 shift → then adjust |

---

## 6. Slippage and Fee Model

### OMEGA_QUANT Transaction Cost Model

| Component | Rate | Applied When |
|-----------|------|-------------|
| **Commission** | 0.15% (15 bps) | Every trade (buy and sell) |
| **Tax** | 0.10% (10 bps) | Sell trades only |
| **Slippage** | ~2 bps | Estimated market impact |
| **Round-trip total** | ~27 bps | Buy commission + sell commission + tax + slippage |

### Backtest Cost Application

```python
# Per-trade cost model (conceptual)
buy_cost = trade_value * (commission_rate + slippage)
sell_cost = trade_value * (commission_rate + tax_rate + slippage)
total_cost = buy_cost + sell_cost  # ~27 bps round-trip
```

### Vietnam-Specific Cost Considerations

| Factor | Impact |
|--------|--------|
| **Board lot (100 shares)** | Cannot trade fractional lots → rounding cost |
| **Price limits (±7%)** | Cannot exit at desired price when limit-down |
| **T+2.5 settlement** | Capital locked for 2.5 days → opportunity cost |
| **Thin books (mid/small cap)** | Actual slippage may exceed 2 bps estimate |
| **ATO/ATC auctions** | Different execution quality vs. continuous session |

### Cost Verification

- [ ] Backtest engine applies commission, tax, AND slippage
- [ ] Costs applied at execution time, not signal generation time
- [ ] Cost-adjusted Sharpe reported alongside gross Sharpe
- [ ] Turnover-controlled comparison (same turnover, different alphas)

---

## 7. Backtest Engine Configuration

### OMEGA_QUANT BacktestEngine Defaults

| Parameter | Default | Notes |
|-----------|---------|-------|
| **Initial capital** | 1,000,000,000 VND (1B) | Configurable per run |
| **Fee rate** | 0.0015 (15 bps) | Commission per side |
| **Tax rate** | 0.0010 (10 bps) | Sell-side only |
| **Slippage** | 0.0002 (2 bps) | Per-side estimate |
| **Rebalance** | Daily | Day-by-day simulation |

### Metrics Computed

| Metric | Formula | Minimum Acceptable |
|--------|---------|-------------------|
| **Total return** | (final_value / initial_value) - 1 | > 0 after costs |
| **Annualized volatility** | std(daily_returns) * sqrt(~248) | Context-dependent |
| **Sharpe ratio** | (mean_return - rf) / std_return * sqrt(248) | > 0.5 net of costs |
| **Sortino ratio** | mean_return / downside_std * sqrt(248) | > 0.7 |
| **Max drawdown** | max peak-to-trough decline | < 25% |
| **Win rate** | % of profitable trades | > 50% |

---

## 8. Decision Principles

### When to Trust a Backtest

| Condition | Trust Level |
|-----------|-------------|
| PIT-safe + survivorship-free + cost-adjusted + walk-forward OOS | High |
| PIT-safe + cost-adjusted but in-sample only | Low (hypothesis only) |
| No PIT validation | ZERO — do not use |
| Gross returns only | Suspect — re-run with costs |

### Red Flags

| Flag | Likely Problem |
|------|---------------|
| Sharpe > 3.0 | Almost certainly look-ahead bias |
| Perfect monotonic equity curve | Data leakage |
| IC = 1.0 | Label is in feature set |
| Zero drawdown | Position sizing bug or no trading |
| Win rate > 80% | Overfitting or look-ahead |

---

## 9. Verification Checklist (Pre-Approval)

- [ ] **PIT**: All features T-1 shifted, `as_of <= available_at` verified
- [ ] **Survivorship**: Universe is point-in-time, delistings included
- [ ] **Costs**: Commission (15bps) + tax (10bps) + slippage (2bps) applied
- [ ] **Walk-forward**: Minimum 12 OOS folds with embargo
- [ ] **CPCV**: 45-fold results reported (if used)
- [ ] **Corporate actions**: Adjusted at `available_at`, not retroactively
- [ ] **Calendar**: VN trading days only (config/vn_holidays.json)
- [ ] **Capital**: Initial capital specified, returns are percentage-based
- [ ] **Metrics**: Sharpe, Sortino, max_drawdown, win_rate all reported
- [ ] **Reproducibility**: Seeds set, deterministic execution

---

## 10. Anti-Patterns

| Don't | Do |
|-------|-----|
| Use random train/test splits on time-series | Chronological splits with embargo |
| Report gross returns only | Always report net-of-cost returns |
| Ignore delistings | Include with terminal returns |
| Adjust corporate actions retroactively | Adjust at available_at |
| Optimize on full sample | Walk-forward with OOS validation |
| Assume 252 trading days/year | Use ~248 VN trading days |
| Use same data for signal and evaluation | Separate signal generation and backtest evaluation |
| Ignore board lot rounding | Round positions to 100-share lots |
| Forget T+2.5 settlement | Account for capital lockup in turnover |
| Backtest only in-sample | Minimum 12 OOS folds required |

---

## 11. SOD/PIT Guardrails

| Guardrail | Rule |
|-----------|------|
| **PIT: absolute** | Any code that accesses future data must raise `PITViolationError` |
| **PIT: defense-in-depth** | T-1 shift applied in both generator and evaluator |
| **SOD: backtest != live** | Backtester (L2) cannot approve own results for live deployment |
| **SOD: Tier 3 audit** | Backtest code submitted to Code Reviewer (role 21) + QA Engineer (role 17) |
| **SOD: evidence** | All backtest results persisted to `.ly_state/session/` for audit |
| **Reproducibility** | All seeds set, deterministic execution, results hashable |

---

> **Remember:** A backtest that hasn't been PIT-validated is fiction. Treat all in-sample results as hypotheses, not evidence.
