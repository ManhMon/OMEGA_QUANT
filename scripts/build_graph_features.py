"""Build the PIT-safe dated graph feature parquet."""

import argparse
from datetime import timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omega.quant.graph.materialize import MaterializationError, materialize, parse_cutoff_at, write_atomic


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff-at", required=True)
    parser.add_argument("--snapshot-root", default=".ly_state/graph_snapshots")
    parser.add_argument("--output-root", default=".ly_state/graph_features")
    args = parser.parse_args(argv)
    try:
        cutoff = parse_cutoff_at(args.cutoff_at)
        features, counters = materialize(cutoff, args.snapshot_root)
        signal_date = cutoff.tz_convert("Asia/Ho_Chi_Minh").date()
        target = Path(args.output_root) / f"graph_features_{signal_date:%Y%m%d}.parquet"
        write_atomic(features, target)
    except (MaterializationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"counters={counters.as_dict()}")
    print(f"target={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
