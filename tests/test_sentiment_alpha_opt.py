from datetime import datetime, timezone
from math import exp, log1p
from random import Random
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

from omega.quant.signal.sentiment_alpha import (
    SentimentAlphaEngine,
    ecosystem_sentiment_spillover,
    news_count_surprise,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from run_sentiment_blend import blend_signals


TIMES = {
    "as_of": datetime(2026, 8, 6, tzinfo=timezone.utc),
    "available_at": datetime(2026, 8, 5, 12, tzinfo=timezone.utc),
    "timestamp": datetime(2026, 8, 7, tzinfo=timezone.utc),
}


@pytest.mark.parametrize("decay", [float("nan"), float("inf"), float("-inf"), -0.1])
def test_invalid_sentiment_decay_rejected(decay):
    with pytest.raises(ValueError, match="sentiment_decay"):
        SentimentAlphaEngine(sentiment_decay=decay)


@pytest.mark.parametrize("scale", [float("nan"), float("inf"), float("-inf")])
def test_invalid_sentiment_scale_rejected(scale):
    with pytest.raises(ValueError, match="sentiment_scale"):
        SentimentAlphaEngine(sentiment_scale=scale)


@pytest.mark.parametrize("default_score", [float("nan"), float("inf"), float("-inf")])
def test_invalid_default_score_rejected(default_score):
    with pytest.raises(ValueError, match="default_score"):
        SentimentAlphaEngine(default_score=default_score)


def test_sentiment_decay_and_volume_scaling():
    result = SentimentAlphaEngine(sentiment_scale=1.0, sentiment_decay=0.5).combine_sentiment_alpha(
        pd.Series([0.0], index=["VNM"]), pd.Series([1.0], index=["VNM"]),
        article_counts=pd.Series([3], index=["VNM"]), sentiment_age_days=2, **TIMES,
    )
    assert result["VNM"] == pytest.approx(log1p(3) * exp(-1), rel=1e-12)


def test_zero_decay_and_per_symbol_age_hard_cutoff():
    result = SentimentAlphaEngine(sentiment_scale=1.0, sentiment_decay=0).combine_sentiment_alpha(
        pd.Series([0.0, 0.0], index=["B", "A"]), pd.Series([1.0, 1.0], index=["A", "B"]),
        sentiment_age_days=pd.Series([89, 90], index=["A", "B"]), **TIMES,
    )
    assert result.to_dict() == pytest.approx({"A": 1.0, "B": 0.0})


@pytest.mark.parametrize("ages", [pd.Series([float("nan")], index=["VNM"]), pd.Series([1, 2], index=["VNM", "VNM"])])
def test_invalid_sentiment_age_rejected(ages):
    with pytest.raises(ValueError, match="sentiment_age_days"):
        SentimentAlphaEngine().combine_sentiment_alpha(
            pd.Series([0.0], index=["VNM"]), pd.Series([0.1], index=["VNM"]),
            sentiment_age_days=ages, **TIMES,
        )


@pytest.mark.parametrize("counts", [pd.Series([float("nan")], index=["VNM"]), pd.Series([-1], index=["VNM"])])
def test_invalid_article_count_rejected(counts):
    with pytest.raises(ValueError, match="article_counts"):
        SentimentAlphaEngine().combine_sentiment_alpha(
            pd.Series([0.0], index=["VNM"]), pd.Series([0.1], index=["VNM"]),
            article_counts=counts, **TIMES,
        )


def test_available_at_after_as_of_rejected():
    with pytest.raises(ValueError, match="available_at"):
        SentimentAlphaEngine().combine_sentiment_alpha(
            pd.Series([0.0], index=["VNM"]), pd.Series([0.1], index=["VNM"]),
            as_of=TIMES["as_of"], available_at=TIMES["timestamp"], timestamp=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )


def test_as_of_after_timestamp_rejected():
    with pytest.raises(ValueError, match="as_of must not exceed timestamp"):
        SentimentAlphaEngine().combine_sentiment_alpha(
            pd.Series([0.0], index=["VNM"]), pd.Series([0.1], index=["VNM"]),
            as_of=TIMES["timestamp"], available_at=TIMES["available_at"], timestamp=TIMES["as_of"],
        )


def test_blend_accepts_prior_day_sentiment_generated_after_close():
    result = blend_signals(
        {"signals": {"VNM": 0.0}},
        {
            "date": "2026-08-05",
            "generated_at": "2026-08-05T20:00:00",
            "scores": {"VNM": 1.0},
        },
        target_date="2026-08-06",
        sentiment_scale=0.1,
    )
    assert result["signals"]["VNM"] == pytest.approx(0.1)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_base_signals_rejected(value):
    with pytest.raises(ValueError, match="base_signals"):
        SentimentAlphaEngine().combine_sentiment_alpha(
            pd.Series([value], index=["VNM"]), pd.Series([0.1], index=["VNM"]), **TIMES,
        )


def test_duplicate_base_signal_symbols_rejected():
    with pytest.raises(ValueError, match="base_signals must have unique index"):
        SentimentAlphaEngine().combine_sentiment_alpha(
            pd.Series([0.0, 0.1], index=["VNM", "VNM"]),
            pd.Series([0.1], index=["VNM"]), **TIMES,
        )


def test_per_symbol_pit_timestamps_reject_local_violation():
    with pytest.raises(ValueError, match="available_at must be strictly less"):
        SentimentAlphaEngine().combine_sentiment_alpha(
            pd.Series([0.0, 0.0], index=["VNM", "VIC"]),
            pd.Series([0.1, 0.2], index=["VNM", "VIC"]),
            available_at=pd.Series([TIMES["available_at"], TIMES["as_of"]], index=["VNM", "VIC"]),
            timestamp=pd.Series([TIMES["timestamp"], TIMES["as_of"]], index=["VNM", "VIC"]),
            as_of=TIMES["as_of"],
        )


@pytest.mark.parametrize(
    ("available_at", "timestamp", "message"),
    [
        (pd.Series([pd.NaT], index=["VNM"]), pd.Series([TIMES["timestamp"]], index=["VNM"]), "available_at contains NaT"),
        (pd.Series([TIMES["available_at"]], index=["VNM"]), pd.Series([datetime(2026, 8, 7)], index=["VNM"]), "compatible timezones"),
    ],
)
def test_per_symbol_pit_timestamps_reject_invalid_values(available_at, timestamp, message):
    with pytest.raises(ValueError, match=message):
        SentimentAlphaEngine().combine_sentiment_alpha(
            pd.Series([0.0], index=["VNM"]), pd.Series([0.1], index=["VNM"]),
            as_of=TIMES["as_of"], available_at=available_at, timestamp=timestamp,
        )


def test_sector_neutralization_preserves_base_signal():
    result = SentimentAlphaEngine(sentiment_scale=1.0).combine_sentiment_alpha(
        pd.Series([10.0, 20.0], index=["VNM", "VIC"]),
        pd.Series([0.1, 0.3], index=["VNM", "VIC"]),
        sectors=pd.Series(["Consumer", "Consumer"], index=["VNM", "VIC"]), **TIMES,
    )
    assert result.to_dict() == pytest.approx({"VIC": 20.1, "VNM": 9.9})


def _count_panel(values):
    sessions = pd.date_range("2026-10-01", periods=len(values), tz="Asia/Ho_Chi_Minh")
    counts = pd.Series(values, index=sessions, dtype=object)
    available = pd.Series(sessions + pd.Timedelta(hours=15, minutes=30), index=sessions)
    return counts, available


def _surprise(counts, available, **kwargs):
    return news_count_surprise(counts, available_at=available,
                               decision_time=pd.Timestamp("2026-10-20T11:29:20Z"),
                               window=3, min_history=2, **kwargs)


def test_news_count_surprise_prior_only_population_moments():
    counts, available = _count_panel([0, 2, 1, 10, 0])
    result = _surprise(counts, available)
    assert result.iloc[0]["status"] == "insufficient_history"
    assert pd.isna(result.iloc[0]["surprise"])
    assert result.iloc[2]["prior_mean"] == 1
    assert result.iloc[2]["prior_std"] == 1
    assert result.iloc[2]["surprise"] == 0
    assert result.iloc[3]["surprise"] == 5
    mutated = counts.copy()
    mutated.iloc[-1] = 1e12
    pd.testing.assert_frame_equal(result.iloc[:-1], _surprise(mutated, available).iloc[:-1])
    changed_current = counts.copy()
    changed_current.iloc[2] = 100
    current = _surprise(changed_current, available)
    assert current.iloc[2]["prior_mean"] == result.iloc[2]["prior_mean"]
    assert current.iloc[2]["prior_std"] == result.iloc[2]["prior_std"]
    assert result.attrs["historical_eligible"] is False


def test_news_count_surprise_zero_history_and_clipping():
    counts, available = _count_panel([2, 2, 100])
    result = _surprise(counts, available)
    assert result.iloc[-1]["status"] == "zero_variance"
    assert pd.isna(result.iloc[-1]["surprise"])
    counts, available = _count_panel([0, 2, 0])
    assert _surprise(counts, available).iloc[-1]["surprise"] == -1
    counts, available = _count_panel([1e12, 1e12 - 2, 0])
    assert _surprise(counts, available).iloc[-1]["surprise"] == -5
    assert _surprise(*_count_panel([])).empty


def test_news_count_surprise_availability_cutoff_and_late_revision():
    counts, available = _count_panel([0, 2, 1, 2])
    # A delayed count cannot influence an earlier decision, even if loaded today.
    available.iloc[1] = available.iloc[-1]
    result = _surprise(counts, available)
    assert result.iloc[2]["history_count"] == 1
    assert result.iloc[2]["status"] == "insufficient_history"
    exact = news_count_surprise(counts, available_at=available,
                               decision_time=available.iloc[-1], window=3, min_history=2)
    assert len(exact) == 4
    before = news_count_surprise(counts, available_at=available,
                                decision_time=available.iloc[-1] - pd.Timedelta(microseconds=1),
                                window=3, min_history=2)
    assert list(before.index) == [counts.index[0], counts.index[2]]
    utc = available.dt.tz_convert("UTC")
    pd.testing.assert_frame_equal(_surprise(counts, available), _surprise(counts, utc))


@pytest.mark.parametrize("value", [None, "3", [], True, float("nan"), float("inf"), float("-inf"), -1, 0.5, 1e13, pytest.param(10**400, id="integer-overflow")])
def test_news_count_surprise_invalid_counts(value):
    counts, available = _count_panel([0, 2, value])
    with pytest.raises(ValueError):
        _surprise(counts, available)


@pytest.mark.parametrize("change", ["duplicate", "unsorted", "naive", "nat", "availability_index", "availability_naive", "availability_nat", "time_order"])
def test_news_count_surprise_rejects_malformed_sessions(change):
    counts, available = _count_panel([0, 2, 1])
    if change == "duplicate":
        counts.index = pd.DatetimeIndex([counts.index[0]] * 3)
    elif change == "unsorted":
        counts = counts.iloc[::-1]
    elif change == "naive":
        counts.index = counts.index.tz_localize(None)
    elif change == "nat":
        counts.index = pd.DatetimeIndex([counts.index[0], pd.NaT, counts.index[-1]])
    elif change == "availability_index":
        available = available.iloc[::-1]
    elif change == "availability_naive":
        available = available.dt.tz_localize(None)
    elif change == "availability_nat":
        available.iloc[0] = pd.NaT
    else:
        available.iloc[0] = counts.index[0] - pd.Timedelta(microseconds=1)
    with pytest.raises(ValueError):
        _surprise(counts, available)


@pytest.mark.parametrize(("window", "minimum"), [(0, 2), (-1, 2), (253, 2), (True, 2), (3, 1), (3, 4), (3, None)])
def test_news_count_surprise_invalid_windows(window, minimum):
    counts, available = _count_panel([0, 2, 1])
    with pytest.raises(ValueError):
        news_count_surprise(counts, available_at=available, decision_time=available.iloc[-1],
                            window=window, min_history=minimum)


def test_news_count_surprise_no_mutation_or_calendar_invention():
    counts, available = _count_panel([0, 2, 1])
    # Explicit Saturday/Sunday observations remain research inputs, not certified sessions.
    counts.index = counts.index + pd.Timedelta(days=2)
    available.index = counts.index
    available = available + pd.Timedelta(days=2)
    saved_counts, saved_available = counts.copy(deep=True), available.copy(deep=True)
    _surprise(counts, available)
    pd.testing.assert_series_equal(counts, saved_counts)
    pd.testing.assert_series_equal(available, saved_available)


# Spillover contract fixtures stay local so these adversarial cases run independently.
_SPILL_DECISION = pd.Timestamp("2026-08-06T00:00:00Z")
_SPILL_LAG = pd.Timestamp("2026-08-05T16:00:00Z")
_SPILL_AS_OF = pd.Timestamp("2026-08-04T00:00:00Z")
_SPILL_AVAILABLE = pd.Timestamp("2026-08-05T12:00:00Z")
_SPILL_EXPECTED_AT = pd.Timestamp("2026-08-03T00:00:00Z")


def _spill_news(rows=None):
    columns = ["issuer", "observed", "expected", "sector", "as_of",
               "available_at", "expected_available_at"]
    if rows is None:
        rows = [{"issuer": "A", "observed": 0.5, "expected": 0.1,
                 "sector": "S", "as_of": _SPILL_AS_OF,
                 "available_at": _SPILL_AVAILABLE,
                 "expected_available_at": _SPILL_EXPECTED_AT}]
    frame = pd.DataFrame(rows, columns=columns)
    for column in ("observed", "expected", "as_of", "available_at", "expected_available_at"):
        frame[column] = frame[column].astype(object)
    return frame


def _spill_edges(rows=None):
    columns = ["source", "target", "weight", "as_of", "available_at", "valid_until"]
    if rows is None:
        rows = [{"source": "A", "target": "B", "weight": 1.0,
                 "as_of": _SPILL_AS_OF, "available_at": _SPILL_AVAILABLE,
                 "valid_until": None}]
    frame = pd.DataFrame(rows, columns=columns)
    for column in ("weight", "as_of", "available_at", "valid_until"):
        frame[column] = frame[column].astype(object)
    return frame


def _spill(news=None, edges=None):
    return ecosystem_sentiment_spillover(
        _spill_news() if news is None else news,
        _spill_edges() if edges is None else edges,
        decision_time=_SPILL_DECISION, lag_time=_SPILL_LAG, graph_complete=True,
    )


@pytest.mark.parametrize("slot,bad", [("news", None), ("news", []),
                                        ("edges", None), ("edges", [])])
def test_spillover_requires_dataframes(slot, bad):
    args = {"news": _spill_news(), "edges": _spill_edges()}
    args[slot] = bad
    args["decision_time"], args["lag_time"], args["graph_complete"] = (
        _SPILL_DECISION, _SPILL_LAG, True,
    )
    with pytest.raises(ValueError, match="invalid_spillover_schema_or_size"):
        ecosystem_sentiment_spillover(**args)


@pytest.mark.parametrize("slot,change", [("news", "missing"), ("news", "extra"),
                                           ("news", "duplicate"), ("edges", "missing"),
                                           ("edges", "extra"), ("edges", "duplicate")])
def test_spillover_requires_exact_unique_columns(slot, change):
    frame = _spill_news() if slot == "news" else _spill_edges()
    if change == "missing":
        frame = frame.iloc[:, :-1]
    elif change == "extra":
        frame["unexpected"] = 1
    else:
        frame = pd.concat([frame, frame.iloc[:, [0]]], axis=1)
    with pytest.raises(ValueError, match="invalid_spillover_schema_or_size"):
        _spill(news=frame) if slot == "news" else _spill(edges=frame)


@pytest.mark.parametrize("field", ["issuer", "sector", "source", "target"])
@pytest.mark.parametrize("bad", [None, "", " padded", "x\n", 7,
                                 pytest.param("x" * 129, id="overlong")])
def test_spillover_rejects_malformed_identifiers(field, bad):
    news, edges = _spill_news(), _spill_edges()
    if field in ("issuer", "sector"):
        news.loc[0, field] = bad
    else:
        edges.loc[0, field] = bad
    with pytest.raises(ValueError, match="invalid_spillover_identifier"):
        _spill(news, edges)


def test_spillover_rejects_duplicate_issuer_rows():
    row = _spill_news().iloc[0].to_dict()
    with pytest.raises(ValueError, match="duplicate_spillover_issuer"):
        _spill(_spill_news([row, row]))


@pytest.mark.parametrize("column", ["observed", "expected"])
@pytest.mark.parametrize("bad", [True, "0.2", [], float("inf"), float("-inf"),
                                  -1.01, 1.01, pytest.param(10**400, id="integer-overflow")])
def test_spillover_rejects_invalid_scores(column, bad):
    news = _spill_news()
    news.at[0, column] = bad
    with pytest.raises(ValueError, match="invalid_spillover_score"):
        _spill(news=news)


@pytest.mark.parametrize("column,bad", [("observed", None), ("observed", float("nan")),
                                         ("expected", None), ("expected", float("nan"))])
def test_spillover_unknown_scores_remain_unknown(column, bad):
    news = _spill_news()
    news.at[0, column] = bad
    result = _spill(news=news)
    if column == "observed":
        assert pd.isna(result.loc["A", "direct_news"])
        assert pd.isna(result.loc["A", "innovation"])
    else:
        assert result.loc["A", "direct_news"] == pytest.approx(0.5)
        assert pd.isna(result.loc["A", "innovation"])


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), float("-inf"),
                                  True, "1", -0.1, 1e12 + 1, pytest.param(10**400, id="integer-overflow")])
