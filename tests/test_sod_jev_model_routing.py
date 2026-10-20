import hashlib
import os
import time
import sys
import types
from datetime import datetime
# Regression coverage: decision binding, atomic publication, pre-audit, throttling, credential safety.
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path

import pytest
from argparse import Namespace

from scripts.jev_model_router import (
    ADVERSARIAL_DIRECTIVE_24D,
    DIMENSION_CATALOG,
    DIMENSION_COUNT,
    L2_LEAD_ALLOWLIST,
    L3_LEAD_ALLOWLIST,
    atomic_publish_decision,
    escape_xml_data,
    evaluate_model_decision,
    load_decision,
    validate_standalone_verdict,
)
import scripts.jev_model_router as jev_router
import scripts.sod_pipeline as sod_pipeline
import scripts.validate_l2_report as validate_l2_report


def test_baseline_routes_by_role_and_publishes_digest(tmp_path):
    path = tmp_path / "decision.json"
    envelope = evaluate_model_decision(role="l2", risk="low", gate="G", session_id="S", task="task", decision_path=path)
    assert envelope["lead_model"] == L2_LEAD_ALLOWLIST[1]
    assert envelope["decision_digest"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert load_decision(
        path,
        envelope["decision_digest"],
        expected_role="l2",
        expected_gate="G",
        expected_session_id="S",
        expected_risk="low",
    )["schema_version"] == "2.0"


def test_dynamic_dimension_catalog_and_focus_validation(tmp_path):
    assert DIMENSION_COUNT == 24 and tuple(item[0] for item in DIMENSION_CATALOG) == tuple(range(1, 25))
    assert "(24) jev secret-safe prompt routing:" in ADVERSARIAL_DIRECTIVE_24D
    assert validate_l2_report._schema_errors(
        {"dimension": 24, "name": "JEV routing"}, validate_l2_report.DIMENSION_SCHEMA, "dimension"
    ) == []
    assert validate_l2_report._schema_errors(
        {"dimension": 25, "name": "invalid"}, validate_l2_report.DIMENSION_SCHEMA, "dimension"
    )
    for invalid in (0, 25, True, "24", [], float("nan"), float("inf")):
        with pytest.raises(ValueError, match="dimension_focus"):
            evaluate_model_decision(
                role="l2", risk="low", response={"dimension_focus": invalid},
                decision_path=tmp_path / "invalid.json",
            )
        assert not (tmp_path / "invalid.json").exists()
    with pytest.raises(ValueError, match="model response must be an object"):
        evaluate_model_decision(role="l2", risk="low", response=[])


def test_decision_round_trips_jev_dimension_focus_and_digest(tmp_path):
    path = tmp_path / "decision.json"
    decision = evaluate_model_decision(
        role="l3", risk="high", gate="G", session_id="S", task="task",
        response={"dimension_focus": 24}, decision_path=path,
    )
    assert decision["dimension_focus"] == 24
    loaded = load_decision(path, decision["decision_digest"], expected_role="l3", expected_gate="G")
    assert loaded["dimension_focus"] == 24
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["dimension_focus"] = 25
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="dimension_focus"):
        load_decision(path, hashlib.sha256(path.read_bytes()).hexdigest())


def _safe_inventory_path(root, value):
    from pathlib import PureWindowsPath

    assert isinstance(value, str) and value and "\\" not in value
    path = Path(value)
    assert not path.is_absolute() and not PureWindowsPath(value).drive
    assert all(part not in ("", ".", "..") for part in value.split("/"))
    candidate = root / path
    assert not candidate.is_symlink() and not any(parent.is_symlink() for parent in candidate.parents)
    resolved = candidate.resolve()
    assert resolved.is_relative_to(root.resolve())
    return resolved


def _inventory_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_inventory_fixture(root, records, expected_paths):
    assert len(records) == len(expected_paths) == len({item["path"] for item in records})
    assert {item["path"] for item in records} == set(expected_paths)
    for item in records:
        path = _safe_inventory_path(root, item["path"])
        assert path.is_file()
        assert type(item["rows"]) is int and item["rows"] >= 0
        assert _inventory_sha(path) == item["sha256"]
        import pyarrow.parquet as pq
        parquet = pq.ParquetFile(path)
        assert item["rows"] == parquet.metadata.num_rows
        assert item["schema_sha256"] == hashlib.sha256(parquet.schema_arrow.serialize().to_pybytes()).hexdigest()
        assert item.get("pit_verified", False) is False
        assert isinstance(item["clock_violations"], dict) and not any(item["clock_violations"].values())
        assert isinstance(item["clock_columns"], dict)
        assert item["kind"] in ("raw", "v10")


def _validate_inventory_clocks(row, cutoff):
    from datetime import timezone

    def parse(value):
        assert isinstance(value, str)
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        assert result.tzinfo is not None and result.utcoffset() is not None
        return result.astimezone(timezone.utc)

    cutoff = parse(cutoff)
    published, ingested, available = (parse(row[key]) for key in ("published_at", "ingested_at", "available_at"))
    assert published <= ingested <= available
    assert available <= cutoff
    return True


def test_inventory_fixture_validation_rejects_mutations(tmp_path):
    import copy

    import pyarrow as pa
    import pyarrow.parquet as pq

    path = tmp_path / "shard.parquet"
    pq.write_table(pa.table({"value": [1]}), path)
    valid = {"path": "shard.parquet", "rows": 1, "sha256": _inventory_sha(path),
             "schema_sha256": hashlib.sha256(pq.ParquetFile(path).schema_arrow.serialize().to_pybytes()).hexdigest(),
             "clock_violations": {}, "clock_columns": {key: key for key in ("published_at", "ingested_at", "available_at")}, "kind": "raw"}
    _validate_inventory_fixture(tmp_path, [valid], ["shard.parquet"])
    for bad_rows in (None, True, -1, 1e13, float("nan"), float("inf"), -float("inf"), "1", []):
        malformed = copy.deepcopy(valid)
        malformed["rows"] = bad_rows
        with pytest.raises(AssertionError):
            _validate_inventory_fixture(tmp_path, [malformed], ["shard.parquet"])
    for mutation in ("hash", "schema", "rows", "missing", "extra", "duplicate", "pit_promotion"):
        records = copy.deepcopy([valid])
        if mutation == "hash": records[0]["sha256"] = "0" * 64
        elif mutation == "schema": records[0]["schema_sha256"] = "0" * 64
        elif mutation == "rows": records[0]["rows"] = True
        elif mutation == "missing": records = []
        elif mutation == "extra": records[0]["path"] = "other.json"
        elif mutation == "duplicate": records.append(copy.deepcopy(records[0]))
        else: records[0]["pit_verified"] = True
        with pytest.raises((AssertionError, KeyError)):
            _validate_inventory_fixture(tmp_path, records, ["shard.parquet"])


def test_inventory_clock_cutoff_is_inclusive_and_ordered():
    assert _validate_inventory_clocks({"published_at": "2026-10-20T04:14:02Z", "ingested_at": "2026-10-20T04:14:02Z", "available_at": "2026-10-20T04:14:02Z"}, "2026-10-20T04:14:03Z")
    with pytest.raises(AssertionError):
        _validate_inventory_clocks({key: "2026-10-20T04:14:04Z" for key in ("published_at", "ingested_at", "available_at")}, "2026-10-20T04:14:03Z")
    assert _validate_inventory_clocks({"published_at": "2026-10-20T04:14:03Z", "ingested_at": "2026-10-20T04:14:03Z",
                                      "available_at": "2026-10-20T04:14:03Z"}, "2026-10-20T04:14:03Z")
    for bad in ({"published_at": "2026-10-20T04:14:04Z", "ingested_at": "2026-10-20T04:14:03Z", "available_at": "2026-10-20T04:14:03Z"},
                {"published_at": "2026-10-20T04:14:03", "ingested_at": "2026-10-20T04:14:03Z", "available_at": "2026-10-20T04:14:03Z"},
                {"published_at": "2026-10-20T04:14:03Z", "ingested_at": "2026-10-20T04:14:03Z", "available_at": "2026-10-20T04:14:02Z"}):
        with pytest.raises(AssertionError):
            _validate_inventory_clocks(bad, "2026-10-20T04:14:03Z")


