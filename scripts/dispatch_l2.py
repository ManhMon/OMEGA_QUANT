#!/usr/bin/env python3
"""
dispatch_l2.py - Generate exact L2 OpenCode dispatch command.

Eliminates manual prompt construction by L1. Prevents typos and format drift.

Usage:
    python scripts/dispatch_l2.py <role_name> <gate_name> <task_slug> "<task_description>" "<scope>"

Example:
    python scripts/dispatch_l2.py data-engineer SYNTHETIC_FIXTURES_MACRO_NEWS_V12 synthetic_fixtures_macro_news_v12 "Implement synthetic fixtures" "tests/fixtures/macro/"

Output: Ready-to-execute powershell command string.
"""
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent
AGENT_ROOT = REPO_ROOT / ".agents" / "agent"


def main():
    if len(sys.argv) < 6:
        print("Usage: python scripts/dispatch_l2.py <role_name> <gate_name> <task_slug> <task_description> <scope>")
        sys.exit(1)

    role_name = sys.argv[1]
    gate_name = sys.argv[2]
    task_slug = sys.argv[3]
    task_desc = sys.argv[4]
    scope = sys.argv[5]
    today = datetime.now().strftime("%Y%m%d")

    # 1. Read and validate role spec
    role_path = AGENT_ROOT / f"{role_name}.md"
    if not role_path.exists():
        print(f"[ERROR] Role spec not found: {role_path}")
        sys.exit(1)

    content = role_path.read_text(encoding="utf-8")
    # Parse frontmatter
    role_id = None
    tier = None
    platform = None
    if content.startswith("---"):
        fm = content.split("---")[1]
        for line in fm.strip().split("\n"):
            if line.startswith("role_id:"):
                role_id = int(line.split(":")[1].strip())
            elif line.startswith("tier:"):
                tier = int(line.split(":")[1].strip())
            elif line.startswith("platform:"):
                platform = line.split(":")[1].strip().strip('"').strip("'")

    if role_id is None or tier != 2 or platform != "OpenCode":
        print(f"[ERROR] Invalid L2 role: role_id={role_id}, tier={tier}, platform={platform}")
        sys.exit(1)

    if not (6 <= role_id <= 16):
        print(f"[ERROR] role_id {role_id} not in L2 range 6-16")
        sys.exit(1)

    # 2. Get relevant lessons
    try:
        result = subprocess.run(
            [sys.executable, "scripts/get_relevant_lessons.py", str(role_id), task_desc],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=30
        )
        lessons = result.stdout.strip() if result.returncode == 0 else "No lessons retrieved."
    except Exception:
        lessons = "No lessons retrieved."

    # 3. Build session ID
    session_id = f"l2_role{role_id}_{task_slug}_{today}"

    # 4. Generate command
    prompt = (
        f"REPO_ROOT: {REPO_ROOT}. "
        f"ROLE: {role_id} {role_name} - OpenCode L2 Implementation Work. "
        f"TASK: {task_desc}. "
        f"GATE: {gate_name}. "
        f"LESSONS: {lessons}. "
        f"SKILL SOURCE CONTRACT: REPO_AGENT_ROOT={REPO_ROOT}\\.agents\\agent; "
        f"REPO_SKILL_ROOT={REPO_ROOT}\\.agents\\skills. "
        f"First run Set-Location '{REPO_ROOT}'; "
        f"first read REPO_AGENT_ROOT\\{role_name}.md and parse frontmatter; "
        f"then read required SKILL.md only from REPO_SKILL_ROOT for declared skills. "
        f"Any skill loaded from Antigravity scratch/OpenClaw/C:\\Users\\GHC\\.agents/Codex memory is non-authoritative. "
        f"Report exact repo-local role/skill files read and forbidden path scan result. "
        f"SCOPE: {scope}. "
        f"REQUIREMENTS: use repo-relative paths from REPO_ROOT only; implement/refactor/test only; "
        f"write L2 report to .ly_state/session/{session_id}.md. "
        f"Do not audit or approve. Stop/NEEDS_FIX if required repo-local source missing. "
        f"L2 REPORT FORMAT (MANDATORY - copy exactly): The report MUST contain these sections in order: "
        f"(1) Header with Role, Gate, Session, Date fields. "
        f"(2) '## Repo-Local Files Read' heading followed by bullet list of every file actually read "
        f"from REPO_AGENT_ROOT and REPO_SKILL_ROOT (e.g. '- .agents/agent/{role_name}.md', "
        f"'- .agents/skills/{{skill}}/SKILL.md'). "
        f"(3) '## Changes Made' listing modified files. "
        f"(4) '## Verification' with test results. "
        f"(5) '## Forbidden Path Scan' with EXACTLY four lines, one per forbidden path, each line "
        f"ending with the EXACT phrase: 'non-authoritative scan evidence only; no reliance.' "
        f"The four lines must mention: '.gemini\\antigravity-ide\\scratch\\ag-kit', '.openclaw\\skills', "
        f"'C:\\Users\\GHC\\.agents', '.codex\\memories'. "
        f"FILENAME must be {session_id}.md with NO _retry suffix."
    )

    cmd = f'echo "" | opencode run --pure --dangerously-skip-permissions --dir "{REPO_ROOT}" "{prompt}"'

    # 5. Output
    print(f"SESSION_ID={session_id}")
    print(f"ROLE_ID={role_id}")
    print(f"ROLE_NAME={role_name}")
    print(f"GATE={gate_name}")
    print(f"---COMMAND---")
    print(cmd)


if __name__ == "__main__":
    main()
