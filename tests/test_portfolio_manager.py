"""Tests for OMEGA_QUANT Portfolio Manager."""

import pytest
import pandas as pd
from omega.core.portfolio_manager import PortfolioManager


def test_portfolio_manager_initialization() -> None:
    pm = PortfolioManager({"max_positions": 10})
    assert pm.max_positions == 10
    assert pm.min_position_size == 0.01


def test_generate_rebalancing_orders_empty_holdings() -> None:
    pm = PortfolioManager({})
    target = pd.DataFrame([
        {"ticker": "SSI", "weight": 0.6},
        {"ticker": "HPG", "weight": 0.4},
    ])
    current = pd.DataFrame()

    orders = pm.generate_orders(target, current)
    assert len(orders) == 2
    assert orders.loc[0, "action"] == "BUY"
    assert orders.loc[0, "quantity"] == 60000.0


def test_generate_rebalancing_orders_with_holdings() -> None:
    pm = PortfolioManager({})
    target = pd.DataFrame([
        {"ticker": "SSI", "weight": 0.6},
        {"ticker": "HPG", "weight": 0.4},
    ])
    current = pd.DataFrame([
        {"ticker": "SSI", "weight": 0.4},
        {"ticker": "HPG", "weight": 0.5},
    ])

    orders = pm.generate_orders(target, current)
    assert len(orders) == 2
    
    ssi_order = orders[orders["ticker"] == "SSI"].iloc[0]
    assert ssi_order["action"] == "BUY"
    assert pytest.approx(ssi_order["weight_change"]) == 0.2
    assert pytest.approx(ssi_order["quantity"]) == 20000.0

    hpg_order = orders[orders["ticker"] == "HPG"].iloc[0]
    assert hpg_order["action"] == "SELL"
    assert pytest.approx(hpg_order["weight_change"]) == 0.1
    assert pytest.approx(hpg_order["quantity"]) == 10000.0
