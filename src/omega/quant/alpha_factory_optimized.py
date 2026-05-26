"""
Alpha Factory with RAM Optimization (SIGKILL FIX)
Version: v21.41-Phase3.4-Reconstruction
Date: 2026-05-08
Author: OpenCode (Senior Quant Coder)

This module provides a RAM-optimized alpha factory that:
1. Uses chunked loading (symbol-by-symbol or fold-by-fold)
2. Integrates SanitizationModule and NeutralizationEngine from layer_01
3. Computes ONLY 5 Macro Alphas (Momentum, Mean-Reversion, Liquidity, Volatility, Trend)
4. Calls gc.collect() after each fold computation
5. Uses existing formulas from ultimate_alpha_arsenal.py

COMPLIANCE:
- PIT (Point-in-Time): All operations use T-1 lagged data
- Vectorization: 100% Pandas/NumPy operations
- RAM Safety: Chunked processing with explicit garbage collection
- Integration: Works with alpha_preprocessing.py

USAGE:
    from .alpha_factory_optimized import OptimizedAlphaFactory
    
    factory = OptimizedAlphaFactory(chunk_size=50)
    alphas = factory.compute_macro_alphas(df, chunk_mode='symbol')
"""

from __future__ import annotations

import gc
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import pandas as pd
import numpy as np

from .alpha_preprocessing import AlphaPreprocessor, PreprocessingConfig
from .neutralization import NeutralizationEngine
from .utils.math import winsorize, zscore, cross_sectional_zscore

logger = logging.getLogger(__name__)


@dataclass
class OptimizedAlphaConfig:
    """Configuration for optimized alpha factory."""
    
    # Chunking parameters
    chunk_size: int = 50  # Number of symbols per chunk
    chunk_mode: str = 'symbol'  # ONLY 'symbol' mode supported (fold mode breaks rolling windows)
    
    # Alpha selection (5 Macro Alphas only)
    enable_momentum: bool = True
    enable_mean_reversion: bool = True
    enable_liquidity: bool = True
    enable_volatility: bool = True
    enable_trend: bool = True
    
    # Preprocessing
    enable_preprocessing: bool = True
    preprocessing_config: Optional[PreprocessingConfig] = None
    
    # RAM management
    enable_gc: bool = True
    gc_frequency: int = 1  # Run gc.collect() every N chunks


