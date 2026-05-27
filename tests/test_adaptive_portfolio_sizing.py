"""Tests for OMEGA_QUANT Adaptive Portfolio Sizing Engine (APSE)."""

import pytest
from datetime import datetime
from omega.quant.adaptive_portfolio_sizing import (
    AdaptiveConfig,
    AdaptivePortfolioSizingEngine
)
from omega.core.vn_market_rules import VnMarketRules


def test_determine_capital_tier() -> None:
    # Micro tier: 0 - 5B
    apse_micro = AdaptivePortfolioSizingEngine(capital=2_000_000_000)
    assert apse_micro.capital_tier == "micro"

    # Small tier: 5B - 20B
    apse_small = AdaptivePortfolioSizingEngine(capital=10_000_000_000)
    assert apse_small.capital_tier == "small"

    # Medium tier: 20B - 100B
    apse_medium = AdaptivePortfolioSizingEngine(capital=50_000_000_000)
    assert apse_medium.capital_tier == "medium"

    # Large tier: > 100B
    apse_large = AdaptivePortfolioSizingEngine(capital=150_000_000_000)
    assert apse_large.capital_tier == "large"


def test_optimize_micro_tier() -> None:
    as_of = datetime(2026, 1, 1)
    apse = AdaptivePortfolioSizingEngine(
        capital=2_000_000_000,
        market_regime="neutral",
        alpha_quality=0.05
    )
    config = apse.optimize(as_of=as_of)
    
    assert isinstance(config, AdaptiveConfig)
    assert config.capital_tier == "micro"
    # Micro holdings: 8 to 12
    assert 8 <= config.target_num_holdings <= 12
    assert config.max_asset_cap == 0.20  # Midpoint of (0.15, 0.25)
    assert config.max_sector_cap == 0.40  # Midpoint of (0.35, 0.45)
    assert config.max_adv_percentage == 0.35  # Midpoint of (0.30, 0.40)


def test_optimize_large_tier() -> None:
    as_of = datetime(2026, 1, 1)
    apse = AdaptivePortfolioSizingEngine(
        capital=150_000_000_000,
        market_regime="bull",
        alpha_quality=0.08
    )
    config = apse.optimize(as_of=as_of)
    
    assert config.capital_tier == "large"
    # Large holdings: 40 to 80
    assert 40 <= config.target_num_holdings <= 80
    assert config.max_asset_cap == pytest.approx(0.075)  # Midpoint of (0.05, 0.10)
    assert config.max_sector_cap == pytest.approx(0.20)  # Midpoint of (0.15, 0.25)
    assert config.max_adv_percentage == pytest.approx(0.165)  # Midpoint of (0.10, 0.20) * 1.1 (bull)
    assert "hft" in config.enabled_alphas


def test_board_lot_integration() -> None:
    apse = AdaptivePortfolioSizingEngine(capital=2_000_000_000)
    assert apse.board_lot_size == VnMarketRules.BOARD_LOT
