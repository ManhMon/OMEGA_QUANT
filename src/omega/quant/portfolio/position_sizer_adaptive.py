"""
Adaptive Portfolio Sizing Engine (APSE)
========================================

Self-adaptive capital management system that optimizes portfolio parameters
based on capital size to maximize risk-adjusted returns.

Author: V21_QUANT Team (OMEGA_QUANT Consolidation)
Date: 2026-04-29
Version: 1.1
Status: OMEGA_QUANT Consolidation - Monolithic omega.quant
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from omega.core.vn_market_rules import VnMarketRules
from omega.quant.constraint_solver import ConstraintConfig
from omega.quant.portfolio_optimizer import OptimizerConfig


@dataclass
class AdaptiveConfig:
    """
    Output configuration from APSE optimization.
    
    Contains all optimized portfolio parameters ready for SystemConfig.
    """
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
        """
        Convert AdaptiveConfig to ConstraintConfig for ConstraintSolver.

        Mapping:
            max_asset_cap -> max_asset_concentration
            max_sector_cap -> max_industry_concentration
            max_position_size -> max_notional_per_asset
            board_lot_size from VnMarketRules (default 100)
            Sensible defaults: max_leverage=2.0, min_cash_balance=10_000.0

        Args:
            as_of: Point-in-time date (T-1 lag enforcement).
            available_at: Date when data becomes available (PIT safety).

        Returns:
            ConstraintConfig ready for ConstraintSolver.validate_weights().
        """
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
        """
        Convert AdaptiveConfig to OptimizerConfig for PortfolioOptimizer.

        Mapping:
            max_asset_cap -> max_concentration
            min_position_size / max_position_size -> min_weight (as fraction)
            max_asset_cap -> max_weight
            target_turnover -> max_turnover
            max_sector_cap -> sector_limits (uniform across sectors)

        Returns:
            OptimizerConfig ready for PortfolioOptimizer.optimize().
        """
        # min_weight as fraction: min_position_size relative to a notional capital
        # Use the ratio min_position_size / max_position_size * max_asset_cap
        # which gives the minimum meaningful weight
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
    """
    Core APSE engine that optimizes portfolio parameters based on capital size.
    
    Guarantees: Total Return > max(Bank Interest Rate, VN-Index Return)
    
    Usage:
        apse = AdaptivePortfolioSizingEngine(
            capital=2_000_000_000,
            market_regime='neutral',
            alpha_quality=0.05
        )
        config = apse.optimize()
    """
    
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
            'holdings_range': (8, 12),  # Reduced from (15, 25) - too many for 1-5B capital
            'asset_cap_range': (0.15, 0.25),
            'sector_cap_range': (0.35, 0.45),
            'adv_pct_range': (0.30, 0.40),
            'turnover_range': (0.40, 0.60),  # Increased from (0.25, 0.35) - need faster rebalancing
            'min_trade_multiplier': 1,
            'enabled_alphas': ['momentum', 'value', 'quality']
        },
        'small': {
            'holdings_range': (30, 60),  # Increased: 10B needs 30-60 holdings to deploy capital efficiently
            'asset_cap_range': (0.10, 0.15),
            'sector_cap_range': (0.25, 0.35),
            'adv_pct_range': (0.20, 0.30),
            'turnover_range': (0.25, 0.35),  # Increased from (0.20, 0.30)
            'min_trade_multiplier': 2,
            'enabled_alphas': ['momentum', 'value', 'quality', 'low_vol', 'size']
        },
        'medium': {
            'holdings_range': (20, 40),  # Reduced from (50, 80)
            'asset_cap_range': (0.08, 0.12),
            'sector_cap_range': (0.20, 0.30),
            'adv_pct_range': (0.15, 0.25),
            'turnover_range': (0.15, 0.25),
            'min_trade_multiplier': 4,
            'enabled_alphas': ['momentum', 'value', 'quality', 'low_vol', 'size', 
                              'liquidity', 'sentiment', 'technical']
        },
        'large': {
            'holdings_range': (40, 80),  # Reduced from (80, 150)
            'asset_cap_range': (0.05, 0.10),
            'sector_cap_range': (0.15, 0.25),
            'adv_pct_range': (0.10, 0.20),
            'turnover_range': (0.10, 0.15),  # Increased from (0.10, 0.20)
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
        avg_stock_price: float = 50.0,  # 1000 VND units
        board_lot_size: Optional[int] = None,
        risk_tolerance: float = 1.0
    ):
        """
        Initialize APSE engine.
        
        Args:
            capital: Total capital in VND
            market_regime: 'bull', 'bear', or 'neutral'
            alpha_quality: IC of alpha signals (e.g., 0.05 for 5% IC)
            avg_stock_price: Average stock price in 1000 VND units
            board_lot_size: Shares per board lot (default from VnMarketRules.BOARD_LOT)
            risk_tolerance: Risk multiplier (default 1.0)
        """
        self.capital = capital
        self.market_regime = market_regime or 'neutral'
        self.alpha_quality = alpha_quality or 0.05
        self.avg_stock_price = avg_stock_price
        self.board_lot_size = board_lot_size if board_lot_size is not None else VnMarketRules.BOARD_LOT
        self.risk_tolerance = risk_tolerance
        
        # Determine capital tier
        self.capital_tier = self._determine_capital_tier(capital)
        self.tier_params = self.TIER_PARAMS[self.capital_tier]
    
    def _determine_capital_tier(self, capital: float) -> str:
        """
        Determine capital tier based on capital size.
        
        Args:
            capital: Total capital in VND
            
        Returns:
            Tier name: 'micro', 'small', 'medium', or 'large'
        """
        for tier, (min_cap, max_cap) in self.TIER_THRESHOLDS.items():
            if min_cap <= capital < max_cap:
                return tier
        return 'large'
    
    def _calculate_optimal_num_holdings(self) -> Tuple[int, int, int]:
        """
        Calculate optimal number of holdings based on capital, tier and liquidity.
        Institutional Logic: More capital requires more symbols to avoid market impact,
        but too many symbols dilute alpha.
        """
        import math

        # Calculate minimum position value (1 board lot)
        min_position_vnd = self.avg_stock_price * 1000 * self.board_lot_size

        # Enforce minimum position size: at least 1.5% of capital for small/medium, 3% for micro
        min_alloc_map = {'micro': 0.03, 'small': 0.015, 'medium': 0.01, 'large': 0.005}
        min_allocation_pct = min_alloc_map.get(self.capital_tier, 0.01)
        min_position_value = max(min_position_vnd, self.capital * min_allocation_pct)

        # Maximum possible holdings given minimum position constraint
        max_possible_holdings = int(self.capital / min_position_value)

        # Liquidity constraint: How many stocks do we need to absorb capital at 25% ADV?
        # Assuming avg stock in universe has 10B ADV (Small Cap VN)
        avg_universe_adv = 10_000_000_000
        max_adv_pct = self.TIER_PARAMS[self.capital_tier]['adv_pct_range'][0]
        capacity_per_stock = avg_universe_adv * max_adv_pct
        min_holdings_for_liquidity = math.ceil(self.capital / capacity_per_stock)

        # Get tier-specific range
        min_h, max_h = self.tier_params['holdings_range']

        # Adjust min/max based on liquidity need
        min_holdings = max(min_h, min_holdings_for_liquidity)
        max_holdings = min(max_h, max_possible_holdings)

        # Ensure we don't hold too many relative to capital (max 1 position per 1% of NAV)
        max_holdings_from_capital = int(self.capital / (self.capital * 0.01))
        max_holdings = min(max_holdings, max_holdings_from_capital)

        if min_holdings > max_holdings:
            min_holdings = max_holdings

        target_holdings = int((min_holdings + max_holdings) / 2)
        
        return target_holdings, min_holdings, max_holdings
    
    def _calculate_optimal_asset_cap(self, num_holdings: int) -> float:
        """
        Calculate max asset cap ensuring diversification.
        
        Args:
            num_holdings: Number of holdings
            
        Returns:
            Max asset cap (0-1)
        """
        # Equal-weight baseline
        equal_weight = 1.0 / num_holdings if num_holdings > 0 else 0.0
        
        # Get tier-specific range
        min_cap, max_cap = self.tier_params['asset_cap_range']
        
        # Use midpoint of range, but ensure it's reasonable vs equal weight
        tier_cap = (min_cap + max_cap) / 2
        
        # Don't go below 2x equal weight (allow some concentration)
        # Don't go above tier max
        optimal_cap = max(equal_weight * 2, min(tier_cap, max_cap))
        
        return optimal_cap
    
    def _calculate_optimal_sector_cap(self) -> float:
        """
        Calculate max sector cap.
        
        Returns:
            Max sector cap (0-1)
        """
        min_cap, max_cap = self.tier_params['sector_cap_range']
        return (min_cap + max_cap) / 2
    
    def _calculate_optimal_adv_pct(self) -> float:
        """
        Calculate max ADV percentage based on tier and market regime.
        
        Returns:
            Max ADV percentage (0-1)
        """
        min_adv, max_adv = self.tier_params['adv_pct_range']
        base_adv = (min_adv + max_adv) / 2
        
        # Adjust for market regime
        regime_adjustment = {
            'bull': 1.1,
            'neutral': 1.0,
            'bear': 0.9
        }[self.market_regime]
        
        # Adjust for risk tolerance
        adjusted_adv = base_adv * regime_adjustment * self.risk_tolerance
        
        # Clamp to tier range
        return np.clip(adjusted_adv, min_adv, max_adv)
    
    def _calculate_min_trade_value(self) -> float:
        """
        Calculate minimum trade value respecting board-lot constraint.
        
        Returns:
            Minimum trade value in VND
        """
        # One board lot value
        one_board_lot_vnd = self.board_lot_size * self.avg_stock_price * 1000
        
        # Scale with tier
        multiplier = self.tier_params['min_trade_multiplier']
        
        return one_board_lot_vnd * multiplier
    
    def _calculate_position_sizes(self, num_holdings: int, asset_cap: float) -> Tuple[float, float]:
        """
        Calculate min and max position sizes.
        
        Args:
            num_holdings: Number of holdings
            asset_cap: Max asset cap
            
        Returns:
            (min_position_size, max_position_size) in VND
        """
        # Min position: 1 board lot
        min_position = self.board_lot_size * self.avg_stock_price * 1000
        
        # Max position: asset_cap * capital
        max_position = asset_cap * self.capital
        
        return min_position, max_position
    
    def _get_feature_gating(self) -> Tuple[List[str], Dict[str, bool]]:
        """
        Determine which alphas/modules to enable based on tier and alpha quality.
        
        Returns:
            (enabled_alphas, enabled_modules)
        """
        # Get tier-specific alphas
        enabled_alphas = self.tier_params['enabled_alphas'].copy()
        
        # Disable weak alphas if IC is low
        if self.alpha_quality < 0.03:
            # Only keep momentum and value
            enabled_alphas = [a for a in enabled_alphas if a in ['momentum', 'value']]
        
        # Module gating
        all_alphas = ['momentum', 'value', 'quality', 'low_vol', 'size',
                     'liquidity', 'sentiment', 'technical', 'hft']
        enabled_modules = {alpha: alpha in enabled_alphas for alpha in all_alphas}
        
        return enabled_alphas, enabled_modules
    
    def _calculate_expected_return(self, num_holdings: int, turnover: float) -> float:
        """
        Estimate expected return from alpha quality using Grinold's Law.
        
        Formula: Expected Return = IC * sqrt(Breadth) * Volatility + RiskFreeRate - TransactionCosts
        
        Where:
        - Breadth = num_holdings * rebalancing_frequency_per_year
        - Rebalancing frequency = annual_turnover (e.g., 0.3 turnover = rebalance 30% of portfolio annually)
        - For trend-following, assume monthly rebalancing (12x per year) with partial turnover
        - Effective Breadth = num_holdings * 12 * (turnover / 1.0) to normalize
        - Transaction Costs = Turnover * 2 * TC_Rate (2x for round-trip)
        
        Args:
            num_holdings: Number of holdings
            turnover: Annual turnover (e.g., 0.3 = 30% annual turnover)
            
        Returns:
            Expected annual return
        """
        # Vietnam market parameters
        volatility = 0.30  # 30% annual volatility
        risk_free_rate = 0.065  # 6.5% bank rate
        tc_rate = 0.003  # 0.3% per trade (one-way)
        
        # Breadth calculation for monthly rebalancing strategy
        # Assume monthly rebalancing (12x per year) with partial portfolio turnover
        # Effective independent bets = num_holdings * rebalancing_frequency
        # Adjust for correlation: use sqrt(12) instead of 12 to account for bet correlation
        rebalancing_frequency = np.sqrt(12)  # ~3.46 effective independent periods per year
        
        # Breadth = num_holdings * effective_rebalancing_frequency
        breadth = num_holdings * rebalancing_frequency
        
        # Grinold's Law: Expected Return = IC * sqrt(Breadth) * Volatility
        gross_alpha = self.alpha_quality * np.sqrt(breadth) * volatility
        
        # Add risk-free rate
        gross_return = gross_alpha + risk_free_rate
        
        # Transaction costs (round-trip = 2x one-way cost)
        # Total cost = annual_turnover * 2 * tc_rate
        transaction_costs = turnover * 2 * tc_rate
        
        # Net return
        net_return = gross_return - transaction_costs
        
        return net_return
    
    def _calculate_sharpe(self, expected_return: float, benchmark_threshold: float) -> float:
        """
        Calculate expected Sharpe ratio.
        
        Args:
            expected_return: Expected annual return
            benchmark_threshold: Benchmark return (max of bank rate, VN-Index)
            
        Returns:
            Expected Sharpe ratio
        """
        # Vietnam market volatility
        volatility = 0.30
        
        # Excess return over benchmark
        excess_return = expected_return - benchmark_threshold
        
        # Sharpe ratio
        sharpe = excess_return / volatility if volatility > 0 else 0.0
        
        return sharpe
    
    def get_benchmark_threshold(self, bank_rate: float, vnindex_return: float) -> float:
        """
        Calculate benchmark threshold (max of bank rate and VN-Index return).
        
        Args:
            bank_rate: Bank interest rate
            vnindex_return: VN-Index return
            
        Returns:
            Benchmark threshold
        """
        return max(bank_rate, vnindex_return)
    
    def optimize(
        self,
        bank_rate: float = 0.065,
        vnindex_return: float = 0.12
    ) -> AdaptiveConfig:
        """
        Optimize portfolio parameters and return AdaptiveConfig.
        
        Args:
            bank_rate: Bank interest rate (default 6.5%)
            vnindex_return: VN-Index return (default 12%)
            
        Returns:
            AdaptiveConfig with optimized parameters
        """
        # Calculate optimal parameters
        target_holdings, min_holdings, max_holdings = self._calculate_optimal_num_holdings()
        asset_cap = self._calculate_optimal_asset_cap(target_holdings)
        sector_cap = self._calculate_optimal_sector_cap()
        adv_pct = self._calculate_optimal_adv_pct()
        min_trade_value = self._calculate_min_trade_value()
        
        # Turnover
        min_turn, max_turn = self.tier_params['turnover_range']
        target_turnover = (min_turn + max_turn) / 2
        
        # Position sizes
        min_position, max_position = self._calculate_position_sizes(target_holdings, asset_cap)
        
        # Feature gating
        enabled_alphas, enabled_modules = self._get_feature_gating()
        
        # Calculate expected performance
        expected_return = self._calculate_expected_return(target_holdings, target_turnover)
        benchmark_threshold = self.get_benchmark_threshold(bank_rate, vnindex_return)
        expected_sharpe = self._calculate_sharpe(expected_return, benchmark_threshold)
        
        # Create config
        config = AdaptiveConfig(
            # Portfolio structure
            target_num_holdings=target_holdings,
            min_num_holdings=min_holdings,
            max_num_holdings=max_holdings,
            
            # Position sizing
            max_asset_cap=asset_cap,
            max_sector_cap=sector_cap,
            min_position_size=min_position,
            max_position_size=max_position,
            
            # Trading constraints
            max_adv_percentage=adv_pct,
            min_trade_value=min_trade_value,
            target_turnover=target_turnover,
            
            # Feature gating
            enabled_alphas=enabled_alphas,
            enabled_modules=enabled_modules,
            
            # Metadata
            capital_tier=self.capital_tier,
            optimization_timestamp=datetime.now(),
            expected_sharpe=expected_sharpe,
            benchmark_threshold=benchmark_threshold,
            expected_return=expected_return
        )
        
        return config
