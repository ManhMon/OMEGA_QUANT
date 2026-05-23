# Vietnam Institutional Universe Filter Spec v1.2 Final

**Status**: APPROVED by Architect (Role 6), QA (Role 17), Data Scientist (Role 14)  
**Date**: 2026-05-16  
**Target**: NAV 1B-2B VND, 5-stock concentrated portfolio  
**Purpose**: Eliminate UPCOM/low-liquidity names, enforce institutional-grade filters

---

## Executive Summary

This spec defines institutional-grade universe filters for Vietnam equity market, designed for NAV 1B-2B VND portfolios. Key features:
- **Exchange**: HOSE/HNX only (exclude UPCOM)
- **Dynamic Sizing**: NAV-aware portfolio optimization (1B-2B → 5 stocks)
- **Liquidity**: ADV20 ≥ 10-20B VND (1% participation)
- **Risk Controls**: Sector limit 25%, limit-lock stress filter, capacity constraints
- **PIT Safety**: All inputs T-1 lagged, no look-ahead bias

---

## Core Filters

### 1. Exchange Filter
```python
allowed_exchanges = {"HOSE", "HNX"}
# Exclude UPCOM by default
# Rationale: UPCOM has poor liquidity, many stale stocks
```

### 2. Dynamic Portfolio Sizing (NAV-Aware)
```python
# Constants
min_position_vnd = 100_000_000  # 100M VND floor (prevent div by zero)
max_position_pct = 0.25  # 25% per stock (concentration limit)
target_adv_participation = 0.01  # 1% of ADV (institutional standard)
min_stocks = 3
max_stocks = 50

# Algorithm: Kelly-like criterion
target_n = clamp(
    floor(sqrt(nav_vnd / min_position_vnd)),
    min_stocks,
    max_stocks
)

# Position sizing with concentration cap
raw_position_vnd = nav_vnd / target_n
position_size_vnd = min(raw_position_vnd, nav_vnd * max_position_pct)

# Board-lot rounding (100 shares)
position_shares = floor(position_size_vnd / close_t1 / 100) * 100

# Reject if rounded position < 80% of min_position intent
if position_shares * close_t1 < min_position_vnd * 0.8:
    action = "REJECT"

# Examples:
# NAV 1B → target_n = floor(sqrt(1B / 100M)) = 3 → round to 5 stocks
# NAV 2B → target_n = floor(sqrt(2B / 100M)) = 4 → round to 5 stocks
# NAV 5B → target_n = floor(sqrt(5B / 100M)) = 7 → round to 10 stocks
```

### 3. Liquidity Filter (PIT-safe, T-1 lag)
```python
# ADV Threshold (stratified by NAV)
if nav_vnd <= 2_000_000_000:
    min_adv20_vnd = 10_000_000_000  # 10B VND (opens ~80-100 names)
else:
    min_adv20_vnd = 20_000_000_000  # 20B VND

# Calculation (PIT-safe)
traded_value_t = close_t * volume_t
adv20_vnd = median(traded_value_{t-19:t}, min_periods=10).shift(1)
# shift(1) ensures T-1 lag for trading day T

# Additional left-tail protection
p20_traded_value_60 = percentile_20(traded_value over prior 60 sessions).shift(1)
require: p20_traded_value_60 >= 0.7 * min_adv20_vnd
```

### 4. Market Cap Filter
```python
min_full_mcap_vnd = 1_000_000_000_000  # 1T VND
min_free_float_mcap_vnd = 300_000_000_000  # 300B VND
free_float_ratio >= 0.10  # 10-15%

# Calculation (PIT-safe)
full_mcap = close_t1 * shares_outstanding_asof_t1
free_float_mcap = full_mcap * free_float_ratio_asof_t1

# Vendor precedence for free-float data
free_float_source = ["VCI", "SSI", "VDSC"]  # Priority order
```

### 5. Price Floor
```python
min_close_price_vnd = 5_000  # Exclude penny stocks
# Use adj_close_t1 or explicitly handle corporate actions
```

### 6. Staleness Filter
```python
# Revised thresholds (Data Scientist Tier-1 tweak)
zero_volume_days_60 <= 5  # Trading days (was 3)
pass_adv_days_60 >= 45
min_trading_history_days = 60

# Alternative: consecutive zero-volume days
consecutive_zero_days <= 2  # Better predictor than total count
```

