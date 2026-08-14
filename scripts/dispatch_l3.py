#!/usr/bin/env python3
"""
dispatch_l3.py - Generate exact L3 Codex audit dispatch command.

Usage:
    python scripts/dispatch_l3.py <l3_role_name> <gate_name> <l2_session_id> <l2_role_name> "<scope>" [--risk low|high]

Example:
    python scripts/dispatch_l3.py code-reviewer SYNTHETIC_FIXTURES_MACRO_NEWS_V12 l2_role15_synthetic_fixtures_macro_news_v12_20260814 data-engineer "tests/fixtures/macro/"
    python scripts/dispatch_l3.py code-reviewer MY_GATE l2_role9_fix_20260814 backend-engineer "src/omega/" --risk high

Risk levels:
    low  = test fixtures, docs, config-only (uses cx/gpt-5.6-sol for ~50% token savings)
    high = production logic, security, data pipeline (uses cx/gpt-5.6-sol(max), default)

Output: Ready-to-execute powershell command + pre-created audit report file.
"""
import sys
import json
import re
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent
AGENT_ROOT = REPO_ROOT / ".agents" / "agent"

MODELS = {
    "low": "cx/gpt-5.6-sol",
    "high": "cx/gpt-5.6-sol(max)",
}


def parse_frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    fm = content.split("---")[1]
    result = {}
    for line in fm.strip().split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip().strip("'\"")
            try:
                v = int(v)
            except ValueError:
                pass
            result[k.strip()] = v
    return result


def main():
    if len(sys.argv) < 6:
        print("Usage: python scripts/dispatch_l3.py <l3_role_name> <gate_name> <l2_session_id> <l2_role_name> <scope> [--risk low|high]")
        sys.exit(1)

    l3_role_name = sys.argv[1]
    gate_name = sys.argv[2]
    l2_session_id = sys.argv[3]
    l2_role_name = sys.argv[4]
    scope = sys.argv[5]
    risk = "high"

    for i, arg in enumerate(sys.argv):
        if arg == "--risk" and i + 1 < len(sys.argv):
            risk = sys.argv[i + 1]

    if risk not in MODELS:
        print(f"[ERROR] Invalid risk level: {risk}. Use 'low' or 'high'.")
        sys.exit(1)

    model = MODELS[risk]
    today = datetime.now().strftime("%Y%m%d")

    # 1. Validate L3 role
    l3_role_path = AGENT_ROOT / f"{l3_role_name}.md"
    if not l3_role_path.exists():
        print(f"[ERROR] L3 role spec not found: {l3_role_path}")
        sys.exit(1)

    l3_fm = parse_frontmatter(l3_role_path.read_text(encoding="utf-8"))
    l3_role_id = l3_fm.get("role_id")
    l3_tier = l3_fm.get("tier")
    l3_platform = l3_fm.get("platform")

    if l3_tier != 3 or l3_platform != "Codex":
        print(f"[ERROR] Not an L3 role: tier={l3_tier}, platform={l3_platform}")
        sys.exit(1)
    if not (17 <= l3_role_id <= 30):
        print(f"[ERROR] role_id {l3_role_id} not in L3 range 17-30")
        sys.exit(1)

    # 2. Validate L2 role
    l2_role_path = AGENT_ROOT / f"{l2_role_name}.md"
    if not l2_role_path.exists():
        print(f"[ERROR] L2 role spec not found: {l2_role_path}")
        sys.exit(1)

    l2_fm = parse_frontmatter(l2_role_path.read_text(encoding="utf-8"))
    l2_role_id = l2_fm.get("role_id")

    if l2_role_id == l3_role_id:
        print(f"[ERROR] Writer == Auditor! l2_role_id={l2_role_id} == l3_role_id={l3_role_id}")
        sys.exit(1)

    # 3. Build IDs
    gate_slug = gate_name.lower()
    l3_session_id = f"l3_role{l3_role_id}_{gate_slug}_{today}"
    report_path = f".ly_state/session/audit_reports/role{l3_role_id}_{gate_slug}_{today}.md"

    # 4. Pre-create audit report file
    report_full = REPO_ROOT / report_path
    report_full.parent.mkdir(parents=True, exist_ok=True)
    report_full.touch()

    # 5. Get lessons
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, "scripts/get_relevant_lessons.py", str(l3_role_id), gate_name],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=30
        )
        lessons = result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        lessons = ""

    # 6. Build prompt
    prompt = (
        f"REPO_ROOT: {REPO_ROOT}. "
        f"ROLE: {l3_role_id} {l3_role_name} - Codex L3 Independent Review. "
        f"GATE: {gate_name}. "
        f"L2_SESSION: {l2_session_id}. L2_ROLE: {l2_role_id} {l2_role_name}. "
        f"SKILL SOURCE CONTRACT: REPO_AGENT_ROOT={REPO_ROOT}\\.agents\\agent; "
        f"REPO_SKILL_ROOT={REPO_ROOT}\\.agents\\skills. "
        f"First read REPO_AGENT_ROOT\\{l3_role_name}.md and parse frontmatter; "
        f"read required SKILL.md only from REPO_SKILL_ROOT. "
        f"Any skill from Antigravity scratch/OpenClaw/C:\\Users\\GHC\\.agents/Codex memory is non-authoritative. "
        f"Report exact repo-local files read and forbidden path scan result. "
        f"SCOPE: {scope}. "
        f"REQUIREMENTS: first run Set-Location '{REPO_ROOT}'; "
        f"use repo-relative paths from REPO_ROOT only; never read/write Antigravity scratch paths. "
        f"AUDIT EVIDENCE CHECKLIST: "
        f"1. Verify l2_role_id={l2_role_id} != l3_role_id={l3_role_id}. "
        f"2. Verify code changes match approved scope. "
        f"3. Run all tests. "
        f"4. Check PIT safety, no look-ahead bias. "
        f"5. Validate SOD boundaries. "
        f"6. Verify L2 report lists repo-local skill source evidence. "
        f"VERDICT: Write [APPROVED] or [NEEDS_FIX] to {report_path}. "
        f"GATE UPDATE: Run this exact command to update the gate (do NOT edit phase_gates.json manually): "
        f"python scripts/update_gate.py {gate_name} "
        f"l2_session_id={l2_session_id} l2_role_id={l2_role_id} l2_role_name={l2_role_name} "
        f"l3_session_id={l3_session_id} l3_role_id={l3_role_id} l3_role_name={l3_role_name} "
        f"audit_report_path={report_path} final_verdict=[verdict] "
        f"sod_boundary_checked=true writer_auditor_separated=true l2_completed=true. "
        f"LESSONS: {lessons}. "
        f"FINAL STEP: L1 must run 'python scripts/sod_gate_enforcer.py' after gate update."
    )

    cmd = (
        f'New-Item -ItemType File -Path {report_path.replace("/", chr(92))} -Force; '
        f'echo "{prompt}" | codex exec -m "{model}" -s danger-full-access --dangerously-bypass-approvals-and-sandbox'
    )

    # 7. Output
    print(f"L3_SESSION_ID={l3_session_id}")
    print(f"L3_ROLE_ID={l3_role_id}")
    print(f"L3_ROLE_NAME={l3_role_name}")
    print(f"L2_ROLE_ID={l2_role_id}")
    print(f"L2_ROLE_NAME={l2_role_name}")
    print(f"MODEL={model}")
    print(f"RISK={risk}")
    print(f"REPORT={report_path}")
    print(f"GATE={gate_name}")
    print(f"---COMMAND---")
    print(cmd)


if __name__ == "__main__":
    main()
