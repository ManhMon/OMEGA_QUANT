from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import scripts.consolidate_historical_news as news

SCHEMA = news.SCHEMA


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(news, "REPO_ROOT", tmp_path)
    shards = tmp_path / "data" / "historical_news" / "run_703_full"
    shards.mkdir(parents=True)
    output = tmp_path / "data" / "news.parquet"
    return tmp_path, shards, output


def frame(**changes):
    values = {
        "symbol": "VNM",
        "title": None,
        "publish_time": pd.Timestamp("2024-02-10T08:30:00+07:00"),
        "sentiment_score": 0.25,
        "available_at": pd.Timestamp("2024-02-10T15:30:00+07:00"),
        "url": None,
        "source": "wire",
        "fetched_at": pd.Timestamp("2024-02-10T09:00:00+07:00"),
        "raw_timestamp": None,
        "payload_sha256": hashlib.sha256(b"news").hexdigest(),
        "parser_version": "news-v10",
        "legacy_row": False,
    }
    values.update(changes)
    return pd.DataFrame([values], columns=SCHEMA.names)


def write_shard(directory: Path, name: str, data: pd.DataFrame | None = None) -> Path:
    path = directory / name
    data = frame() if data is None else data
    schema = SCHEMA
    if any(not field.nullable and data[field.name].isna().any() for field in SCHEMA):
        schema = pa.schema([pa.field(field.name, field.type, nullable=True) for field in SCHEMA])
    arrays = [pa.array(data[field.name].tolist(), type=field.type, from_pandas=True) for field in schema]
    table = pa.Table.from_arrays(arrays, schema=schema)
    pq.write_table(table, path)
    return path


def test_consolidates_ordered_schema_deduplicates_and_keeps_news_on_holiday(repo):
    _, shards, output = repo
    later = frame(symbol="DELISTED", publish_time=pd.Timestamp("2024-02-11T10:00:00Z"),
                  fetched_at=pd.Timestamp("2024-02-11T10:00:00Z"), available_at=pd.Timestamp("2024-02-11T10:00:00Z"),
                  payload_sha256=hashlib.sha256(b"later").hexdigest(), legacy_row=True)
    write_shard(shards, "02-v10.parquet", later)
    write_shard(shards, "01-v10.parquet", frame())
    write_shard(shards, "03-v10.parquet", frame())

    result = news.consolidate_shards(shards.relative_to(news.REPO_ROOT), output.relative_to(news.REPO_ROOT))

    assert list(result.columns) == SCHEMA.names
    assert len(result) == 2
    assert result["publish_time"].is_monotonic_increasing
    assert result.iloc[0]["publish_time"] == pd.Timestamp("2024-02-10T01:30:00Z")
    assert result.iloc[1]["symbol"] == "DELISTED"
    assert bool(result.iloc[1]["legacy_row"])
    assert pq.read_schema(output).equals(news.SCHEMA, check_metadata=False)
    assert all(SCHEMA.field(name).nullable for name in ("title", "available_at", "url", "raw_timestamp"))
    assert all(not SCHEMA.field(name).nullable for name in ("source", "fetched_at", "payload_sha256", "parser_version", "legacy_row"))
    assert output.with_suffix(".parquet.bak").exists() is False


def test_conflicting_rows_with_same_dedup_key_fail_without_replacing_output(repo):
    _, shards, output = repo
    output.write_bytes(b"original")
    write_shard(shards, "01-v10.parquet", frame(title="first"))
    write_shard(shards, "02-v10.parquet", frame(title="second"))

    with pytest.raises(ValueError, match="Conflicting rows"):
        news.consolidate_shards(shards.relative_to(news.REPO_ROOT), output.relative_to(news.REPO_ROOT))
    assert output.read_bytes() == b"original"


