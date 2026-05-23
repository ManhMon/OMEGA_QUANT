"""
Neutralization Engine - Vectorized Factor Neutralization with PIT Safety

Implements:
- Market neutralization (beta-weighted)
- Sector neutralization (group-weighted)
- Style neutralization (value, momentum, quality)
- 100% vectorized via Pandas groupby
- Preserves PIT boundaries

Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 4
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Union
from datetime import datetime


class NeutralizationEngine:
    """
    Vectorized factor neutralization engine.
    
    Neutralizes factor exposures to reduce unintended risk:
    - Market neutralization: Remove market beta
    - Sector neutralization: Remove sector tilts
    - Style neutralization: Remove style factor exposures
    
    All operations are vectorized and preserve PIT safety.
    """
    
    def __init__(
        self,
        market_cap_col: str = 'market_cap',
        sector_col: str = 'sector',
        date_col: str = 'date',
        symbol_col: str = 'symbol'
    ):
        """
        Initialize NeutralizationEngine.
        
        Args:
            market_cap_col: Market capitalization column name
            sector_col: Sector classification column name
            date_col: Date column name
            symbol_col: Symbol column name
        """
        self.market_cap_col = market_cap_col
        self.sector_col = sector_col
        self.date_col = date_col
        self.symbol_col = symbol_col
    
    def neutralize_market(
        self,
        df: pd.DataFrame,
        factor_col: str,
        market_return_col: str = 'market_return',
        method: str = 'beta_weighted'
    ) -> pd.Series:
        """
        Market neutralization - remove market beta exposure.
        
        Args:
            df: Input DataFrame with factor and market returns
            factor_col: Factor column to neutralize
            market_return_col: Market return column
            method: Neutralization method ('beta_weighted' or 'demean')
        
        Returns:
            Market-neutralized factor values
        
        PIT Safety:
            - Uses only data available at each timestamp
            - No forward-looking information
        """
        if method == 'demean':
            # Simple demeaning by date
            neutralized = df.groupby(self.date_col)[factor_col].transform(
                lambda x: x - x.mean()
            )
        elif method == 'beta_weighted':
            # Beta-weighted neutralization
            neutralized = df.groupby(self.date_col, group_keys=False).apply(
                lambda group: self._neutralize_market_beta(
                    group, factor_col, market_return_col
                )
            )[factor_col]
        else:
            raise ValueError(f"Unknown method: {method}")
        
        return neutralized
    
    def _neutralize_market_beta(
        self,
        df: pd.DataFrame,
        factor_col: str,
        market_return_col: str
    ) -> pd.DataFrame:
        """
        Remove market beta from factor using regression.
        
        Args:
            df: DataFrame for single date
            factor_col: Factor column
            market_return_col: Market return column
        
        Returns:
            DataFrame with neutralized factor
        """
        result = df.copy()
        
        # Skip if insufficient data
        if len(df) < 2 or df[market_return_col].std() == 0:
            result[factor_col] = df[factor_col] - df[factor_col].mean()
            return result
        
        # Compute beta via covariance
        cov = np.cov(df[factor_col].fillna(0), df[market_return_col].fillna(0))
        beta = cov[0, 1] / (cov[1, 1] + 1e-10)
        
        # Remove market component
        result[factor_col] = df[factor_col] - beta * df[market_return_col]
        
        # Demean residuals
        result[factor_col] = result[factor_col] - result[factor_col].mean()
        
        return result
    
    def neutralize_sector(
        self,
        df: pd.DataFrame,
        factor_col: str,
        method: str = 'demean'
    ) -> pd.Series:
        """
        Sector neutralization - remove sector tilts.
        
        Args:
            df: Input DataFrame with factor and sector
            factor_col: Factor column to neutralize
            method: Neutralization method ('demean' or 'cap_weighted')
        
        Returns:
            Sector-neutralized factor values
        
        PIT Safety:
            - Neutralization done within each date
            - No cross-date information leakage
        """
        if self.sector_col not in df.columns:
            raise ValueError(f"Sector column '{self.sector_col}' not found")
        
        if method == 'demean':
            # Demean within each sector-date group
            neutralized = df.groupby([self.date_col, self.sector_col])[factor_col].transform(
                lambda x: x - x.mean()
            )
        elif method == 'cap_weighted':
            # Cap-weighted neutralization
            neutralized = df.groupby(self.date_col, group_keys=False).apply(
                lambda group: self._neutralize_sector_cap_weighted(
                    group, factor_col
                )
            )[factor_col]
        else:
            raise ValueError(f"Unknown method: {method}")
        
        return neutralized
    
    def _neutralize_sector_cap_weighted(
        self,
        df: pd.DataFrame,
        factor_col: str
    ) -> pd.DataFrame:
        """
        Remove cap-weighted sector means from factor.
        
        Args:
            df: DataFrame for single date
            factor_col: Factor column
        
        Returns:
            DataFrame with neutralized factor
        """
        result = df.copy()
        
        if self.market_cap_col not in df.columns:
            # Fallback to equal-weighted if no market cap
            result[factor_col] = df.groupby(self.sector_col)[factor_col].transform(
                lambda x: x - x.mean()
            )
            return result
        
        # Compute cap-weighted sector means
        sector_means = df.groupby(self.sector_col).apply(
            lambda group: np.average(
                group[factor_col].fillna(0),
                weights=group[self.market_cap_col].fillna(1)
            )
        )
        
        # Subtract sector mean from each stock
        result[factor_col] = df.apply(
            lambda row: row[factor_col] - sector_means.get(row[self.sector_col], 0),
            axis=1
        )
        
        return result
    
    def neutralize_style(
        self,
        df: pd.DataFrame,
        factor_col: str,
        style_factors: List[str],
        method: str = 'regression'
    ) -> pd.Series:
        """
        Style neutralization - remove style factor exposures.
        
        Args:
            df: Input DataFrame with factor and style factors
            factor_col: Factor column to neutralize
            style_factors: List of style factor columns (e.g., ['value', 'momentum', 'quality'])
            method: Neutralization method ('regression' or 'orthogonalize')
        
        Returns:
            Style-neutralized factor values
        
        PIT Safety:
            - Neutralization done within each date
            - No forward-looking information
        """
        # Validate style factors exist
        missing = [col for col in style_factors if col not in df.columns]
        if missing:
            raise ValueError(f"Missing style factors: {missing}")
        
        if method == 'regression':
            # Regression-based neutralization
            neutralized = df.groupby(self.date_col, group_keys=False).apply(
                lambda group: self._neutralize_style_regression(
                    group, factor_col, style_factors
                )
            )[factor_col]
        elif method == 'orthogonalize':
            # Gram-Schmidt orthogonalization
            neutralized = df.groupby(self.date_col, group_keys=False).apply(
                lambda group: self._neutralize_style_orthogonal(
                    group, factor_col, style_factors
                )
            )[factor_col]
        else:
            raise ValueError(f"Unknown method: {method}")
        
        return neutralized
    
    def _neutralize_style_regression(
        self,
        df: pd.DataFrame,
        factor_col: str,
        style_factors: List[str]
    ) -> pd.DataFrame:
        """
        Remove style exposures using multiple regression.
        
        Args:
            df: DataFrame for single date
            factor_col: Factor column
            style_factors: List of style factor columns
        
        Returns:
            DataFrame with neutralized factor
        """
        result = df.copy()
        
        # Skip if insufficient data
        if len(df) < len(style_factors) + 1:
            result[factor_col] = df[factor_col] - df[factor_col].mean()
            return result
        
        # Prepare data
        y = df[factor_col].fillna(0).values
        X = df[style_factors].fillna(0).values
        
        # Add intercept
        X = np.column_stack([np.ones(len(X)), X])
        
        # Solve via normal equations (X'X)^-1 X'y
        try:
            XtX = X.T @ X
            Xty = X.T @ y
            beta = np.linalg.solve(XtX + 1e-6 * np.eye(len(XtX)), Xty)
            
            # Compute residuals (neutralized factor)
            residuals = y - X @ beta
            result[factor_col] = residuals
        except np.linalg.LinAlgError:
            # Fallback to demeaning if singular
            result[factor_col] = df[factor_col] - df[factor_col].mean()
        
        return result
    
    def _neutralize_style_orthogonal(
        self,
        df: pd.DataFrame,
        factor_col: str,
        style_factors: List[str]
    ) -> pd.DataFrame:
        """
        Remove style exposures using Gram-Schmidt orthogonalization.
        
        Args:
            df: DataFrame for single date
            factor_col: Factor column
            style_factors: List of style factor columns
        
        Returns:
            DataFrame with neutralized factor
        """
        result = df.copy()
        
        # Start with original factor
        orthogonal = df[factor_col].fillna(0).values.copy()
        
        # Orthogonalize against each style factor
        for style in style_factors:
            style_vec = df[style].fillna(0).values
            
            # Project factor onto style and subtract
            projection = np.dot(orthogonal, style_vec) / (np.dot(style_vec, style_vec) + 1e-10)
            orthogonal = orthogonal - projection * style_vec
        
        result[factor_col] = orthogonal
        
        return result
    
    def neutralize_all(
        self,
        df: pd.DataFrame,
        factor_col: str,
        neutralize_market: bool = True,
        neutralize_sector: bool = True,
        neutralize_style: bool = False,
        market_return_col: str = 'market_return',
        style_factors: Optional[List[str]] = None,
        market_method: str = 'beta_weighted',
        sector_method: str = 'demean',
        style_method: str = 'regression'
    ) -> pd.Series:
        """
        Apply all neutralizations in sequence.
        
        Args:
            df: Input DataFrame
            factor_col: Factor column to neutralize
            neutralize_market: Whether to neutralize market
            neutralize_sector: Whether to neutralize sector
            neutralize_style: Whether to neutralize style
            market_return_col: Market return column
            style_factors: List of style factor columns
            market_method: Market neutralization method
            sector_method: Sector neutralization method
            style_method: Style neutralization method
        
        Returns:
            Fully neutralized factor values
        
        Order of operations:
            1. Market neutralization (if enabled)
            2. Sector neutralization (if enabled)
            3. Style neutralization (if enabled)
        """
        result = df.copy()
        neutralized = result[factor_col].copy()
        
        # Market neutralization
        if neutralize_market:
            if market_return_col not in result.columns:
                raise ValueError(f"Market return column '{market_return_col}' not found")
            result[factor_col] = neutralized
            neutralized = self.neutralize_market(
                result, factor_col, market_return_col, method=market_method
            )
        
        # Sector neutralization
        if neutralize_sector:
            result[factor_col] = neutralized
            neutralized = self.neutralize_sector(
                result, factor_col, method=sector_method
            )
        
        # Style neutralization
        if neutralize_style:
            if style_factors is None or len(style_factors) == 0:
                raise ValueError("style_factors must be provided for style neutralization")
            result[factor_col] = neutralized
            neutralized = self.neutralize_style(
                result, factor_col, style_factors, method=style_method
            )
        
        return neutralized
    
    def compute_neutralization_stats(
        self,
        df: pd.DataFrame,
        original_col: str,
        neutralized_col: str
    ) -> Dict[str, float]:
        """
        Compute statistics comparing original and neutralized factors.
        
        Args:
            df: DataFrame with both original and neutralized factors
            original_col: Original factor column
            neutralized_col: Neutralized factor column
        
        Returns:
            Dictionary with statistics:
            - correlation_reduction: Reduction in correlation with market/sector
            - variance_retained: Fraction of variance retained
            - mean_original: Mean of original factor
            - mean_neutralized: Mean of neutralized factor
            - std_original: Std of original factor
            - std_neutralized: Std of neutralized factor
        """
        stats = {}
        
        # Basic statistics
        stats['mean_original'] = df[original_col].mean()
        stats['mean_neutralized'] = df[neutralized_col].mean()
        stats['std_original'] = df[original_col].std()
        stats['std_neutralized'] = df[neutralized_col].std()
        
        # Variance retained
        stats['variance_retained'] = (
            stats['std_neutralized'] ** 2 / (stats['std_original'] ** 2 + 1e-10)
        )
        
        # Correlation between original and neutralized
        stats['correlation'] = df[original_col].corr(df[neutralized_col])
        
        return stats