def test_spillover_rejects_invalid_edge_weights(bad):
    edges = _spill_edges()
    edges.at[0, "weight"] = bad
    with pytest.raises(ValueError, match="invalid_edge_weight"):
        _spill(edges=edges)


def test_spillover_zero_weight_does_not_propagate_unknown_source():
    news = _spill_news([{"issuer": "T", "observed": 0.2, "expected": 0.1,
                         "sector": "S", "as_of": _SPILL_AS_OF,
                         "available_at": _SPILL_AVAILABLE,
                         "expected_available_at": _SPILL_EXPECTED_AT}])
    edge = _spill_edges([{"source": "missing", "target": "T", "weight": 0.0,
                          "as_of": _SPILL_AS_OF, "available_at": _SPILL_AVAILABLE,
                          "valid_until": None}])
    assert _spill(news, edge).loc["T", "spillover"] == 0.0


@pytest.mark.parametrize("slot,column,bad", [
    ("news", "as_of", datetime(2026, 8, 4)),
    ("news", "available_at", "2026-08-05T12:00:00Z"),
    ("news", "expected_available_at", pd.NaT),
    ("edges", "as_of", "2026-08-04T00:00:00Z"),
    ("edges", "available_at", pd.NaT),
    ("edges", "valid_until", datetime(2026, 8, 7)),
])
def test_spillover_rejects_malformed_timestamps(slot, column, bad):
    news, edges = _spill_news(), _spill_edges()
    (news if slot == "news" else edges).at[0, column] = bad
    with pytest.raises(ValueError):
        _spill(news, edges)


