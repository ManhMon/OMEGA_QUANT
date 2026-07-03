from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from omega.core.vn_market_rules import VnMarketRules
from omega.quant.models.conformal_predictor import ConformalTrendPredictor
from omega.quant.models.price_ladder import build_price_ladder


def test_asymmetric_cqr_uses_quantile_models():
    x_train = pd.DataFrame({"x": np.linspace(-2, 2, 80)})
    y_train = x_train["x"] * 0.3 + np.where(x_train["x"] > 0, 0.2, -0.05)
    x_calib = pd.DataFrame({"x": np.linspace(-1, 1, 40)})
    y_calib = x_calib["x"] * 0.3 + np.where(x_calib["x"] > 0, 0.25, -0.02)
    groups = pd.DataFrame({"regime": ["bull"] * 40, "liquidity_bucket": ["high"] * 40})
    model = ConformalTrendPredictor(alpha=0.2, min_group_size=5)
    model.fit(x_train, y_train, x_calib, y_calib, groups)
    pred = model.predict(pd.DataFrame({"x": [0.8]}), pd.DataFrame({"regime": ["bull"], "liquidity_bucket": ["high"]}))
    assert (pred.point[0] - pred.lower[0]) != (pred.upper[0] - pred.point[0])


def test_ladder_monotone_nested():
    ladder = build_price_ladder(27_350, {0.5: (-0.01, 0.01), 0.8: (-0.02, 0.02), 0.9: (-0.03, 0.03)}, VnMarketRules.round_price_tick, VnMarketRules.calculate_price_limits)
    assert ladder["rungs"][1]["price_low"] <= ladder["rungs"][0]["price_low"]
    assert ladder["rungs"][1]["price_high"] >= ladder["rungs"][0]["price_high"]


def test_ladder_respects_price_limits():
    ladder = build_price_ladder(27_350, {0.5: (-0.5, 0.5)}, VnMarketRules.round_price_tick, VnMarketRules.calculate_price_limits)
    floor, ceiling = VnMarketRules.calculate_price_limits(27_350)
    rung = ladder["rungs"][0]
    assert floor <= rung["price_low"] <= ceiling
    assert floor <= rung["price_high"] <= ceiling
    assert VnMarketRules.is_valid_price(rung["price_low"], 27_350)
    assert VnMarketRules.is_valid_price(rung["price_high"], 27_350)


def test_ladder_degenerate_flag():
    ladder = build_price_ladder(10_000, {0.5: (-0.0001, 0.0001)}, VnMarketRules.round_price_tick, VnMarketRules.calculate_price_limits)
    assert ladder["degenerate"] is True


def test_marginal_prob_sums_to_outer_coverage():
    ladder = build_price_ladder(27_350, {0.5: (-0.01, 0.01), 0.8: (-0.02, 0.02), 0.95: (-0.04, 0.04)}, VnMarketRules.round_price_tick, VnMarketRules.calculate_price_limits)
    assert sum(rung["marginal_prob"] for rung in ladder["rungs"]) == 0.95