def test_inventory_path_rejects_windows_and_symlink_paths(tmp_path):
    for value in ("C:/outside/file", "C:\\\\outside\\\\file", "\\\\server\\\\share", "./file", "a//b"):
        with pytest.raises(AssertionError):
            _safe_inventory_path(tmp_path, value)
    outside = tmp_path.parent / "outside-inventory"
    outside.mkdir()
    try:
        (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if sys.platform == "win32" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink creation requires an unavailable privilege")
        raise
    with pytest.raises(AssertionError):
        _safe_inventory_path(tmp_path, "link/file")


def _inspect_inventory_parquet(path, observed, cutoff=None):
    from datetime import date, timezone
    import pyarrow.parquet as pq

    def parse(value):
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return None
        try:
            result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if result.tzinfo is None or result.utcoffset() is None:
                return None
            return result.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None

    assert parse(observed) is not None
    assert cutoff is None or parse(cutoff) is not None
    observed = parse(observed)
    cutoff = parse(cutoff)
    with pq.ParquetFile(path) as parquet:
        schema = parquet.schema_arrow
        names = {name.lower(): name for name in schema.names}

        def column(*aliases):
            return next((names[name] for name in aliases if name in names), None)

        columns = {
            "published_at": column("published_at", "publish_time", "published_time"),
            "ingested_at": column("ingested_at", "ingest_time", "fetched_at"),
            "available_at": column("available_at"),
            "scoring_clock": column("scored_at", "scoring_at", "scoring_time", "score_time"),
        }
        stats = {key: {"missing": 0, "invalid": 0, "future": 0, "min": None, "max": None}
                 for key, name in columns.items() if name}
        violations = {"future_clock_rows": 0, "published_after_ingested": 0,
                      "ingested_after_available": 0, "scored_before_scoring_clock": 0}
        gaps = [key for key, name in columns.items() if not name]
        if "available_at" in gaps:
            violations["missing_required_available_at"] = 1
        rows_read = eligible = 0
        symbol = column("symbol", "ticker")
        symbols = {}
        read_columns = list(dict.fromkeys([name for name in columns.values() if name] + ([symbol] if symbol else [])))
        for batch in parquet.iter_batches(batch_size=8192, columns=read_columns):
            arrays = batch.to_pydict()
            rows_read += batch.num_rows
            for index in range(batch.num_rows):
                times = {}
                for key, name in columns.items():
                    if not name:
                        continue
                    raw = arrays[name][index]
                    value = parse(raw)
                    stat = stats[key]
                    if raw is None:
                        stat["missing"] += 1
                    elif value is None:
                        stat["invalid"] += 1
                    else:
                        text = value.isoformat().replace("+00:00", "Z")
                        stat["min"] = text if stat["min"] is None else min(stat["min"], text)
                        stat["max"] = text if stat["max"] is None else max(stat["max"], text)
                        if value > observed:
                            stat["future"] += 1
                            violations["future_clock_rows"] += 1
                        times[key] = value
                for first, second, label in (
                    ("published_at", "ingested_at", "published_after_ingested"),
                    ("ingested_at", "available_at", "ingested_after_available"),
                    ("scoring_clock", "available_at", "scored_before_scoring_clock"),
                ):
                    if first in times and second in times and times[first] > times[second]:
                        violations[label] += 1
                if symbol:
                    key = str(arrays[symbol][index]) if arrays[symbol][index] is not None else "<missing>"
                    symbols[key] = symbols.get(key, 0) + 1
                if (cutoff is not None and all(key in times for key in ("published_at", "ingested_at", "available_at"))
                        and times["published_at"] <= times["ingested_at"] <= times["available_at"] <= cutoff
                        and (not columns["scoring_clock"] or "scoring_clock" in times
                             and times["scoring_clock"] <= times["available_at"])):
                    eligible += 1
        for key, stat in stats.items():
            violations[key + "_missing_or_invalid"] = stat["missing"] + stat["invalid"]
        if rows_read != parquet.metadata.num_rows:
            raise ValueError("parquet_footer_rows_mismatch")
        return {"rows": rows_read, "schema_sha256": hashlib.sha256(schema.serialize().to_pybytes()).hexdigest(),
                "kind": "v10" if path.name.endswith("-v10.parquet") else "raw", "clock_columns": columns,
                "clock_violations": violations, "clock_details": stats, "clock_gaps": gaps,
                "symbol_row_counts": symbols, "eligible_at_cutoff_rows": eligible}


def _validate_live_news_matrix(root, manifest, matrix):
    assert isinstance(matrix, dict)
    assert matrix["schema_version"] == "news-missing-data-matrix/v1"
    assert matrix["session_id"] == "l4_role15_p0_inventory_20261020"
    assert matrix["gate"] == "GATE_NEWS_SENTIMENT_MACRO_ALPHA_P0_INVENTORY_20261020"
    cutoff = datetime.fromisoformat(matrix["session_cutoff"].replace("Z", "+00:00"))
    observed = datetime.fromisoformat(matrix["observed_at"].replace("Z", "+00:00"))
    assert matrix["session_cutoff"] == "2026-10-20T04:14:03Z"
    assert cutoff.tzinfo is not None and observed.tzinfo is not None and observed >= cutoff

    snapshot = matrix["w0_manifest"]
    snapshot_path = _safe_inventory_path(root, snapshot["path"])
    assert snapshot_path == _safe_inventory_path(root, ".ly_state/session/jev_deep_integration_20260926/W0/input_manifest.json")
    assert _inventory_sha(snapshot_path) == snapshot["sha256"]

    expected = {item["path"]: item for item in manifest["datasets"]}
    assert isinstance(matrix["datasets"], list)
    seen = set()
    for item in matrix["datasets"]:
        assert isinstance(item, dict)
        path = item["path"]
        assert path in expected and path not in seen
        seen.add(path)
        w0 = expected[path]
        assert item["w0_rows"] == w0.get("rows")
        assert item["w0_sha256"] == w0.get("sha256", w0.get("current_sha256"))
        live_path = _safe_inventory_path(root, path)
        assert _inventory_sha(live_path) == item["current_sha256"]
        if path.endswith(".parquet"):
            import pyarrow.parquet as pq
            parquet = pq.ParquetFile(live_path)
            assert parquet.metadata.num_rows == item["current_rows"]
            actual = _inspect_inventory_parquet(live_path, observed)
            for field in ("clock_columns", "clock_violations", "clock_details", "clock_gaps"):
                assert item[field] == actual[field]
        else:
            assert item["clock_columns"] is None and item["clock_violations"] is None
            assert item["current_rows"] is None
    assert seen == set(expected)

    history = matrix["historical_news"]
    history_root = _safe_inventory_path(root, history["root"])
    checkpoint_path = _safe_inventory_path(root, f'{history["root"]}/checkpoint.json')
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert _inventory_sha(checkpoint_path) == history["checkpoint_sha256"]
    assert _inventory_sha(_safe_inventory_path(root, f'{history["root"]}/manifest.json')) == history["manifest_sha256"]
    crawl_manifest = json.loads((history_root / "manifest.json").read_text(encoding="utf-8"))
    assert crawl_manifest["shards"] == checkpoint["shards"]
    shards = history["shards"]
    expected_shards = {history["root"] + "/" + entry["path"]: entry for entry in checkpoint["shards"]}
    assert len(shards) == len(expected_shards) == history["manifest_shard_count"] == 1406
    assert {shard["path"] for shard in shards} == set(expected_shards)
    assert {p.relative_to(root).as_posix() for p in history_root.glob("*.parquet")} == set(expected_shards)
    for shard in shards:
        path = _safe_inventory_path(root, shard["path"])
        actual = _inspect_inventory_parquet(path, observed, cutoff)
        entry = expected_shards[shard["path"]]
        assert shard["sha256"] == entry["sha256"] == _inventory_sha(path)
        for field in ("rows", "schema_sha256"):
            assert shard[field] == entry[field] == actual[field]
        for field in ("kind", "clock_columns", "clock_violations", "clock_details", "clock_gaps", "eligible_at_cutoff_rows"):
            assert shard[field] == actual[field]
        assert not any(shard["clock_violations"].values())
    assert all(shard["path"].startswith(history["root"] + "/") for shard in shards)
    assert history["physical_shard_count"] == len(shards)
    assert history["verified_shards"] == len(shards)
    assert history["raw_rows"] == sum(s["rows"] for s in shards if s["kind"] == "raw")
    assert history["scored_rows"] == sum(s["rows"] for s in shards if s["kind"] == "v10")
    assert history["errors"] == []
    assert history["pit_verified"] is False
    assert history["full_history_verified"] is False
    assert history_root.is_dir()


@pytest.mark.parametrize("artifact", ["absent", "poisoned"])
def test_inventory_validation_never_executes_session_artifacts(tmp_path, artifact):
    snapshot = tmp_path / ".ly_state/session/jev_deep_integration_20260926/W0/input_manifest.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("{}", encoding="utf-8")
    if artifact == "poisoned":
        (tmp_path / ".ly_state/session/l4_role15_p0_inventory_20261020_inventory.py").write_text(
            "raise RuntimeError('session code executed')", encoding="utf-8")
    matrix = {"schema_version": "news-missing-data-matrix/v1", "session_id": "l4_role15_p0_inventory_20261020",
              "gate": "GATE_NEWS_SENTIMENT_MACRO_ALPHA_P0_INVENTORY_20261020",
              "session_cutoff": "2026-10-20T04:14:03Z", "observed_at": "2026-10-20T04:14:03Z",
              "w0_manifest": {"path": snapshot.relative_to(tmp_path).as_posix(), "sha256": _inventory_sha(snapshot)},
              "datasets": []}
    with pytest.raises(KeyError, match="historical_news"):
        _validate_live_news_matrix(tmp_path, {"datasets": []}, matrix)


@pytest.mark.parametrize("value", [None, "", "not-a-time", "2026-10-20T08:30:00", "2026-10-20",
                                  "NaN", "Inf", "-Inf", "0", "-1", "10000000000000"])
def test_inventory_parquet_invalid_clocks_fail_closed(tmp_path, value):
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = tmp_path / "shard.parquet"
    pq.write_table(pa.table({key: pa.array([value], type=pa.string())
                            for key in ("published_at", "ingested_at", "available_at", "scored_at")}), path)
    clock = datetime.fromisoformat("2026-10-20T08:30:00+00:00")
    actual = _inspect_inventory_parquet(path, clock, clock)
    assert actual["eligible_at_cutoff_rows"] == 0
    for key in ("published_at", "ingested_at", "available_at", "scoring_clock"):
        assert actual["clock_violations"][key + "_missing_or_invalid"] == 1
        assert actual["clock_details"][key]["missing" if value is None else "invalid"] == 1


@pytest.mark.parametrize("aliases", [False, True])
@pytest.mark.parametrize("case", ["equal", "future", "published_order", "ingested_order", "scoring_order", "after_cutoff"])
def test_inventory_parquet_clock_boundaries_and_aliases(tmp_path, aliases, case):
    import pyarrow as pa
    import pyarrow.parquet as pq

    names = ("Published_Time", "Fetched_At", "Available_At", "Score_Time") if aliases else (
        "published_at", "ingested_at", "available_at", "scored_at")
    values = ["2026-10-20T15:30:00+07:00"] * 4
    if case in ("future", "after_cutoff"):
        values = ["2026-10-20T08:30:01Z"] * 4
    elif case.endswith("_order"):
        values[{"published_order": 0, "ingested_order": 1, "scoring_order": 3}[case]] = "2026-10-20T08:30:01Z"
    path = tmp_path / "shard-v10.parquet"
    table = pa.table({name: [value] for name, value in zip(names, values)})
    pq.write_table(table, path)
    cutoff = datetime.fromisoformat("2026-10-20T08:30:00+00:00")
    observed = datetime.fromisoformat("2026-10-20T08:30:02+00:00") if case == "after_cutoff" else cutoff
    actual = _inspect_inventory_parquet(path, observed, cutoff)
    assert actual["rows"] == 1 and actual["kind"] == "v10"
    assert actual["schema_sha256"] == hashlib.sha256(table.schema.serialize().to_pybytes()).hexdigest()
    assert actual["clock_columns"] == dict(zip(("published_at", "ingested_at", "available_at", "scoring_clock"), names))
    assert actual["clock_gaps"] == []
    assert actual["eligible_at_cutoff_rows"] == (1 if case == "equal" else 0)
    assert actual["clock_violations"]["future_clock_rows"] == (4 if case == "future" else int(case.endswith("_order")))
    if case.endswith("_order"):
        label = {"published_order": "published_after_ingested", "ingested_order": "ingested_after_available",
                 "scoring_order": "scored_before_scoring_clock"}[case]
        assert actual["clock_violations"][label] == 1


@pytest.mark.parametrize("symbol_column", ["symbol", "Ticker"])
def test_inventory_parquet_optional_scoring_and_symbol_counts(tmp_path, symbol_column):
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = tmp_path / "shard.parquet"
    pq.write_table(pa.table({**{key: ["2026-10-20T15:30:00+07:00"] * 3
                               for key in ("published_at", "ingested_at", "available_at")},
                             symbol_column: ["VNM", None, "VNM"]}), path)
    clock = datetime.fromisoformat("2026-10-20T08:30:00+00:00")
    actual = _inspect_inventory_parquet(path, clock, clock)
    assert actual["eligible_at_cutoff_rows"] == 3
    assert actual["clock_gaps"] == ["scoring_clock"]
    assert not any(actual["clock_violations"].values())
    assert actual["symbol_row_counts"] == {"VNM": 2, "<missing>": 1}


@pytest.mark.parametrize("columns", [[], ["available_at"], ["published_at", "ingested_at"]])
@pytest.mark.parametrize("empty", [False, True])
def test_inventory_parquet_missing_columns_and_empty_rows(tmp_path, columns, empty):
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = tmp_path / "shard.parquet"
    values = [] if empty else ["2026-10-20T08:30:00Z"]
    table = pa.table({name: pa.array(values, type=pa.string()) for name in columns} or {"value": values})
    pq.write_table(table, path)
    clock = datetime.fromisoformat("2026-10-20T08:30:00+00:00")
    actual = _inspect_inventory_parquet(path, clock, clock)
    assert actual["rows"] == len(values)
    assert actual["eligible_at_cutoff_rows"] == 0
    assert actual["clock_violations"].get("missing_required_available_at", 0) == int("available_at" not in columns)
    assert set(actual["clock_gaps"]) == {"published_at", "ingested_at", "available_at", "scoring_clock"} - set(columns)


@pytest.mark.parametrize("clock_type", ["aware", "naive", "date"])
def test_inventory_parquet_typed_clocks_across_batches(tmp_path, clock_type):
    from datetime import date
    import pyarrow as pa
    import pyarrow.parquet as pq

    clock = datetime.fromisoformat("2026-10-20T08:30:00+00:00")
    value, arrow_type = {
        "aware": (clock, pa.timestamp("us", tz="UTC")),
        "naive": (clock.replace(tzinfo=None), pa.timestamp("us")),
        "date": (date(2026, 10, 20), pa.date32()),
    }[clock_type]
    path = tmp_path / "shard.parquet"
    pq.write_table(pa.table({key: pa.array([value] * 8193, type=arrow_type)
                            for key in ("published_at", "ingested_at", "available_at")}), path)
    actual = _inspect_inventory_parquet(path, clock, clock)
    assert actual["rows"] == 8193
    assert actual["eligible_at_cutoff_rows"] == (8193 if clock_type == "aware" else 0)
    assert actual["clock_violations"]["available_at_missing_or_invalid"] == (0 if clock_type == "aware" else 8193)


@pytest.mark.parametrize("bad_clock", [None, "", "bad", "2026-10-20T08:30:00", 0, -1, 1e13,
                                      float("nan"), float("inf"), -float("inf")])
def test_inventory_parquet_rejects_invalid_clock_arguments(tmp_path, bad_clock):
    clock = datetime.fromisoformat("2026-10-20T08:30:00+00:00")
    with pytest.raises(AssertionError):
        _inspect_inventory_parquet(tmp_path / "missing.parquet", bad_clock, clock)
    if bad_clock is not None:
        with pytest.raises(AssertionError):
            _inspect_inventory_parquet(tmp_path / "missing.parquet", clock, bad_clock)


def test_inventory_parquet_observation_clocks_are_isolated(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = tmp_path / "shard.parquet"
    pq.write_table(pa.table({"available_at": ["2026-10-20T08:30:01Z"]}), path)
    clocks = [datetime.fromisoformat(value) for value in ("2026-10-20T08:30:00+00:00", "2026-10-20T08:30:02+00:00")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda clock: _inspect_inventory_parquet(path, clock), clocks))
    assert [result["clock_violations"]["future_clock_rows"] for result in results] == [1, 0]


@pytest.mark.parametrize("failure", ["missing", "directory", "corrupt", "footer", "read"])
def test_inventory_parquet_io_failures_propagate(tmp_path, monkeypatch, failure):
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = tmp_path / "shard.parquet"
    if failure == "directory":
        path.mkdir()
    elif failure == "corrupt":
        path.write_bytes(b"not parquet")
    elif failure in ("footer", "read"):
        pq.write_table(pa.table({"available_at": ["2026-10-20T08:30:00Z"]}), path)
        if failure == "footer":
            monkeypatch.setattr(pq.ParquetFile, "iter_batches", lambda *args, **kwargs: iter(()))
        else:
            def fail_read(*args, **kwargs):
                raise OSError("injected parquet read failure")
            monkeypatch.setattr(pq.ParquetFile, "iter_batches", fail_read)
    clock = datetime.fromisoformat("2026-10-20T08:30:00+00:00")
    with pytest.raises((OSError, ValueError)):
        _inspect_inventory_parquet(path, clock, clock)


@pytest.mark.parametrize("bad_path", ["../escape", "C:\\\\outside\\\\file.json", "\\\\server\\\\share\\\\file.json"])
def test_live_inventory_matrix_rejects_unsafe_paths(tmp_path, bad_path):
    with pytest.raises(AssertionError):
        _safe_inventory_path(tmp_path, bad_path)




def test_w0_inventory_binds_sources_consumers_and_market_release():
    import pyarrow.parquet as pq

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / ".ly_state/session/jev_deep_integration_20260926/W0/input_manifest.json").read_text(encoding="utf-8"))
    matrix = json.loads((root / ".ly_state/session/missing_data_matrix.json").read_text(encoding="utf-8"))
    _validate_live_news_matrix(root, manifest, matrix)
    manifest = json.loads((root / ".ly_state/session/jev_deep_integration_20260926/W0/input_manifest.json").read_text(encoding="utf-8"))
    gates = json.loads((root / ".ly_state/session/phase_gates.json").read_text(encoding="utf-8"))
    assert manifest["repo_commit"] == "74a3b507776b78cf361e8f7f0f4ac0c7efe9e3ae"
    assert manifest["gate_recorded_in_phase_gates"] is (manifest["gate"] in gates)
    if manifest["gate_recorded_in_phase_gates"]:
        receipt = gates[manifest["gate"]]
        assert receipt["final_verdict"] == "[APPROVED]"
        assert receipt["l2_session_id"] == "l2_role6_jev_deep_integration_w0_inventory_20260927"
        assert (root / receipt["audit_report_path"]).is_file()
    assert all(gates[name]["final_verdict"] == "[APPROVED]" for name in manifest["recorded_approved_gates"])
    graph = manifest["graph_evidence"]
    assert graph["sha256"] == "45679feb71de68a995e8581410f17338ba30bdc504fa710dc0a0a0dcb7da72ad"
    assert hashlib.sha256((root / graph["path"]).read_bytes()).hexdigest() == graph["sha256"]
    contract = root / ".ly_state/session/anti_drip_contract_l2_role6_jev_deep_integration_w0_inventory_20260927.json"
    assert hashlib.sha256(contract.read_bytes()).hexdigest() == "44bac89575abe3738712cd5742f710ecbb222163a4785a43b87b71537e33909b"
    assert json.loads(contract.read_text(encoding="utf-8"))["required_findings"] == []
    for entry in (*manifest["sources"], *manifest["consumers"], *manifest["datasets"]):
        path = Path(entry["path"])
        assert not path.is_absolute() and ".." not in path.parts and (root / path).is_file()
    consumers = {entry["path"]: entry["call"] for entry in manifest["consumers"]}
    assert "classify_jev(domain=copilot-router-v1)" in consumers["src/omega/data/smart_llm_router.py"]
    assert "evaluate_model_decision" in consumers["scripts/sod_pipeline.py"]
    release = manifest["datasets"][0]
    assert hashlib.sha256((root / release["path"]).read_bytes()).hexdigest() == release["sha256"]
    assert pq.ParquetFile(root / release["path"]).metadata.num_rows == release["rows"]
    canonical = manifest["datasets"][1]
    assert canonical["current_sha256"] != canonical["release_manifest_canonical_sha256"]
    checkpoint = manifest["datasets"][-1]
    assert json.loads((root / checkpoint["routing_plan"]).read_text(encoding="utf-8"))["llm_mode"] == "off"


