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

try:
    from scripts.dispatch_l2 import (
        ADVERSARIAL_DIRECTIVE_16D,
        build_lessons_data_block,
        build_graph_prompt_evidence,
        build_verified_prompt_read_statement,
        ensure_session_containment,
        load_sanitized_lesson_entries,
        ps_quote,
        write_prompt_with_sha256,
        acquire_session_lock,
        release_session_lock,
        run_graph_predispatch_gate,
        validate_identifier,
    )
except ImportError:  # direct script execution: python scripts/dispatch_l3.py
    from dispatch_l2 import (
        ADVERSARIAL_DIRECTIVE_16D,
        build_lessons_data_block,
        build_graph_prompt_evidence,
        build_verified_prompt_read_statement,
        ensure_session_containment,
        load_sanitized_lesson_entries,
        ps_quote,
        write_prompt_with_sha256,
        acquire_session_lock,
        release_session_lock,
        run_graph_predispatch_gate,
        validate_identifier,
    )

REPO_ROOT = Path(__file__).parent.parent
AGENT_ROOT = REPO_ROOT / ".agents" / "agent"

MODELS = {
    "low": "cx/gpt-5.6-sol(medium)",
    "medium": "cx/gpt-5.6-sol(xhigh)",
    "high": "cx/gpt-5.6-sol(max)",
    # fallback khi GPT 429: 9router/ag/gemini-3.7-flash-high
}
VALID_RISK_LEVELS = ("low", "high")

# Deep audit (final advisory, L1 dispatch trực tiếp qua codex exec)
DEEPAUDIT_MODEL = "cx/gpt-5.6-sol(max)"
DEEPAUDIT_FALLBACK = "9router/ag/gemini-3.7-flash-high"  # dùng khi DEEPAUDIT_MODEL bị 429


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


HIGH_RISK_PATTERNS = [
    "macro_pipeline", "macro_news_pipeline",  # complex data pipelines
    "playwright", "sbv", "transport",         # WAF/browser/network
    "migration", "merge", "parquet",          # data persistence
    "llm", "alpha",                           # LLM/alpha logic
]
MEDIUM_RISK_PATTERNS = [
    "src/", ".py",                            # standard production source
]
LOW_RISK_PATTERNS = [
    "tests/fixtures/", "fixture",             # test fixtures only
    ".md", ".json", ".txt",                   # docs/config
    "requirements.txt", ".gitattributes",     # build config
    "tests/"                                  # general tests
]


def infer_risk(scope: str) -> tuple[str, str]:
    """Return (risk, reason) based on scope content."""
    scope_lower = scope.lower()
    high_matches = [p for p in HIGH_RISK_PATTERNS if p in scope_lower]
    medium_matches = [p for p in MEDIUM_RISK_PATTERNS if p in scope_lower]
    low_matches = [p for p in LOW_RISK_PATTERNS if p in scope_lower]

    if high_matches:
        return "high", f"high-risk patterns: {high_matches[:2]}"
    if medium_matches:
        return "medium", f"medium-risk patterns: {medium_matches[:2]}"
    if low_matches:
        return "low", f"low-risk patterns: {low_matches[:2]}"
    return "medium", "no pattern match, defaulting to medium"


def parse_cli_args(args: list[str]) -> tuple[str, str, str, str, str, str | None, bool]:
    """Strictly parse five positionals plus optional --risk/--run (each once).
    Reject unknown/duplicate/dangling/assignment-form/extra tokens with exit 2."""
    if any(not isinstance(arg, str) or re.search(r"[\x00-\x1f\x7f-\x9f]", arg) for arg in args):
        print("[ERROR] CLI arguments must be control-free strings.", file=sys.stderr)
        sys.exit(2)
    pos_args: list[str] = []
    explicit_risk: str | None = None
    run_mode = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--risk":
            if explicit_risk is not None:
                print("[ERROR] Duplicate --risk flag provided.", file=sys.stderr)
                sys.exit(2)
            if i + 1 >= len(args):
                print("[ERROR] Flag --risk requires a value: 'low' or 'high'", file=sys.stderr)
                sys.exit(2)
            val = args[i + 1]
            if val not in VALID_RISK_LEVELS:
                print(f"[ERROR] Invalid risk level: '{val}'. Must be 'low' or 'high'.", file=sys.stderr)
                sys.exit(2)
            explicit_risk = val
            i += 2
            continue
        if arg == "--run":
            if run_mode:
                print("[ERROR] Duplicate --run flag provided.", file=sys.stderr)
                sys.exit(2)
            run_mode = True
            i += 1
            continue
        if arg.startswith("-"):
            print(f"[ERROR] Unknown or unsupported flag: '{arg}'.", file=sys.stderr)
            sys.exit(2)
        pos_args.append(arg)
        i += 1

    if len(pos_args) != 5:
        print(
            "Usage: python scripts/dispatch_l3.py <l3_role_name> <gate_name> "
            "<l2_session_id> <l2_role_name> <scope> [--risk low|high] [--run]",
            file=sys.stderr,
        )
        sys.exit(2)

    return pos_args[0], pos_args[1], pos_args[2], pos_args[3], pos_args[4], explicit_risk, run_mode


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # C2: strict argv parsing BEFORE any filesystem side effect, role lookup,
    # report placeholder creation, prompt creation, or run-mode activation.
    l3_role_name, gate_name, l2_session_id, l2_role_name, scope, explicit_risk, run_mode = \
        parse_cli_args(sys.argv[1:])

    # B2-HARDENING: strict identifier allowlist before any path/PS interpolation.
    validate_identifier(l3_role_name, "l3_role_name")
    validate_identifier(gate_name, "gate_name")
    validate_identifier(l2_session_id, "l2_session_id")
    validate_identifier(l2_role_name, "l2_role_name")

    if explicit_risk:
        risk = explicit_risk
        risk_reason = "explicit --risk flag"
    else:
        risk, risk_reason = infer_risk(scope)
        print(f"[AUTO-RISK] Inferred: {risk} ({risk_reason})")

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
    if re.search(r"_\d{8}$", gate_slug):
        l3_session_id = f"l3_role{l3_role_id}_{gate_slug}"
        report_path = f".ly_state/session/audit_reports/role{l3_role_id}_{gate_slug}.md"
    else:
        l3_session_id = f"l3_role{l3_role_id}_{gate_slug}_{today}"
        report_path = f".ly_state/session/audit_reports/role{l3_role_id}_{gate_slug}_{today}.md"

    # 3b. Single-instance lock keyed on session id (anti duplicate-dispatch),
    # acquired before any report placeholder, prompt, or process side effect.
    lock_path = acquire_session_lock(l3_session_id, REPO_ROOT)
    try:
        graph_evidence = run_graph_predispatch_gate(l3_session_id, scope, REPO_ROOT)
        _dispatch_l3_body(
            l3_role_name, l2_role_name, gate_name, l2_session_id, scope,
            l3_role_id, l2_role_id, l3_session_id, report_path,
            risk, risk_reason, model, explicit_risk is not None, run_mode, graph_evidence,
        )
    finally:
        release_session_lock(lock_path)


