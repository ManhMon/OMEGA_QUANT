"""Explicit offline shadow CLI; default disabled, static credential-safe errors."""

import argparse
from contextlib import redirect_stdout
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with redirect_stdout(sys.stderr):
    from omega.pipeline.shadow_pipeline import MAX_BYTES, ShadowPipeline, canonical, sandbox_path, strict_json


def run_shadow_pipeline(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--mode", choices=("disabled", "replay", "shadow", "paper"), default="disabled")
    parser.add_argument("--input", required=True)
    parser.add_argument("--state", required=True)
    args = parser.parse_args(argv)
    try:
        path = sandbox_path(args.input, existing=True)
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("input exceeds bound")
        with path.open("rb") as handle:
            request = strict_json(handle.read(MAX_BYTES + 1))
        result = ShadowPipeline(args.state, mode=args.mode).run(request)
        # Runtime JSON needs finite values; stdout contains only validated fields, never exception strings.
        sys.stdout.write(canonical(result).decode("utf-8") + "\n")
        return 0 if result["committed"] and result["readiness_within_limits"] and result["outcome"] != "rejected" else 2
    except (Exception, MemoryError):
        sys.stderr.write("shadow cycle failed; no live action\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(run_shadow_pipeline())
