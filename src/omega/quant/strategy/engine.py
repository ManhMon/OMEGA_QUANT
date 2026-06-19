"""
Strategy Engine - V21 Institutional
Orchestrates Layer 02 end-to-end: scores -> blend -> filters -> universe -> sizing.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np

from omega.quant.signal_blender import SignalBlender, BlendedSignal
from omega.quant.strategy.market_regime import MarketRegimeFilter, RegimeReport, MarketRegime
from omega.quant.data.dynamic_universe import DynamicUniverseSelector, UniverseConfig, SelectedUniverse
from omega.quant.portfolio.position_sizer import PositionSizer, PositionConfig, TargetPortfolio
from omega.quant.execution.transaction_cost import TransactionCostModel, CostEstimate


@dataclass
class StrategyOutput:
    """Final output of Layer 02 strategy engine."""
    regime_report: RegimeReport
    blended_signal: BlendedSignal
    selected_universe: SelectedUniverse
    target_portfolio: TargetPortfolio
    estimated_costs: Dict[str, CostEstimate]


class StrategyEngine:
    """Full Layer 02 orchestration engine.

    Flow:
    1. Regime filter on market index
    2. Blend model signals
    3. Select dynamic universe
    4. Size positions
    5. Estimate transaction costs
    """

    def __init__(
        self,
        blender: Optional[SignalBlender] = None,
        regime_filter: Optional[MarketRegimeFilter] = None,
        universe_selector: Optional[DynamicUniverseSelector] = None,
        position_sizer: Optional[PositionSizer] = None,
        tx_cost_model: Optional[TransactionCostModel] = None
    ):
        self.blender = blender or SignalBlender()
        self.regime_filter = regime_filter or MarketRegimeFilter()
        self.universe_selector = universe_selector or DynamicUniverseSelector()
        self.position_sizer = position_sizer or PositionSizer()
        self.tx_cost_model = tx_cost_model or TransactionCostModel()

    def run(
        self,
        market_index_prices: np.ndarray,
        model_scores: Dict[str, Dict[str, float]],
        model_weights: Dict[str, float],
        all_symbols: List[str],
        adv_values: Dict[str, float],
        sectors: Dict[str, str],
        volatilities: Dict[str, float],
        prices: Dict[str, float],
        capital: float,
        is_active: Optional[Dict[str, bool]] = None,
        win_rates: Optional[Dict[str, float]] = None,
        payoff_ratios: Optional[Dict[str, float]] = None
    ) -> StrategyOutput:
        """Execute Layer 02 end-to-end.

        Returns:
            StrategyOutput with all intermediate artifacts
        """
        # 1. Regime filter
        regime_report = self.regime_filter.detect(market_index_prices)

        # If regime says not tradeable, return empty portfolio
        if not regime_report.is_tradeable:
            empty_signal = BlendedSignal(final_scores={}, model_contributions={}, weights_used=model_weights)
            empty_universe = SelectedUniverse(symbols=[], scores={}, liquidity={}, sector_weights={}, excluded_reason={})
            empty_portfolio = TargetPortfolio(weights={}, shares={}, cash_weight=1.0, metadata={"blocked_by_regime": regime_report.regime.value})
            return StrategyOutput(
                regime_report=regime_report,
                blended_signal=empty_signal,
                selected_universe=empty_universe,
                target_portfolio=empty_portfolio,
                estimated_costs={}
            )

        # 2. Blend signals
        blended = self.blender.blend(model_scores, model_weights)

        # 3. Select dynamic universe
        selected = self.universe_selector.select(
            symbols=all_symbols,
            scores=blended.final_scores,
            adv_values=adv_values,
            sectors=sectors,
            is_active=is_active
        )

        # 4. Size positions
        portfolio = self.position_sizer.compute(
            symbols=selected.symbols,
            scores=blended.final_scores,
            volatilities=volatilities,
            capital=capital,
            prices=prices,
            win_rates=win_rates,
            payoff_ratios=payoff_ratios,
        )

        # 5. Estimate transaction costs for each selected symbol
        estimated_costs: Dict[str, CostEstimate] = {}
        for symbol in selected.symbols:
            weight = float(portfolio.weights.get(symbol, 0.0))
            order_value = float(capital) * weight
            if order_value <= 0:
                continue
            estimated_costs[symbol] = self.tx_cost_model.estimate_cost(
                symbol=symbol,
                order_value=order_value,
                adv_value=float(adv_values.get(symbol, 0.0)),
                price=float(prices.get(symbol, 0.0)),
                side="BUY",
            )

        # 6. Adjust weights for transaction costs (must-fix)
        if estimated_costs and portfolio.weights:
            adjusted_weights: Dict[str, float] = {}
            for symbol, w in portfolio.weights.items():
                ce = estimated_costs.get(symbol)
                if ce is None:
                    adjusted_weights[symbol] = float(w)
                    continue
                adjusted_weights[symbol] = self.tx_cost_model.adjust_position_for_cost(
                    target_weight=float(w),
                    total_capital=float(capital),
                    cost_estimate=ce,
                    min_weight=0.0,
                )

            # Renormalize adjusted weights (keep same symbol set)
            s = sum(adjusted_weights.values())
            if s > 0:
                adjusted_weights = {k: v / s for k, v in adjusted_weights.items()}

            portfolio = self.position_sizer.build_from_weights(
                symbols=selected.symbols,
                weights=adjusted_weights,
                capital=float(capital),
                prices=prices,
            )

        return StrategyOutput(
            regime_report=regime_report,
            blended_signal=blended,
            selected_universe=selected,
            target_portfolio=portfolio,
            estimated_costs=estimated_costs,
        )