class OptimizedAlphaFactory:
    """
    RAM-optimized alpha factory with chunked loading.
    
    Features:
    - Chunked processing (SYMBOL-BY-SYMBOL ONLY - fold mode breaks rolling windows)
    - Only 5 Macro Alphas (Momentum, Mean-Reversion, Liquidity, Volatility, Trend)
    - Integrated preprocessing (sanitization + neutralization)
    - Explicit garbage collection after each chunk
    - Memory-efficient operations
    
    IMPORTANT: Fold-based chunking is NOT supported because it breaks rolling window
    calculations (e.g., RSI_14, ROC_20 require continuous time series per symbol).
    Only symbol-based chunking preserves PIT compliance and numerical correctness.
    """
    
    def __init__(self, config: Optional[OptimizedAlphaConfig] = None):
        """Initialize optimized alpha factory."""
        self.config = config or OptimizedAlphaConfig()
        
        if self.config.enable_preprocessing:
            preprocessing_config = self.config.preprocessing_config or PreprocessingConfig()
            self.preprocessor = AlphaPreprocessor(config=preprocessing_config)
        else:
            self.preprocessor = None
        
        self.stats = {
            'chunks_processed': 0,
            'symbols_processed': 0,
            'alphas_computed': 0,
            'gc_calls': 0,
        }
    
    def compute_macro_alphas(
        self,
        df: pd.DataFrame,
        symbol_col: str = 'ticker',
        date_col: str = 'date',
        chunk_mode: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Compute 5 Macro Alphas with RAM optimization.
        
        Args:
            df: DataFrame with OHLCV data
            symbol_col: Symbol column name
            date_col: Date column name
            chunk_mode: MUST be 'symbol' (fold mode deprecated due to P0 bug)
            
        Returns:
            DataFrame with macro alpha columns
        """
        if df.empty:
            logger.warning("Empty DataFrame, returning empty result")
            return pd.DataFrame()
        
        # Validate required columns
        required_cols = [date_col, symbol_col, 'open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Determine chunk mode (ONLY 'symbol' supported)
        chunk_mode = chunk_mode or self.config.chunk_mode
        
        if chunk_mode != 'symbol':
            logger.warning(f"chunk_mode='{chunk_mode}' is deprecated. Forcing 'symbol' mode to preserve rolling window correctness.")
            chunk_mode = 'symbol'
        
        logger.info(f"Computing 5 Macro Alphas with {chunk_mode} chunking (chunk_size={self.config.chunk_size})")
        
        # Sort by date and symbol for PIT safety
        df_sorted = df.sort_values([date_col, symbol_col]).reset_index(drop=True)
        
        # Step 1: Sanitize OHLCV (if preprocessing enabled)
        if self.preprocessor is not None:
            logger.info("Step 1: Sanitizing OHLCV data...")
            df_sorted = self.preprocessor.sanitize_ohlcv(
                df_sorted,
                ohlcv_cols=['open', 'high', 'low', 'close', 'volume'],
                symbol_col=symbol_col,
                date_col=date_col,
            )
        
        # Step 2: Compute alphas in chunks (SYMBOL MODE ONLY)
        df_alphas = self._compute_by_symbol_chunks(df_sorted, symbol_col, date_col)
        
        # Step 3: Normalize and neutralize (if preprocessing enabled)
        if self.preprocessor is not None:
            logger.info("Step 3: Normalizing and neutralizing alphas...")
            alpha_cols = [col for col in df_alphas.columns if col.startswith('alpha_')]
            
            # Normalize
            df_alphas = self.preprocessor.normalize_signals(
                df_alphas,
                alpha_cols=alpha_cols,
                date_col=date_col,
                symbol_col=symbol_col,
            )
            
            # Update alpha_cols to use normalized versions
            alpha_cols_zscore = [f"{col}_zscore" for col in alpha_cols]
            
            # Neutralize
            df_alphas = self.preprocessor.neutralize_signals(
                df_alphas,
                alpha_cols=alpha_cols_zscore,
                date_col=date_col,
                symbol_col=symbol_col,
            )
        
        logger.info(f"Alpha computation complete. Stats: {self.stats}")
        
        return df_alphas
    
    def _compute_by_symbol_chunks(
        self,
        df: pd.DataFrame,
        symbol_col: str,
        date_col: str,
    ) -> pd.DataFrame:
        """Compute alphas by processing symbols in chunks."""
        symbols = df[symbol_col].unique()
        n_symbols = len(symbols)
        chunk_size = self.config.chunk_size
        
        logger.info(f"Processing {n_symbols} symbols in chunks of {chunk_size}")
        
        results = []
        
        for i in range(0, n_symbols, chunk_size):
            chunk_symbols = symbols[i:i+chunk_size]
            chunk_df = df[df[symbol_col].isin(chunk_symbols)].copy()
            
            logger.info(f"Processing chunk {i//chunk_size + 1}/{(n_symbols + chunk_size - 1)//chunk_size} ({len(chunk_symbols)} symbols)")
            
            # Compute alphas for this chunk
            chunk_alphas = self._compute_alphas_for_chunk(chunk_df, symbol_col, date_col)
            results.append(chunk_alphas)
            
            # Update stats
            self.stats['chunks_processed'] += 1
            self.stats['symbols_processed'] += len(chunk_symbols)
            
            # Garbage collection
            if self.config.enable_gc and (self.stats['chunks_processed'] % self.config.gc_frequency == 0):
                gc.collect()
                self.stats['gc_calls'] += 1
                logger.debug(f"gc.collect() called (total: {self.stats['gc_calls']})")
        
        # Concatenate all chunks
        df_result = pd.concat(results, axis=0, ignore_index=True)
        
        # Final garbage collection
        if self.config.enable_gc:
            gc.collect()
            self.stats['gc_calls'] += 1
        
        return df_result
    
    def _compute_by_fold_chunks(
        self,
        df: pd.DataFrame,
        symbol_col: str,
        date_col: str,
    ) -> pd.DataFrame:
        """
        DEPRECATED: Fold-based chunking breaks rolling window calculations.
        
        This method is kept for backward compatibility but should NOT be used.
        It splits time series at chunk boundaries, causing incorrect alpha values
        for indicators that require lookback periods (RSI, ROC, Bollinger, etc.).
        
        Use _compute_by_symbol_chunks() instead.
        """
        logger.error("DEPRECATED: _compute_by_fold_chunks() breaks rolling windows. Use symbol-based chunking instead.")
        raise NotImplementedError(
            "Fold-based chunking is deprecated due to P0 bug (breaks rolling window history). "
            "Use chunk_mode='symbol' instead."
        )
    
    def _compute_alphas_for_chunk(
        self,
        df: pd.DataFrame,
        symbol_col: str,
        date_col: str,
    ) -> pd.DataFrame:
        """Compute 5 Macro Alphas for a single chunk."""
        df_work = df.copy()
        alphas_dict = {}
        
        # Import alpha functions from ultimate_alpha_arsenal
        from .ultimate_alpha_arsenal import (
            compute_roc,
            compute_rsi,
            compute_returns,
            compute_bollinger_distance,
            compute_rsi_crossover,
            compute_volume_ma_ratio,
            compute_illiquidity_amihud,
            compute_atr_normalized,
            compute_historical_volatility,
            compute_distance_to_ma,
        )
        
        # 1. MOMENTUM ALPHAS (5 alphas)
        if self.config.enable_momentum:
            alphas_dict['alpha_roc_20'] = compute_roc(df_work, period=20, symbol_col=symbol_col)
            alphas_dict['alpha_rsi_14'] = compute_rsi(df_work, period=14, symbol_col=symbol_col)
            alphas_dict['alpha_ret_20d'] = compute_returns(df_work, period=20, symbol_col=symbol_col)
            alphas_dict['alpha_ret_60d'] = compute_returns(df_work, period=60, symbol_col=symbol_col)
            alphas_dict['alpha_roc_60'] = compute_roc(df_work, period=60, symbol_col=symbol_col)
        
        # 2. MEAN REVERSION ALPHAS (3 alphas)
        if self.config.enable_mean_reversion:
            alphas_dict['alpha_bollinger_dist_20'] = compute_bollinger_distance(df_work, period=20, symbol_col=symbol_col)
            alphas_dict['alpha_rsi_crossover_20_60'] = compute_rsi_crossover(df_work, short_period=20, long_period=60, symbol_col=symbol_col)
            alphas_dict['alpha_bollinger_dist_60'] = compute_bollinger_distance(df_work, period=60, symbol_col=symbol_col)
        
        # 3. LIQUIDITY ALPHAS (3 alphas)
        if self.config.enable_liquidity:
            alphas_dict['alpha_vol_ma_ratio_5_20'] = compute_volume_ma_ratio(df_work, short_period=5, long_period=20, symbol_col=symbol_col)
            alphas_dict['alpha_illiquidity_amihud_20'] = compute_illiquidity_amihud(df_work, period=20, symbol_col=symbol_col)
            alphas_dict['alpha_vol_ma_ratio_10_60'] = compute_volume_ma_ratio(df_work, short_period=10, long_period=60, symbol_col=symbol_col)
        
        # 4. VOLATILITY ALPHAS (2 alphas)
        if self.config.enable_volatility:
            alphas_dict['alpha_atr_14_norm'] = compute_atr_normalized(df_work, period=14, symbol_col=symbol_col)
            alphas_dict['alpha_hist_vol_20'] = compute_historical_volatility(df_work, period=20, symbol_col=symbol_col)
        
        # 5. TREND ALPHAS (2 alphas)
        if self.config.enable_trend:
            alphas_dict['alpha_dist_ma_20'] = compute_distance_to_ma(df_work, period=20, symbol_col=symbol_col)
            alphas_dict['alpha_dist_ma_60'] = compute_distance_to_ma(df_work, period=60, symbol_col=symbol_col)
        
        # Concatenate alphas to df_work
        if alphas_dict:
            df_work = pd.concat([df_work, pd.DataFrame(alphas_dict, index=df_work.index)], axis=1)
            self.stats['alphas_computed'] += len(alphas_dict)
        
        return df_work
    
    def get_stats(self) -> Dict:
        """Get factory statistics."""
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset factory statistics."""
        self.stats = {
            'chunks_processed': 0,
            'symbols_processed': 0,
            'alphas_computed': 0,
            'gc_calls': 0,
        }


# Convenience function for quick alpha computation
def compute_optimized_alphas(
    df: pd.DataFrame,
    config: Optional[OptimizedAlphaConfig] = None,
    **kwargs,
) -> pd.DataFrame:
    """
    Convenience function for quick optimized alpha computation.
    
    Args:
        df: DataFrame with OHLCV data
        config: Factory configuration (optional)
        **kwargs: Additional arguments passed to compute_macro_alphas
        
    Returns:
        DataFrame with macro alphas
    """
    factory = OptimizedAlphaFactory(config=config)
    return factory.compute_macro_alphas(df, **kwargs)


__all__ = [
    'OptimizedAlphaFactory',
    'OptimizedAlphaConfig',
    'compute_optimized_alphas',
]