@pytest.mark.parametrize("slot", ["news", "edges"])
def test_spillover_rejects_asof_after_availability(slot):
    news, edges = _spill_news(), _spill_edges()
    frame = news if slot == "news" else edges
    frame.at[0, "as_of"] = _SPILL_AVAILABLE + pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="invalid_spillover_time_order"):
        _spill(news, edges)


@pytest.mark.parametrize("expected_at", [_SPILL_AS_OF, _SPILL_AS_OF + pd.Timedelta(seconds=1)])
def test_spillover_rejects_expectation_leakage(expected_at):
    news = _spill_news()
    news.at[0, "expected_available_at"] = expected_at
    with pytest.raises(ValueError, match="invalid_spillover_expectation_time"):
        _spill(news=news)


@pytest.mark.parametrize("valid_until", [_SPILL_AS_OF, _SPILL_AS_OF - pd.Timedelta(seconds=1)])
def test_spillover_rejects_empty_edge_validity_interval(valid_until):
    edges = _spill_edges()
    edges.at[0, "valid_until"] = valid_until
    with pytest.raises(ValueError, match="invalid_spillover_edge_interval"):
        _spill(edges=edges)


def test_spillover_accepts_open_edge_validity_interval():
    assert _spill().loc["B", "spillover"] == pytest.approx(0.4)


