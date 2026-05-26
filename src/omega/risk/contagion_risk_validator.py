"""
Contagion Risk Validator - V21_QUANT Layer 04
Integrates Global Contagion Detector with Risk Manager.

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

from ..layer_08_situational_awareness.contagion_detector import (
    GlobalContagionDetector,
    GlobalIndexData,
    MarketStressLevel,
    ContagionReport,
    get_market_stress_signal
)
from ..layer_08_situational_awareness.cii_module import (
    CIICalculator,
    CountryData,
    CountryScore
)


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
    
    # Data source (in production, this would be a data provider)
    data_provider: Optional[object] = None


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
        self.detector = GlobalContagionDetector(
            lookback_days=self.config.lookback_days,
            correlation_window=self.config.correlation_window,
            volatility_window=self.config.volatility_window
        )
        self.cii_calculator = CIICalculator() if self.config.enable_cii_weighting else None
    
    def validate(
        self,
        vn_returns: np.ndarray,
        global_indices: List[GlobalIndexData],
        cii_scores: Optional[Dict[str, float]] = None,
        as_of_time: Optional[datetime] = None
    ) -> Tuple[bool, float, ContagionReport]:
        """
        Validate portfolio against global contagion risk.
        
        Args:
            vn_returns: VN-Index log returns (60+ days)
            global_indices: List of GlobalIndexData objects
            cii_scores: Optional CII scores from Layer 08
            as_of_time: Validation timestamp (defaults to now)
        
        Returns:
            Tuple of (is_safe, risk_multiplier, contagion_report)
            - is_safe: True if GREEN, False if YELLOW/RED
            - risk_multiplier: Position sizing adjustment (0.3-1.0)
            - contagion_report: Full ContagionReport for logging
        
        PIT Guarantee:
            All input data must be as of `as_of_time`.
        """
        if not self.config.enabled:
            # Validator disabled, return safe with no adjustment
            return True, 1.0, None
        
        as_of_time = as_of_time or datetime.utcnow()
        
        # Detect contagion risk
        report = self.detector.detect_contagion(
            vn_returns,
            global_indices,
            cii_scores,
            as_of_time
        )
        
        # Determine risk multiplier based on stress level
        stress_level = report.sri.level
        
        if stress_level == MarketStressLevel.GREEN:
            is_safe = True
            multiplier = self.config.green_multiplier
        elif stress_level == MarketStressLevel.YELLOW:
            is_safe = False
            multiplier = self.config.yellow_multiplier
        else:  # RED
            is_safe = False
            multiplier = self.config.red_multiplier
        
        return is_safe, multiplier, report
    
    def get_risk_narrative(self, report: ContagionReport) -> str:
        """
        Generate risk narrative for Risk Manager logging.
        
        Args:
            report: ContagionReport from validate()
        
        Returns:
            Human-readable risk summary
        """
        if report is None:
            return "Contagion risk validator disabled."
        
        return report.risk_narrative


class ContagionRiskGuard:
    """
    High-level Risk Guard interface for contagion monitoring.
    
    This class provides a simplified interface for the Risk Manager
    to integrate contagion risk without managing data fetching.
    
    Usage:
        guard = ContagionRiskGuard(data_provider)
        signal, multiplier, narrative = guard.check_contagion_risk()
        
        if signal == MarketStressLevel.RED:
            # Halt trading or reduce positions
    """
    
    def __init__(
        self,
        data_provider: object,
        config: Optional[ContagionRiskConfig] = None
    ):
        """
        Initialize contagion risk guard.
        
        Args:
            data_provider: Data provider with methods:
                - get_vn_index_returns(days: int) -> np.ndarray
                - get_global_index_data(index_name: str, days: int) -> GlobalIndexData
                - get_cii_scores() -> Dict[str, float]
            config: Optional configuration
        """
        self.data_provider = data_provider
        self.validator = ContagionRiskValidator(config)
        self.config = config or ContagionRiskConfig()
    
    def check_contagion_risk(
        self,
        as_of_time: Optional[datetime] = None
    ) -> Tuple[MarketStressLevel, float, str]:
        """
        Check current contagion risk and return actionable signal.
        
        Args:
            as_of_time: Check timestamp (defaults to now)
        
        Returns:
            Tuple of (stress_level, risk_multiplier, narrative)
            - stress_level: GREEN/YELLOW/RED
            - risk_multiplier: Position sizing adjustment (0.3-1.0)
            - narrative: Human-readable risk summary
        
        Example:
            >>> guard = ContagionRiskGuard(data_provider)
            >>> signal, multiplier, narrative = guard.check_contagion_risk()
            >>> print(f"{signal.value}: {narrative}")
            >>> if signal == MarketStressLevel.RED:
            >>>     # Reduce all positions by 70%
            >>>     adjusted_weights = {s: w * multiplier for s, w in weights.items()}
        """
        as_of_time = as_of_time or datetime.utcnow()
        
        # Fetch data from provider
        vn_returns = self.data_provider.get_vn_index_returns(
            self.config.lookback_days
        )
        
        global_indices = []
        for index_name in ['SPX', 'HSI', 'SSE']:
            idx_data = self.data_provider.get_global_index_data(
                index_name,
                self.config.lookback_days
            )
            if idx_data:
                global_indices.append(idx_data)
        
        cii_scores = None
        if self.config.enable_cii_weighting:
            cii_scores = self.data_provider.get_cii_scores()
        
        # Validate
        is_safe, multiplier, report = self.validator.validate(
            vn_returns,
            global_indices,
            cii_scores,
            as_of_time
        )
        
        narrative = self.validator.get_risk_narrative(report)
        
        return report.sri.level, multiplier, narrative


# ============================================================================
# RISK MANAGER INTEGRATION HELPERS
# ============================================================================

def create_contagion_validator(
    enabled: bool = True,
    yellow_multiplier: float = 0.7,
    red_multiplier: float = 0.3
) -> ContagionRiskValidator:
    """
    Factory function to create ContagionRiskValidator for Risk Manager.
    
    Args:
        enabled: Enable/disable contagion risk checking
        yellow_multiplier: Position reduction for YELLOW signal (default 0.7)
        red_multiplier: Position reduction for RED signal (default 0.3)
    
    Returns:
        Configured ContagionRiskValidator instance
    
    Example (in risk_manager.py):
        >>> from .contagion_risk_validator import create_contagion_validator
        >>> 
        >>> class RiskManager:
        >>>     def __init__(self, config):
        >>>         self.config = config
        >>>         self._validators = self._initialize_validators()
        >>>         self._contagion_validator = create_contagion_validator(
        >>>             enabled=config.enable_contagion_check,
        >>>             yellow_multiplier=0.7,
        >>>             red_multiplier=0.3
        >>>         )
    """
    config = ContagionRiskConfig(
        enabled=enabled,
        yellow_multiplier=yellow_multiplier,
        red_multiplier=red_multiplier
    )
    return ContagionRiskValidator(config)


def apply_contagion_risk_adjustment(
    symbol_weights: Dict[str, float],
    risk_multiplier: float
) -> Dict[str, float]:
    """
    Apply contagion risk multiplier to symbol weights.
    
    Args:
        symbol_weights: Original symbol weights (sum to 1.0)
        risk_multiplier: Multiplier from ContagionRiskValidator (0.3-1.0)
    
    Returns:
        Adjusted symbol weights (sum to risk_multiplier)
    
    Example:
        >>> weights = {'VNM': 0.3, 'VIC': 0.4, 'HPG': 0.3}
        >>> adjusted = apply_contagion_risk_adjustment(weights, 0.7)
        >>> # Result: {'VNM': 0.21, 'VIC': 0.28, 'HPG': 0.21}
    """
    return {
        symbol: weight * risk_multiplier
        for symbol, weight in symbol_weights.items()
    }


# ============================================================================
# MOCK DATA PROVIDER (FOR TESTING)
# ============================================================================

class MockDataProvider:
    """
    Mock data provider for testing contagion risk integration.
    
    In production, replace with real data provider that fetches from:
    - VN-Index: vnstock or direct exchange API
    - Global indices: Yahoo Finance, Bloomberg, or market data vendor
    - CII scores: Layer 08 CII module with live data feeds
    """
    
    def get_vn_index_returns(self, days: int) -> np.ndarray:
        """Mock VN-Index returns."""
        np.random.seed(42)
        return np.random.normal(0.001, 0.015, days)
    
    def get_global_index_data(
        self,
        index_name: str,
        days: int
    ) -> Optional[GlobalIndexData]:
        """Mock global index data."""
        np.random.seed(hash(index_name) % 2**32)
        
        country_map = {'SPX': 'US', 'HSI': 'HK', 'SSE': 'CN'}
        price_map = {'SPX': 5200.0, 'HSI': 18500.0, 'SSE': 3100.0}
        
        if index_name not in country_map:
            return None
        
        returns = np.random.normal(0.0005, 0.012, days)
        
        return GlobalIndexData(
            index_name=index_name,
            country_code=country_map[index_name],
            timestamp=datetime.utcnow(),
            close_price=price_map[index_name],
            returns=returns
        )
    
    def get_cii_scores(self) -> Dict[str, float]:
        """Mock CII scores."""
        return {
            'US': 28.0,
            'HK': 42.0,
            'CN': 35.0
        }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == '__main__':
    """
    Example: Integrate contagion risk with Risk Manager.
    """
    print("Contagion Risk Validator - V21_QUANT Layer 04")
    print("=" * 70)
    
    # 1. Create mock data provider
    data_provider = MockDataProvider()
    
    # 2. Create contagion risk guard
    guard = ContagionRiskGuard(data_provider)
    
    # 3. Check contagion risk
    signal, multiplier, narrative = guard.check_contagion_risk()
    
    print(f"\nMarket Stress Signal: {signal.value}")
    print(f"Risk Multiplier: {multiplier:.1%}")
    print(f"\nRisk Narrative:")
    print(f"  {narrative}")
    
    # 4. Apply to portfolio weights
    original_weights = {
        'VNM': 0.25,
        'VIC': 0.30,
        'HPG': 0.25,
        'VHM': 0.20
    }
    
    adjusted_weights = apply_contagion_risk_adjustment(
        original_weights,
        multiplier
    )
    
    print(f"\nPosition Sizing Adjustment:")
    print(f"  Original weights: {original_weights}")
    print(f"  Adjusted weights: {adjusted_weights}")
    print(f"  Total exposure: {sum(adjusted_weights.values()):.1%}")
    
    # 5. Risk Manager integration example
    print(f"\n" + "=" * 70)
    print("Risk Manager Integration Example:")
    print("=" * 70)
    
    print("""