@pytest.mark.parametrize("shard", ["manifest.json", "quant_records.json", "routing_plan.json", "evaluation_records.json"])
def test_corrupted_hybrid_checkpoint_shards_fail_closed(tmp_path, shard):
    from scripts.run_hybrid_fundamental import compute_run_contract_hash, parse_cli_args, run_pipeline

    output = tmp_path / "out.parquet"
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    args = parse_cli_args([
        "--decision-cutoff", "2026-06-15T15:00:00+07:00",
        "--knowledge-cutoff", "2026-06-15T09:00:00+07:00",
        "--symbols", "VNM", "--output", str(output),
        "--checkpoint-dir", str(checkpoint), "--llm-mode", "off", "--resume",
    ])
    (checkpoint / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "run_contract_hash": compute_run_contract_hash(vars(args), ["VNM"]),
        "status": "in_progress",
    }), encoding="utf-8")
    (checkpoint / shard).write_text("{truncated", encoding="utf-8")
    code, result, summary = run_pipeline(args)
    assert code == 6 and result is None and summary["status"] == "resume_manifest_corrupted"
    assert not output.exists()


def test_context_bound_decision_rejects_replay(tmp_path):
    path = tmp_path / "decision.json"
    envelope = evaluate_model_decision(role="l3", risk="high", gate="G", session_id="S", task="task", decision_path=path)
    for kwargs in (
        {"expected_role": "l2"},
        {"expected_gate": "OTHER"},
        {"expected_session_id": "OTHER"},
        {"expected_risk": "low"},
    ):
        with pytest.raises(ValueError, match="context mismatch"):
            load_decision(path, envelope["decision_digest"], **kwargs)