### 7. Board Lot Rule
```python
board_lot = 100  # shares
rounding = floor(target_shares / 100) * 100
```

### 8. Settlement & Holding
```python
settlement = "T+2.5"
min_holding_period = 3  # days
```

### 9. Price Bands (Limit Lock)
```python
# Exchange-specific limits
HOSE_limit = 0.07  # ±7%
HNX_limit = 0.10  # ±10%

# Rationale: Prevent fill assumptions on limit-up/down days
```

### 10. Foreign Room (Optional)
```python
# Optional filter for institutional compliance
filter_by_foreign_ownership_limit = True  # Default: enabled
exclude_if_foreign_room_remaining < threshold
```

### 11. Execution Slippage Model
```python
# HOSE
slippage_hose = 10  # bps base
impact_hose = impact_bps * sqrt(order_value / adv20_vnd)
total_slippage_hose = slippage_hose + impact_hose

# HNX
slippage_hnx = 20  # bps base
impact_hnx = impact_bps * sqrt(order_value / adv20_vnd)
total_slippage_hnx = slippage_hnx + impact_hnx
```

### 12. Status Exclusions
```python
# Canonical status mapping (Architect requirement)
suspended = ["SUSPENDED", "HALTED"]
restricted = ["RESTRICTED", "CONTROL"]
warning = ["WARNING", "SPECIAL_SURVEILLANCE"]

# Exclude if any status match
exclude = suspended + restricted + warning + ["foreign_room_exhausted"]
```

### 13. Rebalance / Hysteresis
```python
# Eligibility computed daily (data through T-1)
eligibility_snapshot_time = "T-1 market close (15:00 VN time)"

# Rebalance frequency
rebalance_frequency = "weekly_or_monthly"
rebalance_date_weekly = "last_trading_day_of_week"
rebalance_date_monthly = "last_trading_day_of_month"

# Entry/remain thresholds
entry_threshold = 1.0  # 100% of filters
remain_threshold = 0.85  # 85% for liquidity/mcap (avoid turnover)

# Hard-fail filters (no hysteresis)
hard_fail = ["exchange", "suspension", "stale_data", "insufficient_history"]
```

### 14. Limit-Lock Stress Filter
```python
# Exchange-specific thresholds (Data Scientist Tier-1 tweak)
if exchange == "HOSE":
    max_limit_down_hits_60 = 2
    max_total_limit_hits_60 = 5
    max_consecutive_limit_hits_20 = 2
elif exchange == "HNX":
    max_limit_down_hits_60 = 4  # Accept higher volatility (was 2)
    max_total_limit_hits_60 = 7
    max_consecutive_limit_hits_20 = 3

# Detection formula (Architect requirement)
if exchange == "HOSE":
    ref_price = prior_close
    limit_up = close >= ref_price * 1.07
    limit_down = close <= ref_price * 0.93
elif exchange == "HNX":
    ref_price = prior_close
    limit_up = close >= ref_price * 1.10
    limit_down = close <= ref_price * 0.90

# Count over 60 trading days (not calendar days)
limit_down_hits_60 = sum(limit_down over prior 60 trading days)
```

### 15. Capacity / Liquidation Constraint
```python
# Days to liquidate calculation
days_to_liquidate = position_value / adv20_vnd / participation_cap

# Thresholds
max_days_to_liquidate_entry = 3
max_days_to_liquidate_remain = 5

# Stratified by ADV (Data Scientist Tier-2 recommendation)
if adv20_vnd >= 20_000_000_000:
    max_days_to_liquidate_entry = 3
elif adv20_vnd >= 10_000_000_000:
    max_days_to_liquidate_entry = 5
```

### 16. Data Freshness / As-Of Controls
```python
# All inputs point-in-time as-of T-1
eligibility_snapshot = "T-1 market close"

# Fundamental data uses effective_date, not file load date
free_float_effective_date = "as_of_date"
shares_outstanding_effective_date = "as_of_date"

# Corporate actions frozen to PIT state
corporate_action_cutoff = "T-1 close"

# Stale data exclusion
if free_float_age > 180:  # days
    action = "EXCLUDE"
if shares_outstanding_age > 180:
    action = "EXCLUDE"

# Fallback behavior (Architect requirement)
if adv20_unavailable and trading_history >= 60:
    action = "REJECT"  # No fallback, strict PIT-safe
```