@pytest.mark.parametrize("column,value", [
    ("symbol", None), ("symbol", "  "), ("source", ""), ("parser_version", None),
    ("payload_sha256", "x" * 64), ("payload_sha256", "g" * 64), ("legacy_row", None),
    ("publish_time", None), ("fetched_at", None), ("available_at", None),
    ("sentiment_score", float("nan")), ("sentiment_score", float("inf")),
    ("sentiment_score", float("-inf")), ("sentiment_score", 1.0000001),
    ("sentiment_score", -1.0000001), ("sentiment_score", 1e12),
])
def test_rejects_invalid_values(repo, column, value):
    _, shards, output = repo
    write_shard(shards, "bad-v10.parquet", frame(**{column: value}))
    with pytest.raises((ValueError, pa.ArrowException)):
        news.consolidate_shards(shards.relative_to(news.REPO_ROOT), output.relative_to(news.REPO_ROOT))
    assert not output.exists()


def test_rejects_naive_timestamps_and_future_or_out_of_order_times(repo):
    root, shards, output = repo
    naive = frame(publish_time=pd.Timestamp("2024-02-10 08:30"))
    fields = [pa.field(field.name, pa.timestamp("us") if field.name == "publish_time" else field.type, nullable=field.nullable) for field in SCHEMA]
    arrays = [pa.array(naive[field.name].tolist(), type=field.type) for field in fields]
    pq.write_table(pa.Table.from_arrays(arrays, schema=pa.schema(fields)), shards / "naive-v10.parquet")
    with pytest.raises(ValueError, match="schema"):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root))
    (shards / "naive-v10.parquet").unlink()
    future = frame(available_at=pd.Timestamp("2024-02-10T08:00:00+07:00"))
    write_shard(shards, "future-v10.parquet", future)
    with pytest.raises(ValueError, match="timestamps violate"):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root))


def test_accepts_bounds_and_utc_equivalent_pit_equality(repo):
    _, shards, output = repo
    item = frame(publish_time=pd.Timestamp("2024-06-03T08:30:00+07:00"),
                 fetched_at=pd.Timestamp("2024-06-03T01:30:00Z"),
                 available_at=pd.Timestamp("2024-06-03T01:30:00Z"), sentiment_score=-1.0)
    write_shard(shards, "good-v10.parquet", item)
    result = news.consolidate_shards(shards.relative_to(news.REPO_ROOT), output.relative_to(news.REPO_ROOT))
    assert result.iloc[0]["publish_time"] == result.iloc[0]["available_at"]


@pytest.mark.parametrize("column,dtype", [("symbol", "int64"), ("title", "list<item: string>"), ("sentiment_score", "string")])
def test_rejects_schema_drift_including_empty_shard(repo, column, dtype):
    _, shards, output = repo
    index = SCHEMA.get_field_index(column)
    arrow_type = pa.list_(pa.string()) if dtype.startswith("list") else (pa.string() if dtype == "string" else pa.int64())
    fields = [pa.field(field.name, arrow_type if i == index else field.type, nullable=field.nullable) for i, field in enumerate(SCHEMA)]
    table = pa.Table.from_arrays([pa.array([], type=field.type) for field in fields], schema=pa.schema(fields))
    pq.write_table(table, shards / "empty-bad-v10.parquet")
    with pytest.raises(ValueError, match="schema"):
        news.consolidate_shards(shards.relative_to(news.REPO_ROOT), output.relative_to(news.REPO_ROOT))


@pytest.mark.parametrize("kind", ["empty", "corrupt", "directory", "bom", "invalid_utf8"])
def test_rejects_invalid_shard_files(repo, kind):
    _, shards, output = repo
    path = shards / "bad-v10.parquet"
    if kind == "empty":
        pq.write_table(pa.Table.from_pandas(frame().iloc[:0], schema=SCHEMA, preserve_index=False), path)
    elif kind == "corrupt":
        path.write_bytes(b"not a parquet file")
    elif kind == "directory":
        path.mkdir()
    elif kind == "bom":
        path.write_bytes(b"\xef\xbb\xbf{}")
    else:
        path.write_bytes(b"\xff\xfe")
    with pytest.raises((ValueError, OSError, pa.ArrowException, FileNotFoundError)):
        news.consolidate_shards(shards.relative_to(news.REPO_ROOT), output.relative_to(news.REPO_ROOT))


