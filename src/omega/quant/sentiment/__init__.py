"""
OMEGA_QUANT Sentiment Analysis Module.

Vietnam Sentiment Index (VSI) engine for institutional-grade
market sentiment scoring.
"""

from omega.quant.sentiment.vsi_engine import (
    VSIPortfolioEngine,
    SentimentPolarity,
    VSILevel,
    SentimentDictionary,
    SourceCredibility,
    SentimentData,
    SentimentScore,
    VSIScore,
)

__all__ = [
    "VSIPortfolioEngine",
    "SentimentPolarity",
    "VSILevel",
    "SentimentDictionary",
    "SourceCredibility",
    "SentimentData",
    "SentimentScore",
    "VSIScore",
]

# Auto-wired submodules and subpackages
try:
    from . import cii_engine
except ImportError:
    pass

try:
    from . import contagion_detector
except ImportError:
    pass

try:
    from . import vsi_engine
except ImportError:
    pass
