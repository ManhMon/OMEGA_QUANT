"""
Global Contagion Detector - OMEGA_QUANT Sentiment Module
Phase 25.4: Country Instability & Correlation Spillover Monitor

Monitors correlation shift from global markets (S&P 500, HSI, Shanghai)
to VN-Index. Outputs a composite Spreading Risk Index (SRI) for Risk Guard.

INSTITUTIONAL GRADE IMPLEMENTATION:
- Vectorized operations (NumPy/Pandas)
- Point-in-time (PIT) safe: all timestamps explicit
- No look-ahead bias
- Clear data lineage
- Auditable risk calculations
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from omega.quant.sentiment.cii_engine import CIIPortfolioEngine, CountryData, CountryScore


class MarketStressLevel(Enum):
    """Market stress signal levels for Risk Guard integration."""
    GREEN = "GREEN"    # Normal conditions (SRI < 30)
    YELLOW = "YELLOW"  # Elevated risk (SRI 30-60)
    RED = "RED"        # High contagion risk (SRI > 60)


@dataclass
class GlobalIndexData:
    """Price data for a global index at a point in time."""
    index_name: str
    country_code: str
    timestamp: datetime
    close_price: float
    returns: np.ndarray  # Historical log returns


@dataclass
class CorrelationMetrics:
    """Correlation metrics between VN-Index and a global index."""
    index_name: str
    correlation: float
    correlation_shift: float
    rolling_volatility: float
    volatility_shift: float
    timestamp: datetime


@dataclass
class SpreadingRiskIndex:
    """Spreading Risk Index (SRI) - composite contagion risk score."""
    score: float
    level: MarketStressLevel
    correlation_component: float
    volatility_component: float
    cii_component: float
    dominant_source: str
    timestamp: datetime


@dataclass
class ContagionReport:
    """Complete contagion risk report for Risk Guard."""
    sri: SpreadingRiskIndex
    correlations: List[CorrelationMetrics]
    cii_scores: Dict[str, float]  # {country_code: cii_score}
    risk_narrative: str
    timestamp: datetime


class GlobalContagionDetector:
    """Vectorized global contagion detector for VN-Index."""
    
    MONITORED_INDICES = {
        'SPX': 'US',
        'HSI': 'HK',
        'SSE': 'CN',
    }
    
    CORRELATION_HIGH_THRESHOLD = 0.7
    CORRELATION_SHIFT_THRESHOLD = 0.2
    VOLATILITY_HIGH_THRESHOLD = 25.0
    VOLATILITY_SHIFT_THRESHOLD = 5.0
    
    def __init__(
        self,
        lookback_days: int = 60,
        correlation_window: int = 30,
        volatility_window: int = 20
    ):
        self.lookback_days = lookback_days
        self.correlation_window = correlation_window
        self.volatility_window = volatility_window
        self.cii_engine = CIIPortfolioEngine()
        
    def detect_contagion(
        self,
        vn_returns: np.ndarray,
        global_indices: List[GlobalIndexData],
        cii_scores: Optional[Dict[str, float]] = None,
        as_of_time: Optional[datetime] = None
    ) -> ContagionReport:
        """Detect contagion risk from global markets to VN-Index (PIT safe)."""
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety")
            
        self._validate_inputs(vn_returns, global_indices)
        
        correlations = []
        for idx_data in global_indices:
            corr_metrics = self._calculate_correlation_metrics(
                vn_returns,
                idx_data,
                as_of_time
            )
            correlations.append(corr_metrics)
            
        sri = self._calculate_sri(
            correlations,
            cii_scores or {},
            as_of_time
        )
        
        narrative = self._generate_risk_narrative(sri, correlations)
        
        return ContagionReport(
            sri=sri,
            correlations=correlations,
            cii_scores=cii_scores or {},
            risk_narrative=narrative,
            timestamp=as_of_time
        )

    def _validate_inputs(
        self,
        vn_returns: np.ndarray,
        global_indices: List[GlobalIndexData]
    ) -> None:
        if len(vn_returns) < self.lookback_days:
            raise ValueError(
                f"VN-Index returns length ({len(vn_returns)}) < "
                f"required lookback ({self.lookback_days})"
            )
            
        for idx_data in global_indices:
            if len(idx_data.returns) < self.lookback_days:
                raise ValueError(
                    f"{idx_data.index_name} returns length ({len(idx_data.returns)}) < "
                    f"required lookback ({self.lookback_days})"
                )

    def _calculate_correlation_metrics(
        self,
        vn_returns: np.ndarray,
        idx_data: GlobalIndexData,
        as_of_time: datetime
    ) -> CorrelationMetrics:
        min_len = min(len(vn_returns), len(idx_data.returns))
        vn_ret = vn_returns[-min_len:]
        idx_ret = idx_data.returns[-min_len:]
        
        current_corr = self._rolling_correlation(
            vn_ret[-self.correlation_window:],
            idx_ret[-self.correlation_window:]
        )
        
        if len(vn_ret) >= 2 * self.correlation_window:
            prev_corr = self._rolling_correlation(
                vn_ret[-2*self.correlation_window:-self.correlation_window],
                idx_ret[-2*self.correlation_window:-self.correlation_window]
            )
        else:
            prev_corr = current_corr
            
        corr_shift = current_corr - prev_corr
        
        current_vol = self._rolling_volatility(
            idx_ret[-self.volatility_window:]
        )
        
        if len(idx_ret) >= 2 * self.volatility_window:
            prev_vol = self._rolling_volatility(
                idx_ret[-2*self.volatility_window:-self.volatility_window]
            )
        else:
            prev_vol = current_vol
            
        vol_shift = current_vol - prev_vol
        
        return CorrelationMetrics(
            index_name=idx_data.index_name,
            correlation=current_corr,
            correlation_shift=corr_shift,
            rolling_volatility=current_vol,
            volatility_shift=vol_shift,
            timestamp=as_of_time
        )

    def _rolling_correlation(
        self,
        returns_a: np.ndarray,
        returns_b: np.ndarray
    ) -> float:
        if len(returns_a) < 2 or len(returns_b) < 2:
            return 0.0
        corr_matrix = np.corrcoef(returns_a, returns_b)
        return float(corr_matrix[0, 1])

    def _rolling_volatility(
        self,
        returns: np.ndarray,
        annualization_factor: float = 252.0
    ) -> float:
        if len(returns) < 2:
            return 0.0
        daily_vol = np.std(returns, ddof=1)
        annualized_vol = daily_vol * np.sqrt(annualization_factor)
        return float(annualized_vol * 100)

    def _calculate_sri(
        self,
        correlations: List[CorrelationMetrics],
        cii_scores: Dict[str, float],
        as_of_time: datetime
    ) -> SpreadingRiskIndex:
        corr_component = 0.0
        vol_component = 0.0
        cii_component = 0.0
        
        max_risk_score = 0.0
        dominant_source = "NONE"
        
        for corr_metrics in correlations:
            idx_name = corr_metrics.index_name
            country_code = self.MONITORED_INDICES.get(idx_name, 'XX')
            cii_score = cii_scores.get(country_code, 20.0)
            
            idx_corr_risk = 0.0
            if abs(corr_metrics.correlation) >= self.CORRELATION_HIGH_THRESHOLD:
                idx_corr_risk += 20.0
            if abs(corr_metrics.correlation_shift) >= self.CORRELATION_SHIFT_THRESHOLD:
                idx_corr_risk += 10.0
            corr_component += idx_corr_risk
            
            idx_vol_risk = 0.0
            if corr_metrics.rolling_volatility >= self.VOLATILITY_HIGH_THRESHOLD:
                idx_vol_risk += 15.0
            if abs(corr_metrics.volatility_shift) >= self.VOLATILITY_SHIFT_THRESHOLD:
                idx_vol_risk += 10.0
            vol_component += idx_vol_risk
            
            idx_cii_risk = 0.0
            if abs(corr_metrics.correlation) >= self.CORRELATION_HIGH_THRESHOLD:
                if cii_score >= 60:
                    idx_cii_risk += 15.0
                elif cii_score >= 40:
                    idx_cii_risk += 10.0
                elif cii_score >= 30:
                    idx_cii_risk += 5.0
            cii_component += idx_cii_risk
            
            total_idx_risk = idx_corr_risk + idx_vol_risk + idx_cii_risk
            if total_idx_risk > max_risk_score:
                max_risk_score = total_idx_risk
                dominant_source = idx_name
                
        corr_component = min(40.0, corr_component)
        vol_component = min(30.0, vol_component)
        cii_component = min(30.0, cii_component)
        
        sri_score = corr_component + vol_component + cii_component
        sri_score = float(np.clip(sri_score, 0, 100))
        
        if sri_score >= 60:
            level = MarketStressLevel.RED
        elif sri_score >= 30:
            level = MarketStressLevel.YELLOW
        else:
            level = MarketStressLevel.GREEN
            
        return SpreadingRiskIndex(
            score=sri_score,
            level=level,
            correlation_component=corr_component,
            volatility_component=vol_component,
            cii_component=cii_component,
            dominant_source=dominant_source,
            timestamp=as_of_time
        )

    def _generate_risk_narrative(
        self,
        sri: SpreadingRiskIndex,
        correlations: List[CorrelationMetrics]
    ) -> str:
        level_desc = {
            MarketStressLevel.GREEN: "Normal market conditions",
            MarketStressLevel.YELLOW: "Elevated contagion risk",
            MarketStressLevel.RED: "High contagion risk"
        }
        
        narrative = f"{level_desc[sri.level]} (SRI: {sri.score:.1f}/100). "
        if sri.dominant_source != "NONE":
            narrative += f"Primary risk source: {sri.dominant_source}. "
            
        risk_factors = []
        if sri.correlation_component >= 20:
            risk_factors.append("strong correlation")
        if sri.volatility_component >= 15:
            risk_factors.append("elevated volatility")
        if sri.cii_component >= 15:
            risk_factors.append("country instability")
            
        if risk_factors:
            narrative += f"Key factors: {', '.join(risk_factors)}."
        else:
            narrative += "No significant risk factors detected."
            
        return narrative


def get_market_stress_signal(
    vn_returns: np.ndarray,
    global_indices: List[GlobalIndexData],
    cii_scores: Optional[Dict[str, float]] = None,
    as_of_time: Optional[datetime] = None
) -> Tuple[MarketStressLevel, ContagionReport]:
    """Convenience function for Risk Guard integration (PIT safe)."""
    if as_of_time is None:
        raise ValueError("as_of_time is mandatory for PIT safety")
    detector = GlobalContagionDetector()
    report = detector.detect_contagion(vn_returns, global_indices, cii_scores, as_of_time)
    return report.sri.level, report
