from datetime import datetime, timezone
from math import exp, log1p
from pathlib import Path
import sys

import pandas as pd
import pytest

from omega.quant.signal.sentiment_alpha import SentimentAlphaEngine, news_count_surprise

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
