import pandas as pd
import pytest

from omega.quant.graph.builder import build_graph
from omega.quant.signal.sentiment_loader import SentimentDataLoader


def test_loader_joins_only_available_sentiment_in_chronological_order():
    loader = SentimentDataLoader(
        pd.DataFrame(
            {
                "symbol": ["AAA", "AAA"],
                "date": ["2026-01-01", "2026-01-02"],
                "market_implied_sentiment": [0.1, 0.2],
                "available_at": ["2026-01-01", "2026-01-03"],
            }
        ),
        pd.DataFrame(
            {
                "symbol": ["AAA"],
                "publish_time": ["2026-01-01"],
                "sentiment_score": [0.7],
                "available_at": ["2026-01-02"],
            }
        ),
    )

    joined = loader.join_sentiment_to_market(pd.DataFrame({"symbol": ["AAA"] * 3, "date": ["2026-01-01", "2026-01-02", "2026-01-03"]}))

    assert joined["sentiment_proxy"].tolist() == [0.1, 0.1, 0.2]
    assert pd.isna(joined.loc[0, "news_sentiment"])
    assert joined.loc[1, "news_sentiment"] == 0.7
    assert (joined["sentiment_proxy_available_at"].dropna() <= joined.loc[joined["sentiment_proxy_available_at"].notna(), "date"]).all()


def test_loader_rejects_unprovenanced_news():
    loader = SentimentDataLoader(
        pd.DataFrame({"symbol": ["AAA"], "date": ["2026-01-01"], "market_implied_sentiment": [0.1], "available_at": ["2026-01-01"]}),
        pd.DataFrame({"symbol": ["AAA"], "publish_time": ["2026-01-02"], "sentiment_score": [0.1], "available_at": ["2026-01-01"]}),
    )

    with pytest.raises(ValueError, match="PIT violation"):
        loader.load_news_sentiment()


def test_loader_aggregates_daily_news_with_latest_availability_and_utc_keys():
    loader = SentimentDataLoader(
        pd.DataFrame({"symbol": ["AAA"], "date": ["2026-01-02 00:00:00+07:00"], "market_implied_sentiment": [0.1], "available_at": ["2026-01-01 17:00:00+00:00"]}),
        pd.DataFrame(
            {
                "symbol": ["AAA", "AAA"],
                "publish_time": ["2026-01-01 09:00:00+07:00", "2026-01-01 15:00:00+07:00"],
                "sentiment_score": [0.2, 0.8],
                "available_at": ["2026-01-01 10:00:00+07:00", "2026-01-02 00:00:00+07:00"],
            }
        ),
    )

    news = loader.load_news_sentiment()
    joined = loader.join_sentiment_to_market(pd.DataFrame({"symbol": ["AAA"], "date": ["2026-01-01 17:00:00+00:00"]}))

    assert news.loc[0, "sentiment_score"] == pytest.approx(0.5)
    assert news.loc[0, "available_at"] == pd.Timestamp("2026-01-01 17:00:00+00:00")
    assert str(news["available_at"].dt.tz) == "UTC"
    assert joined.loc[0, "news_sentiment"] == pytest.approx(0.5)


def test_graph_includes_provenanced_sentiment_factors():
    graph = build_graph(
        {
            "observed_at": "2026-01-01T00:00:00Z",
            "sentiment_proxy": [{"symbol": "AAA", "sentiment_proxy": 0.2, "available_at": "2026-01-01"}],
            "news_sentiment": [{"symbol": "AAA", "news_sentiment": -0.1, "available_at": "2026-01-01"}],
        }
    )

    assert graph.nodes["sentiment_proxy:AAA"]["factor"] == "sentiment_proxy"
    assert graph["AAA"]["news_sentiment:AAA"]["weight"] == -0.1


@pytest.mark.parametrize("observed_at", [None, "not-a-datetime"])
def test_graph_rejects_missing_or_invalid_observed_at_when_sentiment_exists(observed_at):
    with pytest.raises(ValueError, match="observed_at must be a valid datetime"):
        build_graph({"observed_at": observed_at, "sentiment_proxy": [{"symbol": "AAA", "sentiment_proxy": 0.2, "available_at": "2026-01-01"}]})


