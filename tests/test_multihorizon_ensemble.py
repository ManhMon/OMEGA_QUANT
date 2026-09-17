import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import statsmodels.stats.multitest as multitest

from scripts import backtest_multihorizon_ensemble as ensemble
from scripts import run_backtest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


class _FakeGenome:
    def __init__(self, signal: pd.Series):
        self._signal = signal

    def evaluate_vectorized(self, panel: pd.DataFrame) -> pd.Series:
        return self._signal.reindex(panel.index).fillna(0.0)


class _FakeAlpha:
    def __init__(self, expression: str, test_ic: float, signal: pd.Series):
        self.expression = expression
        self.test_ic = test_ic
        self.hit_rate = 0.55
        self.genome = _FakeGenome(signal)


def _make_panel() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=6)
    symbols = ["AAA", "BBB", "CCC"]
    index = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"])
    base = np.linspace(10.0, 15.0, len(index))
    panel = pd.DataFrame(
        {
            "open": base,
            "high": base * 1.01,
            "low": base * 0.99,
            "close": base,
            "volume": np.full(len(index), 1_000_000.0),
        },
        index=index,
    )
    panel["returns"] = panel.groupby(level="symbol")["close"].pct_change().fillna(0.0)
    return panel


def _make_gate_panel(forward_returns: list[float]) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=len(forward_returns))
    index = pd.MultiIndex.from_product([dates, ["AAA"]], names=["date", "symbol"])
    close = np.linspace(10.0, 10.0 + len(forward_returns) - 1, len(forward_returns))
    panel = pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.full(len(forward_returns), 1_000_000.0),
            "fwd_ret_15": forward_returns,
        },
        index=index,
    )
    panel["returns"] = panel.groupby(level="symbol")["close"].pct_change().fillna(0.0)
    return panel


def _make_dynamic_df() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2023-01-02", periods=140)
    rows = []
    for ticker, price_base, volume_base in (
        ("AAA", 20_000.0, 800_000),
        ("BBB", 18_000.0, 700_000),
        ("CCC", 15_000.0, 200_000),
    ):
        for date in dates:
            price = price_base * (1 + rng.normal(0, 0.01))
            volume = max(int(volume_base * (1 + rng.normal(0, 0.05))), 100)
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "open": price * 0.99,
                    "high": price * 1.02,
                    "low": price * 0.98,
                    "close": max(price, 1.0),
                    "volume": volume,
                }
            )
    return pd.DataFrame(rows)


def _make_static_universe_df() -> pd.DataFrame:
    rows = []
    history_dates = pd.bdate_range("2022-07-01", periods=70)
    val_dates = pd.bdate_range("2022-08-01", periods=12)

    for date in history_dates:
        rows.extend(
            [
                {"date": date, "ticker": "AAA", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1_000_000},
                {"date": date, "ticker": "BBB", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100_000},
            ]
        )

    for date in val_dates:
        rows.extend(
            [
                {"date": date, "ticker": "AAA", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100_000},
                {"date": date, "ticker": "BBB", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 2_000_000},
            ]
        )

    return pd.DataFrame(rows)


def test_parse_horizons_defaults_and_custom_values():
    parser = ensemble.build_parser()
    args = parser.parse_args([])
    assert args.horizons == [15, 30, 40]

    args = parser.parse_args(["--horizons", "10,20,20,40"])
    assert args.horizons == [10, 20, 40]


def test_build_multi_horizon_config_uses_requested_horizons():
    config = ensemble.build_multi_horizon_config([7, 14, 21], state_dir="tmp_state")
    assert config.horizons == [7, 14, 21]
    assert config.state_dir == "tmp_state"


def test_apply_dynamic_universe_schedule_drops_pre_rebalance_rows_and_filters_symbols():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2024-01-01",
                    "2024-01-01",
                    "2024-01-02",
                    "2024-01-02",
                    "2024-01-03",
                    "2024-01-03",
                ]
            ),
            "ticker": ["AAA", "BBB", "AAA", "BBB", "AAA", "BBB"],
            "close": [10, 11, 10.5, 11.5, 11, 12],
            "open": [10, 11, 10.5, 11.5, 11, 12],
            "high": [10, 11, 10.5, 11.5, 11, 12],
            "low": [10, 11, 10.5, 11.5, 11, 12],
            "volume": [1000, 1000, 1000, 1000, 1000, 1000],
        }
    )
    schedule = {
        "2024-01-02": ["BBB"],
        "2024-01-03": ["AAA"],
    }

    filtered = ensemble.apply_dynamic_universe_schedule(df, schedule)

    assert filtered["date"].min() == pd.Timestamp("2024-01-02")
    assert filtered.loc[filtered["date"] == pd.Timestamp("2024-01-02"), "ticker"].tolist() == ["BBB"]
    assert filtered.loc[filtered["date"] == pd.Timestamp("2024-01-03"), "ticker"].tolist() == ["AAA"]


def test_build_dynamic_universe_schedule_is_pit_safe():
    schedule, evidence = ensemble.build_dynamic_universe_schedule(
        _make_dynamic_df(),
        symbol_count=2,
        lookback_days=30,
        rebalance_days=20,
        min_history_days=10,
    )

    assert schedule
    assert evidence
    assert all(item["selection_end_before_rebalance"] for item in evidence)
    assert all(
        pd.Timestamp(item["selection_end"]) < pd.Timestamp(item["rebalance_date"])
        for item in evidence
        if item["selection_end"] is not None
    )


