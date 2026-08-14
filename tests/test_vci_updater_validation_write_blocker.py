"""
Regression test: combined validation-failure write blocker.
Gate: CANONICAL_VCI_UPDATER_LEGACY_TRACKING_20260613

Proves that atomic_write_with_backup is NEVER called when combined
validation fails and dry_run=False (L3 finding from Role17).

Also verifies that dry_run=True preserves no-write behavior and returns
the invalid summary without writing.
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

# Ensure src/ and repo root are on path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import update_market_data as umd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_df(n: int = 5) -> pd.DataFrame:
    """Create a small valid DataFrame matching canonical schema."""
    dates = pd.date_range("2026-06-01", periods=n, freq="B")
    return pd.DataFrame({
        "ticker": "VCB",
        "date": dates,
        "exchange": "HOSE",
        "open": np.full(n, 50000.0),
        "high": np.full(n, 51000.0),
        "low": np.full(n, 49000.0),
        "close": np.full(n, 50500.0),
        "volume": np.full(n, 100000, dtype=np.int64),
        "as_of": "2026-06-13 00:00:00",
        "available_at": (dates + pd.Timedelta(days=1)).tz_localize(umd.VN_TZ),
        "source": "vnstock_vci",
        "price_scale": "VND",
        "adjusted": "backward_adjusted",
        "rebuild_date": "2026-06-13",
    })


def _make_invalid_df(n: int = 5) -> pd.DataFrame:
    """Create a DataFrame that will FAIL combined validation.

    Injects:
    - Null OHLCV values
    - Non-positive OHLC prices
    - Negative volume
    - Invalid exchange
    """
    dates = pd.date_range("2026-06-01", periods=n, freq="B")
    return pd.DataFrame({
        "ticker": "BAD",
        "date": dates,
        "exchange": "INVALID_EXCHANGE",
        "open": [np.nan, -1.0, 0.0, 50000.0, np.nan],
        "high": [np.nan, 51000.0, 0.0, 51000.0, np.nan],
        "low": [np.nan, 49000.0, 0.0, 49000.0, np.nan],
        "close": [np.nan, 50500.0, 0.0, 50500.0, np.nan],
        "volume": [-100, 100000, 0, 100000, -50],
        "as_of": "2026-06-13 00:00:00",
        "available_at": (dates + pd.Timedelta(days=1)).tz_localize(umd.VN_TZ),
        "source": "vnstock_vci",
        "price_scale": "VND",
        "adjusted": "backward_adjusted",
        "rebuild_date": "2026-06-13",
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCombinedValidationWriteBlocker:
    """Regression: atomic_write_with_backup MUST NOT be called when
    combined validation fails and dry_run=False."""

    @patch("update_market_data.atomic_write_with_backup")
    @patch("update_market_data._create_vnstock_client")
    @patch("update_market_data.read_canonical_max_date")
    @patch("update_market_data.read_canonical")
    @patch("update_market_data.fetch_symbols")
    @patch("update_market_data.load_universe_from_json")
    def test_write_blocked_when_combined_invalid_dry_run_false(
        self,
        mock_load_universe,
        mock_fetch,
        mock_read_canonical,
        mock_read_max_date,
        mock_client,
        mock_atomic_write,
    ):
        """When combined validation fails and dry_run=False,
        atomic_write_with_backup must NOT be called."""
        # Arrange
        mock_load_universe.return_value = {"hsx": ["VCB"], "hnx": []}
        mock_read_max_date.return_value = pd.Timestamp("2026-05-30")

        # Fetch returns invalid data that will poison combined
        invalid_new = _make_invalid_df(5)
        mock_fetch.return_value = (invalid_new, {
            "fetched": 1, "empty": 0, "errors": 0, "rows": 5,
            "total_symbols": 1, "errors_list": [], "empty_tickers": [],
        })

        # Existing canonical is valid
        existing = _make_valid_df(10)
        mock_read_canonical.return_value = existing

        mock_client.return_value = MagicMock()

        canonical_path = REPO_ROOT / "data" / "market_2015_now.parquet"
        output_path = REPO_ROOT / ".ly_state" / "session" / "test_no_write_output.parquet"

        # Act
        result = umd.run_updater(
            canonical_path=canonical_path,
            output_path=output_path,
            start_date="2026-06-01",
            end_date="2026-06-07",
            dry_run=False,
            symbol_filter={"BAD"},
        )

        # Assert: atomic_write_with_backup was NOT called
        mock_atomic_write.assert_not_called()

        # Assert: result status is validation_failed
        assert result["status"] == "validation_failed"
        assert "errors" in result
        assert len(result["errors"]) > 0

    @patch("update_market_data.atomic_write_with_backup")
    @patch("update_market_data._create_vnstock_client")
    @patch("update_market_data.read_canonical_max_date")
    @patch("update_market_data.read_canonical")
    @patch("update_market_data.fetch_symbols")
    @patch("update_market_data.load_universe_from_json")
    def test_dry_run_no_write_even_when_invalid(
        self,
        mock_load_universe,
        mock_fetch,
        mock_read_canonical,
        mock_read_max_date,
        mock_client,
        mock_atomic_write,
    ):
        """When dry_run=True, no write occurs regardless of validation."""
        # Arrange
        mock_load_universe.return_value = {"hsx": ["VCB"], "hnx": []}
        mock_read_max_date.return_value = pd.Timestamp("2026-05-30")

        invalid_new = _make_invalid_df(5)
        mock_fetch.return_value = (invalid_new, {
            "fetched": 1, "empty": 0, "errors": 0, "rows": 5,
            "total_symbols": 1, "errors_list": [], "empty_tickers": [],
        })

        existing = _make_valid_df(10)
        mock_read_canonical.return_value = existing
        mock_client.return_value = MagicMock()

        canonical_path = REPO_ROOT / "data" / "market_2015_now.parquet"
        output_path = REPO_ROOT / ".ly_state" / "session" / "test_dry_run_output.parquet"

        # Act
        result = umd.run_updater(
            canonical_path=canonical_path,
            output_path=output_path,
            start_date="2026-06-01",
            end_date="2026-06-07",
            dry_run=True,
            symbol_filter={"BAD"},
        )

        # Assert: no write
        mock_atomic_write.assert_not_called()

        # Assert: dry_run status returned (summary includes validation info)
        assert result["status"] == "dry_run"
        assert result["dry_run"] is True

    @patch("update_market_data.publish_candidate")
    @patch("update_market_data.validate_release_gates")
    @patch("update_market_data.atomic_write_with_backup")
    @patch("update_market_data._create_vnstock_client")
    @patch("update_market_data.read_canonical_max_date")
    @patch("update_market_data.read_canonical")
    @patch("update_market_data.fetch_symbols")
    @patch("update_market_data.load_universe_from_json")
    def test_write_proceeds_when_combined_valid(
        self,
        mock_load_universe,
        mock_fetch,
        mock_read_canonical,
        mock_read_max_date,
        mock_client,
        mock_atomic_write,
        mock_release_gates,
        mock_publish,
    ):
        """When combined validation passes, atomic_write_with_backup IS called."""
        # Arrange
        mock_load_universe.return_value = {"hsx": ["VCB"], "hnx": []}
        mock_read_max_date.return_value = pd.Timestamp("2026-05-30")

        valid_new = _make_valid_df(5)
        mock_fetch.return_value = (valid_new, {
            "fetched": 1, "empty": 0, "errors": 0, "rows": 5,
            "total_symbols": 1, "errors_list": [], "empty_tickers": [],
        })

        existing = _make_valid_df(10)
        mock_read_canonical.return_value = existing
        mock_client.return_value = MagicMock()
        mock_release_gates.return_value = (True, [], {"rejected_rows": 0, "vci_authority": {"validation_outcome": "passed"}})

        mock_publish.return_value = {
            "candidate_path": "candidate.parquet", "pointer_path": "pointer.json",
            "sha256": "a" * 64, "run_id": "release",
            "vci_authority_receipt_path": "authority.json",
        }

        canonical_path = REPO_ROOT / "data" / "market_2015_now.parquet"
        output_path = REPO_ROOT / ".ly_state" / "session" / "test_valid_output.parquet"

        # Act
        result = umd.run_updater(
            canonical_path=canonical_path,
            output_path=output_path,
            start_date="2026-06-01",
            end_date="2026-06-07",
            dry_run=False,
            symbol_filter={"VCB"},
        )

        # Assert: publication occurs only after combined validation succeeds.
        assert result["status"] == "published"
        mock_publish.assert_called_once()

    @pytest.mark.parametrize(
        ("fetch_stats", "expected_symbols"),
        [
            (
                {
                    "fetched": 0, "empty": 1, "errors": 0, "rows": 0,
                    "total_symbols": 1, "errors_list": [], "empty_tickers": ["EMPTY"],
                },
                ["EMPTY"],
            ),
            (
                {
                    "fetched": 0, "empty": 0, "errors": 1, "rows": 0,
                    "total_symbols": 1,
                    "errors_list": [{"symbol": "ERROR", "error": "history unavailable"}],
                    "empty_tickers": [],
                },
                ["ERROR"],
            ),
        ],
        ids=["all_empty", "all_error"],
    )
    @patch("update_market_data.atomic_write_with_backup")
    @patch("update_market_data._create_vnstock_client")
    @patch("update_market_data.fetch_symbols")
    @patch("update_market_data.load_universe_from_json")
    def test_empty_fetch_with_unresolved_lifecycle_requires_evidence(
        self,
        mock_load_universe,
        mock_fetch,
        mock_client,
        mock_atomic_write,
        fetch_stats,
        expected_symbols,
        tmp_path,
    ):
        """All-empty and all-error fetches cannot publish without lifecycle evidence."""
        mock_load_universe.return_value = {"hsx": expected_symbols, "hnx": []}
        mock_fetch.return_value = (pd.DataFrame(columns=umd.CANONICAL_COLUMNS), fetch_stats)
        mock_client.return_value = MagicMock()
        output_path = tmp_path / "published.parquet"

        result = umd.run_updater(
            canonical_path=tmp_path / "canonical.parquet",
            output_path=output_path,
            start_date="2026-06-01",
            end_date="2026-06-07",
        )

        mock_atomic_write.assert_not_called()
        assert not output_path.exists()
        assert result["status"] == "lifecycle_evidence_required"
        assert result["unresolved_lifecycle_symbols"] == expected_symbols
        assert result["fetch_stats"] == fetch_stats

    @patch("update_market_data.atomic_write_with_backup")
    @patch("update_market_data._create_vnstock_client")
    @patch("update_market_data.fetch_symbols")
    @patch("update_market_data.load_universe_from_json")
    def test_clean_all_empty_fetch_returns_no_new_data(
        self,
        mock_load_universe,
        mock_fetch,
        mock_client,
        mock_atomic_write,
        tmp_path,
    ):
        """An all-empty response without unresolved lifecycle symbols remains a no-op."""
        fetch_stats = {
            "fetched": 0, "empty": 1, "errors": 0, "rows": 0,
            "total_symbols": 1, "errors_list": [], "empty_tickers": [],
        }
        mock_load_universe.return_value = {"hsx": ["CLEAN"], "hnx": []}
        mock_fetch.return_value = (pd.DataFrame(columns=umd.CANONICAL_COLUMNS), fetch_stats)
        mock_client.return_value = MagicMock()
        output_path = tmp_path / "published.parquet"

        result = umd.run_updater(
            canonical_path=tmp_path / "canonical.parquet",
            output_path=output_path,
            start_date="2026-06-01",
            end_date="2026-06-07",
        )

        mock_atomic_write.assert_not_called()
        assert not output_path.exists()
        assert result == {"status": "no_new_data", "fetch_stats": fetch_stats}

    @patch("update_market_data.atomic_write_with_backup")
    @patch("update_market_data._create_vnstock_client")
    @patch("update_market_data.read_canonical")
    @patch("update_market_data.fetch_symbols")
    @patch("update_market_data.load_universe_from_json")
    def test_sparse_terminal_universe_requires_official_evidence(
        self,
        mock_load_universe,
        mock_fetch,
        mock_read_canonical,
        mock_client,
        mock_atomic_write,
        tmp_path,
    ):
        """A stale canonical-equal 575/128 result cannot publish without official evidence."""
        symbols = [f"S{i:03d}" for i in range(575)]
        mock_load_universe.return_value = {"hsx": symbols, "hnx": []}
        sparse_data = pd.concat(
            [_make_valid_df(1).assign(ticker=symbol) for symbol in symbols[:128]],
            ignore_index=True,
        )
        mock_fetch.return_value = (sparse_data, {
            "fetched": 128, "empty": 447, "errors": 0, "rows": 128,
            "total_symbols": 575, "errors_list": [], "empty_tickers": symbols[128:],
        })
        mock_read_canonical.return_value = sparse_data
        mock_client.return_value = MagicMock()
        canonical_path = tmp_path / "market.parquet"
        canonical_path.touch()

        result = umd.run_updater(
            canonical_path=canonical_path,
            start_date="2026-06-01",
            end_date="2026-06-07",
        )

        mock_atomic_write.assert_not_called()
        assert result["status"] == "lifecycle_evidence_required"
        assert len(result["unresolved_lifecycle_symbols"]) == 447


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
