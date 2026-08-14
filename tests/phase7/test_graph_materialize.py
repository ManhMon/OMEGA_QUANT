"""Phase 7b graph materialization contract tests."""

from datetime import datetime, timezone
import importlib
import numpy as np
import subprocess
import sys

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from omega.quant.graph import materialize as build_features
from omega.quant.graph.materialize import COLUMNS, MaterializationError, SCHEMA, write_atomic
import omega.quant.graph.snapshot as snapshot

materialize_module = importlib.import_module("omega.quant.graph.materialize")


def _write(root, entity, observed_at, rows, symbol=None):
    frame = pd.DataFrame(rows)
    frame["observed_at"] = observed_at
    if symbol:
        frame["_symbol"] = symbol
        path = root / entity / observed_at[:10] / f"{symbol}.parquet"
    else:
        path = root / entity / observed_at[:10] / "snapshot.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def _fixture(tmp_path):
    _write(tmp_path, "industry_sectors", "2026-07-26T03:00:00Z", [{"ticker": "BBB", "industry_name": "Banks"}, {"ticker": "AAA", "industry_name": "Banks"}])
    _write(tmp_path, "officers", "2026-07-26T02:00:00Z", [{"name": "Jane"}, {"name": "John"}], "AAA")
    _write(tmp_path, "officers", "2026-07-26T05:00:00Z", [{"name": "Future"}], "BBB")
    _write(tmp_path, "industry_list_by_industry", "2026-07-26T01:00:00Z", [{"organ_name": "Acme Subs", "symbol": "CCC"}])
    _write(tmp_path, "subsidiaries", "2026-07-26T04:00:00Z", [{"organ_name": "Acme Subs", "ownership_percent": 40}], "AAA")
    _write(tmp_path, "ownership", "2026-07-26T03:30:00Z", [{"owner_type": "AAA"}], "AAA")


def test_materialization_preserves_rows_and_contract(tmp_path):
    _fixture(tmp_path)
    features, counters = build_features("2026-07-26T11:00:00+07:00", tmp_path)
    assert features.columns.tolist() == COLUMNS
    assert features["ticker"].tolist() == ["AAA", "BBB", "CCC"]
    assert features["observed_at"].max() == pd.Timestamp("2026-07-26T04:00:00Z")
    assert features["observed_at"].max() <= pd.Timestamp("2026-07-26T04:00:00Z")
    assert features["peer_mean_ic"].dtype == "float64"
    assert features["peer_mean_ic"].isna().all()
    table = pa.Table.from_pandas(features, schema=SCHEMA, preserve_index=False)
    assert table.schema == SCHEMA
    assert counters.missing_symbol_files == 0


def test_atomic_write_preserves_peer_nan_through_parquet_roundtrip(tmp_path):
    _fixture(tmp_path)
    features, _ = build_features("2026-07-26T11:00:00+07:00", tmp_path)
    target = tmp_path / "graph_features.parquet"

    write_atomic(features, target)

    column = pq.read_table(target, schema=SCHEMA)["peer_mean_ic"]
    assert column.null_count == 0
    assert np.isnan(column.to_numpy()).all()


def test_z_offset_boundary_and_local_signal_date(tmp_path):
    _write(tmp_path, "industry_sectors", "2026-07-26T16:00:00Z", [{"ticker": "AAA", "industry_name": "Banks"}])
    features, _ = build_features("2026-07-26T23:00:00+07:00", tmp_path)
    assert features.iloc[0]["signal_date"] == pd.Timestamp("2026-07-26").date()
    assert features.iloc[0]["observed_at"] == pd.Timestamp("2026-07-26T16:00:00Z")


def test_missing_symbol_and_bad_timestamps_are_dropped(tmp_path):
    _write(tmp_path, "industry_sectors", "not-a-time", [{"ticker": "AAA", "industry_name": "Banks"}])
    _write(tmp_path, "industry_sectors", "2026-07-26T10:00:00", [{"ticker": "BBB", "industry_name": "Banks"}])
    _write(tmp_path, "industry_sectors", "2026-07-26T10:00:00Z", [{"ticker": "CCC", "industry_name": "Banks"}], "CCC")
    features, counters = build_features("2026-07-26T11:00:00Z", tmp_path)
    assert features["ticker"].tolist() == ["CCC"]
    assert counters.malformed_timestamp == 2
    assert counters.missing_symbol_files == 0


@pytest.mark.parametrize("value", ["2026-07-26T11:00:00", "not-a-time", "2026-02-30T11:00:00Z"])
def test_cutoff_requires_valid_explicit_timezone(value):
    with pytest.raises(MaterializationError):
        build_features(value)


def test_atomic_write_failure_keeps_previous_target(tmp_path, monkeypatch):
    target = tmp_path / "graph.parquet"
    original = pd.DataFrame({"ticker": ["OLD"]})
    original.to_parquet(target, index=False)
    features = pd.DataFrame(columns=COLUMNS)
    monkeypatch.setattr(materialize_module.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("blocked")))
    with pytest.raises(MaterializationError, match="atomic-replace failure"):
        write_atomic(features, target)
    assert pq.read_table(target).to_pandas().equals(original)


def test_cli_invalid_cutoff_exits_nonzero(tmp_path):
    result = subprocess.run([sys.executable, "scripts/build_graph_features.py", "--cutoff-at", "2026-07-26T11:00:00", "--snapshot-root", str(tmp_path)], capture_output=True, text=True)
    assert result.returncode != 0