def test_select_period_universe_static_uses_pre_period_history_only():
    df = _make_static_universe_df()

    filtered, meta = ensemble.select_period_universe(
        df,
        pd.Timestamp("2022-08-01"),
        pd.Timestamp("2022-08-31"),
        symbol_count=1,
        dynamic_universe=False,
    )

    assert sorted(filtered["ticker"].unique().tolist()) == ["AAA"]
    assert meta["selected_symbols"] == ["AAA"]
    assert meta["history_fallback_to_train_start"] is False
    assert meta["selection_source_end"] < "2022-08-01"


def test_select_period_universe_static_falls_back_to_train_start_when_no_pre_period_history():
    dates = pd.bdate_range("2021-01-04", periods=40)
    df = pd.DataFrame(
        {
            "date": np.repeat(dates, 2),
            "ticker": [ticker for _ in dates for ticker in ("AAA", "BBB")],
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.0,
            "volume": [900_000 if ticker == "AAA" else 100_000 for _ in dates for ticker in ("AAA", "BBB")],
        }
    )

    filtered, meta = ensemble.select_period_universe(
        df,
        pd.Timestamp("2021-01-04"),
        pd.Timestamp("2021-02-28"),
        symbol_count=1,
        dynamic_universe=False,
    )

    assert sorted(filtered["ticker"].unique().tolist()) == ["AAA"]
    assert meta["history_fallback_to_train_start"] is True
    assert meta["selection_source_start"] == "2021-01-04"


def test_build_combined_weights_aggregates_multiple_horizons_with_joblib_backend():
    panel = _make_panel()
    index = panel.index
    signal_one = pd.Series(np.tile([0.1, 0.8, 0.4], 6), index=index)
    signal_two = pd.Series(np.tile([0.6, 0.2, 0.9], 6), index=index)
    alphas = [
        _FakeAlpha("H15d:alpha_one", 0.12, signal_one),
        _FakeAlpha("H30d:alpha_two", 0.08, signal_two),
    ]

    weights, contributions = ensemble.build_combined_weights(
        alphas,
        panel,
        workers=2,
        parallel_backend="joblib",
    )

    assert contributions == 2
    assert list(weights.columns) == ["AAA", "BBB", "CCC"]
    assert np.allclose(weights.sum(axis=1).values, 1.0)
    assert (weights >= 0).all().all()


def test_build_combined_weights_falls_back_to_sequential_after_joblib_error(monkeypatch):
    panel = _make_panel()
    index = panel.index
    signal_one = pd.Series(np.tile([0.1, 0.8, 0.4], 6), index=index)
    signal_two = pd.Series(np.tile([0.6, 0.2, 0.9], 6), index=index)
    alphas = [
        _FakeAlpha("H15d:alpha_one", 0.12, signal_one),
        _FakeAlpha("H30d:alpha_two", 0.08, signal_two),
    ]

    def raise_permission_error(*args, **kwargs):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(ensemble, "Parallel", raise_permission_error)

    weights, contributions = ensemble.build_combined_weights(
        alphas,
        panel,
        workers=2,
        parallel_backend="joblib",
    )

    assert contributions == 2
    assert list(weights.columns) == ["AAA", "BBB", "CCC"]
    assert np.allclose(weights.sum(axis=1).values, 1.0)


def test_apply_profit_factor_gate_keeps_alpha_at_relaxed_threshold():
    panel = _make_gate_panel([0.0, 0.06, -0.05, 0.06, -0.05])
    signal = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0], index=panel.index)
    alpha = _FakeAlpha("H15d:keep", 0.08, signal)

    survivors = ensemble.apply_profit_factor_gate([alpha], panel, [15])

    assert survivors == [alpha]


def test_apply_profit_factor_gate_filters_below_relaxed_threshold():
    panel = _make_gate_panel([0.0, 0.06, -0.05, 0.06, -0.05])
    keep_signal = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0], index=panel.index)
    drop_signal = pd.Series([1.0, 1.0, -1.0, 1.0, 1.0], index=panel.index)
    keep_alpha = _FakeAlpha("H15d:keep", 0.08, keep_signal)
    drop_alpha = _FakeAlpha("H15d:drop", 0.08, drop_signal)

    survivors = ensemble.apply_profit_factor_gate([keep_alpha, drop_alpha], panel, [15])

    assert survivors == [keep_alpha]


def test_apply_fdr_filter_uses_relaxed_alpha(monkeypatch):
    captured: dict[str, object] = {}

    def fake_multipletests(p_values, alpha, method):
        captured["alpha"] = alpha
        captured["method"] = method
        return np.array([True, False]), np.array(p_values), alpha, alpha

    monkeypatch.setattr(multitest, "multipletests", fake_multipletests)

    panel = _make_gate_panel([0.0, 0.02, -0.01, 0.03, -0.02])
    signal = pd.Series([1.0, -1.0, 1.0, -1.0, 1.0], index=panel.index)
    keep_alpha = _FakeAlpha("H15d:keep", 0.08, signal)
    drop_alpha = _FakeAlpha("H15d:drop", 0.08, signal * -1)

    survivors = ensemble.apply_fdr_filter([keep_alpha, drop_alpha], panel, [15])

    assert captured == {"alpha": 0.15, "method": "fdr_bh"}
    assert survivors == [keep_alpha]


def test_run_backtest_alias_points_to_multihorizon_ensemble_script():
    assert run_backtest.SCRIPTS["multihorizon-ensemble"] == "backtest_multihorizon_ensemble.py"