@pytest.mark.parametrize("lag", [_SPILL_DECISION, _SPILL_DECISION + pd.Timedelta(seconds=1)])
def test_spillover_requires_lag_before_decision(lag):
    with pytest.raises(ValueError, match="invalid_spillover_cutoff_or_coverage"):
        ecosystem_sentiment_spillover(_spill_news(), _spill_edges(),
                                      decision_time=_SPILL_DECISION, lag_time=lag,
                                      graph_complete=True)


@pytest.mark.parametrize("coverage", [0, 1, "true", None, pd.NA, np.bool_(True)])
def test_spillover_requires_boolean_coverage(coverage):
    with pytest.raises(ValueError, match="invalid_spillover_cutoff_or_coverage"):
        ecosystem_sentiment_spillover(_spill_news(), _spill_edges(),
                                      decision_time=_SPILL_DECISION, lag_time=_SPILL_LAG,
                                      graph_complete=coverage)


def test_spillover_empty_panels_return_empty_frame():
    result = _spill(_spill_news([]), _spill_edges([]))
    assert result.empty
    assert list(result.columns) == ["direct_news", "innovation", "sector_news", "spillover"]


@pytest.mark.parametrize("kind", ["edge_count", "node_count", "incoming_degree"])
def test_spillover_graph_caps_fail_closed(kind, monkeypatch):
    monkeypatch.setattr(
        pd.DataFrame, "reindex",
        lambda *args, **kwargs: pytest.fail("graph cap must precede dense reindex"),
    )
    if kind == "edge_count":
        count = 100_001
        sources, targets = [f"S{i}" for i in range(count)], ["T"] * count
    elif kind == "node_count":
        count = 5_001
        sources, targets = [f"S{i}" for i in range(count)], [f"T{i}" for i in range(count)]
    else:
        count = 1_001
        sources, targets = [f"S{i}" for i in range(count)], ["T"] * count
    edges = pd.DataFrame({
        "source": sources, "target": targets, "weight": [1.0] * count,
        "as_of": [_SPILL_AS_OF] * count, "available_at": [_SPILL_AVAILABLE] * count,
        "valid_until": [None] * count,
    })
    with pytest.raises(ValueError, match="invalid_spillover_(schema_or_size|graph_size)"):
        _spill(edges=edges)


