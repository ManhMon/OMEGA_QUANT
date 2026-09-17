# tests/test_market_release_hook.py
"""Tests for fundamental post-release hook module."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from omega.data.market_release_hook import rebuild_fundamental_matrix, run_post_release_hook


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA"],
            "available_at": [datetime.now(timezone.utc).isoformat()],
            "pe": [10.0],
        }
    )


def test_rebuild_fundamental_matrix_atomic_publication(tmp_path: Path):
    output = tmp_path / "fundamental.parquet"
    frame = _frame()

    result = rebuild_fundamental_matrix(frame, output)

    assert result == output
    assert output.exists()
    loaded = pd.read_parquet(output)
    assert loaded.to_dict("records") == frame.to_dict("records")


def test_rebuild_rejects_missing_schema(tmp_path: Path):
    with pytest.raises(ValueError):
        rebuild_fundamental_matrix(pd.DataFrame({"ticker": ["AAA"]}), tmp_path / "x.parquet")


def test_rebuild_rejects_future_pit_with_immutable_cutoff(tmp_path: Path):
    frame = _frame()
    frame["available_at"] = datetime(2026, 9, 12, 10, tzinfo=timezone.utc).isoformat()
    with pytest.raises(ValueError):
        rebuild_fundamental_matrix(
            frame,
            tmp_path / "x.parquet",
            cutoff_at=datetime(2026, 9, 12, 9, tzinfo=timezone.utc),
        )


def test_rebuild_rejects_nan_and_inf_numeric_values(tmp_path: Path):
    for value in [float("nan"), float("inf"), float("-inf")]:
        frame = _frame()
        frame["pe"] = [value]
        with pytest.raises(ValueError):
            rebuild_fundamental_matrix(frame, tmp_path / "x.parquet")


def test_rebuild_rejects_empty_matrix(tmp_path: Path):
    with pytest.raises(ValueError):
        rebuild_fundamental_matrix(pd.DataFrame(columns=["ticker", "available_at"]), tmp_path / "x.parquet")


def test_rebuild_rejects_duplicate_tickers(tmp_path: Path):
    frame = _frame()
    frame = pd.concat([frame, frame], ignore_index=True)
    with pytest.raises(ValueError):
        rebuild_fundamental_matrix(frame, tmp_path / "x.parquet")


def test_rebuild_rollback_restores_previous_output(tmp_path: Path, monkeypatch):
    output = tmp_path / "matrix.parquet"
    original = _frame()
    rebuild_fundamental_matrix(original, output)

    replacement = _frame()
    replacement["pe"] = [99.0]

    import omega.data.market_release_hook as hook

    def fail_replace(src, dst):
        raise OSError("replacement failure")

    monkeypatch.setattr(hook.os, "replace", fail_replace)
    with pytest.raises(OSError):
        rebuild_fundamental_matrix(replacement, output)

    assert pd.read_parquet(output)["pe"].iloc[0] == 10.0


def test_run_post_release_hook_rebuilds_from_release(tmp_path: Path):
    release = tmp_path / "release.parquet"
    output = tmp_path / "matrix.parquet"
    pd.DataFrame({"ticker": ["AAA"]}).to_parquet(release, index=False)

    def rebuild(path: Path) -> pd.DataFrame:
        assert path == release
        return _frame()

    run_post_release_hook(release, output, rebuild)

    assert pd.read_parquet(output)["pe"].iloc[0] == 10.0