def test_repo_path_rejects_absolute_traversal_symlink_and_hardlink_alias(repo, tmp_path):
    root, shards, output = repo
    with pytest.raises(ValueError):
        news.consolidate_shards(shards, output.relative_to(root))
    with pytest.raises(ValueError):
        news.consolidate_shards(Path("../outside"), Path("data/out.parquet"))
    write_shard(shards, "01-v10.parquet")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pass
    else:
        with pytest.raises(ValueError):
            news.consolidate_shards(Path("link"), Path("data/out.parquet"))
    hardlink = root / "alias-v10.parquet"
    try:
        os.link(shards / "01-v10.parquet", hardlink)
    except OSError:
        pytest.skip("Hard links unsupported")
    with pytest.raises(ValueError, match="distinct"):
        news.consolidate_shards(shards.relative_to(root), Path("alias-v10.parquet"))


@pytest.mark.parametrize("constant,value", [("MAX_SHARDS", 0), ("MAX_ROWS", 0), ("MAX_BYTES", 0)])
def test_enforces_resource_limits(repo, monkeypatch, constant, value):
    _, shards, output = repo
    write_shard(shards, "01-v10.parquet")
    monkeypatch.setattr(news, constant, value)
    with pytest.raises(ValueError, match="limit"):
        news.consolidate_shards(shards.relative_to(news.REPO_ROOT), output.relative_to(news.REPO_ROOT))


def test_backup_and_output_replacement_failure_cleanup(repo, monkeypatch):
    root, shards, output = repo
    output.write_bytes(b"original")
    write_shard(shards, "01-v10.parquet")
    backup = output.with_suffix(".parquet.bak")
    real_replace = os.replace

    def fail_backup(source, destination):
        if destination == backup:
            raise OSError("copy backup failure")
        return real_replace(source, destination)

    monkeypatch.setattr(news.os, "replace", fail_backup)
    with pytest.raises(OSError):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root))
    assert output.read_bytes() == b"original"
    assert not list(output.parent.glob(".*.tmp"))
    monkeypatch.setattr(news.os, "replace", real_replace)
    news.consolidate_shards(shards.relative_to(root), output.relative_to(root))
    assert backup.read_bytes() == b"original"


def test_lock_contention_and_foreign_lock_are_fail_closed(repo):
    root, shards, output = repo
    write_shard(shards, "01-v10.parquet")
    lock = output.with_name(output.name + ".lock")
    lock.write_text("foreign-owner", encoding="ascii")
    with pytest.raises(RuntimeError, match="locked"):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root))
    assert lock.read_text(encoding="ascii") == "foreign-owner"


def test_failed_output_replace_keeps_old_file_and_cleans_temps(repo, monkeypatch):
    root, shards, output = repo
    output.write_bytes(b"original")
    write_shard(shards, "01-v10.parquet")
    def fail_replace(source, destination):
        if destination == output:
            raise OSError("credential=https://user:secret@example.invalid")
        return os.replace(source, destination)
    monkeypatch.setattr(news.os, "replace", fail_replace)
    with pytest.raises(OSError):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root), backup=False)
    assert output.read_bytes() == b"original"
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))
    assert not output.with_name(output.name + ".lock").exists()


def test_shard_mutation_during_validation_prevents_replacement(repo, monkeypatch):
    root, shards, output = repo
    output.write_bytes(b"original")
    shard = write_shard(shards, "01-v10.parquet")
    state = news._file_state
    def mutate_after_read(path):
        result = state(path)
        if path == shard:
            os.utime(path, None)
        return result
    monkeypatch.setattr(news, "_file_state", mutate_after_read)
    with pytest.raises(RuntimeError, match="changed"):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root), backup=False)
    assert output.read_bytes() == b"original"


def test_failed_fsync_preserves_output_and_cleans_temporary_files(repo, monkeypatch):
    root, shards, output = repo
    output.write_bytes(b"original")
    write_shard(shards, "01-v10.parquet")
    monkeypatch.setattr(news, "_fsync_file", lambda path: (_ for _ in ()).throw(OSError("fsync failure")))
    with pytest.raises(OSError):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root), backup=False)
    assert output.read_bytes() == b"original"
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))