# In risk_manager.py:

from .contagion_risk_validator import (
    create_contagion_validator,
    apply_contagion_risk_adjustment
)

class RiskManager:
    def __init__(self, config):
        self.config = config
        self._validators = self._initialize_validators()
        
        # Add contagion risk validator
        self._contagion_validator = create_contagion_validator(
            enabled=config.enable_contagion_check,
            yellow_multiplier=0.7,
            red_multiplier=0.3
        )
    
    def _validate_portfolio_with_tiers(self, target_portfolio):
        # ... existing validation logic ...
        
        # Check contagion risk
        if self._contagion_validator.config.enabled:
            vn_returns = self._fetch_vn_index_returns()
            global_data = self._fetch_global_index_data()
            cii_scores = self._fetch_cii_scores()
            
            is_safe, multiplier, report = self._contagion_validator.validate(
                vn_returns, global_data, cii_scores
            )
            
            if not is_safe:
                # Apply risk multiplier
                if multiplier < trim_factor:
                    trim_factor = multiplier
                
                if report.sri.level == MarketStressLevel.RED:
                    level = RiskLevel.RED
                    violations.append(f"CONTAGION RISK: {report.risk_narrative}")
                else:
                    level = RiskLevel.AMBER if level == RiskLevel.GREEN else level
                    violations.append(f"CONTAGION WARNING: {report.risk_narrative}")
                
                # Log contagion event
                self._log_risk_event("contagion_risk", {
                    "sri_score": report.sri.score,
                    "stress_level": report.sri.level.value,
                    "multiplier": multiplier,
                    "dominant_source": report.sri.dominant_source
                }, approved=is_safe)
        
        # ... rest of validation logic ...
    """)