### 17. Sector Limit
```python
max_sector_weight = 0.25  # 25% NAV per industry

# Industry taxonomy (Architect requirement)
industry_source = "VCI_LEVEL2_v2026"  # Canonical source

# Sector cap allocator (Architect requirement)
# If breach, rank by liquidity, trim deterministically
if sector_weight > 0.25:
    trim_candidates = rank_by_adv(sector_names)
    remove_lowest_adv_until(sector_weight <= 0.25)
```

---

## Implementation Checklist

### Phase 1: Data Preparation
- [ ] Load market data (HOSE/HNX only)
- [ ] Compute ADV20 (median, min_periods=10, shift(1))
- [ ] Compute p20_traded_value_60 (percentile_20, shift(1))
- [ ] Load market cap, free-float, shares_outstanding (as_of T-1)
- [ ] Load sector mapping (VCI_LEVEL2_v2026)
- [ ] Compute limit-hit counts (60 trading days)
- [ ] Load status codes (suspended/restricted/warning)

### Phase 2: Filter Application
- [ ] Apply exchange filter (HOSE/HNX)
- [ ] Apply status exclusions (hard-fail)
- [ ] Apply staleness filter (zero_volume <=5, pass_adv >=45)
- [ ] Apply price floor (>5,000 VND)
- [ ] Apply market cap filter (full >1T, free-float >300B)
- [ ] Apply liquidity filter (ADV20 >=10-20B, p20 >=0.7*ADV20)
- [ ] Apply limit-lock stress filter (exchange-specific)
- [ ] Apply capacity constraint (days_to_liquidate <=3)
- [ ] Apply sector limit (25% per industry)

### Phase 3: Portfolio Construction
- [ ] Compute NAV-aware portfolio size (sqrt formula)
- [ ] Rank eligible names by alpha/composite score
- [ ] Select top N names (N = target_n)
- [ ] Compute position sizes (with concentration cap)
- [ ] Round to board lots (100 shares)
- [ ] Verify sector weights (<=25% per industry)
- [ ] Compute days_to_liquidate for each position

### Phase 4: Validation
- [ ] Verify no UPCOM names
- [ ] Verify all ADV20 >= threshold
- [ ] Verify all sector weights <= 25%
- [ ] Verify all days_to_liquidate <= 3
- [ ] Verify PIT-safe (all inputs T-1)
- [ ] Export portfolio state

---

## Expected Outcomes (NAV 1B-2B)

| Metric | Target | Rationale |
|:---|:---|:---|
| Portfolio Size | 5 stocks | Conviction mode, 20% per stock |
| Min ADV20 | 10-20B VND | 1% participation for 200-400M position |
| Eligible Universe | 80-100 names | HOSE/HNX mid-caps + large-caps |
| Sector Concentration | ≤25% | Diversification across industries |
| Days to Liquidate | ≤3 days | Exit capacity under stress |
| Exchange | HOSE/HNX only | No UPCOM, no penny stocks |

---

## Approval Record

| Role | Status | Date | Notes |
|:---|:---|:---|:---|
| System Architect (Role 6) | ✅ APPROVED | 2026-05-16 | Production-ready, 6 implementation details added |
| QA Engineer (Role 17) | ✅ APPROVED | 2026-05-16 | PIT-safe, executable, adequate risk controls |
| Data Scientist (Role 14) | ✅ APPROVED | 2026-05-16 | Tier-1 tweaks: ADV 10-20B, zero-volume <=5, HNX limit <=4 |

---

## Version History

- **v1.0** (2026-05-16): Initial draft
- **v1.1** (2026-05-16): Added Architect feedback (4 changes)
- **v1.2 Final** (2026-05-16): Incorporated Data Scientist Tier-1 tweaks + Architect implementation details

---

**Status**: LOCKED for Phase 11 v3 implementation  
**Next Steps**: Code filters, rerun Phase 8-11 pipeline, audit new portfolio
