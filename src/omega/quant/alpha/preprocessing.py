"""
Alpha Preprocessing Module - Mandatory Sanitization and Neutralization Pipeline
Version: v21.40-Phase3.4-Reconstruction
Date: 2026-05-08
Author: OpenCode (Senior Quant Coder)

This module provides the mandatory preprocessing pipeline for all alpha signals:
1. Winsorization (1%/99%) on raw OHLCV data
2. Z-score normalization on computed signals
3. Market neutralization before IC computation

COMPLIANCE:
- PIT (Point-in-Time): All operations use T-1 lagged data
- Vectorization: 100% Pandas/NumPy operations
- Robustness: Handles NaN, Inf, and edge cases
- Integration: Works with alpha_discovery.py and ultimate_alpha_arsenal.py

USAGE:
    from omega.quant.alpha.preprocessing import AlphaPreprocessor
    
    preprocessor = AlphaPreprocessor()
    
    # Step 1: Sanitize raw OHLCV
    df_clean = preprocessor.sanitize_ohlcv(df)
    
    # Step 2: Compute alphas on clean data
    alphas = compute_alphas(df_clean)
    
    # Step 3: Normalize and neutralize alphas
    alphas_final = preprocessor.normalize_and_neutralize(alphas, df_clean)
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import pandas as pd
import numpy as np

from omega.quant.utils.math import winsorize, zscore, cross_sectional_zscore
from omega.quant.features.neutralization import HierarchicalNeutralizer

logger = logging.getLogger(__name__)


@dataclass
class PreprocessingConfig:
    """Configuration for alpha preprocessing pipeline."""
    
    # Winsorization parameters
    winsorize_lower: float = 0.01  # 1st percentile
    winsorize_upper: float = 0.99  # 99th percentile
    
    # Z-score parameters
    zscore_epsilon: float = 1e-9
    
    # Neutralization parameters
    enable_neutralization: bool = True
    min_l4_size: int = 5
    min_l3_size: int = 5
    min_l2_size: int = 10
    min_exchange_size: int = 3
    
    # Market metadata columns
    sector_col: str = "sector"
    price_bucket_col: str = "price_bucket"
    liquidity_bucket_col: str = "liquidity_bucket"
    exchange_col: str = "exchange"


class AlphaPreprocessor:
    """
    Mandatory preprocessing pipeline for alpha signals.
    
    Pipeline:
    1. Sanitize OHLCV: Winsorize raw price/volume data (per date cross-section)
    2. Normalize Signals: Z-score computed alpha signals (per date cross-section)
    3. Neutralize: Remove sector/price/liquidity biases (hierarchical fallback)
    
    All operations are cross-sectional (per date) to ensure PIT compliance.
    """
    
    def __init__(self, config: Optional[PreprocessingConfig] = None):
        """Initialize preprocessor with configuration."""
        self.config = config or PreprocessingConfig()
        
        if self.config.enable_neutralization:
            self.neutralization_engine = HierarchicalNeutralizer(
                min_l4_size=self.config.min_l4_size,
                min_l3_size=self.config.min_l3_size,
                min_l2_size=self.config.min_l2_size,
                min_l1_size=self.config.min_exchange_size,
                winsorize_lower=self.config.winsorize_lower,
                winsorize_upper=self.config.winsorize_upper,
            )
        else:
            self.neutralization_engine = None
    
    def sanitize_ohlcv(
        self,
        df: pd.DataFrame,
        ohlcv_cols: Optional[List[str]] = None,
        symbol_col: str = "ticker",
        date_col: str = "date",
    ) -> pd.DataFrame:
        """
        Step 1: Sanitize raw OHLCV data with winsorization.
        
        Applies cross-sectional winsorization (per date) to remove extreme outliers
        in price and volume data before alpha computation.
        
        Args:
            df: DataFrame with OHLCV data
            ohlcv_cols: List of columns to sanitize (default: open, high, low, close, volume)
            symbol_col: Symbol column name
            date_col: Date column name
            
        Returns:
            DataFrame with sanitized OHLCV columns
        """
        if ohlcv_cols is None:
            ohlcv_cols = ["open", "high", "low", "close", "volume"]
        
        df_work = df.copy()
        df_work = df_work.sort_values([date_col, symbol_col]).reset_index(drop=True)
        
        # Apply cross-sectional winsorization per date
        for col in ohlcv_cols:
            if col not in df_work.columns:
                logger.warning(f"Column '{col}' not found, skipping sanitization")
                continue
            
            # Winsorize per date (cross-sectional)
            df_work[f"{col}_sanitized"] = df_work.groupby(date_col)[col].transform(
                lambda x: winsorize(
                    x,
                    lower_percentile=self.config.winsorize_lower,
                    upper_percentile=self.config.winsorize_upper,
                )[0]  # winsorize returns (series, count)
            )
            
            # Replace original column with sanitized version
            df_work[col] = df_work[f"{col}_sanitized"]
            df_work = df_work.drop(columns=[f"{col}_sanitized"])
        
        logger.info(f"Sanitized {len(ohlcv_cols)} OHLCV columns with {self.config.winsorize_lower}/{self.config.winsorize_upper} winsorization")
        
        return df_work
    
    def normalize_signals(
        self,
        df: pd.DataFrame,
        alpha_cols: List[str],
        date_col: str = "date",
        symbol_col: str = "ticker",
    ) -> pd.DataFrame:
        """
        Step 2: Normalize alpha signals with cross-sectional z-score.
        
        Applies cross-sectional z-score normalization (per date) to standardize
        alpha signals before neutralization.
        
        Args:
            df: DataFrame with alpha columns
            alpha_cols: List of alpha column names to normalize
            date_col: Date column name
            symbol_col: Symbol column name
            
        Returns:
            DataFrame with normalized alpha columns (suffix: _zscore)
        """
        df_work = df.copy()
        df_work = df_work.sort_values([date_col, symbol_col]).reset_index(drop=True)
        
        for alpha_col in alpha_cols:
            if alpha_col not in df_work.columns:
                logger.warning(f"Alpha column '{alpha_col}' not found, skipping normalization")
                continue
            
            # Apply cross-sectional z-score per date
            df_work[f"{alpha_col}_zscore"] = df_work.groupby(date_col)[alpha_col].transform(
                lambda x: cross_sectional_zscore(x, epsilon=self.config.zscore_epsilon)
            )
        
        logger.info(f"Normalized {len(alpha_cols)} alpha signals with cross-sectional z-score")
        
        return df_work
    
    def neutralize_signals(
        self,
        df: pd.DataFrame,
        alpha_cols: List[str],
        date_col: str = "date",
        symbol_col: str = "ticker",
    ) -> pd.DataFrame:
        """
        Step 3: Neutralize alpha signals to remove sector/price/liquidity biases.
        
        Applies hierarchical neutralization (L4 -> L3 -> L2 -> L1 -> L0) to remove
        systematic biases from alpha signals.
        
        Args:
            df: DataFrame with alpha columns and market metadata
            alpha_cols: List of alpha column names to neutralize
            date_col: Date column name
            symbol_col: Symbol column name
            
        Returns:
            DataFrame with neutralized alpha columns (suffix: _neutral)
        """
        if not self.config.enable_neutralization or self.neutralization_engine is None:
            logger.info("Neutralization disabled, skipping")
            return df
        
        df_work = df.copy()
        df_work = df_work.sort_values([date_col, symbol_col]).reset_index(drop=True)
        
        # Check for required metadata columns
        required_cols = [self.config.sector_col, self.config.price_bucket_col]
        missing_cols = [col for col in required_cols if col not in df_work.columns]
        
        if missing_cols:
            logger.warning(f"Missing required columns for neutralization: {missing_cols}")
            logger.warning("Creating default metadata columns")
            
            if self.config.sector_col not in df_work.columns:
                df_work[self.config.sector_col] = "Unknown"
            
            if self.config.price_bucket_col not in df_work.columns:
                df_work[self.config.price_bucket_col] = "P3"
            
            if self.config.liquidity_bucket_col not in df_work.columns:
                df_work[self.config.liquidity_bucket_col] = "L3"
        
        # Convert to MultiIndex for neutralization engine
        if not isinstance(df_work.index, pd.MultiIndex):
            df_indexed = df_work.set_index([date_col, symbol_col])
        else:
            df_indexed = df_work
        
        # Apply neutralization
        df_neutralized = self.neutralization_engine.neutralize_panel(
            df_indexed,
            alpha_cols=alpha_cols,
            sector_col=self.config.sector_col,
            price_level_col=self.config.price_bucket_col,
            liquidity_col=self.config.liquidity_bucket_col if self.config.liquidity_bucket_col in df_work.columns else None,
            exchange_col=self.config.exchange_col if self.config.exchange_col in df_work.columns else None,
        )
        
        # Replace original columns with neutralized versions
        for alpha_col in alpha_cols:
            neutral_col = f"{alpha_col}_neutral"
            if neutral_col in df_neutralized.columns:
                df_neutralized[alpha_col] = df_neutralized[neutral_col]
                df_neutralized = df_neutralized.drop(columns=[neutral_col])
        
        logger.info(f"Neutralized {len(alpha_cols)} alpha signals with hierarchical neutralization")
        
        # Convert back to flat index if needed
        if not isinstance(df.index, pd.MultiIndex):
            df_neutralized = df_neutralized.reset_index()
        
        return df_neutralized
    
    def preprocess_pipeline(
        self,
        df: pd.DataFrame,
        alpha_cols: List[str],
        ohlcv_cols: Optional[List[str]] = None,
        symbol_col: str = "ticker",
        date_col: str = "date",
        sanitize_ohlcv: bool = True,
        normalize_signals: bool = True,
        neutralize_signals: bool = True,
    ) -> pd.DataFrame:
        """
        Full preprocessing pipeline: Sanitize -> Normalize -> Neutralize.
        
        Args:
            df: DataFrame with OHLCV and alpha columns
            alpha_cols: List of alpha column names
            ohlcv_cols: List of OHLCV columns to sanitize (optional)
            symbol_col: Symbol column name
            date_col: Date column name
            sanitize_ohlcv: Enable OHLCV sanitization
            normalize_signals: Enable signal normalization
            neutralize_signals: Enable signal neutralization
            
        Returns:
            DataFrame with preprocessed alpha signals
        """
        df_work = df.copy()
        
        # Step 1: Sanitize OHLCV (optional, typically done before alpha computation)
        if sanitize_ohlcv and ohlcv_cols is not None:
            df_work = self.sanitize_ohlcv(
                df_work,
                ohlcv_cols=ohlcv_cols,
                symbol_col=symbol_col,
                date_col=date_col,
            )
        
        # Step 2: Normalize signals
        if normalize_signals:
            df_work = self.normalize_signals(
                df_work,
                alpha_cols=alpha_cols,
                date_col=date_col,
                symbol_col=symbol_col,
            )
            
            # Update alpha_cols to use normalized versions
            alpha_cols = [f"{col}_zscore" for col in alpha_cols]
        
        # Step 3: Neutralize signals
        if neutralize_signals:
            df_work = self.neutralize_signals(
                df_work,
                alpha_cols=alpha_cols,
                date_col=date_col,
                symbol_col=symbol_col,
            )
        
        return df_work
    
    def get_preprocessing_report(self) -> str:
        """Generate preprocessing report with statistics."""
        report = "=== Alpha Preprocessing Pipeline Report ===\n"
        report += f"Winsorization: {self.config.winsorize_lower}/{self.config.winsorize_upper}\n"
        report += f"Z-score epsilon: {self.config.zscore_epsilon}\n"
        report += f"Neutralization enabled: {self.config.enable_neutralization}\n"
        
        if self.neutralization_engine is not None:
            report += "\n" + self.neutralization_engine.get_neutralization_report()
        
        return report


# Convenience function for quick preprocessing
def preprocess_alphas(
    df: pd.DataFrame,
    alpha_cols: List[str],
    config: Optional[PreprocessingConfig] = None,
    **kwargs,
) -> pd.DataFrame:
    """
    Convenience function for quick alpha preprocessing.
    
    Args:
        df: DataFrame with alpha columns
        alpha_cols: List of alpha column names
        config: Preprocessing configuration (optional)
        **kwargs: Additional arguments passed to preprocess_pipeline
        
    Returns:
        DataFrame with preprocessed alphas
    """
    preprocessor = AlphaPreprocessor(config=config)
    return preprocessor.preprocess_pipeline(df, alpha_cols, **kwargs)


__all__ = [
    "AlphaPreprocessor",
    "PreprocessingConfig",
    "preprocess_alphas",
]
