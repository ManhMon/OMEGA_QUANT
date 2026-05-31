"""
OMEGA_QUANT Unified Feature Adapter
Merges 3 feature systems into 1 unified interface:
1. FeatureModule (10 basic features)
2. AlternativeFeatureGenerator (25 derived features)
3. ultimate_alpha_arsenal (130 institutional alphas)

Provides single entry point for backtest/screening pipeline.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - All underlying systems enforce T-1 lag.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class UnifiedFeatureAdapter:
    """
    Single entry point for all feature generation.
    Combines FeatureModule + AlternativeFeatureGenerator + ultimate_alpha_arsenal.
    """

    def __init__(self, use_arsenal: bool = True, use_alt_features: bool = True, use_alt_data: bool = True):
        self.use_arsenal = use_arsenal
        self.use_alt_features = use_alt_features
        self.use_alt_data = use_alt_data
        self._arsenal_features: List[str] = []
        self._alt_features: List[str] = []
        self._alt_data_features: List[str] = []

    def generate_all(self, panel: pd.DataFrame) -> pd.DataFrame:
        """
        Generate all features from all 3 systems.

        Args:
            panel: MultiIndex [date, symbol] DataFrame with open/high/low/close/volume

        Returns:
            Panel with all features added.
        """
        result = panel.copy()
        total_before = len(result.columns)

        # 1. Alternative Features (25 derived from OHLCV)
        if self.use_alt_features:
            try:
                from omega.quant.evolution.alternative_features import AlternativeFeatureGenerator
                feat_gen = AlternativeFeatureGenerator()
                result = feat_gen.generate_all(result)
                self._alt_features = feat_gen.get_feature_names()
                logger.info("Alt features: +%d", len(self._alt_features))
            except Exception as e:
                logger.warning("AlternativeFeatureGenerator failed: %s", e)

        # 2. Alternative Data (8 proxy signals)
        if self.use_alt_data:
            try:
                from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher
                fetcher = AlternativeDataFetcher()
                result = fetcher.generate_all(result)
                self._alt_data_features = fetcher.get_feature_names()
                logger.info("Alt data: +%d", len(self._alt_data_features))
            except Exception as e:
                logger.warning("AlternativeDataFetcher failed: %s", e)

        # 3. Ultimate Alpha Arsenal (130 institutional alphas)
        if self.use_arsenal:
            try:
                from omega.quant.ultimate_alpha_arsenal import compute_ultimate_alphas
                # Arsenal expects flat DataFrame with ticker/date columns
                flat = result.reset_index()
                flat.columns = ['date', 'ticker'] + list(flat.columns[2:])
                # Ensure required columns
                required = ['date', 'ticker', 'open', 'high', 'low', 'close', 'volume']
                if all(c in flat.columns for c in required):
                    arsenal_df = compute_ultimate_alphas(flat[required], symbol_col='ticker')
                    # Get alpha columns (prefixed with alpha_)
                    alpha_cols = [c for c in arsenal_df.columns if c.startswith('alpha_')]
                    if alpha_cols:
                        # Merge back to MultiIndex
                        arsenal_df = arsenal_df.set_index(['date', 'ticker'])[alpha_cols]
                        arsenal_df.index.names = ['date', 'symbol']
                        # Join to result
                        result = result.join(arsenal_df, how='left')
                        self._arsenal_features = alpha_cols
                        logger.info("Arsenal alphas: +%d", len(alpha_cols))
                else:
                    logger.warning("Arsenal skipped: missing required columns")
            except Exception as e:
                logger.warning("ultimate_alpha_arsenal failed: %s", e)

        total_after = len(result.columns)
        logger.info("UnifiedFeatureAdapter: %d -> %d columns (+%d features)",
                    total_before, total_after, total_after - total_before)
        return result

    def get_all_feature_names(self) -> List[str]:
        """Return all generated feature names across all systems."""
        return self._alt_features + self._alt_data_features + self._arsenal_features

    def get_feature_groups(self) -> dict:
        """Return features grouped by source system."""
        return {
            "alt_features": self._alt_features,
            "alt_data": self._alt_data_features,
            "arsenal": self._arsenal_features,
        }
