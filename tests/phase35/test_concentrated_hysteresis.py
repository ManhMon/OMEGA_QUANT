"""Tests for concentrated overlay rank hysteresis.

Gate: HYBRID_REGIME_HYSTERESIS_OVERLAY_20260630
"""

from __future__ import annotations

import argparse

import pandas as pd

from scripts import backtest_hybrid_regime as hybrid_regime


class TestLongOnlyConcentratedOverlayHysteresis:
    def test_retains_previous_name_within_hysteresis_buffer(self):
        overlay = hybrid_regime.LongOnlyConcentratedOverlay(top_k=2, hysteresis=1)
        state = {}

        first = pd.DataFrame([[0.40, 0.30, 0.20, 0.10]], columns=list("ABCD"), index=[0])
        second = pd.DataFrame([[0.40, 0.20, 0.30, 0.10]], columns=list("ABCD"), index=[1])

        initial = overlay.apply(first, panel=pd.DataFrame(), state=state)
        follow_up = overlay.apply(second, panel=pd.DataFrame(), state=state)

        assert list(initial.loc[0][initial.loc[0] > 0].index) == ["A", "B"]
        assert list(follow_up.loc[1][follow_up.loc[1] > 0].index) == ["A", "B"]
        assert state["long_only_concentrated_prev_selected"] == ["A", "B"]

    def test_drops_previous_name_after_rank_falls_beyond_buffer(self):
        overlay = hybrid_regime.LongOnlyConcentratedOverlay(top_k=2, hysteresis=1)
        state = {}

        first = pd.DataFrame([[0.40, 0.30, 0.20, 0.10]], columns=list("ABCD"), index=[0])
        third = pd.DataFrame([[0.40, 0.10, 0.30, 0.20]], columns=list("ABCD"), index=[1])

        overlay.apply(first, panel=pd.DataFrame(), state=state)
        follow_up = overlay.apply(third, panel=pd.DataFrame(), state=state)

        assert list(follow_up.loc[1][follow_up.loc[1] > 0].index) == ["A", "C"]
        assert state["long_only_concentrated_prev_selected"] == ["A", "C"]

    def test_zero_sum_row_clears_state(self):
        overlay = hybrid_regime.LongOnlyConcentratedOverlay(top_k=2, hysteresis=2)
        state = {"long_only_concentrated_prev_selected": ["A", "B"]}

        out = overlay.apply(
            pd.DataFrame([[0.0, 0.0, 0.0]], columns=list("ABC"), index=[0]),
            panel=pd.DataFrame(),
            state=state,
        )

        assert out.loc[0].sum() == 0.0
        assert state["long_only_concentrated_prev_selected"] == []


class TestConcentratedHysteresisCli:
    def test_cli_default_is_two(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["prog"])
        args = hybrid_regime.parse_args()
        assert args.risk_concentrated_hysteresis == 2

    def test_cli_custom_value_flows_into_config(self):
        args = argparse.Namespace(
            capital=1_000_000.0,
            hmm_reentry_threshold=0.6,
            cost_per_trade_bps=35.0,
            min_trade_threshold_bps=250.0,
            rebalance_every_n_days=15,
            tail_target_vol_ann=0.2,
            tail_max_abs_weight=0.25,
            tail_downside_only_vol_target=False,
            risk_regime_sizing_scale=0.5,
            risk_concentrated_hysteresis=4,
            risk_latent_gmm_bear_dampening=0.45,
            tcost_dynamic_ic_lookback=20,
        )

        config = hybrid_regime.safe_build_pipeline_config(args)

        assert config["risk_concentrated_hysteresis"] == 4

    def test_overlay_builder_wires_hysteresis(self):
        overlays = hybrid_regime.build_scenario_overlays(
            capital=1_000_000.0,
            top_k=3,
            concentrated_hysteresis=5,
        )

        baseline_overlay = next(
            overlay
            for overlay in overlays["Baseline"]
            if isinstance(overlay, hybrid_regime.LongOnlyConcentratedOverlay)
        )
        hybrid_overlay = next(
            overlay
            for overlay in overlays["Hybrid"]
            if isinstance(overlay, hybrid_regime.LongOnlyConcentratedOverlay)
        )

        assert baseline_overlay.hysteresis == 5
        assert hybrid_overlay.hysteresis == 5