def _dispatch_l3_body(l3_role_name, l2_role_name, gate_name, l2_session_id, scope,
                      l3_role_id, l2_role_id, l3_session_id, report_path,
                      risk, risk_reason, model, _explicit_flag, run_mode, graph_evidence):
    # 4. Pre-create audit report file (containment-checked inside .ly_state/session)
    report_full = ensure_session_containment(REPO_ROOT / report_path, REPO_ROOT)
    report_full.parent.mkdir(parents=True, exist_ok=True)
    report_full.touch()

    # 5. Get lessons as sanitized structured DATA only
    entries = load_sanitized_lesson_entries(l3_role_id, gate_name)
    lessons_block = build_lessons_data_block(entries)

    # 6. Build prompt
    prompt = (
        f"REPO_ROOT: {REPO_ROOT}. "
        f"ROLE: {l3_role_id} {l3_role_name} - Codex L3 Independent Review. "
        f"GATE: {gate_name}. "
        f"{build_graph_prompt_evidence(graph_evidence)} "
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
        f"{ADVERSARIAL_DIRECTIVE_16D}"
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
        f"LESSONS: {lessons_block}. "
        f"FINAL STEP: L1 must run 'python scripts/sod_gate_enforcer.py' after gate update."
    )

    # Transport prompt via UTF-8 temp file (injection-safe; avoids the
    # Windows 32767-char command-line limit) with SHA-256 binding: hash,
    # verify, and decode ONE byte buffer; mismatch exits 2 before spawn.
    # Same bound digest protects the cx, OpenCode, and fallback variants.
    prompt_dir = REPO_ROOT / ".ly_state" / "session"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = ensure_session_containment(prompt_dir / f"prompt_{l3_session_id}.txt", REPO_ROOT)
    expected_digest = write_prompt_with_sha256(prompt_path, prompt)
    read_stmt = build_verified_prompt_read_statement(prompt_path, expected_digest)

    if model.startswith("cx/"):
        cmd = (
            f'New-Item -ItemType File -Path {ps_quote(report_path.replace("/", chr(92)))} -Force | Out-Null; '
            f'{read_stmt} echo "" | codex exec -m "{model}" -s danger-full-access '
            f"--dangerously-bypass-approvals-and-sandbox $__OMEGA_PROMPT"
        )
    else:
        cmd = (
            f'{read_stmt} echo "" | opencode run -m "{model}" --pure --dangerously-skip-permissions '
            f'--dir "{REPO_ROOT}" $__OMEGA_PROMPT'
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

    if run_mode:
        import subprocess

        def execute_ps(ps_command: str) -> subprocess.CompletedProcess:
            # B2-HARDENING: argument-list execution (no shell=True string);
            # the whole PS command travels as one -Command argument, so no
            # cmd.exe/shell metacharacter interpolation can occur.
            return subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_command],
                shell=False, cwd=str(REPO_ROOT), capture_output=True, text=True,
            )

        print("\n[RUN] Executing L3 audit...")
        r = execute_ps(cmd)
        print(r.stdout)
        if r.stderr:
            print(r.stderr)
        # C4: integrity failure (exit 2) is fail-closed and NEVER activates
        # the 429 fallback; no second process may be spawned on mismatch.
        if r.returncode == 2:
            print("[FAIL] Prompt integrity check failed; aborting without fallback.", file=sys.stderr)
            sys.exit(2)
        sys.exit(r.returncode)



if __name__ == "__main__":
    main()
