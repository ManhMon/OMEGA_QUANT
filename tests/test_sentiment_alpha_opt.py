from datetime import datetime, timezone
from math import exp, log1p
from pathlib import Path
import sys

import pandas as pd
import pytest

from omega.quant.signal.sentiment_alpha import SentimentAlphaEngine

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
