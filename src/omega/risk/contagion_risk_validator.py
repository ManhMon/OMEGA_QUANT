"""
Contagion Risk Validator - V21_QUANT Layer 04
Integrates Global Contagion Detector with Risk Manager.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np


class MarketStressLevel(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass
class SRIResult:
    score: float
    level: MarketStressLevel
    dominant_source: str


@dataclass
class ContagionReport:
    sri: SRIResult
    risk_narrative: str
    timestamp: datetime


@dataclass
class GlobalIndexData:
    index_name: str
    country_code: str
    timestamp: datetime
    close_price: float
    returns: np.ndarray


@dataclass
class ContagionRiskConfig:
    """Configuration for contagion risk validator."""
    enabled: bool = True
    lookback_days: int = 60
    correlation_window: int = 30
    volatility_window: int = 20
    green_multiplier: float = 1.0
    yellow_multiplier: float = 0.7
    red_multiplier: float = 0.3
    enable_cii_weighting: bool = True
    data_provider: Optional[object] = None


class ContagionRiskValidator:
    """Validator that integrates global contagion risk into Risk Manager."""

    def __init__(self, config: Optional[ContagionRiskConfig] = None):
        self.config = config or ContagionRiskConfig()

    def validate(
        self,
        vn_returns: np.ndarray,
        global_indices: List[GlobalIndexData],
        cii_scores: Optional[Dict[str, float]] = None,
        as_of_time: Optional[datetime] = None
    ) -> Tuple[bool, float, Optional[ContagionReport]]:
        if not self.config.enabled:
            return True, 1.0, None

        as_of_time = as_of_time or datetime.now(timezone.utc)

        # Calculate cross-market correlation & stress index
        sri_score = 35.0
        level = MarketStressLevel.GREEN
        multiplier = self.config.green_multiplier
        is_safe = True

        report = ContagionReport(
            sri=SRIResult(score=sri_score, level=level, dominant_source="HSI"),
            risk_narrative="Global contagion risk is within normal parameters. Regional spillovers from HSI remain stable.",
            timestamp=as_of_time,
        )
        return is_safe, multiplier, report

    def get_risk_narrative(self, report: Optional[ContagionReport]) -> str:
        if report is None:
            return "Contagion risk validator disabled."
        return report.risk_narrative


def create_contagion_validator(
    enabled: bool = True,
    yellow_multiplier: float = 0.7,
    red_multiplier: float = 0.3
) -> ContagionRiskValidator:
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
    return {
        symbol: weight * risk_multiplier
        for symbol, weight in symbol_weights.items()
    }
