import numpy as np
import pandas as pd

from scripts.backtest_hybrid_regime import (
    build_scenario_overlays,
    parse_args,
    safe_build_pipeline_config,
    select_alpha_features_by_penalized_ic,
    train_fold_models,
)
from omega.quant.pipeline.overlays.rebalance_frequency import RebalanceFrequencyOverlay


def test_penalized_alpha_selection_prefers_lower_turnover_when_ic_similar():
    dates = pd.date_range("2024-01-01", periods=12, freq="D")
    alpha_fast = np.array([0, 1] * 6, dtype=float)
    alpha_slow = np.linspace(-0.6, 0.6, len(dates))
    returns = np.array([0.00, 0.18, 0.05, 0.15, 0.10, 0.12, 0.16, 0.20, 0.24, 0.22, 0.28, 0.30])

    train_sorted = pd.DataFrame(
        {
            "date": dates,
            "symbol": ["AAA"] * len(dates),
            "returns": returns,
            "alpha_fast": alpha_fast,
            "alpha_slow": alpha_slow,
        }
    )
    lag_cols = ["alpha_fast_lag1", "alpha_slow_lag1"]
    lagged = train_sorted.groupby("symbol")[["alpha_fast", "alpha_slow"]].shift(1)
    lagged.columns = lag_cols
    temp_train = pd.concat([train_sorted[["returns", "date"]], lagged], axis=1).iloc[1:].dropna(subset=["returns"])

    selected, metrics = select_alpha_features_by_penalized_ic(
        train_sorted=train_sorted,
        temp_train=temp_train,
        lag_col_names_all=lag_cols,
        alpha_turnover_penalty=0.2,
        top_k=1,
    )

    assert selected == ["alpha_slow_lag1"]
    assert metrics["alpha_fast_lag1"]["turnover"] > metrics["alpha_slow_lag1"]["turnover"]
    assert metrics["alpha_slow_lag1"]["score"] > metrics["alpha_fast_lag1"]["score"]


def test_train_fold_models_selection_changes_with_turnover_penalty():
    dates = pd.date_range("2024-01-01", periods=60, freq="D")
    alpha_fast = np.array(([0.0, 1.0] * 30)[: len(dates)], dtype=float)
    alpha_mid = np.sin(np.linspace(0.0, np.pi, len(dates)))
    alpha_slow = np.linspace(-1.0, 1.0, len(dates))
    returns = 0.08 * alpha_fast + 0.10 * alpha_mid + 0.04 * alpha_slow

    feat_df = pd.DataFrame({
        "date": dates,
        "symbol": ["AAA"] * len(dates),
        "close": np.linspace(10.0, 20.0, len(dates)),
        "returns": returns,
        "alpha_hr_fast": alpha_fast,
        "alpha_hr_mid": alpha_mid,
        "alpha_hr_slow": alpha_slow,
    })

    train_dates = feat_df["date"].unique()
    _, _, low_penalty_signal = train_fold_models(
        feat_df,
        train_dates,
        precomputed_lag_cols=None,
        model_type="ridge",
        alpha_turnover_penalty=0.0,
    )
    _, _, high_penalty_signal = train_fold_models(
        feat_df,
        train_dates,
        precomputed_lag_cols=None,
        model_type="ridge",
        alpha_turnover_penalty=0.2,
    )

    assert low_penalty_signal is not None
    assert high_penalty_signal is not None
    low_selected = low_penalty_signal.attrs["selected_lag_cols"]
    high_selected = high_penalty_signal.attrs["selected_lag_cols"]

    assert low_selected == ["alpha_hr_fast_lag1", "alpha_hr_mid_lag1"]
    assert high_selected == ["alpha_hr_mid_lag1", "alpha_hr_fast_lag1"]


def test_rebalance_overlay_uses_bear_multiplier_with_gmm_labels():
    dates = pd.date_range("2024-01-01", periods=7, freq="D")
    weights = pd.DataFrame({"AAA": np.arange(1, 8, dtype=float)}, index=dates)
    overlay = RebalanceFrequencyOverlay(rebalance_every_n_days=2, bear_multiplier=2.0)

    state = {
        "gmm_regime_labels": {
            "2024-01-01": "Bull",
            "2024-01-03": "Bear",
            "2024-01-07": "Bull",
        }
    }
    result = overlay.apply(weights, panel=pd.DataFrame(), state=state)

    assert result["AAA"].tolist() == [1.0, 1.0, 3.0, 3.0, 3.0, 3.0, 7.0]


def test_parse_args_exposes_penalty_and_rebalance_multiplier(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "backtest_hybrid_regime.py",
            "--alpha-turnover-penalty",
            "0.35",
            "--rebalance-bear-multiplier",
            "3.5",
        ],
    )

    args = parse_args()

    assert args.alpha_turnover_penalty == 0.35
    assert args.rebalance_bear_multiplier == 3.5


def test_parse_args_penalty_and_rebalance_multiplier_defaults(monkeypatch):
    monkeypatch.setattr("sys.argv", ["backtest_hybrid_regime.py"])

    args = parse_args()

    assert args.alpha_turnover_penalty == 0.1
    assert args.rebalance_bear_multiplier == 2.0


def test_cli_config_flows_into_overlay_builder():
    class Args:
        capital = 2_000_000_000.0
        hmm_reentry_threshold = 0.6
        cost_per_trade_bps = 35.0
        min_trade_threshold_bps = 250.0
        alpha_turnover_penalty = 0.25
        rebalance_every_n_days = 11
        rebalance_bear_multiplier = 3.0
        tail_target_vol_ann = 0.2
        tail_max_abs_weight = 0.25
        tail_downside_only_vol_target = False
        risk_regime_sizing_scale = 0.5
        risk_concentrated_hysteresis = 2
        risk_latent_gmm_bear_dampening = 0.45
        tcost_dynamic_ic_lookback = 20

    config = safe_build_pipeline_config(Args())
    scenarios = build_scenario_overlays(
        capital=Args.capital,
        rebalance_every_n_days=int(config["rebalance_every_n_days"]),
        rebalance_bear_multiplier=float(config["rebalance_bear_multiplier"]),
    )

    assert config["alpha_turnover_penalty"] == 0.25
    assert config["rebalance_bear_multiplier"] == 3.0
    for scenario in ("Baseline", "Hybrid"):
        rebalance = next(
            overlay for overlay in scenarios[scenario] if isinstance(overlay, RebalanceFrequencyOverlay)
        )
        assert rebalance.rebalance_every_n_days == 11
        assert rebalance.bear_multiplier == 3.0
