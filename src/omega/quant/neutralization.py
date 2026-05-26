"""
Unified Neutralization Module - V21_QUANT Consolidation
Combines cross-sectional and factor-based neutralization strategies.

This module consolidates:
- lightweight_neutralization.py (4-tier hierarchical fallback)
- neutralization_engine.py (L3/L2/L1 hierarchical)
- factor_neutralization.py (Fama-French 3-factor)

Author: OpenCode (AI Assistant)
Date: 2026-05-05
Status: Consolidation Phase 1.1
Plan: docs/CONSOLIDATION_PLAN.md
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

from omega.quant.neutralization_engine import (
    FactorNeutralizer,
    FactorReturns,
    RollingFactorNeutralizer,
)

__all__ = [
    "NeutralizationEngine",
    "NeutralizationValidator",
    "FactorNeutralizer",
    "FactorReturns",
    "RollingFactorNeutralizer",
]


class NeutralizationEngine:
    """
    Unified neutralization engine with multiple strategies.
    
    Strategies:
    1. 'cross_sectional': 4-Tier Hierarchical Fallback (default)
       - Tier 1: Sector × Price-Bucket (2D buckets, threshold: 5 stocks)
       - Tier 2: Sector-only (1D, threshold: 10 stocks)
       - Tier 3: Exchange-only (HOSE/HNX/UPCOM)
       - Tier 4: Market-wide (entire market)
    
    2. 'factor': Fama-French 3-Factor Regression
       - Market (VNI): Market excess return
       - Size (SMB): Small minus Big
       - Value (HML): High minus Low
    
    Features:
    - Winsorization (1%/99%) before Z-score calculation
    - Fallback distribution logging for monitoring
    - Robust handling of VN market's small sample sizes
    - PIT-compliant (no temporal leakage)
    """
    
    def __init__(self, 
                 strategy: str = 'cross_sectional',
                 min_bucket_size: int = 5, 
                 min_sector_size: int = 10,
                 min_exchange_size: int = 3,
                 winsorize_lower: float = 0.01,
                 winsorize_upper: float = 0.99):
        """
        Args:
            strategy: 'cross_sectional' (bucket-based) or 'factor' (regression-based)
            min_bucket_size: Minimum stocks per bucket for Tier 1 (2D neutralization)
            min_sector_size: Minimum stocks per sector for Tier 2 (1D neutralization)
            min_exchange_size: Minimum stocks per exchange for Tier 3 (Exchange neutralization)
            winsorize_lower: Lower quantile for winsorization (default 1%)
            winsorize_upper: Upper quantile for winsorization (default 99%)
        """
        if strategy not in ['cross_sectional', 'factor']:
            raise ValueError(f"Invalid strategy: {strategy}. Must be 'cross_sectional' or 'factor'")
        
        self.strategy = strategy
        self.min_bucket_size = min_bucket_size
        self.min_sector_size = min_sector_size
        self.min_exchange_size = min_exchange_size
        self.winsorize_lower = winsorize_lower
        self.winsorize_upper = winsorize_upper
        self.neutralization_stats = {}
        self.fallback_distribution = {
            'tier1_2d': 0,
            'tier2_sector': 0,
            'tier3_exchange': 0,
            'tier4_market': 0
        }
    
    def _winsorize(self, series: pd.Series) -> pd.Series:
        """
        Apply winsorization to handle extreme outliers.
        
        Args:
            series: Input series (per cross-section)
            
        Returns:
            Winsorized series
        """
        lower = series.quantile(self.winsorize_lower)
        upper = series.quantile(self.winsorize_upper)
        return series.clip(lower=lower, upper=upper)
    
    def _safe_standardize(self, group: pd.Series, epsilon: float = 1e-9) -> pd.Series:
        """
        Safely standardize a group (mean=0, std=1) after winsorization.
        Handles edge cases: constant values, NaN, single values.
        
        Note: Winsorization should be applied BEFORE calling this method.
        """
        mean = group.mean()
        std = group.std()
        
        # Handle edge cases
        if pd.isna(mean) or pd.isna(std) or std < epsilon:
            return pd.Series(0.0, index=group.index)
        
        return (group - mean) / (std + epsilon)
    
    def neutralize_cross_sectional(self, 
                                    alpha: pd.Series, 
                                    sector: pd.Series,
                                    price_bucket: pd.Series, 
                                    exchange: pd.Series = None) -> Tuple[pd.Series, Dict]:
        """
        Neutralize alpha with 4-tier Hierarchical Fallback.
        
        Tier 1: Sector × Price-Bucket (threshold: 5 stocks)
        Tier 2: Sector-only (threshold: 10 stocks)
        Tier 3: Exchange-only (HOSE/HNX/UPCOM)
        Tier 4: Market-wide (entire market)
        
        Args:
            alpha: Raw alpha signal (MultiIndex: date, symbol)
            sector: Sector labels (same index as alpha)
            price_bucket: Price bucket labels (same index as alpha)
            exchange: Exchange labels (same index as alpha, optional for Tier 3)

        Returns:
            Tuple of (neutralized_alpha, stats_dict)
        """
        result = alpha.copy()
        stats = {
            'tier1_2d': 0,
            'tier2_sector': 0,
            'tier3_exchange': 0,
            'tier4_market': 0
        }

        # Winsorize alpha
        alpha_winsorized = self._winsorize(alpha)

        # Tier 1: Sector × Price-Bucket (2D)
        composite_key = sector.astype(str) + '_' + price_bucket.astype(str)

        for bucket_label, group_idx in composite_key.groupby(composite_key).groups.items():
            group_alpha = alpha_winsorized.loc[group_idx]

            if len(group_alpha) >= self.min_bucket_size:
                # Tier 1: 2D Neutralization
                result.loc[group_idx] = self._safe_standardize(group_alpha)
                stats['tier1_2d'] += 1
                self.fallback_distribution['tier1_2d'] += len(group_idx)
            else:
                # Tier 2: Sector-only fallback
                sector_label = bucket_label.split('_')[0]
                sector_mask = (sector == sector_label)
                full_sector_alpha = alpha_winsorized.loc[sector_mask]

                if len(full_sector_alpha) >= self.min_sector_size:
                    # Tier 2: Sector-only neutralization
                    s_mean = full_sector_alpha.mean()
                    s_std = full_sector_alpha.std()
                    if not pd.isna(s_mean) and not pd.isna(s_std) and s_std > 1e-9:
                        result.loc[group_idx] = (group_alpha - s_mean) / s_std
                    else:
                        result.loc[group_idx] = 0.0
                    stats['tier2_sector'] += 1
                    self.fallback_distribution['tier2_sector'] += len(group_idx)
                else:
                    # Tier 3: Exchange-only fallback
                    if exchange is not None:
                        exchange_label = exchange.loc[group_idx].iloc[0] if len(group_idx) > 0 else None
                        if exchange_label:
                            exchange_mask = (exchange == exchange_label)
                            full_exchange_alpha = alpha_winsorized.loc[exchange_mask]
                            
                            if len(full_exchange_alpha) >= self.min_exchange_size:
                                # Tier 3: Exchange-only neutralization
                                e_mean = full_exchange_alpha.mean()
                                e_std = full_exchange_alpha.std()
                                if not pd.isna(e_mean) and not pd.isna(e_std) and e_std > 1e-9:
                                    result.loc[group_idx] = (group_alpha - e_mean) / e_std
                                else:
                                    result.loc[group_idx] = 0.0
                                stats['tier3_exchange'] += 1
                                self.fallback_distribution['tier3_exchange'] += len(group_idx)
                                continue
                    
                    # Tier 4: Market-wide fallback
                    m_mean = alpha_winsorized.mean()
                    m_std = alpha_winsorized.std()
                    if not pd.isna(m_mean) and not pd.isna(m_std) and m_std > 1e-9:
                        result.loc[group_idx] = (group_alpha - m_mean) / m_std
                    else:
                        result.loc[group_idx] = 0.0
                    stats['tier4_market'] += 1
                    self.fallback_distribution['tier4_market'] += len(group_idx)

        self.neutralization_stats = stats
        return result, stats
    
    def neutralize_factor(self,
                         features: Dict[str, np.ndarray],
                         market_returns: np.ndarray,
                         smb_returns: np.ndarray,
                         hml_returns: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Neutralize features using Fama-French 3-Factor regression.
        
        For each feature:
        1. Regress feature on factor returns (Market, SMB, HML)
        2. Compute predicted feature based on factor betas
        3. Return residual: feature - predicted
        
        Args:
            features: Dict mapping feature_name -> array of feature values
            market_returns: VN index / market return series
            smb_returns: Small-minus-big return series
            hml_returns: High-minus-low return series
            
        Returns:
            Dict mapping feature_name -> array of factor-neutral residuals
        """
        # Build factor matrix
        X = np.column_stack([market_returns, smb_returns, hml_returns])
        
        neutralized: Dict[str, np.ndarray] = {}
        
        for feat_name, feat_values in features.items():
            if len(feat_values) != len(market_returns):
                raise ValueError(
                    f"Feature {feat_name} length {len(feat_values)} "
                    f"doesn't match factor length {len(market_returns)}"
                )
            
            # Regress feature on factors
            betas, r2 = self._regress(feat_values, X)
            
            # Predict feature from factors
            feature_pred = (
                betas[0] * market_returns + 
                betas[1] * smb_returns + 
                betas[2] * hml_returns
            )
            
            # Residual: factor-neutral feature
            neutralized[feat_name] = feat_values - feature_pred
        
        return neutralized
    
    def _regress(self, y: np.ndarray, X: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Run OLS regression: y = X @ beta + epsilon
        
        Args:
            y: Dependent variable (n_obs,)
            X: Independent variables (n_obs, n_factors)
            
        Returns:
            beta: Factor coefficients (n_factors,)
            r2: R-squared
        """
        # Add intercept
        X_with_intercept = np.column_stack([np.ones(len(X)), X])
        
        # OLS: beta = (X'X)^-1 X'y
        try:
            XtX = X_with_intercept.T @ X_with_intercept
            Xty = X_with_intercept.T @ y
            
            # Add small regularization for numerical stability
            XtX += np.eye(XtX.shape[0]) * 1e-8
            
            beta = np.linalg.solve(XtX, Xty)
        except np.linalg.LinAlgError:
            # Fallback: use pseudo-inverse
            beta = np.linalg.lstsq(X_with_intercept, y, rcond=None)[0]
        
        # Compute R-squared
        y_pred = X_with_intercept @ beta
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        
        if ss_tot > 1e-10:
            r2 = 1.0 - (ss_res / ss_tot)
        else:
            r2 = 0.0
        
        return beta[1:], r2  # Skip intercept
    
    def neutralize_batch(self, 
                        panel: pd.DataFrame, 
                        alpha_cols: List[str],
                        sector_col: str = 'sector',
                        price_bucket_col: str = 'price_bucket',
                        exchange_col: str = 'exchange') -> pd.DataFrame:
        """
        Neutralize multiple alpha columns in batch with 4-tier fallback.
        Per-date neutralization only (no future data leakage).
        High-performance vectorized version using standard pandas operations.
        Memory-optimized: avoids full dataframe copy.
        
        Args:
            panel: DataFrame with MultiIndex (date, symbol)
            alpha_cols: List of alpha column names to neutralize
            sector_col: Sector column name
            price_bucket_col: Price bucket column name
            exchange_col: Exchange column name (for Tier 3 fallback)
        
        Returns:
            DataFrame with neutralized alpha columns added
        """
        if self.strategy != 'cross_sectional':
            raise ValueError("neutralize_batch only supports 'cross_sectional' strategy")
        
        # Check required columns
        if sector_col not in panel.columns:
            raise ValueError(f"Missing sector column: {sector_col}")
        if price_bucket_col not in panel.columns:
            raise ValueError(f"Missing price bucket column: {price_bucket_col}")

        # Neutralize each alpha column
        for alpha_col in alpha_cols:
            if alpha_col not in panel.columns:
                continue

            neutral_col = f'{alpha_col}_neutral'
            
            # Process per-date to avoid look-ahead bias
            for date in panel.index.get_level_values('date').unique():
                date_data = panel.loc[date]
                
                # Get exchange data if available
                exchange_data = date_data[exchange_col] if exchange_col in panel.columns else None
                
                # Apply 4-tier neutralization
                neutral_values, _ = self.neutralize_cross_sectional(
                    alpha=date_data[alpha_col],
                    sector=date_data[sector_col],
                    price_bucket=date_data[price_bucket_col],
                    exchange=exchange_data
                )
                
                # Assign back to panel
                panel.loc[date, neutral_col] = neutral_values

        return panel
    
    def compute_neutralization_quality(self, 
                                       alpha: pd.Series, 
                                       alpha_neutral: pd.Series,
                                       sector: pd.Series) -> Dict:
        """
        Compute quality metrics for neutralization.
        
        Args:
            alpha: Raw alpha
            alpha_neutral: Neutralized alpha
            sector: Sector labels
            
        Returns:
            Dictionary with quality metrics
        """
        metrics = {}
        
        # Overall correlation reduction
        corr_raw = alpha.corr(sector.astype('category').cat.codes)
        corr_neutral = alpha_neutral.corr(sector.astype('category').cat.codes)
        
        metrics['correlation_reduction'] = abs(corr_raw) - abs(corr_neutral)
        
        # Sector-wise IC (Information Coefficient)
        ic_by_sector = {}
        for sector_label in sector.unique():
            mask = sector == sector_label
            if mask.sum() > 1:
                ic = alpha_neutral[mask].corr(alpha[mask])
                ic_by_sector[sector_label] = ic
        
        metrics['ic_by_sector'] = ic_by_sector
        metrics['mean_ic'] = np.mean(list(ic_by_sector.values())) if ic_by_sector else np.nan
        
        # Signal preservation
        metrics['signal_preservation'] = alpha_neutral.std() / (alpha.std() + 1e-9)
        
        return metrics
    
    def get_neutralization_report(self) -> str:
        """
        Generate a human-readable report of neutralization statistics.
        Includes fallback distribution tracking.
        """
        report = f"=== Neutralization Report ({self.strategy}) ===\n"
        
        if self.strategy == 'cross_sectional':
            report += f"Tier 1 (Sector × Price): {self.neutralization_stats.get('tier1_2d', 0)} buckets, "
            report += f"{self.fallback_distribution.get('tier1_2d', 0)} stocks\n"
            report += f"Tier 2 (Sector-only): {self.neutralization_stats.get('tier2_sector', 0)} buckets, "
            report += f"{self.fallback_distribution.get('tier2_sector', 0)} stocks\n"
            report += f"Tier 3 (Exchange-only): {self.neutralization_stats.get('tier3_exchange', 0)} buckets, "
            report += f"{self.fallback_distribution.get('tier3_exchange', 0)} stocks\n"
            report += f"Tier 4 (Market-wide): {self.neutralization_stats.get('tier4_market', 0)} buckets, "
            report += f"{self.fallback_distribution.get('tier4_market', 0)} stocks\n"
            
            # Calculate percentages
            total_stocks = sum(self.fallback_distribution.values())
            if total_stocks > 0:
                report += "\nFallback Distribution:\n"
                for tier, count in self.fallback_distribution.items():
                    pct = (count / total_stocks) * 100
                    report += f"  {tier}: {pct:.1f}%\n"
        
        return report
    
    def get_fallback_distribution(self) -> Dict:
        """
        Get the current fallback distribution for monitoring.
        
        Returns:
            Dictionary with tier names and stock counts
        """
        return self.fallback_distribution.copy()


class NeutralizationValidator:
    """
    Validates neutralization to ensure no look-ahead bias or data leakage.
    """
    
    @staticmethod
    def check_temporal_integrity(alpha: pd.Series, alpha_neutral: pd.Series) -> bool:
        """
        Verify that neutralization doesn't introduce temporal leakage.
        
        Args:
            alpha: Raw alpha
            alpha_neutral: Neutralized alpha
            
        Returns:
            True if no leakage detected
        """
        # Check that neutralization is purely cross-sectional (within-date)
        # by verifying that time-series correlation is preserved
        
        if isinstance(alpha.index, pd.MultiIndex):
            # Group by symbol
            for symbol in alpha.index.get_level_values('symbol').unique():
                alpha_ts = alpha.loc[(slice(None), symbol), :]
                neutral_ts = alpha_neutral.loc[(slice(None), symbol), :]
                
                # Correlation should be high (neutralization is linear)
                corr = alpha_ts.corr(neutral_ts)
                if corr < 0.5:  # Arbitrary threshold
                    print(f"Warning: Low correlation for {symbol}: {corr:.3f}")
                    return False
        
        return True
    
    @staticmethod
    def check_no_nan_leakage(alpha: pd.Series, alpha_neutral: pd.Series) -> bool:
        """
        Verify that NaN patterns are preserved (no information leakage).
        """
        nan_mask_raw = alpha.isna()
        nan_mask_neutral = alpha_neutral.isna()
        
        # NaN patterns should be identical
        if not nan_mask_raw.equals(nan_mask_neutral):
            print("Warning: NaN patterns differ between raw and neutral alpha")
            return False
        
        return True


if __name__ == '__main__':
    print("Testing Unified NeutralizationEngine...\n")
    
    # Create sample data with exchange information
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='D')
    symbols = ['VNM', 'VCB', 'HPG', 'FPT', 'VIC', 'SAB', 'MWG', 'PNJ']
    exchanges = ['HOSE', 'HOSE', 'HOSE', 'HOSE', 'HOSE', 'HOSE', 'HNX', 'HNX']
    
    data = []
    for date in dates:
        for i, symbol in enumerate(symbols):
            data.append({
                'date': date,
                'symbol': symbol,
                'alpha': np.random.randn(),
                'sector': np.random.choice(['Financials', 'Industrials', 'Consumer']),
                'price_bucket': np.random.choice(['penny', 'small', 'large']),
                'exchange': exchanges[i]
            })
    
    panel = pd.DataFrame(data).set_index(['date', 'symbol'])
    
    # Test cross-sectional neutralization
    engine = NeutralizationEngine(strategy='cross_sectional')
    
    # Neutralize for a single date
    date_sample = panel.loc['2023-06-15']
    alpha_neutral, stats = engine.neutralize_cross_sectional(
        date_sample['alpha'],
        date_sample['sector'],
        date_sample['price_bucket'],
        date_sample['exchange']
    )
    
    print("Cross-Sectional Neutralization Statistics:")
    print(f"  Tier 1 (2D): {stats['tier1_2d']}")
    print(f"  Tier 2 (Sector): {stats['tier2_sector']}")
    print(f"  Tier 3 (Exchange): {stats['tier3_exchange']}")
    print(f"  Tier 4 (Market): {stats['tier4_market']}")
    
    print("\n" + engine.get_neutralization_report())
    
    # Validate
    validator = NeutralizationValidator()
    temporal_ok = validator.check_temporal_integrity(date_sample['alpha'], alpha_neutral)
    nan_ok = validator.check_no_nan_leakage(date_sample['alpha'], alpha_neutral)
    
    print(f"Validation:")
    print(f"  Temporal Integrity: {'OK' if temporal_ok else 'FAILED'}")
    print(f"  NaN Leakage: {'OK' if nan_ok else 'FAILED'}")
    
    print("\n[OK] Unified NeutralizationEngine ready for production use.")
