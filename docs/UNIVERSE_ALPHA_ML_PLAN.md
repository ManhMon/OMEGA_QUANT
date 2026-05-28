# PHƯƠNG ÁN TỔNG HỢP: Alpha-Aware Universe + ML Combination
# Kết hợp Phương án 3 + 5 + Priority 1
# Ngày: 2026-05-28
# Status: PENDING IMPLEMENTATION

## TỔNG QUAN

Kết hợp 3 yếu tố:
- **Phương án 3**: Alpha-Aware Universe Selection (chọn mã có IC contribution cao)
- **Phương án 5**: ML Universe Selection (XGBoost predict mã nào có IC > 0)
- **Priority 1**: ML-based Alpha Combination (thay equal weight bằng Ridge/XGBoost)

## ALPHA INVENTORY (94+ signals available)

### ultimate_alpha_arsenal.py (79 functions):
- 11 VN-specific: T+2 settlement, limit-lock, foreign flow, penny trap
- 20+ microstructure: VWAP deviation, order flow, smart money
- 15+ volatility: Garman-Klass, Yang-Zhang, Parkinson, Bollinger
- 10+ momentum: acceleration, RSI divergence, turtle traders
- 10+ volume/liquidity: Amihud, OBV, turnover exhaustion

### Other modules (15 functions):
- core_alphas.py: 13 core alphas (shift(1) PIT safe)
- phase34_microstructure_alphas.py: 7 microstructure
- vn_alphas.py: 5 VN-specific
- macro_alphas.py: 5 macro factors

## KIẾN TRÚC MỚI

```
Phase 1: Load ALL data (1501 tickers)
    ↓
Phase 2: Compute ALL 94+ alphas on full dataset (vectorized)
    ↓
Phase 3: ML Universe Selection
    - Per-ticker trailing IC for each alpha
    - XGBoost predicts: which tickers will have IC > 0 next quarter?
    - Select top 30 by predicted IC contribution
    - Hard floor: ADV >= 2B VND
    ↓
Phase 4: ML Alpha Combination (per universe)
    - Ridge regression: optimal alpha weights (not equal)
    - Train on validation set
    - Regularization prevents overfitting
    ↓
Phase 5: Portfolio Construction
    - Composite signal = weighted sum of alphas (ML weights)
    - Risk guard: 25% concentration, 40% ADV
    ↓
Phase 6: Execution + Attribution
```

## IMPLEMENTATION STEPS

### Step 1: Compute all 94+ alphas
- Wire `compute_ultimate_alphas()` from ultimate_alpha_arsenal.py
- Apply T-1 shift to all
- Cross-sectional z-score

### Step 2: Per-ticker IC computation
- For each ticker × alpha: compute trailing 60-day IC
- Store as matrix: (ticker, alpha) → IC value

### Step 3: ML Universe Selection
- Features: [ADV, volatility, market_cap, mean_IC_last_60d, n_positive_IC_alphas]
- Target: mean_IC_next_quarter > 0
- Model: XGBoost classifier
- Output: probability of being "alpha-rich" ticker
- Select: top 30 by probability, floor ADV >= 2B

### Step 4: ML Alpha Combination
- For selected universe, train Ridge regression:
  - X = alpha signals (94 columns)
  - y = fwd_ret_5
  - Train on train+val period
  - Output: optimal weights per alpha
- Apply weights to create composite signal

### Step 5: Walk-forward with quarterly universe refresh
- Every quarter: re-run Steps 3-4
- Universe changes based on predicted IC
- Alpha weights update based on recent performance

## EXPECTED RESULTS

| Metric | Current (U20 equal-weight) | Target (ML combo) |
|--------|---------------------------|-------------------|
| Sharpe | 1.93 | 2.5-3.0 |
| Alphas active | 3 | 15-30 |
| Universe | Fixed 20 | Dynamic 30 (ML-selected) |
| Alpha weights | Equal | ML-optimized |
| Diversification | Low | High |

## RISKS

1. Overfitting: 94 alphas on 20 tickers = overfit risk → need strong regularization
2. Compute time: 94 alphas × 1501 tickers × 11 years = heavy → need vectorization
3. Complexity: More moving parts → harder to debug
4. Mitigation: Purged CV + embargo + L2 regularization + walk-forward validation
