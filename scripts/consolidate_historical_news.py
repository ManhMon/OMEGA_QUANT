#!/usr/bin/env python3
"""Consolidate validated historical news parquet shards into one dataset."""
from __future__ import annotations

import argparse
import hashlib
from itertools import islice
import math
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parent.parent
SHARDS_DIR = Path("data/historical_news/run_703_full")
DEFAULT_OUTPUT = Path("data/news_sentiment_2015_now.parquet")
# ponytail: logical workload ceilings, not a peak-RSS guarantee; stream when these no longer fit.
MAX_SHARDS = 1_000
MAX_ROWS = 5_000_000
MAX_BYTES = 1_000_000_000
SCHEMA = pa.schema([
    pa.field("symbol", pa.string()),
    pa.field("title", pa.string()),
    pa.field("publish_time", pa.timestamp("us", tz="UTC")),
    pa.field("sentiment_score", pa.float64()),
    pa.field("available_at", pa.timestamp("us", tz="UTC")),
    pa.field("url", pa.string()),
    pa.field("source", pa.string(), nullable=False),
    pa.field("fetched_at", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("raw_timestamp", pa.string()),
    pa.field("payload_sha256", pa.string(), nullable=False),
    pa.field("parser_version", pa.string(), nullable=False),
    pa.field("legacy_row", pa.bool_(), nullable=False),
])
_TIMESTAMP_COLUMNS = ("publish_time", "fetched_at", "available_at")
_DEDUP_COLUMNS = ("symbol", "publish_time", "payload_sha256")


def _repo_path(path: Path) -> Path:
    path = Path(path)
    root = REPO_ROOT.resolve(strict=True)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Paths must be repo-relative and confined to the repository")
    candidate = root / path
    current = root
    for part in path.parts:
        if part in ("", "."):
            continue
        current /= part
        if current.is_symlink():
            raise ValueError("Symlink paths are not allowed")
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError("Path escapes the repository")
    return candidate


def _check_path(path: Path, *, directory: bool = False) -> None:
    _repo_path(path.relative_to(REPO_ROOT.resolve(strict=True)))
    if path.exists() and (path.is_symlink() or (not path.is_dir() if directory else not path.is_file())):
        raise ValueError("Expected a regular file or directory")
    if not directory and path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Expected a regular file")


def _check_schema(path: Path) -> tuple[int, int]:
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    if schema.names != SCHEMA.names:
        raise ValueError("Shard schema columns do not match producer v10")
    for actual, expected in zip(schema, SCHEMA):
        actual_type = actual.type
        expected_type = expected.type
        if pa.types.is_timestamp(expected_type):
            valid_type = pa.types.is_timestamp(actual_type) and actual_type.tz is not None
        else:
            valid_type = actual_type == expected_type
        if not valid_type or actual.nullable != expected.nullable:
            raise ValueError("Shard schema types do not match producer v10")
    metadata = parquet.metadata
    return metadata.num_rows, sum(metadata.row_group(i).total_byte_size for i in range(metadata.num_row_groups))


def _validate_frame(df: pd.DataFrame) -> pd.DataFrame:
    if list(df.columns) != SCHEMA.names:
        raise ValueError("Shard columns do not match producer v10")
    for name in _TIMESTAMP_COLUMNS:
        try:
            df[name] = df[name].dt.tz_convert("UTC")
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("News timestamps must be timezone-aware") from exc
        if df[name].isna().any():
            raise ValueError("News timestamps cannot be null")
    for name in ("symbol", "source", "parser_version"):
        values = df[name]
        if values.isna().any() or values.str.strip().eq("").any():
            raise ValueError(f"Required field {name} cannot be null or blank")
    if df["payload_sha256"].isna().any() or not df["payload_sha256"].str.fullmatch(r"[0-9a-fA-F]{64}").all():
        raise ValueError("payload_sha256 must contain 64 hexadecimal characters")
    df["payload_sha256"] = df["payload_sha256"].str.lower()
    if df["legacy_row"].isna().any() or not df["legacy_row"].isin([True, False]).all():
        raise ValueError("legacy_row must contain non-null booleans")
    scores = df["sentiment_score"]
    if scores.isna().any() or not scores.map(lambda value: math.isfinite(value) and -1 <= value <= 1).all():
        raise ValueError("sentiment_score must be finite and within [-1, 1]")
    if not ((df["publish_time"] <= df["fetched_at"]) & (df["fetched_at"] <= df["available_at"])).all():
        raise ValueError("News timestamps violate publish_time <= fetched_at <= available_at")
    return df


def _same_file(left: Path, right: Path) -> bool:
    return left.resolve(strict=False) == right.resolve(strict=False) or (
        left.exists() and right.exists() and os.path.samefile(left, right)
    )


def _check_destinations(output: Path, backup_path: Path, shards: list[Path], backup: bool) -> None:
    destinations = [output, backup_path] if backup else [output]
    for destination in destinations:
        _check_path(destination)
        if any(_same_file(path, destination) for path in shards):
            raise ValueError("Input, output, and backup paths must be distinct files")
    if backup and _same_file(output, backup_path):
        raise ValueError("Output and backup paths must be distinct files")


def _file_state(path: Path) -> tuple[int, int, int, int, int]:
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _shard_paths(directory: Path) -> list[Path]:
    paths = list(islice(directory.glob("*-v10.parquet"), MAX_SHARDS + 1))
    if len(paths) > MAX_SHARDS:
        raise ValueError("Shard count exceeds configured limit")
    return sorted(paths)


def _snapshot_unchanged(directory: Path, states: dict, digests: dict) -> None:
    if _shard_paths(directory) != list(states):
        raise RuntimeError("Shard set changed during consolidation")
    for path, state in states.items():
        _check_path(path)
        if _file_state(path) != state:
            raise RuntimeError("A shard changed during consolidation")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != digests[path] or _file_state(path) != state:
            raise RuntimeError("A shard changed during consolidation")


def _fsync_file(path: Path) -> None:
    fd = os.open(path, os.O_RDWR)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_directory(path: Path) -> None:
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _replace_file(source: Path, destination: Path) -> None:
    _check_path(destination)
    os.replace(source, destination)
    _fsync_directory(destination.parent)


def consolidate_shards(
    shards_dir: Path = SHARDS_DIR,
    output_file: Path = DEFAULT_OUTPUT,
    backup: bool = True,
) -> pd.DataFrame:
    shards_dir = _repo_path(shards_dir)
    output_file = _repo_path(output_file)
    _check_path(shards_dir, directory=True)
    _check_path(output_file)
    if not shards_dir.is_dir():
        raise ValueError("Shard path must be a directory")
    shard_paths = _shard_paths(shards_dir)
    if not shard_paths:
        raise FileNotFoundError("No v10 parquet shards found")
    if any(path.is_symlink() for path in shard_paths):
        raise ValueError("Symlink shards are not allowed")
    backup_path = output_file.with_suffix(".parquet.bak")
    lock_path = output_file.with_name(output_file.name + ".lock")
    _check_destinations(output_file, backup_path, shard_paths, backup)
    if output_file.parent == shards_dir and output_file.match("*-v10.parquet"):
        raise ValueError("Output cannot be a shard path")
    shard_states = {path: _file_state(path) for path in shard_paths}

    rows = 0
    total_bytes = 0
    for path in shard_paths:
        _check_path(path)
        shard_rows, shard_bytes = _check_schema(path)
        rows += shard_rows
        total_bytes += max(path.stat().st_size, shard_bytes)
        if rows > MAX_ROWS or total_bytes > MAX_BYTES:
            raise ValueError("Shard data exceeds configured resource limits")
    if rows == 0:
        raise ValueError("All shard files are empty")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    _check_destinations(output_file, backup_path, shard_paths, backup)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("Consolidation output is locked") from exc
    owner = os.fstat(fd)
    try:
        os.fsync(fd)
        frames = []
        shard_digests = {}
        for path in shard_paths:
            _check_path(path)
            if _file_state(path) != shard_states[path]:
                raise RuntimeError("A shard changed during consolidation")
            with path.open("rb") as stream:
                shard_digests[path] = hashlib.file_digest(stream, "sha256").hexdigest()
                stream.seek(0)
                table = pq.ParquetFile(stream).read()
            if _file_state(path) != shard_states[path]:
                raise RuntimeError("A shard changed during consolidation")
            frame = _validate_frame(table.to_pandas())
            frames.append(frame)
        unified = pd.concat(frames, ignore_index=True)
        duplicate_rows = unified.duplicated(subset=list(_DEDUP_COLUMNS), keep=False)
        if duplicate_rows.any():
            duplicate_frame = unified.loc[duplicate_rows]
            if duplicate_frame.drop_duplicates().duplicated(subset=list(_DEDUP_COLUMNS), keep=False).any():
                raise ValueError("Conflicting rows share a deduplication key")
        unified = unified.drop_duplicates(subset=list(_DEDUP_COLUMNS), keep="first")
        unified = unified.sort_values(["publish_time", "symbol"], kind="mergesort").reset_index(drop=True)

        _check_destinations(output_file, backup_path, shard_paths, backup)
        temp_fd, temp_name = tempfile.mkstemp(prefix=f".{output_file.name}.", suffix=".tmp", dir=output_file.parent)
        os.close(temp_fd)
        temp_output = Path(temp_name)
        temp_backup = None
        try:
            table = pa.Table.from_pandas(unified, schema=SCHEMA, preserve_index=False, safe=True)
            pq.write_table(table, temp_output)
            _fsync_file(temp_output)
            if backup and output_file.exists():
                backup_fd, name = tempfile.mkstemp(prefix=f".{backup_path.name}.", suffix=".tmp", dir=backup_path.parent)
                os.close(backup_fd)
                temp_backup = Path(name)
                shutil.copy2(output_file, temp_backup)
                _fsync_file(temp_backup)
                _check_destinations(output_file, backup_path, shard_paths, backup)
                _snapshot_unchanged(shards_dir, shard_states, shard_digests)
                _replace_file(temp_backup, backup_path)
                temp_backup = None
            _check_destinations(output_file, backup_path, shard_paths, backup)
            _snapshot_unchanged(shards_dir, shard_states, shard_digests)
            _replace_file(temp_output, output_file)
        finally:
            for temporary in (temp_output, temp_backup):
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return unified
    finally:
        os.close(fd)
        try:
            current = lock_path.lstat()
            if (current.st_dev, current.st_ino) == (owner.st_dev, owner.st_ino):
                lock_path.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consolidate historical news shards", allow_abbrev=False, exit_on_error=False)
    parser.add_argument("--shards-dir", type=Path, default=SHARDS_DIR, help="Repo-relative directory containing *-v10.parquet")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Repo-relative consolidated parquet file")
    parser.add_argument("--no-backup", action="store_true", help="Do not backup existing output file")
    try:
        args, unknown = parser.parse_known_args(argv)
    except argparse.ArgumentError:
        print("Consolidation failed: invalid command-line arguments.", file=sys.stderr)
        return 2
    except SystemExit as exc:
        return int(exc.code)
    if unknown:
        print("Consolidation failed: invalid command-line arguments.", file=sys.stderr)
        return 2
    try:
        df = consolidate_shards(args.shards_dir, args.output, backup=not args.no_backup)
        if df.empty:
            print("Consolidation failed: no validated rows.", file=sys.stderr)
            return 1
        print(f"Consolidated {len(df)} rows across {df['symbol'].nunique()} symbols.")
        print(f"Date range: {df['publish_time'].min()} to {df['publish_time'].max()}")
        print(f"Average sentiment: {df['sentiment_score'].mean():.4f} (std: {df['sentiment_score'].std():.4f})")
        print(f"Positive: {(df['sentiment_score'] > 0).sum()} | Negative: {(df['sentiment_score'] < 0).sum()} | Neutral: {(df['sentiment_score'] == 0).sum()}")
        return 0
    except (OSError, ValueError, RuntimeError, pa.ArrowException, pd.errors.ParserError):
        print("Consolidation failed: validation or I/O error.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
