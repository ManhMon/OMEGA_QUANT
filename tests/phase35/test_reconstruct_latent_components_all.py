import pandas as pd
import pytest

from scripts import reconstruct_latent_components_all as script
from scripts.reconstruct_latent_components_all import (
    compute_dynamic_universe_membership,
    select_top_liquid_tickers,
)


def test_select_top_liquid_tickers_uses_requested_window_and_ranking():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2014-12-31",
                    "2015-01-05",
                    "2015-01-05",
                    "2015-01-06",
                    "2015-01-06",
                    "2016-01-05",
                    "2016-01-05",
                ]
            ),
            "ticker": ["OLD", "AAA", "BBB", "AAA", "BBB", "AAA", "BBB"],
            "volume": [10_000, 100, 500, 900, 100, 200, 300],
        }
    )

    result = select_top_liquid_tickers(
        df,
        top_n=2,
        start_date="2015-01-01",
        end_date="2016-12-31",
    )

    assert result == ["AAA", "BBB"]


def test_dynamic_universe_membership_on_date_t_ignores_future_volume_changes():
    base_df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2020-01-01",
                    "2020-01-01",
                    "2020-01-02",
                    "2020-01-02",
                    "2020-01-03",
                    "2020-01-03",
                ]
            ),
            "ticker": ["AAA", "BBB", "AAA", "BBB", "AAA", "BBB"],
            "volume": [100.0, 200.0, 100.0, 200.0, 100.0, 200.0],
        }
    )
    shocked_df = base_df.copy()
    shocked_df.loc[
        (shocked_df["ticker"] == "AAA") & (shocked_df["date"] == pd.Timestamp("2020-01-03")),
        "volume",
    ] = 1_000_000.0

    base_membership = compute_dynamic_universe_membership(base_df, top_n=1)
    shocked_membership = compute_dynamic_universe_membership(shocked_df, top_n=1)

    target_date = pd.Timestamp("2020-01-02")
    base_on_t = base_membership.loc[base_membership["date"] == target_date, "ticker"].tolist()
    shocked_on_t = shocked_membership.loc[shocked_membership["date"] == target_date, "ticker"].tolist()

    assert base_on_t == ["BBB"]
    assert shocked_on_t == base_on_t


def test_build_feature_panel_uses_forward_returns_and_main_deletes_intermediate_parquet(tmp_path, monkeypatch):
    raw_df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2015-01-05",
                    "2015-01-06",
                    "2015-01-07",
                    "2015-01-05",
                    "2015-01-06",
                    "2015-01-07",
                ]
            ),
            "ticker": ["AAA", "AAA", "AAA", "BBB", "BBB", "BBB"],
            "open": [10.0, 11.0, 12.0, 20.0, 21.0, 22.0],
            "high": [10.5, 11.5, 12.5, 20.5, 21.5, 22.5],
            "low": [9.5, 10.5, 11.5, 19.5, 20.5, 21.5],
            "close": [10.0, 11.0, 12.0, 20.0, 21.0, 22.0],
            "volume": [100.0, 110.0, 120.0, 300.0, 310.0, 320.0],
        }
    )

    class StubAdapter:
        def __init__(self, **_kwargs):
            pass

        def generate_all(self, panel):
            return panel.reset_index()[["date", "symbol"]]

    monkeypatch.setattr(script, "UnifiedFeatureAdapter", StubAdapter)

    feat_df = script.build_feature_panel(raw_df, top_n=1)
    assert feat_df["returns"].iloc[0] == pytest.approx(0.05)
    assert feat_df["returns"].iloc[1] == pytest.approx(0.04761904761904767)
    assert pd.isna(feat_df["returns"].iloc[-1])
    assert feat_df["ticker"].unique().tolist() == ["BBB"]

    features_output = tmp_path / "features_advanced_top104_2015_2026.parquet"
    latent_call = {}

    monkeypatch.setattr(script, "MARKET_PATH", tmp_path / "market_2015_now.parquet")
    raw_df.to_parquet(script.MARKET_PATH, index=False)
    monkeypatch.setattr(script, "build_feature_panel", lambda *_args, **_kwargs: feat_df)

    def fake_run_latent_alpha_mining(**kwargs):
        latent_call.update(kwargs)
        assert kwargs["features_path"].exists()

    monkeypatch.setattr(script, "run_latent_alpha_mining", fake_run_latent_alpha_mining)
    monkeypatch.setattr(
        script,
        "parse_args",
        lambda: script.argparse.Namespace(
            top_n=104,
            start_date="2015-01-01",
            end_date="2026-12-31",
            features_output=features_output,
            latent_components=16,
            train_ratio=0.6,
        ),
    )

    script.main()

    assert latent_call["features_path"] == features_output
    assert not features_output.exists()
