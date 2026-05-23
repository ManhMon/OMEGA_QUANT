# V21 NEUTRALIZATION LOGIC - REUSABLE PATTERNS FOUND

**Search Date:** 2026-05-13
**Search Scope:** V21_QUANT directory structure
**Target:** Neutralization logic for OMEGA_QUANT reuse

---

## EXECUTIVE SUMMARY

Found **comprehensive neutralization implementations** in V21_QUANT with the following reusable patterns:

1. **Hierarchical Fallback Neutralization** (4-5 tier system)
2. **Fama-French 3-Factor Model** (Market, SMB, HML)
3. **Cross-Sectional Z-Score** (vectorized, PIT-safe)
4. **Winsorization** (1%/99% percentile clipping)
5. **Sector/Industry/Market Hierarchy** (with exchange-level fallback)

---

## KEY FILES IDENTIFIED

### Primary Implementation Files

1. **V21_QUANT/src/v21_system/layer_01_core_intelligence/neutralization.py** (633 lines)
   - Unified neutralization engine (consolidated from 3 modules)
   - Status: Production Implementation (2026-05-05)
   - Features: 5-tier hierarchical fallback (L4→L3→L2→L1→L0)

2. **V21_QUANT/src/v21_system/core_intelligence/factor_neutralization.py** (318 lines)
   - Fama-French 3-factor model implementation
   - Cross-sectional factor neutralization
   - Rolling window factor neutralization

3. **V21_QUANT/src/v21_system/layer_01_core_intelligence/alpha_preprocessing.py** (369 lines)
   - Preprocessing pipeline with neutralization integration
   - Winsorization → Z-score → Neutralization

4. **V21_QUANT/src/v21_system/layer_01_core_intelligence/utils/math.py** (384 lines)
   - Core math utilities: winsorize, zscore, cross_sectional_zscore
   - 100% vectorized implementations

5. **OMEGA_QUANT/packages/quant/src/omega/quant/features/neutralization.py** (427 lines)
   - OMEGA's current neutralization module
   - Implements: winsorize, market_neutralize, factor_neutralize

---

## HIERARCHICAL FALLBACK PATTERN (V21 5-TIER SYSTEM)

### Architecture

**Tier L4 (Most Specific):** Sector × Price-Level × Liquidity-Bucket
- Minimum size: 5 stocks
- Use case: Fine-grained neutralization for liquid stocks

**Tier L3 (Specific):** Sector × Price-Level
- Minimum size: 5 stocks
- Use case: When liquidity bucket too granular

**Tier L2 (Broad):** Sector-only
- Minimum size: 10 stocks
- Use case: Small sectors without price differentiation

**Tier L1 (Exchange):** Exchange-level (HOSE/HNX/UPCOM)
- Minimum size: 3 stocks
- Use case: VN market-specific fallback

**Tier L0 (Global):** Market-wide cross-sectional Z-score
- No minimum
- Use case: Final fallback for all remaining stocks

### Implementation Pattern

\\\python
# From V21_QUANT/src/v21_system/layer_01_core_intelligence/neutralization.py

class NeutralizationEngine:
    def neutralize_cross_section(self, alpha, sector, price_level, 
                                  liquidity_bucket=None, exchange=None):
        # Step 1: Winsorize (1%/99%)
        alpha_winsorized, _ = winsorize(alpha, 0.01, 0.99)
        
        # Step 2: Try L4 (Sector × Price × Liquidity)
        if liquidity_bucket is not None:
            l4_key = sector + '_' + price_level + '_' + liquidity_bucket
            for bucket, group_idx in l4_key.groupby(l4_key).groups.items():
                if len(group_idx) >= min_l4_size:
                    result[group_idx] = cross_sectional_zscore(alpha[group_idx])
                    neutralized_mask[group_idx] = True
        
        # Step 3: Try L3 (Sector × Price) for remaining
        remaining = ~neutralized_mask
        l3_key = sector[remaining] + '_' + price_level[remaining]
        for bucket, group_idx in l3_key.groupby(l3_key).groups.items():
            if len(group_idx) >= min_l3_size:
                result[group_idx] = cross_sectional_zscore(alpha[group_idx])
                neutralized_mask[group_idx] = True
        
        # Step 4: Try L2 (Sector-only) for remaining
        remaining = ~neutralized_mask
        for sector_label in sector[remaining].unique():
            sector_idx = (sector == sector_label) & remaining
            if len(sector_idx) >= min_l2_size:
                result[sector_idx] = cross_sectional_zscore(alpha[sector_idx])
                neutralized_mask[sector_idx] = True
        
        # Step 5: Try L1 (Exchange) for remaining (VN-specific)
        remaining = ~neutralized_mask
        if exchange is not None:
            for exchange_label in exchange[remaining].unique():
                exchange_idx = (exchange == exchange_label) & remaining
                if len(exchange_idx) >= min_exchange_size:
                    result[exchange_idx] = cross_sectional_zscore(alpha[exchange_idx])
                    neutralized_mask[exchange_idx] = True
        
        # Step 6: L0 (Global) for all remaining
        remaining = ~neutralized_mask
        if remaining.any():
            result[remaining] = cross_sectional_zscore(alpha[remaining])
        
        return result, stats
