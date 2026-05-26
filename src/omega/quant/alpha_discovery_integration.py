"""
Alpha Discovery Integration - Preprocessing Pipeline Integration
Version: v21.40-Phase3.4-Reconstruction
Date: 2026-05-08
Author: OpenCode (Senior Quant Coder)

This module integrates the preprocessing pipeline into the alpha discovery workflow.
It provides a unified interface for:
1. Computing macro alphas with mandatory preprocessing
2. Running alpha discovery with sanitization and neutralization
3. Evaluating IC on preprocessed signals

INTEGRATION POINTS:
- alpha_preprocessing.py: Sanitization, normalization, neutralization
- macro_alphas.py: 5 high-IC macro alphas
- alpha_discovery.py: Expression-based alpha generation
- ultimate_alpha_arsenal.py: Legacy alpha computation

WORKFLOW:
    Raw OHLCV → Sanitize → Compute Alphas → Normalize → Neutralize → IC Evaluation
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import pandas as pd
import numpy as np

from .alpha_preprocessing import AlphaPreprocessor, PreprocessingConfig
from .macro_alphas import compute_macro_alphas, MACRO_ALPHA_COLUMNS, get_macro_alpha_metadata
from .alpha_discovery import AlphaJudge, AlphaAlchemist

logger = logging.getLogger(__name__)


@dataclass
class AlphaDiscoveryConfig:
    """Configuration for alpha discovery with preprocessing."""
    
    # Preprocessing config
    preprocessing: PreprocessingConfig = None
    
    # Alpha computation
    enable_macro_alphas: bool = True
    enable_expression_alphas: bool = False  # Disable for now, focus on macro
    
    # IC evaluation
    ic_threshold: float = 0.05  # Target: avg IC > 0.05
    min_coverage: float = 0.80
    future_return_horizon: int = 3  # T+3 holding period
    
    # Column names
    symbol_col: str = "ticker"
    date_col: str = "date"
    close_col: str = "close"
    
    def __post_init__(self):
        if self.preprocessing is None:
            self.preprocessing = PreprocessingConfig()


class AlphaDiscoveryPipeline:
    """
    Unified alpha discovery pipeline with mandatory preprocessing.
    
    Pipeline stages:
    1. Sanitize OHLCV (winsorization)
    2. Compute alphas (macro + expression-based)
    3. Normalize signals (z-score)
    4. Neutralize signals (hierarchical)
    5. Evaluate IC and filter
    """
    
    def __init__(self, config: Optional[AlphaDiscoveryConfig] = None):
        """Initialize pipeline with configuration."""
        self.config = config or AlphaDiscoveryConfig()
        self.preprocessor = AlphaPreprocessor(config=self.config.preprocessing)
        self.judge = AlphaJudge(ic_threshold=self.config.ic_threshold)
        self.alchemist = AlphaAlchemist()
        
        # Track statistics
        self.stats = {
            "alphas_computed": 0,
            "alphas_passed_ic": 0,
            "avg_ic": 0.0,
            "preprocessing_applied": False,
        }
    
    def run_full_pipeline(
        self,
        df: pd.DataFrame,
        compute_future_returns: bool = True,
    ) -> Tuple[pd.DataFrame, Dict[str, float]]:
        """
        Run full alpha discovery pipeline with preprocessing.
        
        Args:
            df: DataFrame with OHLCV data
            compute_future_returns: Whether to compute future returns for IC evaluation
            
        Returns:
            Tuple of (df_with_alphas, ic_scores_dict)
        """
        logger.info("Starting alpha discovery pipeline with preprocessing")
        
        # Stage 1: Sanitize OHLCV
        logger.info("Stage 1: Sanitizing OHLCV data")
        df_clean = self.preprocessor.sanitize_ohlcv(
            df,
            ohlcv_cols=["open", "high", "low", "close", "volume"],
            symbol_col=self.config.symbol_col,
            date_col=self.config.date_col,
        )
        
        # Stage 2: Compute alphas
        logger.info("Stage 2: Computing alphas")
        alpha_cols = []
        
        if self.config.enable_macro_alphas:
            logger.info("Computing 5 macro alphas")
            df_clean = compute_macro_alphas(
                df_clean,
                symbol_col=self.config.symbol_col,
                date_col=self.config.date_col,
            )
            alpha_cols.extend(MACRO_ALPHA_COLUMNS)
            self.stats["alphas_computed"] += len(MACRO_ALPHA_COLUMNS)
        
        if self.config.enable_expression_alphas:
            logger.info("Computing expression-based alphas (disabled for Phase 3.4)")
            # TODO: Integrate expression-based alpha generation
            pass
        
        # Stage 3: Normalize signals (z-score)
        logger.info("Stage 3: Normalizing alpha signals")
        df_normalized = self.preprocessor.normalize_signals(
            df_clean,
            alpha_cols=alpha_cols,
            date_col=self.config.date_col,
            symbol_col=self.config.symbol_col,
        )
        
        # Update alpha_cols to use normalized versions
        alpha_cols_normalized = [f"{col}_zscore" for col in alpha_cols]
        
        # Stage 4: Neutralize signals
        logger.info("Stage 4: Neutralizing alpha signals")
        df_final = self.preprocessor.neutralize_signals(
            df_normalized,
            alpha_cols=alpha_cols_normalized,
            date_col=self.config.date_col,
            symbol_col=self.config.symbol_col,
        )
        
        self.stats["preprocessing_applied"] = True
        
        # Stage 5: Evaluate IC
        if compute_future_returns:
            logger.info("Stage 5: Evaluating IC scores")
            ic_scores = self._evaluate_ic(df_final, alpha_cols_normalized)
        else:
            ic_scores = {}
        
        logger.info(f"Pipeline complete: {self.stats['alphas_computed']} alphas computed, "
                   f"{self.stats['alphas_passed_ic']} passed IC threshold")
        
        return df_final, ic_scores
    
    def _evaluate_ic(
        self,
        df: pd.DataFrame,
        alpha_cols: List[str],
    ) -> Dict[str, float]:
        """
        Evaluate IC scores for all alpha columns.
        
        Args:
            df: DataFrame with alpha columns
            alpha_cols: List of alpha column names
            
        Returns:
            Dict mapping alpha_name -> IC score
        """
        # Compute future returns
        df_work = df.copy()
        df_work = df_work.sort_values([self.config.date_col, self.config.symbol_col])
        
        # Convert to MultiIndex for IC computation
        if not isinstance(df_work.index, pd.MultiIndex):
            df_indexed = df_work.set_index([self.config.date_col, self.config.symbol_col])
        else:
            df_indexed = df_work
        
        # Compute future returns
        close_series = df_indexed[self.config.close_col]
        future_returns = self.judge.compute_future_returns(
            close_series,
            horizon=self.config.future_return_horizon,
        )
        
        # Evaluate IC for each alpha
        ic_scores = {}
        passed_count = 0
        ic_sum = 0.0
        
        for alpha_col in alpha_cols:
            if alpha_col not in df_indexed.columns:
                logger.warning(f"Alpha column '{alpha_col}' not found, skipping IC evaluation")
                continue
            
            alpha_series = df_indexed[alpha_col]
            ic = self.judge.information_coefficient(alpha_series, future_returns)
            ic_scores[alpha_col] = ic
            ic_sum += abs(ic)
            
            if self.judge.passes_threshold(ic):
                passed_count += 1
                logger.info(f"✓ {alpha_col}: IC = {ic:.4f} (PASSED)")
            else:
                logger.info(f"✗ {alpha_col}: IC = {ic:.4f} (FAILED)")
        
        # Update statistics
        self.stats["alphas_passed_ic"] = passed_count
        self.stats["avg_ic"] = ic_sum / len(ic_scores) if ic_scores else 0.0
        
        logger.info(f"IC Evaluation Summary: {passed_count}/{len(ic_scores)} alphas passed threshold")
        logger.info(f"Average |IC|: {self.stats['avg_ic']:.4f}")
        
        return ic_scores
    
    def get_pipeline_report(self) -> str:
        """Generate pipeline execution report."""
        report = "=== Alpha Discovery Pipeline Report ===\n"
        report += f"Alphas Computed: {self.stats['alphas_computed']}\n"
        report += f"Alphas Passed IC Threshold: {self.stats['alphas_passed_ic']}\n"
        report += f"Average |IC|: {self.stats['avg_ic']:.4f}\n"
        report += f"Preprocessing Applied: {self.stats['preprocessing_applied']}\n"
        report += "\n"
        report += self.preprocessor.get_preprocessing_report()
        
        return report
    
    def export_alphas(
        self,
        df: pd.DataFrame,
        alpha_cols: List[str],
        output_path: str,
    ) -> None:
        """
        Export alpha signals to CSV for backtesting.
        
        Args:
            df: DataFrame with alpha columns
            alpha_cols: List of alpha column names to export
            output_path: Output CSV file path
        """
        export_cols = [self.config.date_col, self.config.symbol_col] + alpha_cols
        df_export = df[export_cols].copy()
        df_export.to_csv(output_path, index=False)
        logger.info(f"Exported {len(alpha_cols)} alphas to {output_path}")


# Convenience function for quick alpha discovery
def discover_alphas(
    df: pd.DataFrame,
    config: Optional[AlphaDiscoveryConfig] = None,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Convenience function for quick alpha discovery with preprocessing.
    
    Args:
        df: DataFrame with OHLCV data
        config: Discovery configuration (optional)
        
    Returns:
        Tuple of (df_with_alphas, ic_scores_dict)
    """
    pipeline = AlphaDiscoveryPipeline(config=config)
    return pipeline.run_full_pipeline(df, compute_future_returns=True)


# Integration with existing alpha_discovery.py
def integrate_preprocessing_into_alchemist(
    panel: pd.DataFrame,
    preprocessor: AlphaPreprocessor,
) -> pd.DataFrame:
    """
    Integrate preprocessing into AlphaAlchemist workflow.
    
    This function sanitizes the input panel before expression evaluation.
    
    Args:
        panel: Input panel with OHLCV data
        preprocessor: AlphaPreprocessor instance
        
    Returns:
        Sanitized panel ready for AlphaAlchemist
    """
    # Sanitize OHLCV columns
    panel_clean = preprocessor.sanitize_ohlcv(
        panel,
        ohlcv_cols=["open", "high", "low", "close", "volume"],
    )
    
    return panel_clean


__all__ = [
    "AlphaDiscoveryPipeline",
    "AlphaDiscoveryConfig",
    "discover_alphas",
    "integrate_preprocessing_into_alchemist",
]