def test_creates_nested_output_parent(repo):
    root, shards, _ = repo
    write_shard(shards, "01-v10.parquet")
    output = root / "data" / "nested" / "deeper" / "news.parquet"

    result = news.consolidate_shards(shards.relative_to(root), output.relative_to(root))

    assert len(result) == 1
    assert pq.read_schema(output).equals(SCHEMA, check_metadata=False)


@pytest.mark.parametrize("column,value", [
    ("source", "other"), ("parser_version", "news-v11"),
    ("fetched_at", pd.Timestamp("2024-02-10T09:30:00+07:00")),
    ("available_at", pd.Timestamp("2024-02-10T16:30:00+07:00")),
    ("legacy_row", True), ("title", "different"), ("sentiment_score", 0.5),
])
def test_duplicate_key_conflicts_on_any_other_column_fail(repo, column, value):
    root, shards, output = repo
    write_shard(shards, "01-v10.parquet", frame())
    write_shard(shards, "02-v10.parquet", frame(**{column: value}))

    with pytest.raises(ValueError, match="Conflicting rows"):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root))
    assert not output.exists()


def test_uppercase_and_lowercase_digests_deduplicate(repo):
    root, shards, output = repo
    digest = hashlib.sha256(b"news").hexdigest()
    write_shard(shards, "01-v10.parquet", frame(payload_sha256=digest.lower()))
    write_shard(shards, "02-v10.parquet", frame(payload_sha256=digest.upper()))

    result = news.consolidate_shards(shards.relative_to(root), output.relative_to(root))

    assert len(result) == 1
    assert result.iloc[0]["payload_sha256"] == digest.lower()


@pytest.mark.parametrize("change", ["added", "removed"])
def test_shard_set_change_during_staged_write_prevents_replacement(repo, monkeypatch, change):
    root, shards, output = repo
    output.write_bytes(b"original")
    shard = write_shard(shards, "01-v10.parquet")
    real_write = pq.write_table
    changed = False

    def change_shards(table, where, *args, **kwargs):
        nonlocal changed
        real_write(table, where, *args, **kwargs)
        if not changed and Path(where).suffix == ".tmp":
            changed = True
            if change == "added":
                write_shard(shards, "02-v10.parquet", frame(symbol="OTHER"))
            else:
                shard.unlink()

    monkeypatch.setattr(news.pq, "write_table", change_shards)
    with pytest.raises(RuntimeError, match="Shard set changed"):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root), backup=False)
    assert output.read_bytes() == b"original"


def test_same_size_content_change_with_restored_mtime_is_detected(repo, monkeypatch):
    root, shards, output = repo
    output.write_bytes(b"original")
    shard = write_shard(shards, "01-v10.parquet")
    original_state = news._file_state(shard)
    real_state = news._file_state
    real_snapshot = news._snapshot_unchanged

    def stable_state(path):
        return original_state if path == shard else real_state(path)

    def mutate_then_check(directory, states, digests):
        info = shard.stat()
        data = shard.read_bytes()
        shard.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        os.utime(shard, ns=(info.st_atime_ns, info.st_mtime_ns))
        return real_snapshot(directory, states, digests)

    monkeypatch.setattr(news, "_file_state", stable_state)
    monkeypatch.setattr(news, "_snapshot_unchanged", mutate_then_check)
    with pytest.raises(RuntimeError, match="changed"):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root), backup=False)
    assert output.read_bytes() == b"original"


def test_rejects_exact_input_output_alias_and_nonexistent_shard_pattern(repo):
    root, shards, _ = repo
    shard = write_shard(shards, "01-v10.parquet")
    with pytest.raises(ValueError, match="distinct"):
        news.consolidate_shards(shards.relative_to(root), shard.relative_to(root))
    with pytest.raises(ValueError, match="shard path"):
        news.consolidate_shards(shards.relative_to(root), (shards / "new-v10.parquet").relative_to(root))