\\\

---

## FAMA-FRENCH 3-FACTOR MODEL

### Implementation

\\\python
# From V21_QUANT/src/v21_system/core_intelligence/factor_neutralization.py

class FactorNeutralizer:
    \"\"\"
    Fama-French 3-factor model for Vietnam market:
    - Market (VNI): Market excess return
    - Size (SMB): Small minus Big
    - Value (HML): High minus Low
    \"\"\"
    
    def __init__(self, market_returns, smb_returns, hml_returns):
        self.market_returns = np.asarray(market_returns)
        self.smb_returns = np.asarray(smb_returns)
        self.hml_returns = np.asarray(hml_returns)
    
    def neutralize(self, features: Dict[str, np.ndarray]):
        # Build factor matrix
        X = np.column_stack([self.market_returns, self.smb_returns, self.hml_returns])
        
        neutralized = {}
        for feat_name, feat_values in features.items():
            # OLS regression: feature = alpha + beta_market*Market + beta_smb*SMB + beta_hml*HML
            betas, r2 = self._regress(feat_values, X)
            
            # Predicted feature from factors
            feature_pred = (betas[0] * self.market_returns + 
                           betas[1] * self.smb_returns + 
                           betas[2] * self.hml_returns)
            
            # Residual = factor-neutral feature
            neutralized[feat_name] = feat_values - feature_pred
        
        return neutralized
    
    def _regress(self, y, X):
        # Add intercept
        X_with_intercept = np.column_stack([np.ones(len(X)), X])
        
        # OLS: beta = (X'X)^-1 X'y
        XtX = X_with_intercept.T @ X_with_intercept
        Xty = X_with_intercept.T @ y
        XtX += np.eye(XtX.shape[0]) * 1e-8  # Regularization
        beta = np.linalg.solve(XtX, Xty)
        
        # R-squared
        y_pred = X_with_intercept @ beta
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-10 else 0.0
        
        return beta[1:], r2  # Skip intercept
\\\

---

## VECTORIZED IMPLEMENTATIONS

### Cross-Sectional Z-Score (100% Vectorized)

\\\python
# From V21_QUANT/src/v21_system/layer_01_core_intelligence/utils/math.py

def cross_sectional_zscore(group: pd.Series, epsilon: float = 1e-9) -> pd.Series:
    \"\"\"
    Cross-sectional z-score normalization within a group.
    Standardizes values within a single cross-section (e.g., all stocks on one date).
    \"\"\"
    mean = group.mean()
    std = group.std()
    
    # Handle edge cases
    if pd.isna(mean) or pd.isna(std) or std < epsilon:
        return pd.Series(0.0, index=group.index)
    
    return (group - mean) / (std + epsilon)
\\\

### Winsorization (100% Vectorized)

\\\python
def winsorize(series: pd.Series, 
              lower_percentile: float = 0.01,
              upper_percentile: float = 0.99) -> Tuple[pd.Series, int]:
    \"\"\"Winsorize at specified percentiles (1%/99% default).\"\"\"
    lower = series.quantile(lower_percentile)
    upper = series.quantile(upper_percentile)
    
    series_winsorized = series.clip(lower=lower, upper=upper)
    winsorized_count = (series != series_winsorized).sum()
    
    return series_winsorized, winsorized_count
\\\

---

## PIT SAFETY PATTERNS

### Key Principles from V21

