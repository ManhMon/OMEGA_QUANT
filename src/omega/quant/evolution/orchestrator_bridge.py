"""
OMEGA_QUANT System Orchestrator Bridge
Connects legacy V21_QuantSystem to new unified pipeline.

Since legacy quant system has unresolvable legacy imports,
this bridge provides the same interface using new modules.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class OmegaQuantOrchestrator:
    """
    Modern orchestrator replacing V21QuantSystem.
    Wires: UnifiedFeatureAdapter -> Screening -> HRP -> Regime -> Backtest
    """

    def __init__(self):
        from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
        from omega.quant.evolution.regime_detector import RegimeDetector
        from omega.quant.evolution.hrp_weighter import HRPWeighter
        from omega.quant.evolution.ml_alpha_integration import MLAlphaIntegration
        from omega.quant.parallel_backtest import ParallelBacktestRunner

        self.feature_adapter = UnifiedFeatureAdapter()
        self.regime_detector = RegimeDetector()
        self.hrp = HRPWeighter()
        self.ml_combiner = MLAlphaIntegration()
        self.backtest_runner = ParallelBacktestRunner(num_workers=4)

    def run_research_pipeline(
        self,
        train_panel: pd.DataFrame,
        val_panel: pd.DataFrame,
        test_panel: pd.DataFrame,
        target_col: str = "fwd_ret_5",
    ) -> Dict:
        """
        Full research pipeline: features -> screening -> ML -> HRP -> backtest.

        Args:
            train_panel: MultiIndex [date, symbol] OHLCV + returns
            val_panel: Validation period
            test_panel: Test period (untouched until backtest)
            target_col: Forward return target

        Returns:
            Results dict with metrics.
        """
        logger.info("=== OMEGA QUANT ORCHESTRATOR: Research Pipeline ===")

        # 1. Generate features on val + test
        logger.info("[1/5] Generating features...")
        val_featured = self.feature_adapter.generate_all(val_panel)
        test_featured = self.feature_adapter.generate_all(test_panel)
        features = self.feature_adapter.get_all_feature_names()
        logger.info("  Features: %d", len(features))

        # 2. Train ML combiner on validation
        logger.info("[2/5] Training ML combiner...")
        val_with_target = val_featured.copy()
        val_with_target[target_col] = val_with_target.groupby(level='symbol')['close'].pct_change(5).shift(-5)
        val_with_target = val_with_target.dropna(subset=[target_col])
        train_result = self.ml_combiner.train_combiner(val_with_target, features, target_col)
        logger.info("  ML train: %s", train_result.get('status'))

        # 3. Generate signal on test
        logger.info("[3/5] Generating test signal...")
        ml_signal = self.ml_combiner.predict(test_featured)

        # 4. Build weights + regime + HRP
        logger.info("[4/5] Portfolio construction (HRP + Regime)...")
        test_prices = test_panel['close'].unstack(level='symbol').dropna(axis=1, how='all').ffill()

        # Simple weight from ML signal
        unstacked = ml_signal.unstack(level='symbol') if isinstance(ml_signal.index, pd.MultiIndex) else ml_signal
        if isinstance(unstacked, pd.DataFrame):
            ranked = unstacked.rank(axis=1, pct=True)
            weights = ranked.div(ranked.sum(axis=1), axis=0).fillna(0)
        else:
            weights = pd.DataFrame(1.0 / len(test_prices.columns), index=test_prices.index, columns=test_prices.columns)

        # Regime adjustment
        market_prices = test_prices.mean(axis=1)
        regime_state = self.regime_detector.detect(market_prices)
        weights = weights * regime_state.exposure_multiplier
        row_sums = weights.sum(axis=1)
        weights.loc[row_sums > 1] = weights.loc[row_sums > 1].div(row_sums[row_sums > 1], axis=0)

        # Align
        weights = weights.clip(upper=0.05)
        row_sums = weights.sum(axis=1).replace(0, 1.0)
        weights = weights.div(row_sums, axis=0)

        valid = weights.sum(axis=1) > 0
        weights = weights.loc[valid]
        prices_aligned = test_prices.loc[weights.index]
        common = weights.columns.intersection(prices_aligned.columns)
        weights = weights[common]
        prices_aligned = prices_aligned[common]

        # 5. Backtest
        logger.info("[5/5] Running backtest...")
        if len(weights) >= 10:
            bt_result = self.backtest_runner.run(prices_aligned, weights)
            metrics = bt_result.metrics
        else:
            metrics = {"sharpe": 0, "total_return": 0}

        logger.info("=== ORCHESTRATOR COMPLETE: Sharpe=%.4f, Return=%.4f ===",
                    metrics.get('sharpe', 0), metrics.get('total_return', 0))

        return {
            "features": len(features),
            "ml_train": train_result,
            "regime": regime_state.regime.value,
            "metrics": metrics,
        }
