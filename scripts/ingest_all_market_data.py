"""Deprecated compatibility entry point for canonical market-data ingestion."""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import Optional, Sequence

from scripts import update_market_data


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Translate the legacy CLI boundary and delegate exclusively to the SSOT updater."""
    parser = argparse.ArgumentParser(
        description="DEPRECATED: delegates to scripts/update_market_data.py"
    )
    parser.add_argument("ticker", help="Ticker identifier")
    parser.add_argument("start")
    parser.add_argument("end")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    warnings.warn(
        "scripts/ingest_all_market_data.py is deprecated; use scripts/update_market_data.py",
        DeprecationWarning,
        stacklevel=2,
    )
    canonical_argv = [
        "--symbols", args.ticker.strip().upper(),
        "--start", args.start,
        "--end", args.end,
    ]
    if args.output is not None:
        canonical_argv.extend(["--output", str(args.output)])
    return update_market_data.main(canonical_argv)


if __name__ == "__main__":
    raise SystemExit(main())
