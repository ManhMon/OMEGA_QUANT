#!/usr/bin/env python3
"""Explicit auxiliary lesson extraction sidecar."""

import argparse

from extract_lessons import extract_lessons


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract lessons into the canonical JSONL artifact")
    parser.add_argument("--provider-mode", choices=("remote-api", "fallback-only"),
                        default="fallback-only")
    args = parser.parse_args(argv)
    return extract_lessons(provider_mode=args.provider_mode)


if __name__ == "__main__":
    raise SystemExit(main())
