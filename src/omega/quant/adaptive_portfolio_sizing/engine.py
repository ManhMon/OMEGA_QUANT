"""
Adaptive Portfolio Sizing Engine (APSE) - OMEGA_QUANT Layer 08
Optimizes portfolio structures and alpha settings dynamically by capital scale.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

from omega.core.vn_market_rules import VnMarketRules
from omega.quant.portfolio.constraint_solver import ConstraintConfig
from omega.quant.portfolio.portfolio_optimizer import OptimizerConfig
from omega.quant.adaptive_portfolio_sizing.benchmark_provider import (
    get_bank_interest_rate,
    get_vnindex_return,
)


@dataclass
class AdaptiveConfig:
    """Output configuration from APSE optimization."""
    # Portfolio Structure
    target_num_holdings: int
    min_num_holdings: int
    max_num_holdings: int
    
    # Position Sizing
    max_asset_cap: float
    max_sector_cap: float
    min_position_size: float  # VND
    max_position_size: float  # VND
    
    # Trading Constraints
    max_adv_percentage: float
    min_trade_value: float  # VND
    target_turnover: float
    
    # Feature Gating
    enabled_alphas: List[str] = field(default_factory=list)
    enabled_modules: Dict[str, bool] = field(default_factory=dict)
    
    # Metadata
    capital_tier: str = ""
    optimization_timestamp: datetime = field(default_factory=datetime.now)
    expected_sharpe: float = 0.0
    benchmark_threshold: float = 0.0
    expected_return: float = 0.0

    def to_constraint_config(
        self, as_of: datetime, available_at: datetime
    ) -> ConstraintConfig:
        return ConstraintConfig(
            max_notional_per_asset=self.max_position_size,
            max_leverage=2.0,
            max_industry_concentration=self.max_sector_cap,
            max_asset_concentration=self.max_asset_cap,
            as_of=as_of,
            available_at=available_at,
            long_only=True,
            board_lot_size=VnMarketRules.BOARD_LOT,
            min_cash_balance=10_000.0,
        )

    def to_optimizer_config(self) -> OptimizerConfig:
        min_weight = self.min_position_size / self.max_position_size * self.max_asset_cap if self.max_position_size > 0 else 0.0
        return OptimizerConfig(
            max_leverage=1.0,
            max_concentration=self.max_asset_cap,
            min_weight=min_weight,
            max_weight=self.max_asset_cap,
            max_turnover=self.target_turnover,
            turnover_penalty=0.0,
            transaction_cost_bps=30.0,  # 0.3% one-way = 30 bps
            sector_limits=None,
            liquidity_limits=None,
            method="mean_variance",
            rebalance_threshold=None,
            allow_short=False,
            sector_neutral=False,
        )


class AdaptivePortfolioSizingEngine:
    """Core APSE engine with dynamic benchmark rate updates."""
    
    # Capital tier thresholds (VND)
    TIER_THRESHOLDS = {
        'micro': (0, 5_000_000_000),
        'small': (5_000_000_000, 20_000_000_000),
        'medium': (20_000_000_000, 100_000_000_000),
        'large': (100_000_000_000, float('inf'))
    }
    
    # Tier-specific parameter ranges
    TIER_PARAMS = {
        'micro': {
            'holdings_range': (8, 12),
            'asset_cap_range': (0.15, 0.25),
            'sector_cap_range': (0.35, 0.45),
            'adv_pct_range': (0.30, 0.40),
            'turnover_range': (0.40, 0.60),
            'min_trade_multiplier': 1,
            'enabled_alphas': ['momentum', 'value', 'quality']
        },
        'small': {
            'holdings_range': (30, 60),
            'asset_cap_range': (0.10, 0.15),
            'sector_cap_range': (0.25, 0.35),
            'adv_pct_range': (0.20, 0.30),
            'turnover_range': (0.25, 0.35),
            'min_trade_multiplier': 2,
            'enabled_alphas': ['momentum', 'value', 'quality', 'low_vol', 'size']
        },
        'medium': {
            'holdings_range': (20, 40),
            'asset_cap_range': (0.08, 0.12),
            'sector_cap_range': (0.20, 0.30),
            'adv_pct_range': (0.15, 0.25),
            'turnover_range': (0.15, 0.25),
            'min_trade_multiplier': 4,
            'enabled_alphas': ['momentum', 'value', 'quality', 'low_vol', 'size', 
                              'liquidity', 'sentiment', 'technical']
        },
        'large': {
            'holdings_range': (40, 80),
            'asset_cap_range': (0.05, 0.10),
            'sector_cap_range': (0.15, 0.25),
            'adv_pct_range': (0.10, 0.20),
            'turnover_range': (0.10, 0.15),
            'min_trade_multiplier': 10,
            'enabled_alphas': ['momentum', 'value', 'quality', 'low_vol', 'size',
                              'liquidity', 'sentiment', 'technical', 'hft']
        }
    }
    
    def __init__(
        self,
        capital: float,
        market_regime: Optional[str] = None,
        alpha_quality: Optional[float] = None,
        avg_stock_price: float = 50.0,
        board_lot_size: Optional[int] = None,
        risk_tolerance: float = 1.0
    ):
        self.capital = capital
        self.market_regime = market_regime or 'neutral'
        self.alpha_quality = alpha_quality or 0.05
        self.avg_stock_price = avg_stock_price
        self.board_lot_size = board_lot_size if board_lot_size is not None else VnMarketRules.BOARD_LOT
        self.risk_tolerance = risk_tolerance
        
        self.capital_tier = self._determine_capital_tier(capital)
        self.tier_params = self.TIER_PARAMS[self.capital_tier]
    
    def _determine_capital_tier(self, capital: float) -> str:
        for tier, (min_cap, max_cap) in self.TIER_THRESHOLDS.items():
            if min_cap <= capital < max_cap:
                return tier
        return 'large'
    
    def _calculate_optimal_num_holdings(self) -> Tuple[int, int, int]:
        import math
        min_position_vnd = self.avg_stock_price * 1000 * self.board_lot_size
        min_alloc_map = {'micro': 0.03, 'small': 0.015, 'medium': 0.01, 'large': 0.005}
        min_allocation_pct = min_alloc_map.get(self.capital_tier, 0.01)
        min_position_value = max(min_position_vnd, self.capital * min_allocation_pct)
        max_possible_holdings = int(self.capital / min_position_value)
        
        avg_universe_adv = 10_000_000_000
        max_adv_pct = self.TIER_PARAMS[self.capital_tier]['adv_pct_range'][0]
        capacity_per_stock = avg_universe_adv * max_adv_pct
        min_holdings_for_liquidity = math.ceil(self.capital / capacity_per_stock)
        
        min_h, max_h = self.tier_params['holdings_range']
        min_holdings = max(min_h, min_holdings_for_liquidity)
        max_holdings = min(max_h, max_possible_holdings)
        
        max_holdings_from_capital = int(self.capital / (self.capital * 0.01))
        max_holdings = min(max_holdings, max_holdings_from_capital)
        
        if min_holdings > max_holdings:
            min_holdings = max_holdings
            
        target_holdings = int((min_holdings + max_holdings) / 2)
        return target_holdings, min_holdings, max_holdings
    
    def _calculate_optimal_asset_cap(self, num_holdings: int) -> float:
        equal_weight = 1.0 / num_holdings if num_holdings > 0 else 0.0
        min_cap, max_cap = self.tier_params['asset_cap_range']
        tier_cap = (min_cap + max_cap) / 2
        optimal_cap = max(equal_weight * 2, min(tier_cap, max_cap))
        return optimal_cap
    
    def _calculate_optimal_sector_cap(self) -> float:
        min_cap, max_cap = self.tier_params['sector_cap_range']
        return (min_cap + max_cap) / 2
    
    def _calculate_optimal_adv_pct(self) -> float:
        min_adv, max_adv = self.tier_params['adv_pct_range']
        base_adv = (min_adv + max_adv) / 2
        regime_adjustment = {
            'bull': 1.1,
            'neutral': 1.0,
            'bear': 0.9
        }[self.market_regime]
        adjusted_adv = base_adv * regime_adjustment * self.risk_tolerance
        return np.clip(adjusted_adv, min_adv, max_adv)
    
    def _calculate_min_trade_value(self) -> float:
        one_board_lot_vnd = self.board_lot_size * self.avg_stock_price * 1000
        multiplier = self.tier_params['min_trade_multiplier']
        return one_board_lot_vnd * multiplier
    
    def _calculate_position_sizes(self, num_holdings: int, asset_cap: float) -> Tuple[float, float]:
        min_position = self.board_lot_size * self.avg_stock_price * 1000
        max_position = asset_cap * self.capital
        return min_position, max_position
    
    def _get_feature_gating(self) -> Tuple[List[str], Dict[str, bool]]:
        enabled_alphas = self.tier_params['enabled_alphas'].copy()
        if self.alpha_quality < 0.03:
            enabled_alphas = [a for a in enabled_alphas if a in ['momentum', 'value']]
        all_alphas = ['momentum', 'value', 'quality', 'low_vol', 'size',
                     'liquidity', 'sentiment', 'technical', 'hft']
        enabled_modules = {alpha: alpha in enabled_alphas for alpha in all_alphas}
        return enabled_alphas, enabled_modules
    
    def _calculate_expected_return(self, num_holdings: int, turnover: float, bank_rate: float) -> float:
        volatility = 0.30
        tc_rate = 0.003
        rebalancing_frequency = np.sqrt(12)
        breadth = num_holdings * rebalancing_frequency
        gross_alpha = self.alpha_quality * np.sqrt(breadth) * volatility
        gross_return = gross_alpha + bank_rate
        transaction_costs = turnover * 2 * tc_rate
        net_return = gross_return - transaction_costs
        return net_return
    
    def _calculate_sharpe(self, expected_return: float, benchmark_threshold: float) -> float:
        volatility = 0.30
        excess_return = expected_return - benchmark_threshold
        sharpe = excess_return / volatility if volatility > 0 else 0.0
        return sharpe
    
    def get_benchmark_threshold(self, bank_rate: float, vnindex_return: float) -> float:
        return max(bank_rate, vnindex_return)
    
    def optimize(
        self,
        as_of: datetime,
        vnindex_data: Optional[pd.DataFrame] = None,
        focal_stress_score: float = 0.0
    ) -> AdaptiveConfig:
        """
        Optimize portfolio parameters using dynamic benchmark rates for PIT safety.
        """
        if as_of is None:
            raise ValueError("as_of is mandatory for PIT safety")
            
        date_str = as_of.strftime('%Y-%m-%d')
        start_date_str = (as_of - timedelta(days=365)).strftime('%Y-%m-%d')
        
        # Get dynamic rates from provider
        bank_rate = get_bank_interest_rate(date_str)
        vnindex_return = get_vnindex_return(
            start_date=start_date_str,
            end_date=date_str,
            pit_cutoff_date=date_str,
            data_source=vnindex_data
        )
        
        # Calculate optimal parameters
        target_holdings, min_holdings, max_holdings = self._calculate_optimal_num_holdings()
        asset_cap = self._calculate_optimal_asset_cap(target_holdings)
        sector_cap = self._calculate_optimal_sector_cap()
        adv_pct = self._calculate_optimal_adv_pct()
        min_trade_value = self._calculate_min_trade_value()
        
        # Adjust caps if focal stress is critical (> 60)
        if focal_stress_score > 60.0:
            logger.warning(
                "Critical focal stress detected (%.1f/100). Reducing asset/sector concentration caps by 20%%.",
                focal_stress_score
            )
            asset_cap *= 0.8
            sector_cap *= 0.8
            adv_pct *= 0.8
        
        # Turnover
        min_turn, max_turn = self.tier_params['turnover_range']
        target_turnover = (min_turn + max_turn) / 2
        
        # Position sizes
        min_position, max_position = self._calculate_position_sizes(target_holdings, asset_cap)
        
        # Feature gating
        enabled_alphas, enabled_modules = self._get_feature_gating()
        
        # Under critical stress, enforce defensive alphas
        if focal_stress_score > 60.0:
            enabled_alphas = [a for a in enabled_alphas if a in ['low_vol', 'quality', 'value']]
            if not enabled_alphas:
                enabled_alphas = ['low_vol', 'quality']
            for alpha in enabled_modules:
                enabled_modules[alpha] = alpha in enabled_alphas
        
        # Calculate expected performance
        expected_return = self._calculate_expected_return(target_holdings, target_turnover, bank_rate)
        benchmark_threshold = self.get_benchmark_threshold(bank_rate, vnindex_return)
        expected_sharpe = self._calculate_sharpe(expected_return, benchmark_threshold)
        
        # Create config
        config = AdaptiveConfig(
            target_num_holdings=target_holdings,
            min_num_holdings=min_holdings,
            max_num_holdings=max_holdings,
            max_asset_cap=asset_cap,
            max_sector_cap=sector_cap,
            min_position_size=min_position,
            max_position_size=max_position,
            max_adv_percentage=adv_pct,
            min_trade_value=min_trade_value,
            target_turnover=target_turnover,
            enabled_alphas=enabled_alphas,
            enabled_modules=enabled_modules,
            capital_tier=self.capital_tier,
            optimization_timestamp=as_of,
            expected_sharpe=expected_sharpe,
            benchmark_threshold=benchmark_threshold,
            expected_return=expected_return
        )
        
        return config
