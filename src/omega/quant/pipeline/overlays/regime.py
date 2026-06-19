"""Regime overlay - unified rule-based and HMM regime detection."""
from __future__ import annotations

from typing import Dict, Any
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay


class RegimeOverlay(WeightOverlay):
    """
    Unified regime overlay supporting both rule-based and HMM strategies.

    Args:
        strategy: 'rule_based' (default) or 'hmm'
        hysteresis_days: Min days to hold regime before switching (rule-based only)
        dd_threshold: Drawdown level to trigger BEAR (rule-based only)
        bull_exposure: Exposure multiplier in BULL regime
        bear_exposure: Exposure multiplier in BEAR regime
        sideways_exposure: Exposure multiplier in SIDEWAYS regime
        retrain_every: Retrain HMM every N bars (HMM only)
    """
    def __init__(
        self,
        strategy: str = "rule_based",
        hysteresis_days: int = 5,
        dd_threshold: float = -0.10,
        bull_exposure: float = 1.1,
        bear_exposure: float = 0.5,
        sideways_exposure: float = 0.8,
        retrain_every: int = 60,
    ):
        self.strategy = strategy
        self.hysteresis_days = hysteresis_days
        self.dd_threshold = dd_threshold
        self.bull_exposure = bull_exposure
        self.bear_exposure = bear_exposure
        self.sideways_exposure = sideways_exposure
        self.retrain_every = retrain_every

    def apply(self, weights: pd.DataFrame, panel: pd.DataFrame, state: Dict[str, Any]) -> pd.DataFrame:
        from omega.quant.portfolio.regime_overlay import apply_regime_overlay, RegimeStrategy

        if self.strategy == "rule_based":
            strategy_enum = RegimeStrategy.RULE_BASED
        elif self.strategy == "hmm":
            strategy_enum = RegimeStrategy.HMM
        else:
            raise ValueError(f"Unknown regime strategy: {self.strategy}")

        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(index="date", columns="symbol", values="returns").fillna(0.0)
        returns_pivot = returns_pivot.reindex(index=weights.index, columns=weights.columns, fill_value=0.0)
        market_returns = returns_pivot.mean(axis=1).to_numpy()

        return apply_regime_overlay(
            weights,
            market_returns,
            strategy=strategy_enum,
            hysteresis_days=self.hysteresis_days,
            dd_threshold=self.dd_threshold,
            bull_exposure=self.bull_exposure,
            bear_exposure=self.bear_exposure,
            sideways_exposure=self.sideways_exposure,
            retrain_every=self.retrain_every,
        )
