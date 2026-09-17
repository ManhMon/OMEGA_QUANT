"""
Unit tests for scripts/run_sentiment_blend.py
==============================================
Tests PIT safety (T-1 lag), signal blending, and edge cases.

Gate: SENTIMENT_ALPHA_WIRING_20260619
"""

import json
import pytest
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, mock_open

import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from run_sentiment_blend import (
    validate_pit_safety,
    blend_signals,
    load_ensemble_signals,
    load_sentiment_scores,
    find_latest_valid_sentiment,
    main,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_ensemble_data():
    return {
        "date": "2026-06-19",
        "generated_at": "2026-06-19T16:30:00",
        "model": "stacking_ensemble",
        "signals": {
            "VNM": 0.05,
            "HPG": 0.12,
            "VIC": -0.04,
            "FPT": 0.08,
        },
    }


@pytest.fixture
def sample_sentiment_data():
    return {
        "date": "2026-06-18",
        "scores": {
            "VNM": 0.5,
            "HPG": -0.8,
            "VIC": 1.0,
        },
        "num_articles": 42,
        "generated_at": "2026-06-18T20:00:00",
    }


@pytest.fixture
def empty_sentiment_data():
    return {
        "date": "2026-06-18",
        "scores": {},
        "num_articles": 0,
        "generated_at": "2026-06-18T20:00:00",
    }


# ---------------------------------------------------------------------------
# PIT Safety Tests
# ---------------------------------------------------------------------------

class TestPITSafety:

    def test_pit_pass_sentiment_before_target(self):
        """Sentiment date (T-1) strictly before target date should pass."""
        validate_pit_safety("2026-06-18", "2026-06-19")

    def test_pit_pass_multiple_days_lag(self):
        """Sentiment from several days before target should pass."""
        validate_pit_safety("2026-06-15", "2026-06-19")

    def test_pit_violation_same_day(self):
        """Sentiment date == target date must raise ValueError."""
        with pytest.raises(ValueError, match="PIT VIOLATION"):
            validate_pit_safety("2026-06-19", "2026-06-19")

    def test_pit_violation_future_sentiment(self):
        """Sentiment date after target date must raise ValueError."""
        with pytest.raises(ValueError, match="PIT VIOLATION"):
            validate_pit_safety("2026-06-20", "2026-06-19")


# ---------------------------------------------------------------------------
# Blend Logic Tests
# ---------------------------------------------------------------------------

class TestBlendSignals:

    def test_blend_applies_sentiment_correctly(
        self, sample_ensemble_data, sample_sentiment_data
    ):
        """Blended signals should equal base + sentiment * scale."""
        scale = 0.1
        result = blend_signals(
            sample_ensemble_data,
            sample_sentiment_data,
            target_date="2026-06-19",
            sentiment_scale=scale,
        )

        signals = result["signals"]
        # VNM: 0.05 + 0.5 * 0.1 = 0.10
        assert abs(signals["VNM"] - 0.10) < 1e-6
        # HPG: 0.12 + (-0.8) * 0.1 = 0.04
        assert abs(signals["HPG"] - 0.04) < 1e-6
        # VIC: -0.04 + 1.0 * 0.1 = 0.06
        assert abs(signals["VIC"] - 0.06) < 1e-6
        # FPT: 0.08 + 0.0 * 0.1 = 0.08 (no sentiment, default=0)
        assert abs(signals["FPT"] - 0.08) < 1e-6

    def test_blend_metadata_recorded(
        self, sample_ensemble_data, sample_sentiment_data
    ):
        """Blended result should include sentiment_blend metadata."""
        result = blend_signals(
            sample_ensemble_data,
            sample_sentiment_data,
            target_date="2026-06-19",
            sentiment_scale=0.05,
        )
        meta = result["sentiment_blend"]
        assert meta["applied"] is True
        assert meta["sentiment_date"] == "2026-06-18"
        assert meta["sentiment_scale"] == 0.05
        assert meta["num_sentiment_tickers"] == 3

    def test_blend_empty_sentiment_returns_original(
        self, sample_ensemble_data, empty_sentiment_data
    ):
        """Empty sentiment scores should return original signals unchanged."""
        result = blend_signals(
            sample_ensemble_data,
            empty_sentiment_data,
            target_date="2026-06-19",
            sentiment_scale=0.1,
        )
        assert result["signals"] == sample_ensemble_data["signals"]

    def test_blend_pit_violation_raises(
        self, sample_ensemble_data, sample_sentiment_data
    ):
        """Same-day sentiment should trigger PIT violation in blend."""
        sample_sentiment_data["date"] = "2026-06-19"
        with pytest.raises(ValueError, match="PIT VIOLATION"):
            blend_signals(
                sample_ensemble_data,
                sample_sentiment_data,
                target_date="2026-06-19",
                sentiment_scale=0.1,
            )

    def test_blend_missing_sentiment_date_raises(
        self, sample_ensemble_data
    ):
        """Sentiment data without 'date' should raise ValueError."""
        bad_sentiment = {"scores": {"VNM": 0.5}, "generated_at": "2026-06-18T20:00:00"}
        with pytest.raises(ValueError, match="missing 'date'"):
            blend_signals(
                sample_ensemble_data,
                bad_sentiment,
                target_date="2026-06-19",
                sentiment_scale=0.1,
            )

    def test_blend_default_scale(
        self, sample_ensemble_data, sample_sentiment_data
    ):
        """Default scale (0.05) should produce smaller adjustments."""
        result = blend_signals(
            sample_ensemble_data,
            sample_sentiment_data,
            target_date="2026-06-19",
            sentiment_scale=0.05,
        )
        # VNM: 0.05 + 0.5 * 0.05 = 0.075
        assert abs(result["signals"]["VNM"] - 0.075) < 1e-6

    def test_blend_normalizes_positive_utc_offset(self, sample_ensemble_data):
        """An offset-aware timestamp before the UTC target remains PIT-valid."""
        result = blend_signals(
            sample_ensemble_data,
            {
                "date": "2026-06-18",
                "generated_at": "2026-06-19T10:00:00+07:00",
                "scores": {"VNM": 1.0},
            },
            target_date="2026-06-19",
            sentiment_scale=0.1,
        )

        assert result["signals"]["VNM"] == pytest.approx(0.15)

    def test_blend_normalizes_negative_utc_offset(self, sample_ensemble_data):
        """An offset-aware timestamp after the UTC target remains PIT-invalid."""
        with pytest.raises(ValueError, match="available_at must not exceed as_of"):
            blend_signals(
                sample_ensemble_data,
                {
                    "date": "2026-06-18",
                    "generated_at": "2026-06-19T05:00:00-07:00",
                    "scores": {"VNM": 1.0},
                },
                target_date="2026-06-19",
                sentiment_scale=0.1,
            )


# ---------------------------------------------------------------------------
# Integration-style Tests (mocked I/O)
# ---------------------------------------------------------------------------

class TestMainIntegration:

    def test_main_no_sentiment_file_returns_zero(
        self, sample_ensemble_data, tmp_path
    ):
        """When sentiment file is missing, main() should return 0 (skip blend)."""
        ensemble_dir = tmp_path / ".ly_state" / "shadow_live"
        ensemble_dir.mkdir(parents=True)
        ensemble_file = ensemble_dir / "2026-06-19_ensemble.json"
        with open(ensemble_file, "w") as fh:
            json.dump(sample_ensemble_data, fh)

        sentiment_file = tmp_path / ".ly_state" / "session" / "sentiment_scores.json"

        with patch("run_sentiment_blend.ENSEMBLE_DIR", ensemble_dir), \
             patch("run_sentiment_blend.SENTIMENT_FILE", sentiment_file), \
             patch("sys.argv", ["run_sentiment_blend.py", "--date", "2026-06-19"]):
            result = main()

        assert result == 0

    def test_main_blend_overwrites_ensemble(
        self, sample_ensemble_data, sample_sentiment_data, tmp_path
    ):
        """Successful blend should overwrite the ensemble file."""
        ensemble_dir = tmp_path / ".ly_state" / "shadow_live"
        ensemble_dir.mkdir(parents=True)
        ensemble_file = ensemble_dir / "2026-06-19_ensemble.json"
        with open(ensemble_file, "w") as fh:
            json.dump(sample_ensemble_data, fh)

        sentiment_dir = tmp_path / ".ly_state" / "session"
        sentiment_dir.mkdir(parents=True)
        sentiment_file = sentiment_dir / "sentiment_scores.json"
        with open(sentiment_file, "w") as fh:
            json.dump(sample_sentiment_data, fh)

        with patch("run_sentiment_blend.ENSEMBLE_DIR", ensemble_dir), \
             patch("run_sentiment_blend.SENTIMENT_FILE", sentiment_file), \
             patch("sys.argv", ["run_sentiment_blend.py", "--date", "2026-06-19"]):
            result = main()

        assert result == 0

        with open(ensemble_file) as fh:
            saved = json.load(fh)
        assert saved["sentiment_blend"]["applied"] is True
        assert abs(saved["signals"]["VNM"] - 0.075) < 1e-6  # 0.05 + 0.5*0.05


# ---------------------------------------------------------------------------
# Oracle Integration Path Tests (T-1 scanning)
# ---------------------------------------------------------------------------

class TestOracleIntegrationPath:
    """
    Tests for the T-1 sentiment scanning logic used by the daily oracle pipeline.

    Scenario: Step 1.7 writes sentiment_scores.json with date=today,
    then Step 3.15 calls blend with --date today.
    The scanner must skip same-day sentiment and find a prior-day archive.
    """

    @pytest.fixture
    def same_day_sentiment(self):
        """Sentiment file written on the same day as target (PIT-invalid)."""
        return {
            "date": "2026-06-19",
            "scores": {"VNM": 0.9, "HPG": 0.8, "VIC": 0.7},
            "num_articles": 50,
            "generated_at": "2026-06-19T09:00:00",
        }

    @pytest.fixture
    def prior_day_sentiment(self):
        """Sentiment from the prior trading day (PIT-valid for target 2026-06-19)."""
        return {
            "date": "2026-06-18",
            "scores": {"VNM": 0.5, "HPG": -0.8, "VIC": 1.0},
            "num_articles": 42,
            "generated_at": "2026-06-18T20:00:00",
        }

    def test_find_latest_valid_uses_main_file_when_prior_day(
        self, prior_day_sentiment, tmp_path
    ):
        """When main sentiment file has date < target, use it directly."""
        session_dir = tmp_path / "session"
        session_dir.mkdir()
        main_file = session_dir / "sentiment_scores.json"
        with open(main_file, "w") as fh:
            json.dump(prior_day_sentiment, fh)

        with patch("run_sentiment_blend.SENTIMENT_FILE", main_file), \
             patch("run_sentiment_blend.SENTIMENT_DIR", session_dir):
            result = find_latest_valid_sentiment("2026-06-19")

        assert result is not None
        assert result["date"] == "2026-06-18"

    def test_find_latest_valid_skips_same_day_main(
        self, same_day_sentiment, tmp_path
    ):
        """When main sentiment file has date == target, must NOT use it."""
        session_dir = tmp_path / "session"
        session_dir.mkdir()
        main_file = session_dir / "sentiment_scores.json"
        with open(main_file, "w") as fh:
            json.dump(same_day_sentiment, fh)

        with patch("run_sentiment_blend.SENTIMENT_FILE", main_file), \
             patch("run_sentiment_blend.SENTIMENT_DIR", session_dir):
            result = find_latest_valid_sentiment("2026-06-19")

        assert result is None

    def test_find_latest_valid_falls_back_to_archive(
        self, same_day_sentiment, prior_day_sentiment, tmp_path
    ):
        """Same-day main file → scanner must find T-1 archive."""
        session_dir = tmp_path / "session"
        session_dir.mkdir()

        main_file = session_dir / "sentiment_scores.json"
        with open(main_file, "w") as fh:
            json.dump(same_day_sentiment, fh)

        archive_file = session_dir / "sentiment_scores_2026-06-18.json"
        with open(archive_file, "w") as fh:
            json.dump(prior_day_sentiment, fh)

        with patch("run_sentiment_blend.SENTIMENT_FILE", main_file), \
             patch("run_sentiment_blend.SENTIMENT_DIR", session_dir):
            result = find_latest_valid_sentiment("2026-06-19")

        assert result is not None
        assert result["date"] == "2026-06-18"
        assert result["scores"]["VNM"] == 0.5

    def test_find_latest_valid_picks_most_recent_archive(
        self, same_day_sentiment, tmp_path
    ):
        """Multiple archives → most recent valid one wins."""
        session_dir = tmp_path / "session"
        session_dir.mkdir()

        main_file = session_dir / "sentiment_scores.json"
        with open(main_file, "w") as fh:
            json.dump(same_day_sentiment, fh)

        old_archive = {
            "date": "2026-06-15",
            "scores": {"VNM": 0.1},
            "generated_at": "2026-06-15T20:00:00",
        }
        recent_archive = {
            "date": "2026-06-18",
            "scores": {"VNM": 0.5, "HPG": -0.3},
            "generated_at": "2026-06-18T20:00:00",
        }
        future_archive = {
            "date": "2026-06-19",
            "scores": {"VNM": 0.9},
            "generated_at": "2026-06-19T09:00:00",
        }

        with open(session_dir / "sentiment_scores_2026-06-15.json", "w") as fh:
            json.dump(old_archive, fh)
        with open(session_dir / "sentiment_scores_2026-06-18.json", "w") as fh:
            json.dump(recent_archive, fh)
        with open(session_dir / "sentiment_scores_2026-06-19.json", "w") as fh:
            json.dump(future_archive, fh)

        with patch("run_sentiment_blend.SENTIMENT_FILE", main_file), \
             patch("run_sentiment_blend.SENTIMENT_DIR", session_dir):
            result = find_latest_valid_sentiment("2026-06-19")

        assert result is not None
        assert result["date"] == "2026-06-18"
        assert result["scores"]["HPG"] == -0.3

    def test_find_latest_valid_no_sentiment_at_all(self, tmp_path):
        """No sentiment files anywhere → returns None."""
        session_dir = tmp_path / "session"
        session_dir.mkdir()
        main_file = session_dir / "sentiment_scores.json"

        with patch("run_sentiment_blend.SENTIMENT_FILE", main_file), \
             patch("run_sentiment_blend.SENTIMENT_DIR", session_dir):
            result = find_latest_valid_sentiment("2026-06-19")

        assert result is None

    def test_find_latest_valid_skips_corrupt_archive(
        self, same_day_sentiment, tmp_path
    ):
        """Corrupt archive is skipped; older valid archive is used."""
        session_dir = tmp_path / "session"
        session_dir.mkdir()

        main_file = session_dir / "sentiment_scores.json"
        with open(main_file, "w") as fh:
            json.dump(same_day_sentiment, fh)

        with open(session_dir / "sentiment_scores_2026-06-18.json", "w") as fh:
            fh.write("NOT VALID JSON {{{")

        valid_old = {
            "date": "2026-06-17",
            "scores": {"VNM": 0.2},
            "generated_at": "2026-06-17T20:00:00",
        }
        with open(session_dir / "sentiment_scores_2026-06-17.json", "w") as fh:
            json.dump(valid_old, fh)

        with patch("run_sentiment_blend.SENTIMENT_FILE", main_file), \
             patch("run_sentiment_blend.SENTIMENT_DIR", session_dir):
            result = find_latest_valid_sentiment("2026-06-19")

        assert result is not None
        assert result["date"] == "2026-06-17"

    def test_main_oracle_path_same_day_sentiment_with_archive(
        self, sample_ensemble_data, same_day_sentiment, prior_day_sentiment, tmp_path
    ):
        """
        Full oracle integration: Step 1.7 writes same-day sentiment,
        Step 3.15 blend must find T-1 archive and apply it.
        """
        ensemble_dir = tmp_path / ".ly_state" / "shadow_live"
        ensemble_dir.mkdir(parents=True)
        ensemble_file = ensemble_dir / "2026-06-19_ensemble.json"
        with open(ensemble_file, "w") as fh:
            json.dump(sample_ensemble_data, fh)

        session_dir = tmp_path / ".ly_state" / "session"
        session_dir.mkdir(parents=True)

        main_file = session_dir / "sentiment_scores.json"
        with open(main_file, "w") as fh:
            json.dump(same_day_sentiment, fh)

        archive_file = session_dir / "sentiment_scores_2026-06-18.json"
        with open(archive_file, "w") as fh:
            json.dump(prior_day_sentiment, fh)

        with patch("run_sentiment_blend.ENSEMBLE_DIR", ensemble_dir), \
             patch("run_sentiment_blend.SENTIMENT_FILE", main_file), \
             patch("run_sentiment_blend.SENTIMENT_DIR", session_dir), \
             patch("sys.argv", ["run_sentiment_blend.py", "--date", "2026-06-19"]):
            result = main()

        assert result == 0

        with open(ensemble_file) as fh:
            saved = json.load(fh)
        assert saved["sentiment_blend"]["applied"] is True
        assert saved["sentiment_blend"]["sentiment_date"] == "2026-06-18"
        assert abs(saved["signals"]["VNM"] - 0.075) < 1e-6  # 0.05 + 0.5*0.05

    def test_main_oracle_path_no_valid_sentiment_skips_gracefully(
        self, sample_ensemble_data, same_day_sentiment, tmp_path
    ):
        """
        Same-day sentiment with no archive → blend skipped, raw ensemble preserved.
        main() returns 0 (not an error).
        """
        ensemble_dir = tmp_path / ".ly_state" / "shadow_live"
        ensemble_dir.mkdir(parents=True)
        ensemble_file = ensemble_dir / "2026-06-19_ensemble.json"
        with open(ensemble_file, "w") as fh:
            json.dump(sample_ensemble_data, fh)

        session_dir = tmp_path / ".ly_state" / "session"
        session_dir.mkdir(parents=True)

        main_file = session_dir / "sentiment_scores.json"
        with open(main_file, "w") as fh:
            json.dump(same_day_sentiment, fh)

        with patch("run_sentiment_blend.ENSEMBLE_DIR", ensemble_dir), \
             patch("run_sentiment_blend.SENTIMENT_FILE", main_file), \
             patch("run_sentiment_blend.SENTIMENT_DIR", session_dir), \
             patch("sys.argv", ["run_sentiment_blend.py", "--date", "2026-06-19"]):
            result = main()

        assert result == 0

        with open(ensemble_file) as fh:
            saved = json.load(fh)
        assert "sentiment_blend" not in saved
        assert saved["signals"] == sample_ensemble_data["signals"]

    def test_misdated_archive_same_day_embedded_date_returns_none(
        self, same_day_sentiment, tmp_path
    ):
        """
        FIX2 regression: archive filename says prior-day (2026-06-18) but embedded
        date is same-day (2026-06-19). Scanner must reject it — embedded date is
        authoritative for PIT validity. Returns None when no valid archive exists.
        """
        session_dir = tmp_path / "session"
        session_dir.mkdir()

        main_file = session_dir / "sentiment_scores.json"
        with open(main_file, "w") as fh:
            json.dump(same_day_sentiment, fh)

        misdated_archive = {
            "date": "2026-06-19",
            "scores": {"VNM": 0.9, "HPG": 0.8},
            "num_articles": 30,
            "generated_at": "2026-06-19T08:00:00",
        }
        archive_file = session_dir / "sentiment_scores_2026-06-18.json"
        with open(archive_file, "w") as fh:
            json.dump(misdated_archive, fh)

        with patch("run_sentiment_blend.SENTIMENT_FILE", main_file), \
             patch("run_sentiment_blend.SENTIMENT_DIR", session_dir):
            result = find_latest_valid_sentiment("2026-06-19")

        assert result is None

    def test_misdated_archive_falls_back_to_older_valid(
        self, same_day_sentiment, tmp_path
    ):
        """
        FIX2 regression: misdated archive is skipped, older valid archive is used.
        Archive _2026-06-18.json has embedded date=2026-06-19 (PIT-invalid),
        Archive _2026-06-17.json has embedded date=2026-06-17 (PIT-valid) → selected.
        """
        session_dir = tmp_path / "session"
        session_dir.mkdir()

        main_file = session_dir / "sentiment_scores.json"
        with open(main_file, "w") as fh:
            json.dump(same_day_sentiment, fh)

        misdated = {
            "date": "2026-06-19",
            "scores": {"VNM": 0.9},
            "generated_at": "2026-06-19T08:00:00",
        }
        valid_older = {
            "date": "2026-06-17",
            "scores": {"VNM": 0.2, "HPG": 0.3},
            "generated_at": "2026-06-17T20:00:00",
        }
        with open(session_dir / "sentiment_scores_2026-06-18.json", "w") as fh:
            json.dump(misdated, fh)
        with open(session_dir / "sentiment_scores_2026-06-17.json", "w") as fh:
            json.dump(valid_older, fh)

        with patch("run_sentiment_blend.SENTIMENT_FILE", main_file), \
             patch("run_sentiment_blend.SENTIMENT_DIR", session_dir):
            result = find_latest_valid_sentiment("2026-06-19")

        assert result is not None
        assert result["date"] == "2026-06-17"
        assert result["scores"]["VNM"] == 0.2

    def test_archive_missing_date_field_skipped_gracefully(
        self, same_day_sentiment, tmp_path
    ):
        """
        FIX2 regression: archive with no 'date' field is skipped without error.
        Older valid archive with a proper date field is used as fallback.
        """
        session_dir = tmp_path / "session"
        session_dir.mkdir()

        main_file = session_dir / "sentiment_scores.json"
        with open(main_file, "w") as fh:
            json.dump(same_day_sentiment, fh)

        no_date_archive = {
            "scores": {"VNM": 0.7, "HPG": 0.6},
            "num_articles": 10,
            "generated_at": "2026-06-18T20:00:00",
        }
        valid_older = {
            "date": "2026-06-16",
            "scores": {"VNM": 0.1},
            "generated_at": "2026-06-16T20:00:00",
        }
        with open(session_dir / "sentiment_scores_2026-06-18.json", "w") as fh:
            json.dump(no_date_archive, fh)
        with open(session_dir / "sentiment_scores_2026-06-16.json", "w") as fh:
            json.dump(valid_older, fh)

        with patch("run_sentiment_blend.SENTIMENT_FILE", main_file), \
             patch("run_sentiment_blend.SENTIMENT_DIR", session_dir):
            result = find_latest_valid_sentiment("2026-06-19")

        assert result is not None
        assert result["date"] == "2026-06-16"

    def test_archive_missing_date_field_returns_none_when_only_option(
        self, same_day_sentiment, tmp_path
    ):
        """
        FIX2 regression: if the only archive has no 'date' field, returns None.
        """
        session_dir = tmp_path / "session"
        session_dir.mkdir()

        main_file = session_dir / "sentiment_scores.json"
        with open(main_file, "w") as fh:
            json.dump(same_day_sentiment, fh)

        no_date_archive = {
            "scores": {"VNM": 0.7},
            "generated_at": "2026-06-18T20:00:00",
        }
        with open(session_dir / "sentiment_scores_2026-06-18.json", "w") as fh:
            json.dump(no_date_archive, fh)

        with patch("run_sentiment_blend.SENTIMENT_FILE", main_file), \
             patch("run_sentiment_blend.SENTIMENT_DIR", session_dir):
            result = find_latest_valid_sentiment("2026-06-19")

        assert result is None