def test_spillover_large_weights_and_row_scale_invariance():
    news = _spill_news([
        {"issuer": "A", "observed": 0.6, "expected": 0.2, "sector": "S",
         "as_of": _SPILL_AS_OF, "available_at": _SPILL_AVAILABLE,
         "expected_available_at": _SPILL_EXPECTED_AT},
        {"issuer": "B", "observed": 0.1, "expected": 0.3, "sector": "S",
         "as_of": _SPILL_AS_OF, "available_at": _SPILL_AVAILABLE,
         "expected_available_at": _SPILL_EXPECTED_AT},
        {"issuer": "T", "observed": 0.0, "expected": 0.0, "sector": "S",
         "as_of": _SPILL_AS_OF, "available_at": _SPILL_AVAILABLE,
         "expected_available_at": _SPILL_EXPECTED_AT},
    ])
    rows = [{"source": source, "target": "T", "weight": weight,
             "as_of": _SPILL_AS_OF, "available_at": _SPILL_AVAILABLE,
             "valid_until": None} for source, weight in [("A", 2.0), ("B", 3.0)]]
    base = _spill(news, _spill_edges(rows)).loc["T", "spillover"]
    scaled = [dict(row, weight=row["weight"] * 1e11) for row in rows]
    result = _spill(news, _spill_edges(scaled)).loc["T", "spillover"]
    assert result == pytest.approx(base)
    assert result == pytest.approx(0.04)


