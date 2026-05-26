"""
Pipeline Orchestrator - Phase 3.3
Wires AlphaFactory -> HighAlphaFilter -> IndividualRiskGuard -> ExecutionEngine

Version: v21.0
Date: 2026-05-05
Author: OpenCode

COMPLIANCE:
- PIT Safety: All data uses T-1 lag
- Vectorization: 100% NumPy/Pandas operations
- Modular: Each component is independently testable

Pipeline Flow:
1. AlphaFactory: Compute alpha signals from OHLCV data
2. HighAlphaFilter: Select 10-15 stocks with highest IC
3. IndividualRiskGuard: Validate against risk limits and compute weights
4. ExecutionEngine: Generate execution plan for approved portfolio
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from v21_system.layer_01_core_intelligence.alpha_factory import AlphaFactory
from v21_system.layer_01_core_intelligence.high_alpha_filter import (
    HighAlphaFilter,
    HighAlphaFilterConfig
)
from v21_system.layer_04_risk_management.individual_risk_guard import (
    IndividualRiskGuard,
    IndividualRiskGuardConfig
)
from v21_system.layer_03_execution_engine.execution_engine import (
    ExecutionEngine,
    ExecutionConfig
)


@dataclass
class PipelineConfig:
    """Configuration for pipeline orchestrator"""
    # Capital Configuration
    initial_capital: float = 2_000_000_000.0  # 2B VND
    
    # High-Alpha Filter Configuration
    min_stocks: int = 10
    max_stocks: int = 15
    ic_threshold: float = 0.03
    min_ic_observations: int = 30
    forward_return_period: int = 5  # Days
    
    # Risk Guard Configuration
    max_concentration_per_stock: float = 0.25  # 25% per stock
    max_adv_percentage: float = 0.40  # 40% ADV
    max_notional_per_trade: float = 500_000_000  # 500M VND
    alert_drawdown_threshold: float = 0.10  # 10% drawdown alert
    
    # Execution Configuration
    default_algo: str = "VWAP"
    duration_minutes: int = 60
    use_microstructure: bool = False
    
    # Allocation Method
    allocation_method: str = 'ic_weighted'  # 'equal_weight' or 'ic_weighted'


@dataclass
class PipelineResult:
    """Result of pipeline execution"""
    alphas: pd.DataFrame = field(default_factory=pd.DataFrame)
    selected_stocks: List[str] = field(default_factory=list)
    stock_ics: Dict[str, float] = field(default_factory=dict)
    approved_stocks: List[str] = field(default_factory=list)
    rejected_stocks: List[str] = field(default_factory=list)
    approved_weights: Dict[str, float] = field(default_factory=dict)
    rejection_reasons: Dict[str, List[str]] = field(default_factory=dict)
    execution_plan: Dict[str, Any] = field(default_factory=dict)
    pipeline_summary: Dict[str, Any] = field(default_factory=dict)
    
    def summary(self) -> str:
        """Generate summary string"""
        return (
            f"Pipeline Execution Summary:\n"
            f"  Total Alphas: {self.pipeline_summary.get('total_alphas', 0)}\n"
            f"  Selected Stocks: {self.pipeline_summary.get('selected_stocks_count', 0)}\n"
            f"  Approved Stocks: {self.pipeline_summary.get('approved_stocks_count', 0)}\n"
            f"  Rejected Stocks: {self.pipeline_summary.get('rejected_stocks_count', 0)}\n"
            f"  Total Weight: {self.pipeline_summary.get('total_weight', 0):.2%}\n"
            f"  Execution Trades: {self.pipeline_summary.get('execution_trades', 0)}"
        )


class PipelineOrchestrator:
    """
    Pipeline Orchestrator for V21_QUANT System.
    
    Orchestrates the complete pipeline from alpha generation to execution planning:
    1. AlphaFactory: Compute alpha signals
    2. HighAlphaFilter: Select high-IC stocks
    3. IndividualRiskGuard: Validate risk constraints
    4. ExecutionEngine: Generate execution plan
    
    PIT Compliance:
        - All components use T-1 lagged data
        - Forward returns properly aligned
        - No lookahead bias
    
    Vectorization:
        - All operations use NumPy/Pandas vectorized methods
        - No Python loops in hot paths
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self._initialize_components()
    
    def _initialize_components(self):
        """Initialize all pipeline components"""
        # 1. AlphaFactory
        self.alpha_factory = AlphaFactory()
        
        # 2. HighAlphaFilter
        alpha_filter_config = HighAlphaFilterConfig(
            min_stocks=self.config.min_stocks,
            max_stocks=self.config.max_stocks,
            ic_threshold=self.config.ic_threshold,
            min_ic_observations=self.config.min_ic_observations,
            forward_return_period=self.config.forward_return_period
        )
        self.high_alpha_filter = HighAlphaFilter(alpha_filter_config)
        
        # 3. IndividualRiskGuard
        risk_guard_config = IndividualRiskGuardConfig(
            initial_capital=self.config.initial_capital,
            max_concentration_per_stock=self.config.max_concentration_per_stock,
            min_stocks=self.config.min_stocks,
            max_stocks=self.config.max_stocks,
            max_adv_percentage=self.config.max_adv_percentage,
            max_notional_per_trade=self.config.max_notional_per_trade,
            alert_drawdown_threshold=self.config.alert_drawdown_threshold,
            ic_threshold=self.config.ic_threshold,
            min_ic_observations=self.config.min_ic_observations
        )
        self.individual_risk_guard = IndividualRiskGuard(risk_guard_config)
        
        # 4. ExecutionEngine
        execution_config = ExecutionConfig(
            default_algo=self.config.default_algo,
            duration_minutes=self.config.duration_minutes,
            use_microstructure=self.config.use_microstructure
        )
        self.execution_engine = ExecutionEngine(execution_config)
        
        self.logger.info("Pipeline components initialized successfully")
    
    def _compute_forward_returns(
        self,
        ohlcv_data: pd.DataFrame,
        period: int = 5
    ) -> pd.Series:
        """
        Compute forward returns for IC calculation.
        
        Args:
            ohlcv_data: DataFrame with columns [date, ticker, close]
            period: Forward return period (days)
            
        Returns:
            Series with MultiIndex (date, ticker) and forward returns
        """
        df = ohlcv_data.copy()
        df = df.sort_values(['ticker', 'date'])
        
        # Compute forward returns (shift backwards to align with current date)
        df['forward_return'] = df.groupby('ticker')['close'].pct_change(period).shift(-period)
        
        # Set MultiIndex
        df = df.set_index(['date', 'ticker'])
        
        return df['forward_return']

    def _freeze_ohlcv_as_of(
        self,
        ohlcv_data: pd.DataFrame,
        current_date: pd.Timestamp
    ) -> pd.DataFrame:
        """
        Freeze the OHLCV panel at the pipeline as-of date.

        This prevents downstream alpha/IC calculations from seeing rows that
        would only be available after the execution timestamp.
        """
        as_of_timestamp = pd.Timestamp(current_date)
        frozen = ohlcv_data[ohlcv_data['date'] <= as_of_timestamp].copy()

        if frozen.empty:
            raise ValueError(
                f"ohlcv_data contains no rows on or before current_date={as_of_timestamp}"
            )

        return frozen
    
    def run_pipeline(
        self,
        ohlcv_data: pd.DataFrame,
        market_data: pd.DataFrame,
        current_date: pd.Timestamp,
        current_portfolio: Optional[Dict[str, float]] = None
    ) -> PipelineResult:
        """
        Run complete pipeline from alpha generation to execution planning.
        
        Args:
            ohlcv_data: DataFrame with columns [date, ticker, open, high, low, close, volume]
            market_data: DataFrame with columns [ticker, price, adv, volatility]
            current_date: Current date for pipeline execution
            current_portfolio: Current portfolio weights (optional, defaults to empty)
            
        Returns:
            PipelineResult with all pipeline outputs
            
        Raises:
            ValueError: If inputs are invalid
        """
        self.logger.info(f"Starting pipeline execution for date: {current_date}")
        
        # Validate inputs
        if ohlcv_data.empty:
            raise ValueError("ohlcv_data cannot be empty")
        if market_data.empty:
            raise ValueError("market_data cannot be empty")
        
        required_ohlcv_cols = ['date', 'ticker', 'open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_ohlcv_cols if col not in ohlcv_data.columns]
        if missing_cols:
            raise ValueError(f"ohlcv_data missing columns: {missing_cols}")
        
        required_market_cols = ['ticker', 'price', 'adv', 'volatility']
        missing_cols = [col for col in required_market_cols if col not in market_data.columns]
        if missing_cols:
            raise ValueError(f"market_data missing columns: {missing_cols}")
        
        if current_portfolio is None:
            current_portfolio = {}

        frozen_ohlcv = self._freeze_ohlcv_as_of(ohlcv_data, current_date)
        
        # Step 1: Compute alphas using AlphaFactory
        self.logger.info("Step 1: Computing alpha signals...")
        alphas_df = self.alpha_factory.compute_all_alphas(frozen_ohlcv)
        
        if alphas_df.empty:
            raise ValueError("AlphaFactory returned empty DataFrame")
        
        alpha_cols = [col for col in alphas_df.columns if col.startswith('alpha_')]
        self.logger.info(f"  Generated {len(alpha_cols)} alpha signals")
        
        # Step 2: Compute forward returns for IC calculation
        self.logger.info("Step 2: Computing forward returns...")
        forward_returns = self._compute_forward_returns(
            frozen_ohlcv,
            period=self.config.forward_return_period
        )
        
        # Prepare alphas for HighAlphaFilter (MultiIndex format)
        alphas_indexed = alphas_df.set_index(['date', 'ticker'])
        alphas_only = alphas_indexed[alpha_cols]
        
        # Step 3: Select high-alpha stocks using HighAlphaFilter
        self.logger.info("Step 3: Selecting high-alpha stocks...")
        high_alpha_result = self.high_alpha_filter.select_high_alpha_stocks(
            alphas=alphas_only,
            returns=forward_returns
        )
        
        selected_stocks = high_alpha_result.selected_stocks
        stock_ics = high_alpha_result.stock_ics
        
        self.logger.info(
            f"  Selected {len(selected_stocks)} stocks "
            f"(mean IC: {high_alpha_result.selection_summary.get('mean_ic_selected', 0):.4f})"
        )
        
        if not selected_stocks:
            self.logger.warning("No stocks selected by HighAlphaFilter")
            return PipelineResult(
                alphas=alphas_df,
                pipeline_summary={
                    'total_alphas': len(alpha_cols),
                    'selected_stocks_count': 0,
                    'approved_stocks_count': 0,
                    'rejected_stocks_count': 0,
                    'error': 'No stocks selected by HighAlphaFilter'
                }
            )
        
        # Step 4: Validate portfolio with IndividualRiskGuard
        self.logger.info("Step 4: Validating portfolio with risk guard...")
        risk_guard_result = self.individual_risk_guard.validate_high_alpha_portfolio(
            alphas=alphas_only,
            returns=forward_returns,
            market_data=market_data,
            allocation_method=self.config.allocation_method
        )
        
        approved_stocks = risk_guard_result.approved_stocks
        approved_weights = risk_guard_result.approved_weights
        rejected_stocks = risk_guard_result.rejected_stocks
        rejection_reasons = risk_guard_result.rejection_reasons
        
        self.logger.info(
            f"  Approved {len(approved_stocks)} stocks, "
            f"rejected {len(rejected_stocks)} stocks"
        )
        
        if not approved_stocks:
            self.logger.warning("No stocks approved by IndividualRiskGuard")
            return PipelineResult(
                alphas=alphas_df,
                selected_stocks=selected_stocks,
                stock_ics=stock_ics,
                rejected_stocks=rejected_stocks,
                rejection_reasons=rejection_reasons,
                pipeline_summary={
                    'total_alphas': len(alpha_cols),
                    'selected_stocks_count': len(selected_stocks),
                    'approved_stocks_count': 0,
                    'rejected_stocks_count': len(rejected_stocks),
                    'error': 'No stocks approved by IndividualRiskGuard'
                }
            )
        
        # Step 5: Generate execution plan using ExecutionEngine
        self.logger.info("Step 5: Generating execution plan...")
        
        # Extract prices, ADV, and volatility from market_data
        prices = dict(zip(market_data['ticker'], market_data['price']))
        adv_data = dict(zip(market_data['ticker'], market_data['adv']))
        volatility_data = dict(zip(market_data['ticker'], market_data['volatility']))
        
        execution_plan = self.execution_engine.generate_execution_plan(
            target_portfolio=approved_weights,
            current_portfolio=current_portfolio,
            portfolio_value=self.config.initial_capital,
            prices=prices,
            adv_data=adv_data,
            volatility_data=volatility_data,
            current_date=current_date
        )
        
        self.logger.info(
            f"  Generated execution plan with {execution_plan['summary']['total_trades']} trades"
        )
        
        # Step 6: Compile pipeline summary
        pipeline_summary = {
            'total_alphas': len(alpha_cols),
            'selected_stocks_count': len(selected_stocks),
            'approved_stocks_count': len(approved_stocks),
            'rejected_stocks_count': len(rejected_stocks),
            'total_weight': sum(approved_weights.values()),
            'max_concentration': max(approved_weights.values()) if approved_weights else 0.0,
            'mean_ic_selected': high_alpha_result.selection_summary.get('mean_ic_selected', 0.0),
            'execution_trades': execution_plan['summary']['total_trades'],
            'estimated_impact_bps': execution_plan['summary'].get('portfolio_estimated_impact_bps', 0.0),
            'allocation_method': self.config.allocation_method,
            'current_date': current_date
        }
        
        self.logger.info("Pipeline execution completed successfully")
        
        return PipelineResult(
            alphas=alphas_df,
            selected_stocks=selected_stocks,
            stock_ics=stock_ics,
            approved_stocks=approved_stocks,
            rejected_stocks=rejected_stocks,
            approved_weights=approved_weights,
            rejection_reasons=rejection_reasons,
            execution_plan=execution_plan,
            pipeline_summary=pipeline_summary
        )
    
    def reset_daily_limits(self):
        """Reset daily risk limits (delegates to IndividualRiskGuard)"""
        self.individual_risk_guard.reset_daily_limits()
        self.logger.info("Daily risk limits reset")


if __name__ == '__main__':
    print("=" * 80)
    print("PIPELINE ORCHESTRATOR - DEMO")
    print("=" * 80)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Generate sample data
    np.random.seed(42)
    
    # OHLCV data: 60 days, 30 stocks
    dates = pd.date_range('2026-03-01', periods=60, freq='D')
    stocks = [f'STOCK_{i:03d}' for i in range(30)]
    
    ohlcv_data = []
    for date in dates:
        for stock in stocks:
            base_price = np.random.uniform(20000, 100000)
            volatility = np.random.uniform(0.01, 0.03)
            
            open_price = base_price * (1 + np.random.randn() * volatility)
            close_price = open_price * (1 + np.random.randn() * volatility)
            high_price = max(open_price, close_price) * (1 + abs(np.random.randn()) * volatility * 0.5)
            low_price = min(open_price, close_price) * (1 - abs(np.random.randn()) * volatility * 0.5)
            volume = np.random.uniform(1e6, 5e6)
            
            ohlcv_data.append({
                'date': date,
                'ticker': stock,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume
            })
    
    ohlcv_df = pd.DataFrame(ohlcv_data)
    
    # Market data
    market_data = pd.DataFrame({
        'ticker': stocks,
        'price': np.random.uniform(20000, 100000, len(stocks)),
        'adv': np.random.uniform(1e9, 10e9, len(stocks)),
        'volatility': np.random.uniform(0.01, 0.05, len(stocks))
    })
    
    # Create orchestrator
    config = PipelineConfig(
        initial_capital=2_000_000_000,
        min_stocks=10,
        max_stocks=15,
        max_concentration_per_stock=0.25,
        allocation_method='ic_weighted'
    )
    orchestrator = PipelineOrchestrator(config)
    
    print("\n1. Running pipeline...")
    result = orchestrator.run_pipeline(
        ohlcv_data=ohlcv_df,
        market_data=market_data,
        current_date=pd.Timestamp('2026-04-30')
    )
    
    print("\n2. Pipeline Summary:")
    print(result.summary())
    
    print("\n3. Approved Stocks (Top 10):")
    sorted_approved = sorted(
        result.approved_weights.items(),
        key=lambda x: x[1],
        reverse=True
    )
    for i, (stock, weight) in enumerate(sorted_approved[:10], 1):
        ic = result.stock_ics.get(stock, 0.0)
        notional = weight * config.initial_capital
        print(f"   {i:2d}. {stock}: Weight={weight:.2%}, IC={ic:+.4f}, Notional={notional:,.0f}")
    
    print("\n4. Rejected Stocks:")
    for stock in result.rejected_stocks[:5]:
        reasons = result.rejection_reasons.get(stock, [])
        print(f"   {stock}: {', '.join(reasons)}")
    
    print("\n5. Execution Plan Summary:")
    exec_summary = result.execution_plan.get('summary', {})
    print(f"   Total Trades: {exec_summary.get('total_trades', 0)}")
    print(f"   Estimated Impact: {exec_summary.get('portfolio_estimated_impact_bps', 0):.2f} bps")
    
    print("\n" + "=" * 80)
    print("✅ Pipeline Orchestrator demo complete")
    print("=" * 80)
