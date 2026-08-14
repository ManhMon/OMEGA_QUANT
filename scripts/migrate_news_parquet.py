"""Atomically migrate a news sentiment parquet file to schema v10."""

import argparse
import sys
from pathlib import Path

import pyarrow.parquet as pq

sys.path[:0] = [".", "src"]

try:
    from scripts.fetch_news_sentiment import SCHEMA, migrate_news_sentiment_schema
except ModuleNotFoundError:
    from fetch_news_sentiment import SCHEMA, migrate_news_sentiment_schema


def migrate_news_parquet(path: Path) -> Path:
    table = migrate_news_sentiment_schema(pq.read_table(path))
    if table.schema != SCHEMA or table.num_rows != pq.read_metadata(path).num_rows:
        raise ValueError("news parquet migration validation failed")
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, temporary)
    if pq.read_table(temporary).schema != SCHEMA:
        raise ValueError("news parquet temporary migration validation failed")
    temporary.replace(path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate news parquet to schema v10")
    parser.add_argument("path", type=Path)
    migrate_news_parquet(parser.parse_args().path)


if __name__ == "__main__":
    main()
