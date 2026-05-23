# V21 NEUTRALIZATION - QUICK REFERENCE GUIDE

## KEY FILE PATHS (Absolute)

### Primary Implementation
\\\
C:\Users\GHC\.openclaw\workspace\V21_QUANT\src\v21_system\layer_01_core_intelligence\neutralization.py
C:\Users\GHC\.openclaw\workspace\V21_QUANT\src\v21_system\core_intelligence\factor_neutralization.py
C:\Users\GHC\.openclaw\workspace\V21_QUANT\src\v21_system\layer_01_core_intelligence\utils\math.py
C:\Users\GHC\.openclaw\workspace\V21_QUANT\src\v21_system\layer_01_core_intelligence\alpha_preprocessing.py
\\\

### OMEGA Current Implementation
\\\
C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\quant\src\omega\quant\features\neutralization.py
C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\quant\src\omega\quant\features\cross_sectional.py
C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\quant\tests\test_neutralization.py
\\\

### Alternative V21 Implementations
\\\
C:\Users\GHC\.openclaw\workspace\V21_QUANT\src\v21_system\layer_01_core_intelligence\lightweight_neutralization.py
C:\Users\GHC\.openclaw\workspace\V21_QUANT\src\v21_system\layer_01_core_intelligence\neutralization_engine.py
C:\Users\GHC\.openclaw\workspace\V21_QUANT\src\v21_system\core_intelligence\neutralization.py
\\\

---

## REUSABLE PATTERNS SUMMARY

### 1. HIERARCHICAL FALLBACK (5-Tier System)

**Source:** \
eutralization.py\ lines 145-260

**Tiers:**
- L4: Sector × Price × Liquidity (min 5 stocks)
- L3: Sector × Price (min 5 stocks)
- L2: Sector only (min 10 stocks)
- L1: Exchange (min 3 stocks) - VN market specific
- L0: Global cross-sectional (no minimum)

**Key Method:**
\\\python
NeutralizationEngine.neutralize_cross_section(
    alpha, sector, price_level, liquidity_bucket, exchange
)
\\\

---

### 2. FAMA-FRENCH 3-FACTOR MODEL

**Source:** \actor_neutralization.py\ lines 31-205

**Factors:**
- Market (VNI): Market excess return
- SMB: Small minus Big (size premium)
- HML: High minus Low (value premium)

**Key Methods:**
\\\python
FactorNeutralizer.neutralize(features: Dict[str, np.ndarray])
FactorNeutralizer.get_exposures(features: Dict[str, np.ndarray])
RollingFactorNeutralizer.neutralize(features, start_idx)
\\\

---

### 3. VECTORIZED UTILITIES

**Source:** \utils/math.py\ lines 16-289

**Functions:**
- \winsorize(series, lower=0.01, upper=0.99)\ - Lines 16-48
- \zscore(series, epsilon=1e-9)\ - Lines 51-83
- \cross_sectional_zscore(group, epsilon=1e-9)\ - Lines 263-289
- \olling_zscore(series, window, min_periods)\ - Lines 85-122
- \safe_divide(num, den, fill_value=0.0)\ - Lines 229-260

---

### 4. PREPROCESSING PIPELINE

**Source:** \lpha_preprocessing.py\ lines 193-260

**Pipeline:**
1. Sanitize OHLCV (winsorize raw data)
2. Normalize signals (z-score)
3. Neutralize (hierarchical fallback)

**Key Method:**
\\\python
AlphaPreprocessor.neutralize_signals(
    df, alpha_cols, date_col, symbol_col
)
\\\

---

## IMPLEMENTATION SNIPPETS

### Hierarchical Fallback Core Logic

\\\python
# Step 1: Winsorize
alpha_winsorized, _ = winsorize(alpha, 0.01, 0.99)

# Step 2: Try L4 (most specific)
neutralized_mask = pd.Series(False, index=alpha.index)
l4_key = sector + '_' + price_level + '_' + liquidity_bucket

