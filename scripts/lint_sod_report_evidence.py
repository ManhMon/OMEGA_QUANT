#!/usr/bin/env python3
"""Lint SoD report evidence with the same validator used by the enforcer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sod_report_evidence import validate_report_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate SoD report evidence wording")
    parser.add_argument("report", type=Path)
    parser.add_argument("--gate", required=True)
    args = parser.parse_args(argv)
    try:
        text = args.report.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"FAIL: {exc}")
        return 1
    valid, errors, canonical = validate_report_evidence(
        text, gate_name=args.gate, report_filename=args.report.name
    )
    if valid:
        print(f"PASS: {'canonical' if canonical else 'legacy'} SoD report evidence")
        return 0
    for error in errors:
        print(f"FAIL: {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