1. **T-1 Lag Enforcement:** All market data (price, volume, sector) must be lagged by 1 day
2. **Cross-Sectional Operations:** Neutralization per date to avoid temporal leakage
3. **Index Preservation:** Maintain original index after neutralization
4. **NaN Handling:** Preserve NaN patterns (no information leakage)

### Example Pattern

\\\python
# From V21_QUANT/src/v21_system/layer_01_core_intelligence/neutralization.py

def neutralize_panel(self, panel: pd.DataFrame, alpha_cols: List[str]):
    \"\"\"Neutralize multiple alpha columns across all dates (100% vectorized).\"\"\"
    result = panel.copy()
    
    # Process per-date to avoid look-ahead bias
    for date in panel.index.get_level_values('date').unique():
        date_data = panel.loc[date]
        
        # Apply hierarchical neutralization (cross-sectional)
        neutral_values, _ = self.neutralize_cross_section(
            alpha=date_data[alpha_col],
            sector=date_data['sector'],
            price_level=date_data['price_bucket'],
            liquidity_bucket=date_data.get('liquidity_bucket'),
            exchange=date_data.get('exchange')
        )
        
        # Assign back to panel
        result.loc[date, f'{alpha_col}_neutral'] = neutral_values
    
    return result
\\\

---

## REUSABLE COMPONENTS FOR OMEGA_QUANT

### 1. Hierarchical Fallback Logic
**File:** \V21_QUANT/src/v21_system/layer_01_core_intelligence/neutralization.py\
**Lines:** 145-260 (neutralize_cross_section method)
**Reusability:** HIGH - Can be adapted to any market with sector/industry hierarchy

### 2. Fama-French 3-Factor Model
**File:** \V21_QUANT/src/v21_system/core_intelligence/factor_neutralization.py\
**Lines:** 31-205 (FactorNeutralizer class)
**Reusability:** HIGH - Standard factor model, market-agnostic

### 3. Cross-Sectional Z-Score
**File:** \V21_QUANT/src/v21_system/layer_01_core_intelligence/utils/math.py\
**Lines:** 263-289 (cross_sectional_zscore function)
**Reusability:** VERY HIGH - Core utility, already vectorized

### 4. Winsorization
**File:** \V21_QUANT/src/v21_system/layer_01_core_intelligence/utils/math.py\
**Lines:** 16-48 (winsorize function)
**Reusability:** VERY HIGH - Standard preprocessing, already in OMEGA

### 5. Rolling Factor Neutralization
**File:** \V21_QUANT/src/v21_system/layer_01_core_intelligence/neutralization.py\
**Lines:** 35-93 (RollingFactorNeutralizer class)
**Reusability:** HIGH - Useful for time-series factor neutralization

---

## COMPARISON: V21 vs OMEGA_QUANT

| Feature | V21_QUANT | OMEGA_QUANT (Current) |
|---------|-----------|----------------------|
| Hierarchical Fallback | 5-tier (L4→L0) | Not implemented |
| Factor Model | Fama-French 3-factor | Basic factor_neutralize |
| Winsorization | 1%/99% percentile | std/percentile methods |
| Cross-Sectional Z-Score | Dedicated utility | Not exposed |
| Sector Neutralization | Multi-tier with fallback | Not implemented |
| PIT Safety | Strict T-1 lag enforcement | Basic index preservation |
| Vectorization | 100% pandas/numpy | 100% pandas/numpy |
| Market-Specific Fallback | Exchange-level (VN) | Not implemented |

---

## RECOMMENDED INTEGRATION STRATEGY

### Phase 1: Core Utilities (Low Risk)
1. Port \cross_sectional_zscore\ from V21 utils/math.py
2. Enhance OMEGA's \winsorize\ with V21's percentile logic
3. Add \safe_divide\ and \demean\ utilities

### Phase 2: Hierarchical Neutralization (Medium Risk)
1. Implement 3-tier fallback: Sector×Price → Sector → Global
2. Add \
eutralize_cross_section\ method to OMEGA's neutralization module
3. Integrate with existing \atch_neutralize\

### Phase 3: Factor Model Enhancement (Medium Risk)
1. Port \FactorNeutralizer\ class from V21
2. Add \RollingFactorNeutralizer\ for time-series neutralization
3. Expose factor exposures via \get_exposures\ method

