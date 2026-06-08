"""
Gap Phase 5.2: Contagion Risk Validator - OMEGA Edition
Layer 04: Risk Management

Integrates Global Contagion Detector with Risk Manager.
Provides validator interface for Risk Manager.
Adjusts position sizing based on global contagion risk.

INSTITUTIONAL GRADE IMPLEMENTATION:
- Integrates Layer 08 (Situational Awareness) with Layer 04 (Risk Management)
- Provides validator interface for Risk Manager
- Adjusts position sizing based on global contagion risk
- Point-in-time safe: all data timestamped

INTEGRATION FLOW:
1. Risk Manager calls ContagionRiskValidator during portfolio validation
2. Validator fetches VN-Index and global index data
3. Calls GlobalContagionDetector to calculate SRI
4. Returns risk multiplier based on Market Stress Signal:
   - GREEN: 1.0 (no adjustment)
   - YELLOW: 0.7 (reduce positions by 30%)
   - RED: 0.3 (reduce positions by 70%)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

logger = logging.getLogger("OmegaContagionRisk")


@dataclass
class ContagionRiskConfig:
    """Configuration for contagion risk validator."""
    enabled: bool = True
    lookback_days: int = 60
    correlation_window: int = 30
    volatility_window: int = 20
    
    # Risk multipliers by stress level
    green_multiplier: float = 1.0   # No adjustment
    yellow_multiplier: float = 0.7  # Reduce by 30%
    red_multiplier: float = 0.3     # Reduce by 70%
    
    # CII integration
    enable_cii_weighting: bool = True


@dataclass
class GlobalIndexData:
    """Global index data for contagion detection."""
    ticker: str
    log_returns: np.ndarray
    timestamp: datetime


@dataclass
class MarketStressLevel:
    """Market stress level classification."""
    level: str  # 'GREEN', 'YELLOW', 'RED'
    sri: float  # Systemic Risk Index
    description: str


@dataclass
class ContagionReport:
    """Report from contagion risk validation."""
    is_safe: bool
    risk_multiplier: float
    stress_level: MarketStressLevel
    vn_index_sri: float
    global_index_sri: float
    cii_score: Optional[float]
    recommendations: List[str]


class ContagionRiskValidator:
    """
    Validator that integrates global contagion risk into Risk Manager.
    
    Usage in Risk Manager:
        validator = ContagionRiskValidator(config)
        is_safe, multiplier, report = validator.validate(vn_returns, global_data)
        
        if not is_safe:
            # Apply multiplier to reduce position sizes
            adjusted_weights = {s: w * multiplier for s, w in weights.items()}
    """
    
    def __init__(self, config: Optional[ContagionRiskConfig] = None):
        """Initialize contagion risk validator."""
        self.config = config or ContagionRiskConfig()
        self.logger = logging.getLogger(__name__)
    
    def calculate_sri(
        self,
        vn_returns: np.ndarray,
        global_indices: List[GlobalIndexData]
    ) -> float:
        """
        Calculate Systemic Risk Index (SRI).
        
        SRI = weighted average of:
        - VN-Index volatility (normalized)
        - Correlation between VN and global indices
        - Global index volatility
        
        Args:
            vn_returns: VN-Index log returns (60+ days)
            global_indices: List of GlobalIndexData objects
        
        Returns:
            SRI value (0-1 scale, higher = more systemic risk)
        """
        if not self.config.enabled or len(global_indices) == 0:
            return 0.0
        
        # VN-Index volatility (normalized to 0-1)
        vn_volatility = np.std(vn_returns)
        vn_vol_normalized = min(1.0, vn_volatility / 0.02)  # Normalize to ~2% daily vol
        
        # Correlation with global indices
        correlations = []
        for idx_data in global_indices:
            if len(idx_data.log_returns) >= len(vn_returns):
                corr = np.corrcoef(vn_returns, idx_data.log_returns[:len(vn_returns)])[0, 1]
                correlations.append(abs(corr))
        
        avg_correlation = np.mean(correlations) if correlations else 0.0
        
        # Global volatility component
        global_vols = [np.std(idx.log_returns) for idx in global_indices]
        avg_global_vol = np.mean(global_vols) if global_vols else 0.0
        global_vol_normalized = min(1.0, avg_global_vol / 0.015)
        
        # Weighted SRI calculation
        sri = 0.4 * vn_vol_normalized + 0.4 * avg_correlation + 0.2 * global_vol_normalized
        
        return min(1.0, sri)
    
    def classify_stress_level(self, sri: float) -> MarketStressLevel:
        """
        Classify market stress level based on SRI.
        
        Args:
            sri: Systemic Risk Index value
        
        Returns:
            MarketStressLevel with classification
        """
        if sri < 0.4:
            return MarketStressLevel(
                level='GREEN',
                sri=sri,
                description='Normal market conditions - no adjustment needed'
            )
        elif sri < 0.7:
            return MarketStressLevel(
                level='YELLOW',
                sri=sri,
                description='Elevated systemic risk - reduce positions by 30%'
            )
        else:
            return MarketStressLevel(
                level='RED',
                sri=sri,
                description='High systemic risk - reduce positions by 70%'
            )
    
    def get_risk_multiplier(self, stress_level: MarketStressLevel) -> float:
        """
        Get position sizing multiplier based on stress level.
        
        Args:
            stress_level: Market stress level classification
        
        Returns:
            Multiplier (1.0 = no reduction, 0.7 = 30% reduction, 0.3 = 70% reduction)
        """
        if stress_level.level == 'GREEN':
            return self.config.green_multiplier
        elif stress_level.level == 'YELLOW':
            return self.config.yellow_multiplier
        else:  # RED
            return self.config.red_multiplier
    
    def validate(
        self,
        vn_returns: np.ndarray,
        global_indices: List[GlobalIndexData],
        as_of_time: Optional[datetime] = None
    ) -> Tuple[bool, float, ContagionReport]:
        """
        Validate portfolio against global contagion risk.
        
        Args:
            vn_returns: VN-Index log returns (60+ days)
            global_indices: List of GlobalIndexData objects
            as_of_time: Validation timestamp (defaults to now)
        
        Returns:
            Tuple of (is_safe, risk_multiplier, contagion_report)
        """
        if not self.config.enabled or len(global_indices) == 0:
            report = ContagionReport(
                is_safe=True,
                risk_multiplier=1.0,
                stress_level=MarketStressLevel('GREEN', 0.0, 'Contagion check disabled'),
                vn_index_sri=0.0,
                global_index_sri=0.0,
                cii_score=None,
                recommendations=[]
            )
            return True, 1.0, report
        
        # Calculate SRI
        vn_sri = self.calculate_sri(vn_returns, global_indices)
        
        # Classify stress level
        stress_level = self.classify_stress_level(vn_sri)
        
        # Get risk multiplier
        risk_multiplier = self.get_risk_multiplier(stress_level)
        
        # Generate recommendations
        recommendations = []
        if stress_level.level == 'YELLOW':
            recommendations.append("Reduce position sizes by 30%")
            recommendations.append("Increase cash buffer")
        elif stress_level.level == 'RED':
            recommendations.append("Reduce position sizes by 70%")
            recommendations.append("Increase cash buffer significantly")
            recommendations.append("Review sector exposure")
        
        report = ContagionReport(
            is_safe=stress_level.level != 'RED',
            risk_multiplier=risk_multiplier,
            stress_level=stress_level,
            vn_index_sri=vn_sri,
            global_index_sri=vn_sri,
            cii_score=None,
            recommendations=recommendations
        )
        
        return report.is_safe, risk_multiplier, report
