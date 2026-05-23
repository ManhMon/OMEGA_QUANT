"""
OMEGA_QUANT Automated Security Scanner (Phase 8)

Purpose:
    Integrate Bandit (AST-based Python security linting) and Safety
    (dependency vulnerability checking) into a single CI/CD-compatible
    scan script. Exits non-zero if any issues are found above threshold.

Contract:
    - Input:  scan targets (paths), severity threshold, optional output dir
    - Output: JSON reports + human-readable summary to stdout
    - Exit:   0 = clean, 1 = issues found, 2 = tool error

Usage:
    python scripts/run_security_scan.py                  # scan all packages
    python scripts/run_security_scan.py --path packages/security
    python scripts/run_security_scan.py --severity medium --output-dir .ly_state/security
    python scripts/run_security_scan.py --fail-on-vuln   # CI mode

Reference:
    - Phase 8: Security & Governance
    - docs/FUNCTIONALITY_GAP_ANALYSIS_20260523.md (P1 gap: automated scanning)

Author: DevOps Engineer (Role 11)
Date: 2026-05-23
Version: 1.0.0
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

# Severity ordering for threshold comparison
_SEVERITY_RANK: dict[str, int] = {"low": 1, "medium": 2, "high": 3}

# Default scan targets (relative to repo root)
_DEFAULT_TARGETS: list[str] = ["packages", "scripts", "src"]


# ---------------------------------------------------------------------------
# Bandit runner
# ---------------------------------------------------------------------------

def run_bandit(
    targets: list[str],
    severity_threshold: str,
    output_path: Path,
) -> tuple[bool, dict[str, Any]]:
    """
    Run Bandit AST security scan.

    Returns:
        (clean, report_dict)  — clean=True means no issues at/above threshold
    """
    cmd = [
        sys.executable, "-m", "bandit",
        "-r",                          # recursive
        "-f", "json",                  # machine-readable output
        "-o", str(output_path),        # write JSON to file
        "--severity-level", severity_threshold,
        "--confidence-level", "medium",
        "--quiet",
    ] + targets

    logger.info("Running Bandit: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Bandit exit codes: 0=no issues, 1=issues found, 2=error
    if result.returncode == 2:
        logger.error("Bandit error:\n%s", result.stderr)
        return False, {"error": result.stderr, "results": []}

    # Parse JSON report
    report: dict[str, Any] = {}
    if output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            report = json.load(f)
    else:
        # Bandit may write to stdout when -o fails on some versions
        try:
            report = json.loads(result.stdout) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            report = {"results": [], "raw_stdout": result.stdout}

    issues = report.get("results", [])
    threshold_rank = _SEVERITY_RANK.get(severity_threshold.lower(), 1)

    # Filter to issues at or above threshold (Bandit already filters, but be explicit)
    flagged = [
        i for i in issues
        if _SEVERITY_RANK.get(i.get("issue_severity", "low").lower(), 1) >= threshold_rank
    ]

    clean = len(flagged) == 0
    report["_flagged_count"] = len(flagged)
    report["_threshold"] = severity_threshold

    if clean:
        logger.info("Bandit: CLEAN (0 issues at severity>=%s)", severity_threshold)
    else:
        logger.warning("Bandit: %d issue(s) at severity>=%s", len(flagged), severity_threshold)
        for issue in flagged:
            logger.warning(
                "  [%s/%s] %s — %s:%s",
                issue.get("issue_severity", "?").upper(),
                issue.get("issue_confidence", "?").upper(),
                issue.get("issue_text", ""),
                issue.get("filename", ""),
                issue.get("line_number", ""),
            )

    return clean, report


# ---------------------------------------------------------------------------
# Safety runner
# ---------------------------------------------------------------------------

def run_safety(output_path: Path) -> tuple[bool, dict[str, Any]]:
    """
    Run Safety dependency vulnerability check.

    Returns:
        (clean, report_dict)  — clean=True means no known CVEs
    """
    cmd = [
        sys.executable, "-m", "safety", "check",
        "--json",
        "--output", str(output_path),
    ]

    logger.info("Running Safety: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Safety exit codes: 0=clean, 1=vulnerabilities found, 64+=error
    if result.returncode >= 64:
        logger.error("Safety error:\n%s", result.stderr or result.stdout)
        return False, {"error": result.stderr or result.stdout, "vulnerabilities": []}

    report: dict[str, Any] = {}
    if output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            try:
                raw = json.load(f)
            except json.JSONDecodeError:
                raw = {}
        # Safety v2+ wraps in {"vulnerabilities": [...]}
        # Safety v1 returns a list directly
        if isinstance(raw, list):
            report = {"vulnerabilities": raw}
        else:
            report = raw
    else:
        try:
            raw = json.loads(result.stdout) if result.stdout.strip() else []
            report = {"vulnerabilities": raw} if isinstance(raw, list) else raw
        except json.JSONDecodeError:
            report = {"vulnerabilities": [], "raw_stdout": result.stdout}

    vulns = report.get("vulnerabilities", [])
    clean = len(vulns) == 0
    report["_vuln_count"] = len(vulns)

    if clean:
        logger.info("Safety: CLEAN (0 known vulnerabilities)")
    else:
        logger.warning("Safety: %d known vulnerability(ies)", len(vulns))
        for v in vulns:
            # Support both Safety v1 list format and v2 dict format
            if isinstance(v, list) and len(v) >= 4:
                logger.warning("  [CVE] %s %s — %s", v[0], v[2], v[3])
            elif isinstance(v, dict):
                logger.warning(
                    "  [CVE] %s %s — %s",
                    v.get("package_name", v.get("name", "?")),
                    v.get("analyzed_version", v.get("version", "?")),
                    v.get("advisory", v.get("description", "")),
                )

    return clean, report


# ---------------------------------------------------------------------------
# Summary writer
# ---------------------------------------------------------------------------

def write_summary(
    bandit_clean: bool,
    bandit_report: dict[str, Any],
    safety_clean: bool,
    safety_report: dict[str, Any],
    output_dir: Path,
    severity_threshold: str,
) -> Path:
    """Write combined JSON summary to output_dir/security_scan_summary.json."""
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "severity_threshold": severity_threshold,
        "overall_clean": bandit_clean and safety_clean,
        "bandit": {
            "clean": bandit_clean,
            "flagged_count": bandit_report.get("_flagged_count", 0),
            "report_file": str(output_dir / "bandit_report.json"),
        },
        "safety": {
            "clean": safety_clean,
            "vuln_count": safety_report.get("_vuln_count", 0),
            "report_file": str(output_dir / "safety_report.json"),
        },
    }

    summary_path = output_dir / "security_scan_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("Summary written to %s", summary_path)
    return summary_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OMEGA_QUANT automated security scanner (Bandit + Safety)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0  All scans clean
  1  Security issues found (use --fail-on-vuln to enforce in CI)
  2  Scanner tool error
""",
    )
    parser.add_argument(
        "--path",
        nargs="+",
        default=_DEFAULT_TARGETS,
        metavar="PATH",
        help="Paths to scan with Bandit (default: packages scripts src)",
    )
    parser.add_argument(
        "--severity",
        choices=["low", "medium", "high"],
        default="medium",
        help="Minimum Bandit severity to flag (default: medium)",
    )
    parser.add_argument(
        "--output-dir",
        default=".ly_state/security",
        metavar="DIR",
        help="Directory for JSON reports (default: .ly_state/security)",
    )
    parser.add_argument(
        "--fail-on-vuln",
        action="store_true",
        help="Exit 1 if any issues found (CI mode)",
    )
    parser.add_argument(
        "--skip-bandit",
        action="store_true",
        help="Skip Bandit AST scan",
    )
    parser.add_argument(
        "--skip-safety",
        action="store_true",
        help="Skip Safety dependency scan",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve scan targets relative to repo root (script lives in scripts/)
    repo_root = Path(__file__).parent.parent
    targets = [str(repo_root / p) for p in args.path if (repo_root / p).exists()]

    if not targets and not args.skip_bandit:
        logger.warning("No valid scan targets found from: %s", args.path)

    bandit_clean = True
    bandit_report: dict[str, Any] = {"results": [], "_flagged_count": 0}

    safety_clean = True
    safety_report: dict[str, Any] = {"vulnerabilities": [], "_vuln_count": 0}

    tool_error = False

    # --- Bandit ---
    if not args.skip_bandit:
        bandit_out = output_dir / "bandit_report.json"
        try:
            bandit_clean, bandit_report = run_bandit(targets, args.severity, bandit_out)
        except FileNotFoundError:
            logger.error(
                "Bandit not found. Install with: pip install bandit"
            )
            tool_error = True

    # --- Safety ---
    if not args.skip_safety:
        safety_out = output_dir / "safety_report.json"
        try:
            safety_clean, safety_report = run_safety(safety_out)
        except FileNotFoundError:
            logger.error(
                "Safety not found. Install with: pip install safety"
            )
            tool_error = True

    if tool_error:
        return 2

    # --- Summary ---
    write_summary(
        bandit_clean, bandit_report,
        safety_clean, safety_report,
        output_dir,
        args.severity,
    )

    overall_clean = bandit_clean and safety_clean

    # Final verdict
    if overall_clean:
        logger.info("SECURITY SCAN PASSED — no issues found")
    else:
        logger.warning(
            "SECURITY SCAN FAILED — Bandit: %d issue(s), Safety: %d vuln(s)",
            bandit_report.get("_flagged_count", 0),
            safety_report.get("_vuln_count", 0),
        )

    if args.fail_on_vuln and not overall_clean:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