def test_spillover_high_degree_at_limit_preserves_bound():
    sources = [f"S{i}" for i in range(1_000)]
    news = _spill_news([{
        "issuer": issuer, "observed": 1.0, "expected": -1.0, "sector": "S",
        "as_of": _SPILL_AS_OF, "available_at": _SPILL_AVAILABLE,
        "expected_available_at": _SPILL_EXPECTED_AT,
    } for issuer in sources])
    edges = _spill_edges([{
        "source": source, "target": "T", "weight": 1e12,
        "as_of": _SPILL_AS_OF, "available_at": _SPILL_AVAILABLE, "valid_until": None,
    } for source in sources])
    result = _spill(news, edges)
    assert result.loc["T", "spillover"] == pytest.approx(1.0)
    assert result["spillover"].abs().max() <= 1.0


def test_spillover_failure_does_not_mutate_inputs():
    news, edges = _spill_news(), _spill_edges()
    edges.at[0, "weight"] = -1.0
    news_before, edges_before = news.copy(deep=True), edges.copy(deep=True)
    with pytest.raises(ValueError, match="invalid_edge_weight"):
        _spill(news, edges)
    pd.testing.assert_frame_equal(news, news_before)
    pd.testing.assert_frame_equal(edges, edges_before)


def test_spillover_provenance_is_explicitly_unverified():
    result = _spill()
    assert result.attrs["historical_eligible"] is False
    assert result.attrs["training_provenance_verified"] is False
    assert result.attrs["lag_convention"] == "caller_previous_session_cutoff"
    assert len(result.attrs["news_vintages"]) == len(_spill_news())
    assert len(result.attrs["edge_vintages"]) == 1