### Phase 4: Advanced Features (Higher Risk)
1. Add market-specific fallback logic (configurable)
2. Implement neutralization quality metrics
3. Add validation checks (cross-sectional integrity, NaN preservation)

---

## KEY IMPLEMENTATION PATTERNS

### Pattern 1: Hierarchical Fallback with Tracking

\\\python
neutralized_mask = pd.Series(False, index=alpha.index)
fallback_stats = {'tier1': 0, 'tier2': 0, 'tier3': 0}

# Try Tier 1
for group in tier1_groups:
    if len(group) >= min_tier1_size:
        result[group] = neutralize(alpha[group])
        neutralized_mask[group] = True
        fallback_stats['tier1'] += len(group)

# Try Tier 2 for remaining
remaining = ~neutralized_mask
for group in tier2_groups[remaining]:
    if len(group) >= min_tier2_size:
        result[group] = neutralize(alpha[group])
        neutralized_mask[group] = True
        fallback_stats['tier2'] += len(group)

# Global fallback for all remaining
remaining = ~neutralized_mask
if remaining.any():
    result[remaining] = neutralize(alpha[remaining])
    fallback_stats['tier3'] += remaining.sum()
\\\

### Pattern 2: PIT-Safe Cross-Sectional Processing

\\\python
# Process per date to avoid temporal leakage
for date in df.index.get_level_values('date').unique():
    date_data = df.loc[date]  # Single cross-section
    
    # Apply neutralization (uses only current date's data)
    neutral_values = neutralize_cross_section(
        alpha=date_data['alpha'],
        sector=date_data['sector'],
        price_level=date_data['price_bucket']
    )
    
    # Assign back (maintains T-1 lag if input was lagged)
    df.loc[date, 'alpha_neutral'] = neutral_values
\\\

### Pattern 3: Robust OLS with Regularization

\\\python
# Add small regularization for numerical stability
XtX = X.T @ X
XtX += np.eye(XtX.shape[0]) * 1e-8

try:
    beta = np.linalg.solve(XtX, X.T @ y)
except np.linalg.LinAlgError:
    # Fallback to pseudo-inverse
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
\\\

---

## FILES TO REVIEW FOR DETAILED IMPLEMENTATION

1. **V21_QUANT/src/v21_system/layer_01_core_intelligence/neutralization.py**
   - Lines 96-260: NeutralizationEngine.neutralize_cross_section
   - Lines 261-319: NeutralizationEngine.neutralize_panel
   - Lines 390-544: FactorNeutralizer class

2. **V21_QUANT/src/v21_system/core_intelligence/factor_neutralization.py**
   - Lines 31-205: FactorNeutralizer (standalone version)
   - Lines 207-318: RollingFactorNeutralizer

3. **V21_QUANT/src/v21_system/layer_01_core_intelligence/utils/math.py**
   - Lines 16-48: winsorize
   - Lines 51-83: zscore
   - Lines 263-289: cross_sectional_zscore

4. **V21_QUANT/src/v21_system/layer_01_core_intelligence/alpha_preprocessing.py**
   - Lines 193-260: neutralize_signals (integration example)

---

## TESTING COVERAGE

V21 has comprehensive test coverage:
- \	ests/test_neutralization_engine.py\
- \	ests/layer_01_core_intelligence/test_neutralization_full.py\
- \OMEGA_QUANT/packages/quant/tests/test_neutralization.py\ (528 lines)

Test patterns include:
- Edge cases (zero variance, NaN, insufficient data)
- PIT safety validation
- Index preservation
- Vectorization verification
- Cross-sectional integrity checks

---

## CONCLUSION

V21_QUANT contains **production-ready, institutional-grade neutralization logic** with:

✅ **Hierarchical fallback** (5-tier: Sector×Price×Liquidity → Sector×Price → Sector → Exchange → Global)
✅ **Fama-French 3-factor model** (Market, SMB, HML)
✅ **100% vectorized** implementations (pandas/numpy)
✅ **PIT-safe** operations (T-1 lag enforcement, cross-sectional processing)
✅ **Robust error handling** (zero variance, NaN, collinearity)
✅ **Comprehensive testing** (edge cases, validation, integrity checks)

**Recommendation:** Port hierarchical fallback logic and factor model to OMEGA_QUANT, adapting the 5-tier system to a configurable 3-4 tier system suitable for general markets.

---

**End of Report**
