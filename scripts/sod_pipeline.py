#!/usr/bin/env python3
"""
sod_pipeline.py - Full L2→validate→L3→enforcer pipeline in one command.

Eliminates L1 intermediate wake-ups between steps, saving ~80K context tokens per gate.

Usage:
    python scripts/sod_pipeline.py <l2_role> <l3_role> <gate> <slug> "<task>" "<scope>" [--risk low|high] [--dry-run]

Example:
    python scripts/sod_pipeline.py data-engineer code-reviewer SYNTHETIC_FIXTURES tests/fixtures "Implement fixtures" "tests/fixtures/" --risk low

Stages:
    1. Dispatch L2 OpenCode (waits for completion)
    2. Run validate_l2_report.py (blocks L3 if fail)
    3. Dispatch L3 Codex (waits for completion)
    4. Run sod_gate_enforcer.py

Exit codes:
    0 = Full pipeline PASS
    1 = L2 validation failed (L3 not dispatched)
    2 = L3 audit [NEEDS_FIX]
    3 = Enforcer failed
"""
import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent


def run(cmd, desc, check=True):
    print(f"\n{'='*60}")
    print(f"  STAGE: {desc}")
    print(f"{'='*60}")
    print(f"  CMD: {cmd[:120]}...")
    result = subprocess.run(
        cmd, shell=True, cwd=str(REPO_ROOT),
        capture_output=False, text=True
    )
    if check and result.returncode != 0:
        print(f"\n[FAIL] {desc} — exit code {result.returncode}")
    return result.returncode


def capture(cmd):
    result = subprocess.run(
        cmd, shell=True, cwd=str(REPO_ROOT),
        capture_output=True, text=True
    )
    return result.returncode, result.stdout.strip()


def parse_dispatch_output(output):
    """Extract key=value pairs from dispatch script output."""
    meta = {}
    for line in output.split("\n"):
        if "=" in line and not line.startswith("---"):
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip()
    return meta


def main():
    if len(sys.argv) < 7:
        print("Usage: python scripts/sod_pipeline.py <l2_role> <l3_role> <gate> <slug> <task> <scope> [--risk low|high] [--dry-run]")
        sys.exit(1)

    l2_role = sys.argv[1]
    l3_role = sys.argv[2]
    gate = sys.argv[3]
    slug = sys.argv[4]
    task = sys.argv[5]
    scope = sys.argv[6]
    risk = "high"
    dry_run = False

    for i, arg in enumerate(sys.argv):
        if arg == "--risk" and i + 1 < len(sys.argv):
            risk = sys.argv[i + 1]
        if arg == "--dry-run":
            dry_run = True

    today = datetime.now().strftime("%Y%m%d")

    print(f"\n{'#'*60}")
    print(f"  SOD PIPELINE: {gate}")
    print(f"  L2: {l2_role} -> L3: {l3_role} -> Enforcer")
    print(f"  Risk: {risk}")
    print(f"{'#'*60}")

    # Stage 1: Generate L2 dispatch command
    rc, l2_out = capture(
        f'{sys.executable} scripts/dispatch_l2.py {l2_role} {gate} {slug} "{task}" "{scope}"'
    )
    if rc != 0:
        print(f"[FAIL] dispatch_l2.py failed: {l2_out}")
        sys.exit(1)

    l2_meta = parse_dispatch_output(l2_out)
    session_id = l2_meta.get("SESSION_ID", f"l2_role0_{slug}_{today}")
    role_id = l2_meta.get("ROLE_ID", "0")

    if dry_run:
        print(f"\n[DRY-RUN] Would dispatch L2:\n{l2_out}")
        print(f"\n[DRY-RUN] Then validate, dispatch L3 ({risk}), then enforcer.")
        sys.exit(0)

    # Extract command from output
    cmd_lines = l2_out.split("---COMMAND---\n")
    if len(cmd_lines) < 2:
        print(f"[FAIL] Could not extract L2 command from dispatch output")
        sys.exit(1)
    l2_cmd = cmd_lines[1].strip()

    # Stage 1: Run L2
    rc = run(l2_cmd, f"L2 OpenCode: {l2_role}")
    if rc != 0:
        print(f"[FAIL] L2 exited {rc}")
        sys.exit(1)

    # Stage 2: Validate L2 report
    rc = run(
        f'{sys.executable} scripts/validate_l2_report.py {session_id} {role_id} {l2_role}',
        "Pre-L3 Validation"
    )
    if rc != 0:
        print(f"\n[BLOCKED] L2 report validation failed. Fix L2 report and re-run pipeline.")
        print(f"  Report: .ly_state/session/{session_id}.md")
        sys.exit(1)

    # Stage 3: Generate and run L3
    rc, l3_out = capture(
        f'{sys.executable} scripts/dispatch_l3.py {l3_role} {gate} {session_id} {l2_role} "{scope}" --risk {risk}'
    )
    if rc != 0:
        print(f"[FAIL] dispatch_l3.py failed: {l3_out}")
        sys.exit(1)

    l3_meta = parse_dispatch_output(l3_out)
    l3_cmd_lines = l3_out.split("---COMMAND---\n")
    if len(l3_cmd_lines) < 2:
        print(f"[FAIL] Could not extract L3 command")
        sys.exit(1)
    l3_cmd = l3_cmd_lines[1].strip()

    rc = run(l3_cmd, f"L3 Codex Audit: {l3_role} (model: {l3_meta.get('MODEL', risk)})")
    # L3 exit code 0 doesn't mean APPROVED — check verdict
    report_path = l3_meta.get("REPORT", "")
    if report_path and Path(report_path).exists():
        content = Path(report_path).read_text(encoding="utf-8")
        if "[NEEDS_FIX]" in content:
            print(f"\n[NEEDS_FIX] L3 audit returned NEEDS_FIX.")
            print(f"  Report: {report_path}")
            print(f"  Next: Run extract_lessons.py, fix, re-run pipeline.")
            sys.exit(2)
        elif "[APPROVED]" not in content:
            print(f"\n[WARN] No clear verdict found in {report_path}")
            sys.exit(2)

    # Stage 4: Enforcer
    rc = run(f'{sys.executable} scripts/sod_gate_enforcer.py', "SoD Gate Enforcer")
    if rc != 0:
        print(f"\n[FAIL] Enforcer exit {rc}")
        sys.exit(3)

    print(f"\n{'='*60}")
    print(f"  ✅ PIPELINE COMPLETE: {gate}")
    print(f"  L2: {session_id}")
    print(f"  L3: {l3_meta.get('L3_SESSION_ID', 'unknown')}")
    print(f"  Verdict: [APPROVED]")
    print(f"  Enforcer: [PASS]")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
