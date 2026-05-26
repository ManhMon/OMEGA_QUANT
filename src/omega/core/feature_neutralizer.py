"""
Feature Neutralizer - Pipeline Stage for Factor Neutralization

Integrates NeutralizationEngine into the feature engineering pipeline.
Sits between FeatureFactory and PortfolioOptimizer to neutralize
unwanted factor exposures.

Pipeline Flow:
    FeatureFactory -> FeatureNeutralizer -> PortfolioOptimizer
    
Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 4
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Union
from datetime import datetime

from omega.core.neutralization import NeutralizationEngine


class FeatureNeutralizer:
    """
    Pipeline stage for neutralizing features before portfolio optimization.
    
    Wraps NeutralizationEngine and provides pipeline-friendly interface:
    - Accepts feature DataFrame from FeatureFactory
    - Applies configured neutralizations (market, sector, style)
    - Returns neutralized features ready for PortfolioOptimizer
    - Preserves PIT safety throughout
    """
    
    def __init__(
        self,
        enable_market_neutral: bool = False,
        enable_sector_neutral: bool = False,
        enable_style_neutral: bool = False,
        market_method: str = 'beta_weighted',
        sector_method: str = 'demean',
        style_method: str = 'regression',
        style_factors: Optional[List[str]] = None,
        market_cap_col: str = 'market_cap',
        sector_col: str = 'sector',
        date_col: str = 'date',
        symbol_col: str = 'symbol',
        market_return_col: str = 'market_return'
    ):
        """
        Initialize FeatureNeutralizer.
        
        Args:
            enable_market_neutral: Enable market neutralization
            enable_sector_neutral: Enable sector neutralization
            enable_style_neutral: Enable style neutralization
            market_method: Market neutralization method ('beta_weighted' or 'demean')
            sector_method: Sector neutralization method ('demean' or 'cap_weighted')
            style_method: Style neutralization method ('regression' or 'orthogonalize')
            style_factors: List of style factor columns for neutralization
            market_cap_col: Market capitalization column name
            sector_col: Sector classification column name
            date_col: Date column name
            symbol_col: Symbol column name
            market_return_col: Market return column name
        """
        self.enable_market_neutral = enable_market_neutral
        self.enable_sector_neutral = enable_sector_neutral
        self.enable_style_neutral = enable_style_neutral
        self.market_method = market_method
        self.sector_method = sector_method
        self.style_method = style_method
        self.style_factors = style_factors or []
        self.market_return_col = market_return_col
        
        # Initialize neutralization engine
        self.engine = NeutralizationEngine(
            market_cap_col=market_cap_col,
            sector_col=sector_col,
            date_col=date_col,
            symbol_col=symbol_col
        )
    
    def neutralize_features(
        self,
        df: pd.DataFrame,
        feature_cols: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Neutralize features according to configuration.
        
        Args:
            df: Input DataFrame with features from FeatureFactory
            feature_cols: List of feature columns to neutralize (default: all feat_* columns)
        
        Returns:
            DataFrame with neutralized features
            
        PIT Safety:
            - All neutralization operations preserve T-1 lag
            - No forward-looking information used
        """
        # Validate input
        if df.empty:
            raise ValueError("Input DataFrame is empty")
        
        # Identify feature columns to neutralize
        if feature_cols is None:
            feature_cols = [col for col in df.columns if col.startswith('feat_')]
        
        if not feature_cols:
            raise ValueError("No feature columns found to neutralize")
        
        # Check if any neutralization is enabled
        if not (self.enable_market_neutral or self.enable_sector_neutral or self.enable_style_neutral):
            # No neutralization enabled, return original DataFrame
            return df.copy()
        
        # Create result DataFrame
        result = df.copy()
        
        # Vectorized neutralization: process all features at once
        # Filter to only existing columns
        valid_feature_cols = [col for col in feature_cols if col in result.columns]
        
        if not valid_feature_cols:
            return result
        
        # Store original features for comparison (vectorized copy via dict comprehension)
        result = result.assign(**{f"{feat_col}_original": result[feat_col] for feat_col in valid_feature_cols})
        
        # Apply neutralizations to all features (vectorized batch operation via dict comprehension)
        neutralized_features = {
            feat_col: self.engine.neutralize_all(
                df=result,
                factor_col=feat_col,
                neutralize_market=self.enable_market_neutral,
                neutralize_sector=self.enable_sector_neutral,
                neutralize_style=self.enable_style_neutral,
                market_return_col=self.market_return_col,
                style_factors=self.style_factors if self.enable_style_neutral else None,
                market_method=self.market_method,
                sector_method=self.sector_method,
                style_method=self.style_method
            )
            for feat_col in valid_feature_cols
        }
        result = result.assign(**neutralized_features)
        
        return result
    
    def neutralize_single_feature(
        self,
        df: pd.DataFrame,
        feature_col: str
    ) -> pd.Series:
        """
        Neutralize a single feature column.
        
        Args:
            df: Input DataFrame
            feature_col: Feature column to neutralize
        
        Returns:
            Neutralized feature as pd.Series
        """
        if feature_col not in df.columns:
            raise ValueError(f"Feature column '{feature_col}' not found in DataFrame")
        
        neutralized = self.engine.neutralize_all(
            df=df,
            factor_col=feature_col,
            neutralize_market=self.enable_market_neutral,
            neutralize_sector=self.enable_sector_neutral,
            neutralize_style=self.enable_style_neutral,
            market_return_col=self.market_return_col,
            style_factors=self.style_factors if self.enable_style_neutral else None,
            market_method=self.market_method,
            sector_method=self.sector_method,
            style_method=self.style_method
        )
        
        return neutralized
    
    def compute_neutralization_impact(
        self,
        df: pd.DataFrame,
        feature_cols: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        Compute neutralization impact statistics for each feature.
        
        Args:
            df: DataFrame with both original and neutralized features
            feature_cols: List of feature columns (default: all feat_* columns)
        
        Returns:
            Dictionary mapping feature names to neutralization statistics
        """
        if feature_cols is None:
            feature_cols = [col for col in df.columns if col.startswith('feat_') and not col.endswith('_original')]
        
        # Vectorized impact computation: filter valid columns first
        valid_pairs = [
            (feat_col, f"{feat_col}_original")
            for feat_col in feature_cols
            if feat_col in df.columns and f"{feat_col}_original" in df.columns
        ]
        
        # Compute statistics for all valid features (vectorized)
        impact_stats = {
            feat_col: self.engine.compute_neutralization_stats(
                df=df,
                original_col=original_col,
                neutralized_col=feat_col
            )
            for feat_col, original_col in valid_pairs
        }
        
        return impact_stats
    
    def validate_neutralization(
        self,
        df: pd.DataFrame,
        feature_col: str,
        tolerance: float = 0.1
    ) -> Dict[str, bool]:
        """
        Validate that neutralization successfully reduced exposures.
        
        Args:
            df: DataFrame with neutralized features
            feature_col: Feature column to validate
            tolerance: Tolerance for exposure reduction (default 0.1)
        
        Returns:
            Dictionary with validation results:
            - market_neutral: True if market exposure reduced
            - sector_neutral: True if sector exposure reduced
            - style_neutral: True if style exposure reduced
        """
        validation = {
            'market_neutral': True,
            'sector_neutral': True,
            'style_neutral': True
        }
        
        if feature_col not in df.columns:
            raise ValueError(f"Feature column '{feature_col}' not found")
        
        # Market neutralization check
        if self.enable_market_neutral and self.market_return_col in df.columns:
            # Check correlation with market return
            corr = df[feature_col].corr(df[self.market_return_col])
            validation['market_neutral'] = abs(corr) < tolerance
        
        # Sector neutralization check
        if self.enable_sector_neutral and self.engine.sector_col in df.columns:
            # Check mean by sector (should be close to zero)
            sector_means = df.groupby(self.engine.sector_col)[feature_col].mean()
            validation['sector_neutral'] = (sector_means.abs().max() < tolerance)
        
        # Style neutralization check
        if self.enable_style_neutral and self.style_factors:
            # Vectorized correlation computation for all style factors
            available_style_factors = [sf for sf in self.style_factors if sf in df.columns]
            if available_style_factors:
                # Compute correlations for all style factors at once
                style_corrs = df[[feature_col] + available_style_factors].corr()[feature_col].abs()
                max_corr = style_corrs[available_style_factors].max()
                validation['style_neutral'] = max_corr < tolerance
        
        return validation
    
    @classmethod
    def from_config(cls, config: Dict) -> 'FeatureNeutralizer':
        """
        Create FeatureNeutralizer from configuration dictionary.
        
        Args:
            config: Configuration dictionary with neutralization settings
        
        Returns:
            Configured FeatureNeutralizer instance
        """
        return cls(
            enable_market_neutral=config.get('enable_market_neutral', False),
            enable_sector_neutral=config.get('enable_sector_neutral', False),
            enable_style_neutral=config.get('enable_style_neutral', False),
            market_method=config.get('market_method', 'beta_weighted'),
            sector_method=config.get('sector_method', 'demean'),
            style_method=config.get('style_method', 'regression'),
            style_factors=config.get('style_factors', []),
            market_cap_col=config.get('market_cap_col', 'market_cap'),
            sector_col=config.get('sector_col', 'sector'),
            date_col=config.get('date_col', 'date'),
            symbol_col=config.get('symbol_col', 'symbol'),
            market_return_col=config.get('market_return_col', 'market_return')
        )