def test_no_backup_ignores_existing_backup_directory(repo):
    root, shards, output = repo
    write_shard(shards, "01-v10.parquet")
    backup_dir = output.with_suffix(".parquet.bak")
    backup_dir.mkdir()

    result = news.consolidate_shards(shards.relative_to(root), output.relative_to(root), backup=False)

    assert len(result) == 1
    assert backup_dir.is_dir()
    assert list(backup_dir.iterdir()) == []


@pytest.mark.parametrize("failure", ["copy", "backup_fsync"])
def test_backup_copy_and_fsync_failures_preserve_output_and_clean_temps(repo, monkeypatch, failure):
    root, shards, output = repo
    output.write_bytes(b"original")
    write_shard(shards, "01-v10.parquet")
    if failure == "copy":
        monkeypatch.setattr(news.shutil, "copy2", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("copy failed")))
    else:
        real_fsync = news._fsync_file
        def fail_backup_fsync(path):
            if path.name.startswith(f".{output.name}.bak."):
                raise OSError("backup fsync failed")
            real_fsync(path)
        monkeypatch.setattr(news, "_fsync_file", fail_backup_fsync)

    with pytest.raises(OSError):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root))
    assert output.read_bytes() == b"original"
    assert not list(output.parent.glob(".*.tmp"))


def test_partial_parquet_write_failure_cleans_temporary_output(repo, monkeypatch):
    root, shards, output = repo
    output.write_bytes(b"original")
    write_shard(shards, "01-v10.parquet")
    def partial_write(table, where, *args, **kwargs):
        Path(where).write_bytes(b"partial")
        raise OSError("write failed")
    monkeypatch.setattr(news.pq, "write_table", partial_write)

    with pytest.raises(OSError, match="write failed"):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root), backup=False)
    assert output.read_bytes() == b"original"
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))


def test_nested_concurrent_call_fails_fast_while_outer_call_succeeds(repo, monkeypatch):
    root, shards, output = repo
    write_shard(shards, "01-v10.parquet")
    real_write = pq.write_table
    attempted = False

    def nested_call(table, where, *args, **kwargs):
        nonlocal attempted
        if not attempted and Path(where).suffix == ".tmp":
            attempted = True
            with pytest.raises(RuntimeError, match="locked"):
                news.consolidate_shards(shards.relative_to(root), output.relative_to(root), backup=False)
        return real_write(table, where, *args, **kwargs)

    monkeypatch.setattr(news.pq, "write_table", nested_call)
    result = news.consolidate_shards(shards.relative_to(root), output.relative_to(root), backup=False)

    assert attempted
    assert len(result) == 1
    assert output.exists()


def test_foreign_lock_replacement_is_not_removed(repo, monkeypatch):
    root, shards, output = repo
    write_shard(shards, "01-v10.parquet")
    lock = output.with_name(output.name + ".lock")
    real_lstat = Path.lstat
    replaced = False

    def replace_lock_when_owner_checks(path):
        nonlocal replaced
        if path == lock and not replaced:
            replaced = True
            path.unlink()
            path.write_text("foreign-owner", encoding="ascii")
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", replace_lock_when_owner_checks)
    result = news.consolidate_shards(shards.relative_to(root), output.relative_to(root), backup=False)

    assert len(result) == 1
    assert replaced
    assert lock.read_text(encoding="ascii") == "foreign-owner"


def test_postreplace_directory_fsync_failure_reports_error_with_complete_output(repo, monkeypatch):
    root, shards, output = repo
    write_shard(shards, "01-v10.parquet")
    monkeypatch.setattr(news, "_fsync_directory", lambda path: (_ for _ in ()).throw(OSError("directory fsync failed")))

    with pytest.raises(OSError, match="directory fsync failed"):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root), backup=False)

    assert pq.read_schema(output).equals(SCHEMA, check_metadata=False)
    assert len(pq.read_table(output)) == 1