def test_schema_drift_fails_closed_after_digest_recomputed(tmp_path):
    path = tmp_path / "decision.json"
    evaluate_model_decision(role="l2", risk="low", gate="G", session_id="S", task="task", decision_path=path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("role")
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(ValueError, match="schema mismatch"):
        load_decision(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_extra_decision_field_fails_closed_even_with_matching_digest(tmp_path):
    path = tmp_path / "decision.json"
    evaluate_model_decision(
        role="l2", risk="low", gate="G", session_id="S", task="task", response={}, decision_path=path
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected_authority"] = "approve"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="schema mismatch"):
        load_decision(path, hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.mark.parametrize("role", ["l2", "l3"])
@pytest.mark.parametrize(("member", "injected"), [
    ("gate", '"gate":"OTHER",'),
    ("gate", '"\\u0067ate":"G",'),
    ("role", '"role":"l3",'),
    ("lead_model", '"lead_model":"unapproved",'),
    ("dimension_focus", '"dimension_focus":24,'),
], ids=["context-shadow", "escaped-alias", "role-shadow", "model-shadow", "optional-duplicate"])
def test_digest_valid_duplicate_decision_members_fail_before_validation(tmp_path, role, member, injected):
    path = tmp_path / "decision.json"
    evaluate_model_decision(
        role=role, risk="high", gate="G", session_id="S", task="task",
        response={"dimension_focus": 24}, decision_path=path,
    )
    raw = path.read_text(encoding="utf-8").replace(f'"{member}":', injected + f'"{member}":', 1)
    path.write_text(raw, encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert json.loads(raw)[member] == json.loads(raw.replace(injected, "", 1))[member]
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_decision(path, digest, expected_role=role, expected_gate="G", expected_session_id="S", expected_risk="high")


def test_digest_valid_nested_duplicate_decision_member_fails_at_parser(tmp_path):
    path = tmp_path / "decision.json"
    evaluate_model_decision(role="l2", risk="low", gate="G", session_id="S", task="task", response={}, decision_path=path)
    raw = path.read_text(encoding="utf-8").replace('"gate":', '"extra":{"key":1,"key":2},"gate":', 1)
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_decision(path, hashlib.sha256(path.read_bytes()).hexdigest(), expected_gate="G")


def test_duplicate_decision_digest_mismatch_precedes_parse_and_key_is_not_logged(tmp_path):
    path = tmp_path / "decision.json"
    evaluate_model_decision(role="l2", risk="high", gate="G", session_id="S", task="task", response={}, decision_path=path)
    secret_key = "https://user:password@example.test/?api_key=private"
    raw = path.read_text(encoding="utf-8").replace('"gate":', f'{json.dumps(secret_key)}:1,{json.dumps(secret_key)}:2,"gate":', 1)
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        load_decision(path, "0" * 64)
    with pytest.raises(ValueError, match="duplicate JSON key") as caught:
        load_decision(path, hashlib.sha256(path.read_bytes()).hexdigest())
    assert "password" not in str(caught.value) and "private" not in str(caught.value)


@pytest.mark.parametrize("dispatcher", ["l2", "l3"])
def test_duplicate_decision_fails_closed_before_dispatch(tmp_path, monkeypatch, capsys, dispatcher):
    from scripts import dispatch_l2, dispatch_l3

    path = tmp_path / "decision.json"
    session = f"l2_role11_duplicate_{datetime.now().strftime('%Y%m%d')}"
    evaluate_model_decision(
        role=dispatcher, risk="high", gate="G", session_id=session, task="task",
        response={}, decision_path=path,
    )
    path.write_text(path.read_text(encoding="utf-8").replace('"gate":', '"gate":"OTHER","gate":', 1), encoding="utf-8")
    argv = ["--model-decision-path", str(path), "--model-decision-digest", hashlib.sha256(path.read_bytes()).hexdigest()]
    if dispatcher == "l2":
        monkeypatch.setattr(dispatch_l2, "resolve_l2_roles", lambda *_: [{"role_id": 11}])
        monkeypatch.setattr(dispatch_l2, "acquire_session_lock", lambda *_: pytest.fail("duplicate decision reached dispatch"))
        monkeypatch.setattr(sys, "argv", ["dispatch_l2.py", "devops-engineer", "G", "duplicate", "task", "scripts/jev_model_router.py", "--risk", "high", *argv])
        assert dispatch_l2.main() == 2
    else:
        monkeypatch.setattr(dispatch_l3, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(sys, "argv", ["dispatch_l3.py", "code-reviewer", "G", session, "devops-engineer", "scripts/jev_model_router.py", "--risk", "high", *argv])
        with pytest.raises(SystemExit) as excinfo:
            dispatch_l3.main()
        assert excinfo.value.code == 2
        assert not (tmp_path / ".ly_state").exists()
    assert "duplicate JSON key" in capsys.readouterr().err


def test_digest_tamper_fails_closed(tmp_path):
    path, digest = atomic_publish_decision({"schema_version": "2.0"}, tmp_path / "decision.json")
    path.write_text('{"schema_version":"2.0","tampered":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        load_decision(path, digest)


def test_nonfinite_and_boolean_inputs_fail_closed(tmp_path):
    with pytest.raises(ValueError):
        evaluate_model_decision(role="l2", risk="low", cycle=True)
    with pytest.raises(ValueError):
        json.loads('{"x":NaN}', parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def test_w0_zero_reference_price_does_not_divide():
    from omega.data.vci_direct import validate_price_bounds

    assert validate_price_bounds(27_000, 0, "HOSE") is True
    assert validate_price_bounds(27_000, -1, "HOSE") is True
    assert validate_price_bounds(float("inf"), 0, "HOSE") is False


@pytest.mark.parametrize("cycle", [float("nan"), float("inf"), "1", [], True])
def test_malformed_cycle_rejected_before_publication(tmp_path, cycle):
    path = tmp_path / "decision.json"
    with pytest.raises(ValueError, match="invalid routing inputs"):
        evaluate_model_decision(role="l2", risk="low", cycle=cycle, response={}, decision_path=path)
    assert not path.exists()


@pytest.mark.parametrize("cycle", [0, -1, 4])
def test_out_of_bounds_cycle_rejected_before_publication(tmp_path, cycle):
    path = tmp_path / "decision.json"
    with pytest.raises(RuntimeError, match="MAX_REMEDIATIONS_EXCEEDED"):
        evaluate_model_decision(role="l2", risk="low", cycle=cycle, response={}, decision_path=path)
    assert not path.exists()


def test_high_finding_escalates_l2_and_l3(tmp_path):
    report = tmp_path / "audit.md"
    report.write_text("[NEEDS_FIX] F-001 HIGH", encoding="utf-8")
    assert evaluate_model_decision(role="l2", risk="high", predecessor_report=report)["lead_model"] == L2_LEAD_ALLOWLIST[0]
    assert evaluate_model_decision(role="l3", risk="high", predecessor_report=report)["lead_model"] == L3_LEAD_ALLOWLIST[0]


@pytest.mark.parametrize("role,choices", [("l2", L2_LEAD_ALLOWLIST), ("l3", L3_LEAD_ALLOWLIST)])
def test_high_finding_prevents_provider_downgrade(tmp_path, role, choices):
    report = tmp_path / "audit.md"
    report.write_text("[NEEDS_FIX] F-001 HIGH", encoding="utf-8")
    envelope = evaluate_model_decision(
        role=role, risk="high", gate="G", session_id="S", task="task", predecessor_report=report,
        response={"lead_model": choices[1]}, decision_path=tmp_path / "decision.json",
    )
    assert envelope["escalated"] is True
    assert envelope["lead_model"] == choices[0]
    assert load_decision(
        tmp_path / "decision.json", envelope["decision_digest"], expected_gate="G", expected_session_id="S"
    )["lead_model"] == choices[0]


def test_l2_and_l3_decisions_are_distinct_and_context_bound(tmp_path):
    l2_path = tmp_path / "l2.json"
    l3_path = tmp_path / "l3.json"
    l2 = evaluate_model_decision(role="l2", risk="high", gate="G", session_id="L2", task="task", decision_path=l2_path)
    l3 = evaluate_model_decision(role="l3", risk="high", gate="G", session_id="L3", task="task", decision_path=l3_path)
    assert l2_path != l3_path
    assert l2["decision_digest"] != l3["decision_digest"]
    assert load_decision(l3_path, l3["decision_digest"], expected_role="l3", expected_gate="G", expected_session_id="L3", expected_risk="high")["role"] == "l3"


def test_pipeline_jev_dispatches_distinct_bound_decision_paths(monkeypatch):
    args = Namespace(
        l2_role="devops-engineer", l3_role="code-reviewer", gate="GATE", slug="slug",
        scope="scripts/sod_pipeline.py", risk="high", model=None, subagent_model=None,
        dry_run=False, graph_evidence=None, model_decision_path="l2.json",
        model_decision_digest="a" * 64, pre_audit_path=None, pre_audit_sha256=None,
    )
    captured = []
    monkeypatch.setattr(sod_pipeline, "capture", lambda command: (captured.append(command) or (0, "---COMMAND---\ncmd")))
    monkeypatch.setattr(sod_pipeline, "parse_dispatch_output", lambda output, required: {key: "value" for key in required})
    sod_pipeline._dispatch_l2(args, "task")
    assert "l2.json" in captured[-1]
    args.model_decision_path = "l3.json"
    args.model_decision_digest = "b" * 64
    sod_pipeline._dispatch_l3(args, "l2_session")
    assert "l3.json" in captured[-1]


def test_sod_pipeline_imports_standalone_verdict_validator():
    assert sod_pipeline.validate_standalone_verdict("[APPROVED]") == "APPROVED"


def test_standalone_verdict_rejects_conflicts_and_prose():
    assert validate_standalone_verdict("[APPROVED]\n") == "APPROVED"
    assert validate_standalone_verdict(" [NEEDS_FIX] ") == "NEEDS_FIX"
    for report in (
        "[APPROVED]\n[NEEDS_FIX]",
        "audit complete\n[APPROVED]",
        "[APPROVED]\naudit complete",
        "APPROVED",
    ):
        with pytest.raises(ValueError, match="standalone verdict"):
            validate_standalone_verdict(report)


def test_cycle_four_and_oversized_response_fail_closed():
    with pytest.raises(RuntimeError, match="MAX_REMEDIATIONS_EXCEEDED"):
        evaluate_model_decision(role="l2", risk="low", cycle=4)
    with pytest.raises(ValueError, match="1MB"):
        evaluate_model_decision(role="l2", risk="low", response={"x": "a" * 1_048_577})


def test_prompt_data_escapes_delimiters_and_rejects_controls():
    assert escape_xml_data("<&\"'") == "&lt;&amp;&quot;&apos;"
    with pytest.raises(ValueError):
        escape_xml_data("bad\x00value")

def test_directory_decision_paths_fail_without_publication(tmp_path):
    directory = tmp_path / "decision.json"
    directory.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        atomic_publish_decision({"schema_version": "2.0"}, directory)
    with pytest.raises(FileNotFoundError, match="decision file not found"):
        load_decision(directory, "0" * 64)
    assert not list(directory.iterdir())

def test_injected_scope_control_character_rejected_before_provider(monkeypatch):
    calls = []
    class Client:
        def __init__(self, **_):
            calls.append("provider")
    sdk = types.ModuleType("typesafe_sdk")
    sdk.Choice, sdk.TypeSafeClient = lambda **_: None, Client
    for name in ("TypeSafeAPIConnectionError", "TypeSafeAPITimeoutError", "TypeSafeInternalServerError"):
        setattr(sdk, name, type(name, (Exception,), {}))
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)
    with pytest.raises(ValueError, match="control characters"):
        evaluate_model_decision(role="l2", risk="high", scope=["-x", "bad\x00scope"])
    assert not calls

def test_jev_retries_429_once_then_returns_judgments(monkeypatch):
    calls = []
    response = types.SimpleNamespace(
        nouls={"genuine_testing": types.SimpleNamespace(noul=0.9), "fabricated_evidence": types.SimpleNamespace(noul=0.1)},
        scores={"test_quality": types.SimpleNamespace(score=0.8, confidence=0.9)},
    )

    class Client:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def system_one(self, **_):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("HTTP 429")
            return response

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Noul, sdk.Score, sdk.TypeSafeClient = lambda **_: None, lambda **_: None, Client
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)
    monkeypatch.setattr(validate_l2_report.time, "sleep", lambda seconds: calls.append(seconds))
    assert validate_l2_report.run_jev_judgments("r", "t", ["a.py"]) == {
        "genuine_testing": {"noul": 0.9}, "fabricated_evidence": {"noul": 0.1},
        "test_quality": {"score": 0.8, "confidence": 0.9},
    }
    assert calls == [1, 1, 1]

def test_jev_auth_exception_redacts_credentials_and_fails_open(monkeypatch, capsys):
    class Client:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def system_one(self, **_):
            error = RuntimeError("Authorization: Bearer secret-jev-token")
            error.status = 401
            raise error

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Noul, sdk.Score, sdk.TypeSafeClient = lambda **_: None, lambda **_: None, Client
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)
    assert validate_l2_report.run_jev_judgments("r", "t", ["a.py"]) is None
    assert "secret-jev-token" not in capsys.readouterr().out

def test_jev_429_retry_exhaustion_is_bounded(monkeypatch, capsys):
    calls = []

    class Client:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def system_one(self, **_):
            calls.append("request")
            raise RuntimeError("HTTP 429")

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Noul, sdk.Score, sdk.TypeSafeClient = lambda **_: None, lambda **_: None, Client
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)
    monkeypatch.setattr(validate_l2_report.time, "sleep", lambda seconds: calls.append(seconds))
    assert validate_l2_report.run_jev_judgments("r", "t", ["a.py"]) is None
    assert calls == ["request", 1, "request"]
    assert "429" in capsys.readouterr().out

def _pre_audit_payload():
    return {
        "schema_version": "1.0", "gate": "G", "session_id": "S", "role": "devops-engineer",
        "scope": ["file.py"], "fingerprints": {"file.py": "a" * 64}, "verifier": {"exit_code": 0},
        "ast_findings": [], "judgments": [], "scores": [],
        "routing": {"routing": "JUDGE", "reason_code": "CLEAN_PASS", "evidence_refs": [], "confidence": 1.0},
        "generated_at": "2026-09-23T00:00:00Z",
    }


def _assert_pre_audit_lock_released(lock):
    if os.name == "nt":
        assert not lock.exists()
        return
    import fcntl

    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _assert_decision_lock_released(lock):
    if os.name == "nt":
        assert not lock.exists()
        return
    import fcntl

    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_pre_audit_sidecar_failure_atomically_restores_both_files(tmp_path, monkeypatch):
    target = tmp_path / "pre_audit_S.json"
    sidecar = target.with_suffix(".sha256")
    target.write_bytes(b"old artifact")
    sidecar.write_bytes(b"old digest")
    replace = os.replace
    calls = 0

    def fail_sidecar_once(src, dst):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("sidecar replace failed")
        replace(src, dst)

    monkeypatch.setattr(validate_l2_report.os, "replace", fail_sidecar_once)
    with pytest.raises(OSError, match="sidecar replace failed"):
        validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
    assert target.read_bytes() == b"old artifact"
    assert sidecar.read_bytes() == b"old digest"
    _assert_pre_audit_lock_released(tmp_path / ".pre_audit_S.lock")


@pytest.mark.parametrize("failure", [
    "target_snapshot", "sidecar_snapshot", "first_temp", "second_temp", "payload_write", "sidecar_write",
    "payload_temp_close", "sidecar_temp_close", "payload_fsync", "sidecar_fsync",
])
def test_pre_audit_early_publication_failures_preserve_existing_artifacts(tmp_path, monkeypatch, failure):
    target = tmp_path / "pre_audit_S.json"
    sidecar = target.with_suffix(".sha256")
    target.write_bytes(b"prior artifact")
    sidecar.write_bytes(b"prior digest")
    real_mkstemp = validate_l2_report.tempfile.mkstemp
    allocations = 0
    real_read_bytes = Path.read_bytes

    def fail_snapshot_read(path):
        if failure == "target_snapshot" and path == target or failure == "sidecar_snapshot" and path == sidecar:
            raise OSError(f"injected {failure}")
        return real_read_bytes(path)

    if failure.endswith("_snapshot"):
        monkeypatch.setattr(Path, "read_bytes", fail_snapshot_read)

    def fail_mkstemp(*args, **kwargs):
        nonlocal allocations
        allocations += 1
        if failure == "first_temp" and allocations == 1 or failure == "second_temp" and allocations == 2:
            raise OSError(f"injected {failure}")
        return real_mkstemp(*args, **kwargs)

    if not failure.endswith("_snapshot"):
        monkeypatch.setattr(validate_l2_report.tempfile, "mkstemp", fail_mkstemp)
    if failure in {"payload_write", "sidecar_write"}:
        real_open = Path.open

        def fail_staged_write(path, *args, **kwargs):
            expected_suffix = ".tmp" if failure == "payload_write" else ".sha256.tmp"
            if path.name.endswith(expected_suffix):
                raise OSError(f"injected {failure}")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", fail_staged_write)
    elif failure.endswith("_temp_close"):
        real_close = os.close
        close_count = 0

        def fail_staged_close(fd):
            nonlocal close_count
            close_count += 1
            real_close(fd)
            expected = 1 if failure == "payload_temp_close" else 2
            if close_count == expected:
                raise OSError(f"injected {failure}")

        monkeypatch.setattr(validate_l2_report.os, "close", fail_staged_close)
    elif failure.endswith("_fsync"):
        real_fsync = os.fsync
        fsync_count = 0

        def fail_staged_fsync(fd):
            nonlocal fsync_count
            fsync_count += 1
            lock_fsync = int(not sys.platform.startswith("win"))
            expected = lock_fsync + (1 if failure == "payload_fsync" else 2)
            if fsync_count == expected:
                raise OSError(f"injected {failure}")
            real_fsync(fd)

        monkeypatch.setattr(validate_l2_report.os, "fsync", fail_staged_fsync)

    with pytest.raises(OSError, match=f"injected {failure}"):
        validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
    assert real_read_bytes(target) == b"prior artifact"
    assert real_read_bytes(sidecar) == b"prior digest"
    assert not list(tmp_path.glob("pre_audit_S.*.tmp"))
    _assert_pre_audit_lock_released(tmp_path / ".pre_audit_S.lock")


class _InjectedPublicationAbort(BaseException):
    pass


@pytest.mark.parametrize("replace_call", [1, 2], ids=["target_replace", "sidecar_replace"])
@pytest.mark.parametrize("failure", [OSError, _InjectedPublicationAbort], ids=["oserror", "baseexception"])
@pytest.mark.parametrize("after_replace", [False, True], ids=["before_replace", "after_replace"])
def test_pre_audit_replace_failures_restore_existing_pair(tmp_path, monkeypatch, replace_call, failure, after_replace):
    target = tmp_path / "pre_audit_S.json"
    sidecar = target.with_suffix(".sha256")
    target.write_bytes(b"prior artifact")
    sidecar.write_bytes(b"prior digest")
    real_replace = os.replace
    replacements = 0

    def fail_replace(source, destination):
        nonlocal replacements
        replacements += 1
        if replacements == replace_call:
            if after_replace:
                real_replace(source, destination)
            raise failure("injected replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(validate_l2_report.os, "replace", fail_replace)
    with pytest.raises(failure, match="injected replace failure"):
        validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
    assert target.read_bytes() == b"prior artifact"
    assert sidecar.read_bytes() == b"prior digest"
    assert not list(tmp_path.glob("pre_audit_S.*.tmp"))


@pytest.mark.parametrize("existing", ["target", "sidecar"])
def test_pre_audit_sidecar_failure_restores_asymmetric_existing_artifact(tmp_path, monkeypatch, existing):
    target = tmp_path / "pre_audit_S.json"
    sidecar = target.with_suffix(".sha256")
    if existing == "target":
        target.write_bytes(b"prior artifact")
    else:
        sidecar.write_bytes(b"prior digest")
    real_replace = os.replace
    replacements = 0

    def fail_sidecar_replace(source, destination):
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("injected sidecar replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(validate_l2_report.os, "replace", fail_sidecar_replace)
    with pytest.raises(OSError, match="injected sidecar replace failure"):
        validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
    if existing == "target":
        assert target.read_bytes() == b"prior artifact"
        assert not sidecar.exists()
    else:
        assert not target.exists()
        assert sidecar.read_bytes() == b"prior digest"
    assert not list(tmp_path.glob("pre_audit_S.*.tmp"))


def test_pre_audit_live_lock_rejects_concurrent_writer(tmp_path):
    lock = tmp_path / ".pre_audit_S.lock"
    lock.write_text(str(os.getpid()), encoding="ascii")
    with pytest.raises(FileExistsError):
        validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")

def test_pre_audit_recovers_dead_owner_lock(tmp_path):
    lock = tmp_path / ".pre_audit_S.lock"
    lock.write_text("2147483647", encoding="ascii")
    artifact, sidecar = validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
    assert artifact.is_file() and sidecar.is_file()
    _assert_pre_audit_lock_released(lock)


@pytest.mark.skipif(os.name != "nt", reason="Windows OpenProcess error injection")
@pytest.mark.parametrize("error", [5, 0, 6, 87])
def test_windows_pre_audit_lock_openprocess_error(tmp_path, monkeypatch, error):
    import ctypes

    lock = tmp_path / ".pre_audit_S.lock"
    lock.write_text("2147483647", encoding="ascii")
    artifact = tmp_path / "pre_audit_S.json"
    artifact.write_bytes(b"original")
    monkeypatch.setattr(ctypes.windll.kernel32, "OpenProcess", lambda *_: 0)
    monkeypatch.setattr(ctypes, "GetLastError", lambda: error)

    if error == 87:
        validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
        assert not lock.exists()
    else:
        with pytest.raises(FileExistsError):
            validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
        assert lock.read_bytes() == b"2147483647"
        assert artifact.read_bytes() == b"original"


@pytest.mark.skipif(os.name == "nt", reason="POSIX flock locking")
def test_posix_pre_audit_stale_lock_successor_cannot_be_reclaimed(tmp_path):
    import fcntl

    lock = tmp_path / ".pre_audit_S.lock"
    lock.write_text("2147483647", encoding="ascii")
    owner_fd = os.open(lock, os.O_RDWR)
    fcntl.flock(owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    owner_identity = os.fstat(owner_fd)
    owner_bytes = lock.read_bytes()

    with pytest.raises(FileExistsError, match="lock busy"):
        validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")

    current = lock.stat()
    assert (current.st_dev, current.st_ino) == (owner_identity.st_dev, owner_identity.st_ino)
    assert lock.read_bytes() == owner_bytes
    assert not (tmp_path / "pre_audit_S.json").exists()
    fcntl.flock(owner_fd, fcntl.LOCK_UN)
    validate_l2_report.os.close(owner_fd)


@pytest.mark.skipif(os.name == "nt", reason="POSIX flock locking")
@pytest.mark.parametrize("failure", ["write", "fsync"])
def test_posix_pre_audit_lock_setup_failure_closes_and_releases_lock(tmp_path, monkeypatch, failure):
    lock = tmp_path / ".pre_audit_S.lock"
    real_open, real_write, real_fsync = os.open, os.write, os.fsync
    opened = []

    def record_open(path, flags, mode=0o777):
        fd = real_open(path, flags, mode)
        if Path(path) == lock:
            opened.append(fd)
        return fd

    monkeypatch.setattr(os, "open", record_open)
    if failure == "write":
        def fail_write(fd, data):
            if fd in opened:
                real_write(fd, data)
                raise OSError("injected pre-audit lock write failure")
            return real_write(fd, data)

        monkeypatch.setattr(os, "write", fail_write)
    else:
        def fail_fsync(fd):
            if fd in opened:
                raise OSError("injected pre-audit lock fsync failure")
            return real_fsync(fd)

        monkeypatch.setattr(os, "fsync", fail_fsync)

    with pytest.raises(OSError, match=f"injected pre-audit lock {failure} failure"):
        validate_l2_report._acquire_pre_audit_lock(lock)
    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])

    monkeypatch.setattr(os, "open", real_open)
    monkeypatch.setattr(os, "write", real_write)
    monkeypatch.setattr(os, "fsync", real_fsync)
    artifact, sidecar = validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
    assert artifact.is_file() and sidecar.is_file()


def test_pre_audit_does_not_remove_replaced_lock(tmp_path, monkeypatch):
    lock = tmp_path / ".pre_audit_S.lock"
    original_close = os.close

    def replace_lock_after_close(fd):
        original_close(fd)
        if lock.exists():
            lock.write_text("another-owner", encoding="ascii")

    monkeypatch.setattr(os, "close", replace_lock_after_close)
    validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
    assert lock.read_text(encoding="ascii") == "another-owner"

def test_decision_publication_recovers_dead_owner_lock(tmp_path):
    lock = tmp_path / ".jev_model_decision.lock"
    lock.write_text("2147483647", encoding="ascii")
    path, digest = atomic_publish_decision({"schema_version": "2.0"}, tmp_path / "decision.json")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    _assert_decision_lock_released(lock)


@pytest.mark.skipif(os.name == "nt", reason="POSIX flock locking")
def test_posix_stale_lock_successor_cannot_be_unlinked_by_contender(tmp_path):
    import fcntl

    lock = tmp_path / ".jev_model_decision.lock"
    lock.write_text("2147483647", encoding="ascii")
    owner_fd = os.open(lock, os.O_RDWR)
    fcntl.flock(owner_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    owner_identity = os.fstat(owner_fd)
    owner_bytes = lock.read_bytes()

    with pytest.raises(FileExistsError, match="lock busy"):
        atomic_publish_decision({"schema_version": "2.0"}, tmp_path / "decision.json")

    current = lock.stat()
    assert (current.st_dev, current.st_ino) == (owner_identity.st_dev, owner_identity.st_ino)
    assert lock.read_bytes() == owner_bytes == b"2147483647"
    assert not (tmp_path / "decision.json").exists()
    fcntl.flock(owner_fd, fcntl.LOCK_UN)
    os.close(owner_fd)


def test_decision_publication_preserves_live_aged_lock(tmp_path):
    target = tmp_path / "decision.json"
    target.write_bytes(b"original")
    lock = tmp_path / ".jev_model_decision.lock"
    lock.write_text(str(os.getpid()), encoding="ascii")
    old = time.time() - 600
    os.utime(lock, (old, old))
    with pytest.raises(FileExistsError):
        atomic_publish_decision({"schema_version": "2.0"}, target)
    assert target.read_bytes() == b"original"
    assert lock.read_text(encoding="ascii") == str(os.getpid())


@pytest.mark.skipif(os.name != "nt", reason="Windows stale-lock reclaim race")
@pytest.mark.parametrize("kind", ["decision", "pre_audit"])
def test_windows_two_reclaimers_preserve_successor(tmp_path, monkeypatch, kind):
    import ctypes
    import threading

    lock = tmp_path / (".jev_model_decision.lock" if kind == "decision" else ".pre_audit_S.lock")
    lock.write_text("2147483647", encoding="ascii")
    first_reclaimed = threading.Event()
    release_first = threading.Event()
    owner_created = threading.Event()
    release_owner = threading.Event()
    results = []
    monkeypatch.setattr(ctypes.windll.kernel32, "OpenProcess", lambda *_: 0)
    monkeypatch.setattr(ctypes, "GetLastError", lambda: 87)
    real_write = os.write

    real_open = os.open

    def pause_owner_open(path, flags, mode=0o777):
        fd = real_open(path, flags, mode)
        if threading.current_thread().name == "first" and path == lock and flags & os.O_EXCL:
            current, opened = lock.stat(), os.fstat(fd)
            if (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino):
                owner_created.set()
                assert release_owner.wait(5)
        return fd

    monkeypatch.setattr(os, "open", pause_owner_open)

    def publish():
        try:
            if kind == "decision":
                atomic_publish_decision({"schema_version": "2.0"}, tmp_path / "decision.json")
            else:
                validate_l2_report.write_atomic_pre_audit(_pre_audit_payload(), tmp_path, "S")
            results.append("ok")
        except FileExistsError:
            results.append("busy")

    real_unlink = Path.unlink
    def observe_reclaim(path, *args, **kwargs):
        result = real_unlink(path, *args, **kwargs)
        if path == lock and threading.current_thread().name == "first":
            first_reclaimed.set()
            assert release_first.wait(5)
        return result

    monkeypatch.setattr(Path, "unlink", observe_reclaim)
    first = threading.Thread(target=publish, name="first")
    second = threading.Thread(target=publish, name="second")
    first.start()
    try:
        assert first_reclaimed.wait(5)
        second.start()
        release_first.set()
        assert owner_created.wait(5)
        second.join(5)
    finally:
        release_first.set()
        release_owner.set()
        first.join(5)
        if second.ident is not None:
            second.join(5)
    assert not first.is_alive() and not second.is_alive()
    assert sorted(results) == ["busy", "ok"]
    assert not lock.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows OpenProcess error injection")
@pytest.mark.parametrize("error", [5, 0, 6, 87])
def test_windows_decision_lock_openprocess_error(tmp_path, monkeypatch, error):
    import ctypes

    target = tmp_path / "decision.json"
    target.write_bytes(b"original")
    lock = tmp_path / ".jev_model_decision.lock"
    lock.write_text("2147483647", encoding="ascii")
    monkeypatch.setattr(ctypes.windll.kernel32, "OpenProcess", lambda *_: 0)
    monkeypatch.setattr(ctypes, "GetLastError", lambda: error)

    if error == 87:
        path, _ = atomic_publish_decision({"schema_version": "2.0"}, target)
        assert path == target
        assert not lock.exists()
    else:
        with pytest.raises(FileExistsError):
            atomic_publish_decision({"schema_version": "2.0"}, target)
        assert target.read_bytes() == b"original"
        assert lock.read_bytes() == b"2147483647"


@pytest.mark.parametrize("failure", ["write", "lock_fsync", "payload_fsync"])
def test_decision_publication_lock_setup_failures_close_fd_and_cleanup(tmp_path, monkeypatch, failure):
    target = tmp_path / "decision.json"
    target.write_bytes(b"previous decision")
    lock = tmp_path / ".jev_model_decision.lock"
    real_open, real_write, real_fsync = os.open, os.write, os.fsync
    opened = []

    def record_open(path, flags, mode=0o777):
        fd = real_open(path, flags, mode)
        if Path(path) == lock:
            opened.append(fd)
        return fd

    monkeypatch.setattr(os, "open", record_open)
    if failure == "write":
        def fail_write(fd, data):
            if fd in opened:
                real_write(fd, data)
                raise OSError("injected lock write failure")
            return real_write(fd, data)
        monkeypatch.setattr(os, "write", fail_write)
        message = "injected lock write failure"
    else:
        fsync_calls = 0
        def fail_fsync(fd):
            nonlocal fsync_calls
            fsync_calls += 1
            if failure == "lock_fsync" and fd in opened:
                raise OSError("injected lock fsync failure")
            if failure == "payload_fsync" and fsync_calls == 2:
                raise OSError("injected payload fsync failure")
            return real_fsync(fd)
        monkeypatch.setattr(os, "fsync", fail_fsync)
        message = f"injected {failure.replace('_', ' ')} failure"

    with pytest.raises(OSError, match=message):
        atomic_publish_decision({"schema_version": "2.0"}, target)

    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])
    assert target.read_bytes() == b"previous decision"
    _assert_decision_lock_released(lock)
    assert not list(tmp_path.glob(".decision.json.*.tmp"))
    monkeypatch.setattr(os, "open", real_open)
    monkeypatch.setattr(os, "write", real_write)
    monkeypatch.setattr(os, "fsync", real_fsync)
    published, digest = atomic_publish_decision({"schema_version": "2.0"}, target)
    assert hashlib.sha256(published.read_bytes()).hexdigest() == digest
    _assert_decision_lock_released(lock)


def test_decision_publication_close_failure_still_cleans_lock_and_temp(tmp_path, monkeypatch):
    target = tmp_path / "decision.json"
    lock = tmp_path / ".jev_model_decision.lock"
    real_open, real_close = os.open, os.close
    lock_fds = set()

    def record_open(path, flags, mode=0o777):
        fd = real_open(path, flags, mode)
        if Path(path) == lock:
            lock_fds.add(fd)
        return fd

    def fail_lock_close(fd):
        real_close(fd)
        if fd in lock_fds:
            raise OSError("injected lock close failure")

    monkeypatch.setattr(os, "open", record_open)
    monkeypatch.setattr(os, "close", fail_lock_close)
    with pytest.raises(OSError, match="injected lock close failure"):
        atomic_publish_decision({"schema_version": "2.0"}, target)

    assert target.is_file()
    _assert_decision_lock_released(lock)
    assert not list(tmp_path.glob(".decision.json.*.tmp"))
    for fd in lock_fds:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_decision_publication_preserves_replaced_lock(tmp_path, monkeypatch):
    lock = tmp_path / ".jev_model_decision.lock"
    real_close = os.close

    def replace_after_close(fd):
        real_close(fd)
        if lock.exists():
            lock.write_text("replacement owner", encoding="ascii")

    monkeypatch.setattr(os, "close", replace_after_close)
    atomic_publish_decision({"schema_version": "2.0"}, tmp_path / "decision.json")
    assert lock.read_text(encoding="ascii") == "replacement owner"


@pytest.mark.skipif(os.name == "nt", reason="directory fsync is POSIX-only")
@pytest.mark.parametrize("previous", [None, b"prior decision"], ids=["absent", "existing"])
def test_decision_publication_directory_fsync_failure_closes_descriptors_and_cleans_lock(tmp_path, monkeypatch, previous):
    target = tmp_path / "decision.json"
    if previous is not None:
        target.write_bytes(previous)
    lock = tmp_path / ".jev_model_decision.lock"
    real_open, real_fsync = os.open, os.fsync
    descriptors = []
    fsync_calls = 0

    def record_open(path, flags, mode=0o777):
        fd = real_open(path, flags, mode)
        descriptors.append(fd)
        return fd

    def fail_directory_fsync(fd):
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 3:
            raise OSError("injected directory fsync failure")
        return real_fsync(fd)

    monkeypatch.setattr(os, "open", record_open)
    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    with pytest.raises(OSError, match="injected directory fsync failure"):
        atomic_publish_decision({"schema_version": "2.0"}, target)

    assert (target.read_bytes() == previous if previous is not None else not target.exists())
    _assert_decision_lock_released(lock)
    assert not list(tmp_path.glob(".decision.json.*.tmp"))
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.parametrize("previous", [None, b"prior decision"], ids=["absent", "existing"])
def test_decision_post_replace_error_restores_previous_state(tmp_path, monkeypatch, previous):
    target = tmp_path / "decision.json"
    if previous is not None:
        target.write_bytes(previous)
    real_replace = os.replace
    calls = 0

    def fail_after_replace(src, dst):
        nonlocal calls
        calls += 1
        real_replace(src, dst)
        if calls == 1:
            raise OSError("replace completed before error")

    monkeypatch.setattr(jev_router.os, "replace", fail_after_replace)
    with pytest.raises(OSError, match="replace completed before error"):
        atomic_publish_decision({"schema_version": "2.0"}, target)
    assert (target.read_bytes() == previous if previous is not None else not target.exists())
    assert not list(tmp_path.glob(".decision.json.*.tmp"))
    _assert_decision_lock_released(tmp_path / ".jev_model_decision.lock")


@pytest.mark.parametrize("previous", [None, b"prior decision"], ids=["absent", "existing"])
def test_decision_durability_error_restores_previous_state(tmp_path, monkeypatch, previous):
    target = tmp_path / "decision.json"
    if previous is not None:
        target.write_bytes(previous)
    real_sync = jev_router._fsync_decision_directory
    calls = 0

    def fail_first_sync(directory):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected durability failure")
        real_sync(directory)

    monkeypatch.setattr(jev_router, "_fsync_decision_directory", fail_first_sync)
    with pytest.raises(OSError, match="injected durability failure"):
        atomic_publish_decision({"schema_version": "2.0"}, target)
    assert (target.read_bytes() == previous if previous is not None else not target.exists())
    assert calls == 2
    assert not list(tmp_path.glob(".decision.json.*.tmp"))
    _assert_decision_lock_released(tmp_path / ".jev_model_decision.lock")


def test_decision_predecessor_swap_during_snapshot_fails_before_publication(tmp_path, monkeypatch):
    target = tmp_path / "decision.json"
    target.write_bytes(b"original")
    real_read = jev_router._read_bounded_decision

    def swap_after_read(path):
        raw = real_read(path)
        if path == target:
            replacement = tmp_path / "replacement"
            replacement.write_bytes(b"concurrent decision")
            os.replace(replacement, target)
        return raw

    monkeypatch.setattr(jev_router, "_read_bounded_decision", swap_after_read)
    with pytest.raises(RuntimeError, match="predecessor changed during snapshot"):
        atomic_publish_decision({"schema_version": "2.0"}, target)
    assert target.read_bytes() == b"concurrent decision"
    assert not list(tmp_path.glob(".decision.json.*.tmp"))
    _assert_decision_lock_released(tmp_path / ".jev_model_decision.lock")


@pytest.mark.skipif(os.name == "nt", reason="directory fsync is POSIX-only")
def test_decision_rollback_failure_is_reported_and_lock_released(tmp_path, monkeypatch):
    target = tmp_path / "decision.json"
    target.write_bytes(b"prior decision")
    real_fsync = os.fsync
    calls = 0

    def fail_directory_and_rollback(fd):
        nonlocal calls
        calls += 1
        if calls in (3, 4):
            raise OSError("injected fsync failure")
        real_fsync(fd)

    monkeypatch.setattr(jev_router.os, "fsync", fail_directory_and_rollback)
    with pytest.raises(RuntimeError, match="publication and rollback failed"):
        atomic_publish_decision({"schema_version": "2.0"}, target)
    assert not list(tmp_path.glob(".decision.json.*.tmp"))
    _assert_decision_lock_released(tmp_path / ".jev_model_decision.lock")


@pytest.mark.parametrize("field,value", [
    ("lead_model", "unapproved"), ("subagent_model", "unapproved"),
    ("lead_model", ""), ("lead_model", None), ("lead_model", []),
    ("subagent_model", ""), ("subagent_model", None), ("subagent_model", 0),
    ("execution_timeout", True), ("execution_timeout", "180"),
    ("execution_timeout", 999),
])
@pytest.mark.parametrize("role", ["l2", "l3"])
def test_decision_allowlist_rejects_response_and_digest_rebound_file(tmp_path, role, field, value):
    path = tmp_path / "decision.json"
    valid = evaluate_model_decision(
        role=role, risk="low", gate="G", session_id="S", task="task", response={}, decision_path=path
    )
    with pytest.raises(ValueError, match="allowlist"):
        evaluate_model_decision(
            role=role, risk="low", gate="G", session_id="S", task="task",
            response={field: value}, decision_path=path,
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="allowlist"):
        load_decision(path, hashlib.sha256(path.read_bytes()).hexdigest())
    assert valid["decision_digest"] != hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("response", [
    {"fallback_used": "false"}, {"fallback_used": 0}, {"fallback_used": None},
    {"fallback_used": True}, {"fallback_used": True, "fallback_reason": []},
    {"fallback_reason": "reason"}, {"fallback_used": False, "fallback_reason": "reason"},
    {"fallback_used": False, "fallback_reason": None},
])
def test_malformed_fallback_rejected_before_decision_publication(tmp_path, response):
    path = tmp_path / "decision.json"
    with pytest.raises(ValueError, match="fallback fields"):
        evaluate_model_decision(role="l2", risk="low", response=response, decision_path=path)
    assert not path.exists()


@pytest.mark.parametrize("risk,cycle", [("high", 1), ("low", 2)])
def test_explicit_fallback_only_allowed_on_low_risk_initial_cycle(tmp_path, risk, cycle):
    path = tmp_path / "decision.json"
    with pytest.raises(ValueError, match="fallback fields"):
        evaluate_model_decision(role="l2", risk=risk, cycle=cycle,
                                response={"fallback_used": True, "fallback_reason": "timeout"}, decision_path=path)
    assert not path.exists()


def test_load_decision_uses_descriptor_bound_bounded_read(tmp_path, monkeypatch):
    from scripts.jev_model_router import MAX_RESPONSE_BYTES

    path = tmp_path / "decision.json"
    path.write_bytes(b"{}")
    real_fdopen = os.fdopen
    reads = []

    def observe_fdopen(fd, mode, **kwargs):
        handle = real_fdopen(fd, mode, **kwargs)

        class Reader:
            def __enter__(self):
                handle.__enter__()
                return self
            def __exit__(self, *args):
                return handle.__exit__(*args)
            def fileno(self):
                return handle.fileno()
            def read(self, amount):
                reads.append(amount)
                return b"x" * amount

        return Reader()

    monkeypatch.setattr(jev_router.os, "fdopen", observe_fdopen)
    with pytest.raises(ValueError, match="decision payload exceeds size bound"):
        load_decision(path, "0" * 64)
    assert reads == [MAX_RESPONSE_BYTES + 1]


def test_load_decision_rejects_file_replaced_between_check_and_open(tmp_path, monkeypatch):
    target = tmp_path / "decision.json"
    target.write_bytes(b"{}")
    real_open = os.open

    def swap_for_directory(path, flags, *args):
        if Path(path) == target:
            target.unlink()
            target.mkdir()
        return real_open(path, flags, *args)

    monkeypatch.setattr(jev_router.os, "open", swap_for_directory)
    with pytest.raises((FileNotFoundError, OSError)):
        load_decision(target, "0" * 64)


@pytest.mark.parametrize(("updates", "case"), [
    ({"cycle": 0}, "cycle-zero"), ({"cycle": -1}, "cycle-negative"),
    ({"cycle": 4}, "cycle-too-high"), ({"cycle": True}, "cycle-boolean"),
    ({"gate": ""}, "empty-gate"), ({"gate": "   "}, "blank-gate"),
    ({"gate": None}, "non-string-gate"), ({"session_id": ""}, "empty-session"),
    ({"session_id": "  "}, "blank-session"), ({"session_id": []}, "non-string-session"),
    ({"task": ""}, "empty-task"), ({"task": "  "}, "blank-task"),
    ({"task": None}, "non-string-task"),
    ({"fallback_used": "true", "fallback_reason": "reason"}, "fallback-used-not-bool"),
    ({"fallback_used": True}, "fallback-reason-missing"),
    ({"fallback_used": True, "fallback_reason": []}, "fallback-reason-not-string"),
    ({"fallback_used": True, "fallback_reason": " "}, "fallback-reason-empty"),
    ({"fallback_reason": "reason"}, "fallback-used-missing"),
    ({"fallback_used": False, "fallback_reason": "reason"}, "fallback-reason-without-fallback"),
    ({"fallback_used": False, "fallback_reason": None}, "fallback-false-without-reason"),
    ({"predecessor_findings": "F-001"}, "findings-not-list"),
    ({"predecessor_findings": [1]}, "finding-not-string"),
    ({"predecessor_findings": [""]}, "finding-empty"),
    ({"predecessor_findings": ["not-a-finding"]}, "finding-malformed"),
    ({"predecessor_findings": ["F-001", "F-001"]}, "finding-duplicate"),
], ids=[
    "cycle-zero", "cycle-negative", "cycle-too-high", "cycle-boolean", "empty-gate", "blank-gate",
    "non-string-gate", "empty-session", "blank-session", "non-string-session", "empty-task", "blank-task",
    "non-string-task", "fallback-used-not-bool", "fallback-reason-missing", "fallback-reason-not-string",
    "fallback-reason-empty", "fallback-used-missing", "fallback-reason-without-fallback",
    "fallback-false-without-reason", "findings-not-list",
    "finding-not-string", "finding-empty", "finding-malformed", "finding-duplicate",
])
def test_digest_valid_loaded_decision_fields_fail_closed(tmp_path, updates, case):
    path = tmp_path / f"{case}.json"
    evaluate_model_decision(
        role="l2", risk="low", gate="G", session_id="S", task="task",
        response={}, decision_path=path,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(updates)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        load_decision(path, hashlib.sha256(path.read_bytes()).hexdigest())

def test_sod_pipeline_approved_report_runs_enforcer(monkeypatch, tmp_path):
    monkeypatch.setattr(sod_pipeline, "REPO_ROOT", tmp_path)
    report_path = tmp_path / "audit.md"
    monkeypatch.setattr(sod_pipeline, "_dispatch_l2", lambda *_: ({"SESSION_ID": "S", "ROLE_ID": "11"}, "l2"))
    monkeypatch.setattr(sod_pipeline, "_dispatch_l3", lambda *_: ({"REPORT": "audit.md"}, "l3"))
    monkeypatch.setattr(sod_pipeline, "capture", lambda *_: (0, "PRE_AUDIT_PATH=x\nPRE_AUDIT_SHA256=" + "a" * 64))
    calls = []

    def run(command, description, check=True):
        calls.append((command, description))
        if description.startswith("L3 Codex Audit"):
            report_path.write_text("[APPROVED]\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(sod_pipeline, "run", run)
    assert sod_pipeline.main(["worker", "auditor", "GATE", "slug", "task", "file.py"]) == 0
    assert any(desc == "SoD Gate Enforcer" and command[1:] == ["scripts/sod_gate_enforcer.py"] for command, desc in calls)

def test_jev_l2_decision_uses_dispatch_session_without_republication(monkeypatch, tmp_path):
    session_date = datetime.now().strftime("%Y%m%d")
    monkeypatch.setattr(sod_pipeline, "datetime", types.SimpleNamespace(now=lambda: datetime.strptime(session_date, "%Y%m%d")))
    monkeypatch.setattr(sod_pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sod_pipeline, "_dispatch_l2", lambda *_: ({"SESSION_ID": f"l2_role11_slug_{session_date}", "ROLE_ID": "11"}, "l2"))
    monkeypatch.setattr(sod_pipeline, "_dispatch_l3", lambda *_: pytest.fail("L3 should not run"))
    monkeypatch.setattr(sod_pipeline, "capture", lambda *_: (1, "validation failed"))
    monkeypatch.setattr(sod_pipeline, "run", lambda *_args, **_kwargs: 0)
    published = []

    def decide(**kwargs):
        published.append(kwargs)
        return {"session_id": kwargs["session_id"], "decision_digest": "a" * 64}

    monkeypatch.setattr(sod_pipeline, "evaluate_model_decision", decide)
    assert sod_pipeline.main(["devops-engineer", "code-reviewer", "GATE", "slug", "task", "file.py", "--jev"]) == 1
    assert len(published) == 1
    assert published[0]["session_id"] == f"l2_role11_slug_{session_date}"

def test_standing_regression_classes_are_all_retained():
    from scripts.dispatch_l2 import build_regression_clause, load_regression_classes

    expected = (
        "literal/legacy IPv4 denial", "IPv6 embedded IPv4 payloads", "special-use ranges",
        "sparse config merge preservation", "test isolation snapshot restore", "durable TLS SNI evidence",
        "userinfo credential rejection", "URL redaction in errors",
    )
    assert tuple(load_regression_classes()) == expected
    clause = build_regression_clause()
    assert all(item in clause for item in expected)


def test_l2_report_date_uses_task_date_for_cross_day_session_suffix(monkeypatch):
    session_id = "l2_role11_jev_24d_routing_fix6_20260927_20260928"
    forbidden = validate_l2_report.FORBIDDEN_PATHS
    report = "\n".join([
        "# L2 Implementation Report",
        "- **Role**: 11 devops-engineer - OpenCode L2 Implementation",
        "- **Gate**: `GATE_SOD_24D_JEV_ROUTING_20260927`",
        f"- **Session**: `{session_id}`",
        "- **Date**: `2026-09-27`",
        "- **Anti-Drip Mode**: `remediation`",
        "- **Anti-Drip Contract**: `.ly_state/session/anti_drip_contract_session.json`",
        "- **Anti-Drip Contract SHA-256**: `" + ("a" * 64) + "`",
        "- **Subagent Model**: `ag/gemini`",
        "",
        "## Summary", "done", "## Repo-Local Files Read", "- .agents/agent/devops-engineer.md",
        "## Changes Made", "done", "## Verification", "passed",
        "## Root-Cause Architectural Sweep", "```json", "{}", "```",
        "## Forbidden Path Scan",
        *(f"- `{path}`: not read; {validate_l2_report.FORBIDDEN_SUFFIX}" for path in forbidden),
    ])
    monkeypatch.setattr(validate_l2_report, "_validate_l2_report_content", lambda *_: (True, "OK"))

    assert validate_l2_report._validate_envelope(report, session_id, 11, "devops-engineer", True) == []


def test_jev_api_called_with_choice_questions(monkeypatch):
    recorded = {}

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def system_one(self, state, questions, **_):
            recorded["state"] = state
            recorded["questions"] = questions
            return types.SimpleNamespace(
                choices={
                    "lead_model": types.SimpleNamespace(choice="9router/cx/gpt-6.1-sol"),
                    "subagent_model": types.SimpleNamespace(choice="ag/gemini"),
                    "execution_timeout": types.SimpleNamespace(choice="180"),
                    "dimension_focus": types.SimpleNamespace(choice="24"),
                }
            )

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Choice, sdk.TypeSafeClient = lambda **kwargs: types.SimpleNamespace(**kwargs), MockClient
    sdk.TypeSafeAPIConnectionError = type("TypeSafeAPIConnectionError", (Exception,), {})
    sdk.TypeSafeAPITimeoutError = type("TypeSafeAPITimeoutError", (Exception,), {})
    sdk.TypeSafeInternalServerError = type("TypeSafeInternalServerError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)

    envelope = evaluate_model_decision(role="l2", risk="low", task="fix something", cycle=1)
    assert envelope["lead_model"] == "9router/cx/gpt-6.1-sol"
    assert envelope["subagent_model"] == "ag/gemini"
    assert envelope["execution_timeout"] == 180
    assert envelope["dimension_focus"] == 24
    assert recorded["questions"]["dimension_focus"].criteria.keys() == {str(i) for i in range(1, 25)}
    assert len(recorded["state"]["dimension_catalog"]) == 24
    assert "lead_model" in recorded["questions"]
    assert "subagent_model" in recorded["questions"]


def test_jev_api_redacts_credentials_before_xml_escaping(monkeypatch):
    recorded = {}

    class Client:
        def __init__(self, **_): pass
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def system_one(self, **kwargs):
            recorded.update(kwargs)
            return types.SimpleNamespace(choices={
                "lead_model": types.SimpleNamespace(choice=L2_LEAD_ALLOWLIST[0]),
                "subagent_model": types.SimpleNamespace(choice="ag/gemini"),
                "execution_timeout": types.SimpleNamespace(choice="180"),
                "dimension_focus": types.SimpleNamespace(choice="24"),
            })

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Choice, sdk.TypeSafeClient = lambda **kwargs: kwargs, Client
    for name in ("TypeSafeAPIConnectionError", "TypeSafeAPITimeoutError", "TypeSafeInternalServerError"):
        setattr(sdk, name, type(name, (Exception,), {}))
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)

    jev_router._query_jev_api(
        role="l2", risk="high", task="Bearer task-secret-token <scope>",
        scope=["https://user:scope-password@example.test/?api_key=scope-key"],
        predecessor_findings=["token=prior-secret F-001"],
    )

    serialized = json.dumps(recorded["state"])
    for secret in ("task-secret-token", "scope-password", "scope-key", "prior-secret"):
        assert secret not in serialized
    assert "Bearer [REDACTED]" in recorded["state"]["task_context"]
    assert "&lt;scope&gt;" in recorded["state"]["task_context"]


@pytest.mark.parametrize("path_kind", ["directory", "symlink", "unreadable", "invalid_utf8"])
def test_predecessor_report_invalid_paths_fail_closed(tmp_path, monkeypatch, path_kind):
    report = tmp_path / "report_F-001_HIGH.md"
    if path_kind == "directory":
        report.mkdir()
    elif path_kind == "symlink":
        report.write_text("F-001 HIGH", encoding="utf-8")
        real_lstat = Path.lstat
        def injected_symlink_lstat(path):
            if path == report:
                return types.SimpleNamespace(st_mode=jev_router.stat.S_IFLNK)
            return real_lstat(path)
        monkeypatch.setattr(Path, "lstat", injected_symlink_lstat)
    elif path_kind == "unreadable":
        report.write_text("F-001 HIGH", encoding="utf-8")
        real_open = os.open
        def deny_report_open(path, flags, *args, **kwargs):
            if Path(path) == report:
                raise PermissionError("injected unreadable predecessor report")
            return real_open(path, flags, *args, **kwargs)
        monkeypatch.setattr(os, "open", deny_report_open)
    else:
        report.write_bytes(b"F-001 HIGH \x80\xff")

    with pytest.raises(ValueError, match="predecessor report"):
        evaluate_model_decision(
            role="l2", risk="high", predecessor_report=report,
            response={"lead_model": L2_LEAD_ALLOWLIST[1]},
            decision_path=tmp_path / "decision.json",
        )
    assert not (tmp_path / "decision.json").exists()


def test_fallback_active_on_low_risk_network_error(monkeypatch):
    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def system_one(self, **_):
            raise ConnectionError("Connection refused by api.typesafe.ai")

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Choice, sdk.TypeSafeClient = lambda **kwargs: types.SimpleNamespace(**kwargs), FailingClient
    sdk.TypeSafeAPIConnectionError = ConnectionError
    sdk.TypeSafeAPITimeoutError = TimeoutError
    sdk.TypeSafeInternalServerError = type("TypeSafeInternalServerError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)

    envelope = evaluate_model_decision(role="l2", risk="low", cycle=1)
    assert envelope["fallback_used"] is True
    assert "Connection refused" in envelope["fallback_reason"]
    assert envelope["lead_model"] == L2_LEAD_ALLOWLIST[1]


def test_fallback_active_on_l3_low_risk_network_error(monkeypatch):
    class FailingClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def system_one(self, **_): raise ConnectionError("Connection refused")

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Choice, sdk.TypeSafeClient = lambda **kwargs: types.SimpleNamespace(**kwargs), FailingClient
    sdk.TypeSafeAPIConnectionError, sdk.TypeSafeAPITimeoutError = ConnectionError, TimeoutError
    sdk.TypeSafeInternalServerError = type("TypeSafeInternalServerError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)
    monkeypatch.setattr("scripts.jev_model_router.time.sleep", lambda _: None)
    decision = evaluate_model_decision(role="l3", risk="low")
    assert decision["fallback_used"] is True and decision["dimension_focus"] is None


def test_fallback_reason_redacted_before_durable_publication(tmp_path):
    path = tmp_path / "decision.json"
    envelope = evaluate_model_decision(
        role="l2", risk="low", gate="G", session_id="S", task="task", decision_path=path,
        response={"fallback_used": True, "fallback_reason": "https://user:secret@example.org/?api_key=private"},
    )
    assert "secret" not in path.read_text(encoding="utf-8")
    assert "private" not in path.read_text(encoding="utf-8")
    assert "secret" not in envelope["fallback_reason"]
    assert load_decision(path, envelope["decision_digest"])["fallback_reason"] == envelope["fallback_reason"]


def test_fallback_forbidden_on_high_risk_network_error(monkeypatch):
    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def system_one(self, **_):
            raise ConnectionError("Connection refused")

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Choice, sdk.TypeSafeClient = lambda **kwargs: types.SimpleNamespace(**kwargs), FailingClient
    sdk.TypeSafeAPIConnectionError = ConnectionError
    sdk.TypeSafeAPITimeoutError = TimeoutError
    sdk.TypeSafeInternalServerError = type("TypeSafeInternalServerError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)

    with pytest.raises(ConnectionError):
        evaluate_model_decision(role="l2", risk="high", cycle=1)


def test_fallback_forbidden_on_remediation_cycle(monkeypatch):
    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def system_one(self, **_):
            raise ConnectionError("Connection refused")

    sdk = types.ModuleType("typesafe_sdk")
    sdk.Choice, sdk.TypeSafeClient = lambda **kwargs: types.SimpleNamespace(**kwargs), FailingClient
    sdk.TypeSafeAPIConnectionError = ConnectionError
    sdk.TypeSafeAPITimeoutError = TimeoutError
    sdk.TypeSafeInternalServerError = type("TypeSafeInternalServerError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)

    with pytest.raises(ConnectionError):
        evaluate_model_decision(role="l2", risk="low", cycle=2)


def test_publish_decision_fails_closed_on_replace_error(tmp_path, monkeypatch):
    envelope = {"schema_version": "2.0", "gate": "G", "session_id": "S"}
    target = tmp_path / "decision.json"

    def fail_replace(src, dst):
        raise OSError("Simulated disk error")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="Simulated disk error"):
        atomic_publish_decision(envelope, target)

    assert not target.exists()
    assert not (tmp_path / f".{target.name}.lock").exists()


def test_decision_and_predecessor_exceeding_bound_fail_closed(tmp_path):
    from scripts.jev_model_router import MAX_RESPONSE_BYTES
    oversized = tmp_path / "oversized.md"
    oversized.write_bytes(b"F-001 " * (MAX_RESPONSE_BYTES // 5 + 10))
    with pytest.raises(ValueError, match="predecessor report exceeds size bound"):
        evaluate_model_decision(role="l2", risk="low", predecessor_report=oversized)

    oversized_dec = tmp_path / "decision.json"
    oversized_dec.write_bytes(b"a" * (MAX_RESPONSE_BYTES + 10))
    with pytest.raises(ValueError, match="decision payload exceeds size bound"):
        load_decision(oversized_dec, "0" * 64)


def _jev_fixture(monkeypatch):
    from omega.core import llm_config

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 25, 9, 30, tzinfo=tz)
    monkeypatch.setattr(llm_config, "datetime", Clock)
    calls = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["timeout"] == 10.0
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return None
        def system_one(self, **kwargs):
            calls.append(kwargs)
            return types.SimpleNamespace(choices={"outcome": types.SimpleNamespace(choice="mixed")})

    sdk = types.SimpleNamespace(Choice=lambda **kwargs: kwargs, TypeSafeClient=Client)
    for name in ("TypeSafeAPIConnectionError", "TypeSafeAPITimeoutError", "TypeSafeInternalServerError", "TypeSafeRateLimitError"):
        setattr(sdk, name, type(name, (Exception,), {}))
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)
    return llm_config, calls, sdk


def _jev_args(tmp_path):
    from datetime import timezone
    return dict(domain="alpha_disagreement", facts={"ticker": "VNM", "value_vnd_full": 50_000},
                choices={"outcome": ("trend_supported", "reversal_supported", "mixed", "insufficient")},
                cache_path=tmp_path / "jev.sqlite", as_of=datetime(2026, 9, 25, 10, tzinfo=timezone.utc),
                available_at=datetime(2026, 9, 25, 9, tzinfo=timezone.utc), model="test",
                 entity_ids=("VNM",), source_revisions=("r1",), max_calls=2)


def test_w1_concurrent_same_key_does_not_hold_writer_during_provider(monkeypatch, tmp_path):
    llm, calls, sdk = _jev_fixture(monkeypatch)
    entered, release = Event(), Event()
    original = sdk.TypeSafeClient.system_one

    def blocked(self, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(self, **kwargs)

    monkeypatch.setattr(sdk.TypeSafeClient, "system_one", blocked)
    args = _jev_args(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(llm.classify_jev, **args)
        assert entered.wait(5)
        with sqlite3.connect(args["cache_path"], timeout=0.1) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO usage VALUES ('2026-09-25', 'other', 0)")
        second = pool.submit(llm.classify_jev, **args)
        release.set()
        assert first.result(timeout=5) == second.result(timeout=5)
    assert len(calls) == 1


def test_w1_registry_and_envelope_cache_replay(monkeypatch, tmp_path):
    llm, calls, _ = _jev_fixture(monkeypatch)
    assert len(llm.DOMAIN_REGISTRY) == 11
    args = _jev_args(tmp_path)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 25, 9, 30, tzinfo=tz)
    monkeypatch.setattr(llm, "datetime", Clock)
    decision = llm.classify_jev(**args)
    assert decision["status"] == "accepted" and decision["authority"] == "research_only"
    assert decision["schema_version"] == llm.JEV_SCHEMA_VERSION
    assert decision["source_hash"] == hashlib.sha256(llm._canonical(args["facts"])).hexdigest()
    assert decision["selected"] == {"outcome": "mixed"}
    assert llm.classify_jev(**{**args, "mode": "replay"}) == decision
    assert len(calls) == 1


@pytest.mark.parametrize("change", [
    {"as_of": datetime.fromisoformat("2026-09-25T11:00:00+00:00")},
    {"source_revisions": ("r2",)}, {"entity_ids": ("VCB",)}, {"gate_id": "G2"},
    {"policy_version": "v2"}, {"prompt_version": "v2"}, {"profile_version": "v2"},
    {"feature_version": "v2"}, {"dataset_manifest": "m2"}, {"code_revision": "rev2"},
    {"facts": {"ticker": "VNM", "value_vnd_full": 50_001}},
])
def test_w1_cache_key_distinguishes_information_set(monkeypatch, tmp_path, change):
    llm, calls, _ = _jev_fixture(monkeypatch)
    args = _jev_args(tmp_path)
    original = llm.classify_jev(**args)
    updated = llm.classify_jev(**{**args, **change})
    assert updated["fingerprint"] != original["fingerprint"] and len(calls) == 2


def test_w1_selective_budget_and_429_exhaustion(monkeypatch, tmp_path):
    llm, calls, sdk = _jev_fixture(monkeypatch)
    args = _jev_args(tmp_path)
    for policy in ({"rule_sufficient": True}, {"novelty": False},
                   {"estimated_benefit": 0.5, "estimated_cost": 1}):
        with pytest.raises(ValueError, match="JEV skipped"):
            llm.classify_jev(**{**args, "mode": "selective", **policy})
    assert calls == []
    class RateLimited:
        def __init__(self, **_): pass
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def system_one(self, **_):
            calls.append("429")
            raise sdk.TypeSafeRateLimitError("Bearer private-secret")
    sdk.TypeSafeClient = RateLimited
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="JEV unavailable after two attempts"):
        llm.classify_jev(**{**args, "estimated_cost": 1, "max_spend": 2})
    assert calls == ["429", "429"]
    with pytest.raises(ValueError, match="budget exhausted"):
        llm.classify_jev(**args)


@pytest.mark.parametrize("message", [
    "provider rejected Authorization: Bearer private-token; HTTP 401",
    "provider rejected https://user:password@example.org/?api_key=private; HTTP 403",
    "provider rejected token=private&request=invalid; HTTP 400",
    "provider rejected sk-secretvalue ghp_privatevalue; HTTP 422",
], ids=["auth_bearer_401", "url_credentials_403", "query_token_400", "secret_tokens_422"])
def test_w1_non_transient_provider_errors_are_redacted_and_billed(monkeypatch, tmp_path, message):
    import sqlite3
    llm, calls, sdk = _jev_fixture(monkeypatch)

    class FailingClient:
        def __init__(self, **_): pass
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def system_one(self, **kwargs):
            calls.append(kwargs)
            raise RuntimeError(message)

    sdk.TypeSafeClient = FailingClient
    args = _jev_args(tmp_path)
    with pytest.raises(RuntimeError) as caught:
        llm.classify_jev(**{**args, "estimated_cost": 1})
    assert "provider rejected" in str(caught.value) and "HTTP" in str(caught.value)
    assert not any(marker in str(caught.value) for marker in ("private", "password", "user", "secretvalue"))
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert len(calls) == 1
    with sqlite3.connect(args["cache_path"]) as db:
        assert db.execute("SELECT COUNT(*), SUM(cost) FROM usage").fetchone() == (1, 1)
        assert db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0


@pytest.mark.parametrize("invalid", [
    {"facts": {"x": float("nan")}}, {"facts": {"x": float("inf")}},
    {"facts": {"api_key": "private"}}, {"facts": {"url": "https://u:pass@example.com"}},
    {"choices": {"outcome": ("mixed",)}}, {"entity_ids": ["VNM"]},
    {"max_calls": True}, {"estimated_cost": float("inf")}, {"gate_id": "Bearer private"},
    {"domain": "../../unsafe"},
])
def test_w1_invalid_inputs_never_call_provider(monkeypatch, tmp_path, invalid):
    llm, calls, _ = _jev_fixture(monkeypatch)
    with pytest.raises(ValueError):
        llm.classify_jev(**{**_jev_args(tmp_path), **invalid})
    assert calls == []


def test_w1_corrupt_cache_schema_and_directory_fail_closed(monkeypatch, tmp_path):
    import sqlite3
    llm, calls, _ = _jev_fixture(monkeypatch)
    args = _jev_args(tmp_path)
    first = llm.classify_jev(**args)
    with sqlite3.connect(args["cache_path"]) as db:
        corrupted = {**first, "authority": "bounded_profile"}
        db.execute("UPDATE decisions SET envelope=?", (json.dumps(corrupted),))
    with pytest.raises(ValueError, match="invalid JEV cache envelope"):
        llm.classify_jev(**args)
    assert len(calls) == 1
    with pytest.raises(ValueError, match="file"):
        llm.classify_jev(**{**args, "cache_path": tmp_path})


def test_w1_cache_miss_replay_never_networks(monkeypatch, tmp_path):
    llm, calls, _ = _jev_fixture(monkeypatch)
    with pytest.raises(ValueError, match="cache miss"):
        llm.classify_jev(**{**_jev_args(tmp_path), "mode": "replay"})
    assert calls == []


def test_w1_legacy_daily_key_and_versioned_full_cutoff(monkeypatch, tmp_path):
    llm, calls, _ = _jev_fixture(monkeypatch)
    args = _jev_args(tmp_path)
    args.update(domain="test", choices={"outcome": ("mixed", "other")}, max_calls=3)
    first = llm.classify_jev(**args)
    later = {**args, "as_of": args["as_of"].replace(hour=11)}
    assert llm.classify_jev(**later)["fingerprint"] == first["fingerprint"]
    assert first["version"] == 1 and len(calls) == 1
    full = llm.classify_jev(**{**args, "schema_version": 2})
    assert full["version"] == 2
    assert llm.classify_jev(**{**later, "schema_version": 2})["fingerprint"] != full["fingerprint"]
    assert len(calls) == 3


def test_w1_v2_historical_live_rejected_before_provider_and_cache(monkeypatch, tmp_path):
    llm, calls, _ = _jev_fixture(monkeypatch)
    monkeypatch.setattr(llm, "datetime", datetime)
    args = _jev_args(tmp_path)
    with pytest.raises(ValueError, match="cutoff precedes invocation"):
        llm.classify_jev(**args)
    assert calls == [] and not args["cache_path"].exists()


def test_w1_v2_corrupt_historical_cache_rejected_on_replay(monkeypatch, tmp_path):
    import sqlite3
    llm, calls, _ = _jev_fixture(monkeypatch)
    args = _jev_args(tmp_path)
    envelope = llm.classify_jev(**args)
    envelope["decided_at"] = envelope["decision_time"] = envelope["generated_at"] = "2026-09-26T09:30:00+00:00"
    with sqlite3.connect(args["cache_path"]) as db:
        db.execute("UPDATE decisions SET envelope=?", (json.dumps(envelope),))
    with pytest.raises(ValueError, match="invalid JEV cache envelope"):
        llm.classify_jev(**{**args, "mode": "replay"})
    assert len(calls) == 1


@pytest.mark.parametrize("facts", [
    {"credential": "opaque"}, {"note": "sk-example-token"},
    {"nested": [{"private_key": "opaque"}]}, {"note": "ghp_exampletoken"},
    {"cookie": "opaque"}, {"nested": [{"session_id": "opaque"}]},
    {"sessionToken": "opaque"}, {"set-cookie": "opaque"},
])
def test_w1_sensitive_facts_fail_before_provider_and_cache(monkeypatch, tmp_path, facts):
    llm, calls, _ = _jev_fixture(monkeypatch)
    args = _jev_args(tmp_path)
    with pytest.raises(ValueError, match="invalid JEV facts"):
        llm.classify_jev(**{**args, "facts": facts})
    assert calls == [] and not args["cache_path"].exists()


def test_w1_usage_cap_blocks_rotating_gates_before_provider(monkeypatch, tmp_path):
    import sqlite3
    llm, calls, _ = _jev_fixture(monkeypatch)
    args = _jev_args(tmp_path)
    with sqlite3.connect(args["cache_path"]) as db:
        db.execute("CREATE TABLE usage (day TEXT NOT NULL, gate_id TEXT NOT NULL, cost REAL NOT NULL)")
        db.executemany("INSERT INTO usage VALUES (?, ?, ?)",
                       [("2026-09-25", f"gate{i}", 0.0) for i in range(llm.MAX_JEV_ROWS)])
    with pytest.raises(ValueError, match="usage row limit"):
        llm.classify_jev(**args)
    assert calls == []


def test_w1_usage_retention_persists_on_replay_miss(monkeypatch, tmp_path):
    import sqlite3
    llm, calls, _ = _jev_fixture(monkeypatch)
    args = _jev_args(tmp_path)
    with sqlite3.connect(args["cache_path"]) as db:
        db.execute("CREATE TABLE usage (day TEXT NOT NULL, gate_id TEXT NOT NULL, cost REAL NOT NULL)")
        db.execute("INSERT INTO usage VALUES ('2020-01-01', 'old', 0)")
    with pytest.raises(ValueError, match="cache miss"):
        llm.classify_jev(**{**args, "mode": "replay"})
    with sqlite3.connect(args["cache_path"]) as db:
        assert db.execute("SELECT COUNT(*) FROM usage").fetchone()[0] == 0
    assert calls == []