def test_spillover_matches_fixed_random_one_hop_scalar_reference():
    rng = Random(731)
    issuers = [f"I{i}" for i in range(12)]
    values = {issuer: (rng.uniform(-1, 1), rng.uniform(-1, 1)) for issuer in issuers}
    news = _spill_news([{
        "issuer": issuer, "observed": observed, "expected": expected,
        "sector": f"S{i % 3}", "as_of": _SPILL_AS_OF,
        "available_at": _SPILL_AVAILABLE, "expected_available_at": _SPILL_EXPECTED_AT,
    } for i, (issuer, (observed, expected)) in enumerate(values.items())])
    pairs, rows = set(), []
    while len(rows) < 30:
        source, target = rng.sample(issuers, 2)
        if (source, target) in pairs:
            continue
        pairs.add((source, target))
        rows.append({"source": source, "target": target, "weight": rng.uniform(0.05, 4.0),
                     "as_of": _SPILL_AS_OF, "available_at": _SPILL_AVAILABLE,
                     "valid_until": None})
    actual = _spill(news, _spill_edges(rows))["spillover"]
    incoming = {issuer: [] for issuer in issuers}
    for row in rows:
        source, target, weight = row["source"], row["target"], row["weight"]
        observed, expected = values[source]
        incoming[target].append((weight, max(-1.0, min(1.0, observed - expected))))
    reference = {}
    for target, links in incoming.items():
        total = sum(weight for weight, _ in links)
        reference[target] = sum(weight * innovation for weight, innovation in links) / max(1.0, total)
    assert actual.to_dict() == pytest.approx(reference, abs=1e-12)