def test_accepts_timestamp_zones_and_writes_utc_schema(repo):
    root, shards, output = repo
    data = frame()
    fields = [
        pa.field(field.name, pa.timestamp("us", tz="Asia/Ho_Chi_Minh") if field.name in ("publish_time", "fetched_at", "available_at") else field.type, nullable=field.nullable)
        for field in SCHEMA
    ]
    schema = pa.schema(fields)
    table = pa.Table.from_arrays([pa.array(data[field.name].tolist(), type=field.type) for field in schema], schema=schema)
    pq.write_table(table, shards / "01-v10.parquet")

    result = news.consolidate_shards(shards.relative_to(root), output.relative_to(root))

    assert result.iloc[0]["publish_time"] == pd.Timestamp("2024-02-10T01:30:00Z")
    assert pq.read_schema(output).equals(SCHEMA, check_metadata=False)


def test_max_bytes_counts_uncompressed_footer_size(repo, monkeypatch):
    root, shards, output = repo
    shard = write_shard(shards, "01-v10.parquet", frame(title="x" * 200_000))
    size = shard.stat().st_size
    uncompressed = pq.ParquetFile(shard).metadata.row_group(0).total_byte_size
    assert uncompressed > size
    monkeypatch.setattr(news, "MAX_BYTES", size)

    with pytest.raises(ValueError, match="resource limits"):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root))


def test_shard_glob_stops_after_limit_plus_one(repo, monkeypatch):
    _, shards, _ = repo
    monkeypatch.setattr(news, "MAX_SHARDS", 2)
    yielded = []

    def bounded_glob(path, pattern):
        assert path == shards
        assert pattern == "*-v10.parquet"
        def paths():
            for index in range(10):
                yielded.append(index)
                yield shards / f"{index}-v10.parquet"
        return paths()

    monkeypatch.setattr(Path, "glob", bounded_glob)
    with pytest.raises(ValueError, match="Shard count exceeds"):
        news._shard_paths(shards)
    assert len(yielded) == 3


def test_cli_success_failure_and_unknown_option(repo, capsys):
    root, shards, output = repo
    write_shard(shards, "01-v10.parquet")
    rel_shards, rel_output = shards.relative_to(root), output.relative_to(root)
    assert news.main(["--shards-dir", str(rel_shards), "--output", str(rel_output), "--no-backup"]) == 0
    assert news.main(["--shards-dir", "../escape", "--output", str(rel_output)]) == 1
    assert "secret" not in capsys.readouterr().err
    assert news.main(["--not-a-flag"]) == 2


@pytest.mark.parametrize("argv", [
    ["--out", "data/out.parquet"],
    ["--no-backup=https://user:secret@example.invalid"],
    ["--output", "--https://user:secret@example.invalid"],
    ["--unknown=https://user:secret@example.invalid"],
])
def test_cli_rejects_abbreviations_and_redacts_parser_errors(repo, capsys, argv):
    assert news.main(argv) == 2
    captured = capsys.readouterr()
    assert "secret" not in captured.out + captured.err
    assert "user:" not in captured.out + captured.err


def test_lock_fsync_failure_preserves_output_and_cleans_owned_lock(repo, monkeypatch, capsys):
    root, shards, output = repo
    output.write_bytes(b"original")
    write_shard(shards, "01-v10.parquet")

    def fail_fsync(fd):
        raise OSError("lock fsync failed")

    monkeypatch.setattr(news.os, "fsync", fail_fsync)
    assert news.main(["--shards-dir", str(shards.relative_to(root)), "--output", str(output.relative_to(root))]) == 1
    assert "Consolidation failed" in capsys.readouterr().err
    assert output.read_bytes() == b"original"
    assert not output.with_suffix(".parquet.bak").exists()
    assert not output.with_name(output.name + ".lock").exists()
    assert not list(output.parent.glob(".*.tmp"))


def test_missing_shards_fails_without_creating_output(repo):
    root, shards, output = repo
    with pytest.raises(FileNotFoundError):
        news.consolidate_shards(shards.relative_to(root), output.relative_to(root))
    assert not output.exists()


def test_cli_runs_without_shell_subprocess(repo, monkeypatch):
    root, shards, output = repo
    write_shard(shards, "01-v10.parquet")
    def forbidden(*args, **kwargs):
        raise AssertionError("subprocess is not used")
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert news.main(["--shards-dir", str(shards.relative_to(root)), "--output", str(output.relative_to(root)), "--no-backup"]) == 0