for bucket, group_idx in l4_key.groupby(l4_key).groups.items():
    if len(group_idx) >= min_l4_size:
        result[group_idx] = cross_sectional_zscore(alpha_winsorized[group_idx])
        neutralized_mask[group_idx] = True

# Step 3: Fallback to L3 for remaining
remaining = ~neutralized_mask
l3_key = sector[remaining] + '_' + price_level[remaining]
# ... repeat pattern

# Step 4: Fallback to L2 (sector only)
# Step 5: Fallback to L1 (exchange)
# Step 6: Fallback to L0 (global)
\\\

### Fama-French Neutralization

\\\python
# Build factor matrix
X = np.column_stack([market_returns, smb_returns, hml_returns])

# OLS regression
X_with_intercept = np.column_stack([np.ones(len(X)), X])
XtX = X_with_intercept.T @ X_with_intercept
XtX += np.eye(XtX.shape[0]) * 1e-8  # Regularization
beta = np.linalg.solve(XtX, X_with_intercept.T @ y)

# Compute residuals
feature_pred = beta[1] * market + beta[2] * smb + beta[3] * hml
neutralized = feature - feature_pred
\\\

### Cross-Sectional Z-Score

\\\python
def cross_sectional_zscore(group: pd.Series, epsilon: float = 1e-9):
    mean = group.mean()
    std = group.std()
    
    if pd.isna(mean) or pd.isna(std) or std < epsilon:
        return pd.Series(0.0, index=group.index)
    
    return (group - mean) / (std + epsilon)
\\\

---

## PIT SAFETY CHECKLIST

✅ **T-1 Lag:** All market data lagged by 1 day
✅ **Cross-Sectional:** Process per date (no temporal leakage)
✅ **Index Preservation:** Maintain original index
✅ **NaN Handling:** Preserve NaN patterns
✅ **No Look-Ahead:** Use only past data for rolling operations

---

## INTEGRATION PRIORITY

### HIGH PRIORITY (Core Utilities)
1. \cross_sectional_zscore\ - Already needed, simple port
2. Enhanced \winsorize\ - Add percentile method
3. \safe_divide\ - Utility for robust calculations

### MEDIUM PRIORITY (Hierarchical Neutralization)
1. 3-tier fallback: Sector×Price → Sector → Global
2. \
eutralize_cross_section\ method
3. Fallback statistics tracking

### LOWER PRIORITY (Advanced Features)
1. Fama-French 3-factor model
2. Rolling factor neutralization
3. Neutralization quality metrics

---

## TESTING PATTERNS

### Edge Cases to Test
- Zero variance (all values identical)
- Insufficient data (< min_size)
- NaN values (preserve patterns)
- Single stock per group
- Collinear factors

### Validation Checks
- Cross-sectional integrity (no temporal leakage)
- Index alignment (input == output)
- Zero mean per date (after neutralization)
- Signal preservation (correlation with raw signal)

---

## SEARCH STATISTICS

- **Total Files Found:** 8 neutralization-related Python files
- **Primary Implementation:** 633 lines (unified engine)
- **Factor Model:** 318 lines (Fama-French)
- **Utilities:** 384 lines (math functions)
- **Tests:** 528 lines (OMEGA) + V21 test files
- **Total Matches:** 1642+ occurrences of "neutraliz" pattern

---

## NEXT STEPS

1. **Review** detailed report: \21_neutralization_findings.md\
2. **Read** primary implementation: \
eutralization.py\ (633 lines)
3. **Study** factor model: \actor_neutralization.py\ (318 lines)
4. **Port** core utilities: \utils/math.py\ functions
5. **Adapt** hierarchical fallback for OMEGA_QUANT
6. **Test** with OMEGA's existing test suite

---

**Report Generated:** 2026-05-13T09:37:42Z
**Search Scope:** V21_QUANT + OMEGA_QUANT directories
**Status:** ✅ COMPLETE - Ready for implementation
