"""
OMEGA_QUANT Factory Package
Alpha Discovery & Feature Generation

Exports:
- DiscoveryEngine: Main orchestrator for alpha generation
- AlphaAlchemist: Expression-based alpha evaluator
- TechnicalGenerator: Hard-coded technical features
"""

from .discovery_engine import (
    DiscoveryEngine,
    AlphaAlchemist,
    TechnicalGenerator,
    rank,
    delay,
    delta,
    ts_mean,
    ts_std,
    ts_max,
    ts_min
)

__all__ = [
    "DiscoveryEngine",
    "AlphaAlchemist",
    "TechnicalGenerator",
    "rank",
    "delay",
    "delta",
    "ts_mean",
    "ts_std",
    "ts_max",
    "ts_min"
]