@pytest.mark.parametrize("sentiment", [None, [], {"sentiment_proxy": [], "news_sentiment": []}])
def test_graph_allows_missing_observed_at_without_sentiment_factors(sentiment):
    snapshots = {"list_by_industry": [{"ticker": "AAA", "industry": "Banks"}]}
    if isinstance(sentiment, dict):
        snapshots.update(sentiment)
    elif sentiment is not None:
        snapshots["sentiment_proxy"] = sentiment

    graph = build_graph(snapshots)

    assert graph["AAA"]["Banks"]["observed_at"] is None


@pytest.mark.parametrize("kind,target_key", [("subsidiaries", "subsidiary"), ("ownership", "target")])
def test_graph_rejects_invalid_row_observed_at(kind, target_key):
    with pytest.raises(ValueError, match="observed_at must be a valid datetime"):
        build_graph({kind: [{"ticker": "AAA", target_key: "BBB", "observed_at": "not-a-datetime"}]})


def test_graph_normalizes_observed_at_to_utc_for_every_edge_type():
    graph = build_graph(
        {
            "observed_at": "2026-01-03T00:00:00+07:00",
            "list_by_industry": [{"ticker": "AAA", "industry": "Banks"}],
            "subsidiaries": [{"ticker": "AAA", "subsidiary": "BBB", "observed_at": "2026-01-02T00:00:00+07:00"}],
            "ownership": [{"ticker": "AAA", "target": "CCC", "observed_at": "2026-01-02T00:00:00-05:00"}],
            "officers": [{"ticker": "AAA", "name": "Jane"}, {"ticker": "DDD", "name": "Jane"}],
            "sentiment_proxy": [{"symbol": "AAA", "sentiment_proxy": 0.2, "available_at": "2026-01-02T00:00:00Z"}],
            "news_sentiment": [{"symbol": "AAA", "news_sentiment": -0.1, "available_at": "2026-01-02T00:00:00Z"}],
        }
    )

    expected = {
        "industry_membership": pd.Timestamp("2026-01-02T17:00:00Z"),
        "subsidiary_of": pd.Timestamp("2026-01-01T17:00:00Z"),
        "ownership_by": pd.Timestamp("2026-01-02T05:00:00Z"),
        "same_officer": pd.Timestamp("2026-01-02T17:00:00Z"),
        "sentiment_proxy": pd.Timestamp("2026-01-02T17:00:00Z"),
        "news_sentiment": pd.Timestamp("2026-01-02T17:00:00Z"),
    }
    observed_by_type = {data["edge_type"]: data["observed_at"] for _, _, data in graph.edges(data=True)}

    assert observed_by_type == expected
    assert all(str(timestamp.tz) == "UTC" for timestamp in observed_by_type.values())


def test_graph_rejects_sentiment_not_available_at_observation_time():
    with pytest.raises(ValueError, match="PIT violation"):
        build_graph(
            {
                "observed_at": "2026-01-01T00:00:00Z",
                "sentiment_proxy": [{"symbol": "AAA", "sentiment_proxy": 0.2, "available_at": "2026-01-01T00:00:01Z"}],
            }
        )


def test_graph_sentiment_tie_breaking_is_independent_of_input_order():
    snapshots = {
        "observed_at": "2026-01-03T00:00:00Z",
        "news_sentiment": [
            {"symbol": "AAA", "news_sentiment": 0.5, "available_at": "2026-01-02T00:00:00Z"},
            {"symbol": "AAA", "news_sentiment": 0.8, "available_at": "2026-01-02T00:00:00Z"},
            {"symbol": "AAA", "news_sentiment": 0.9, "available_at": "2026-01-01T00:00:00Z"},
        ],
    }

    graph = build_graph(snapshots)
    reversed_graph = build_graph({**snapshots, "news_sentiment": list(reversed(snapshots["news_sentiment"]))})

    assert graph["AAA"]["news_sentiment:AAA"]["weight"] == 0.8
    assert reversed_graph["AAA"]["news_sentiment:AAA"]["weight"] == 0.8
