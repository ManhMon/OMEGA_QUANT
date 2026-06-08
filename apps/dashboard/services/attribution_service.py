"""
Attribution Service
Wraps attribution.py for performance analysis.
"""
import sys
from pathlib import Path
from typing import Dict, Optional
import pandas as pd
import numpy as np
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from omega.quant.attribution import PerformanceAttribution, AttributionConfig

logger = logging.getLogger(__name__)


class AttributionService:
    """Service for performance attribution analysis"""
    
    def __init__(self):
        self.config = AttributionConfig(pit_compliant=True)
        self.attribution = PerformanceAttribution(self.config)
    
    def decompose_returns(
        self,
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series,
        current_time: Optional[pd.Timestamp] = None
    ) -> Dict:
        """
        Decompose active return into factor and selection components
        
        Args:
            portfolio_returns: Portfolio returns series
            benchmark_returns: Benchmark returns series
            current_time: Current timestamp for PIT validation
            
        Returns:
            Dict with decomposition results
        """
        try:
            result = self.attribution.decompose_returns(
                portfolio_returns,
                benchmark_returns,
                current_time=current_time,
                pit_strict=True
            )
            return result
        except Exception as e:
            logger.error(f"Attribution failed: {e}")
            return {
                "error": str(e),
                "total_portfolio_return": 0.0,
                "total_benchmark_return": 0.0,
                "active_return": 0.0,
                "beta": 0.0,
                "factor_return": 0.0,
                "selection_return": 0.0
            }
    
    def compute_sharpe(
        self,
        returns: pd.Series,
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252
    ) -> float:
        """Compute annualized Sharpe ratio"""
        if len(returns) < 2:
            return 0.0
        
        r = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0).values
        excess = r - (risk_free_rate / periods_per_year)
        
        mean_e = np.mean(excess)
        std_e = np.std(excess, ddof=1)
        
        if std_e < 1e-12:
            return 0.0
        
        return float(mean_e / std_e * np.sqrt(periods_per_year))
    
    def compute_information_ratio(
        self,
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series,
        periods_per_year: int = 252
    ) -> float:
        """Compute annualized Information Ratio"""
        try:
            return self.attribution.information_ratio(
                portfolio_returns,
                benchmark_returns,
                annualise=True
            )
        except Exception as e:
            logger.error(f"IR computation failed: {e}")
            return 0.0
    
    def compute_max_drawdown(self, returns: pd.Series) -> float:
        """Compute maximum drawdown"""
        try:
            return self.attribution.max_drawdown(returns)
        except Exception as e:
            logger.error(f"Max drawdown failed: {e}")
            return 0.0
    
    def sector_attribution(
        self,
        portfolio_weights: pd.Series,
        benchmark_weights: pd.Series,
        sector_returns: pd.Series,
        sectors: pd.Series
    ) -> Optional[pd.DataFrame]:
        """
        BHB sector attribution
        
        Returns:
            DataFrame with allocation, selection, interaction effects
        """
        try:
            return self.attribution.sector_attribution(
                portfolio_weights,
                benchmark_weights,
                sector_returns,
                sectors,
                pit_strict=True
            )
        except Exception as e:
            logger.error(f"Sector attribution failed: {e}")
            return None
