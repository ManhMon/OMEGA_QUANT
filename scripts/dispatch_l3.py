#!/usr/bin/env python3
"""
dispatch_l3.py - Generate exact L3 Codex audit dispatch command.

Usage:
    python scripts/dispatch_l3.py <l3_role_name> <gate_name> <l2_session_id> <l2_role_name> "<scope>" [--risk low|high] [--model <model>] [--subagent-model <model>] [--run]

Example:
    python scripts/dispatch_l3.py code-reviewer SYNTHETIC_FIXTURES_MACRO_NEWS_V12 l2_role15_synthetic_fixtures_macro_news_v12_20260814 data-engineer "tests/fixtures/macro/" --subagent-model ag/gemini-3.8-flash-high --run
    python scripts/dispatch_l3.py code-reviewer MY_GATE l2_role9_fix_20260814 backend-engineer "src/omega/" --risk high --run

Risk levels:
    low  = test fixtures, docs, config-only (uses cx/gpt-5.6-sol for ~50% token savings)
    high = production logic, security, data pipeline (uses cx/gpt-6-astra(low), default)

Output: Ready-to-execute powershell command + pre-created audit report file.
"""
import sys
import subprocess
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

L3_LEAD_MODELS = {
    "low": "cx/gpt-5.6-sol(medium)",
    "medium": "cx/gpt-5.6-sol(medium)",
    "high": "cx/gpt-6-astra(low)",
    # fallback khi GPT 429: Aurora WebChat (gpt-5-6-thinking trên port 8080 qua scripts/run_l3_audit.py)
}
L3_SUBAGENT_MODELS = ("cx/gpt-5.6-luna", "9router/cx/gpt-5.6-luna")
MODELS = L3_LEAD_MODELS
VALID_RISK_LEVELS = ("low", "high")

FALLBACK_MODEL = "chatgpt-web/gpt-5-6-thinking"
AURORA_FALLBACK_SCRIPT = "scripts/run_l3_audit.py"

# Deep audit (final advisory, L1 dispatch trực tiếp qua codex exec)
DEEPAUDIT_MODEL = "cx/gpt-5.6-sol"
DEEPAUDIT_FALLBACK = "chatgpt-web/gpt-5-6-thinking"  # dùng khi DEEPAUDIT_MODEL bị 429


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


class ParsedL3Args(tuple):
    model: str | None = None
    subagent_model: str | None = None

    def __new__(cls, pos0, pos1, pos2, pos3, pos4, risk, run, model=None, subagent_model=None):
        inst = super().__new__(cls, (pos0, pos1, pos2, pos3, pos4, risk, run))
        inst.model = model
        inst.subagent_model = subagent_model
        return inst


def parse_cli_args(args: list[str]):
    """Strictly parse five positionals plus optional --risk/--model/--subagent-model/--run (each once).
    Reject unknown/duplicate/dangling/assignment-form/extra tokens with exit 2."""
    if any(arg in ("--help", "-h") for arg in args):
        print(
            "Usage: python scripts/dispatch_l3.py <l3_role_name> <gate_name> <l2_session_id> <l2_role_name> <scope>\n"
            "                                    [--risk low|high] [--model <model>] [--subagent-model <model>] [--run]\n\n"
            "Pre-dispatch validator, graph resolver, lesson retriever, and command generator for L3 Codex.\n\n"
            "Positional Arguments:\n"
            "  l3_role_name   Kebab-case L3 role name (role IDs 17-30, e.g. code-reviewer, security-auditor)\n"
            "  gate_name      Target gate identifier (e.g. GATE_UPDATE_MARKET_DATA_DIRECT_VCI_20260913)\n"
            "  l2_session_id  L2 session identifier being audited\n"
            "  l2_role_name   L2 role name (must be disjoint from L3 role: Writer != Auditor)\n"
            "  scope          Space-separated list of target files under audit\n\n"
            "Options:\n"
            "  -h, --help     Show this help message and exit\n"
            "  --risk LEVEL   Risk tier ('low', 'high') to select model\n"
            "  --model MODEL  Override model identifier explicitly\n"
            "  --subagent-model MODEL Override subagent model identifier explicitly\n"
            "  --run          Execute command immediately after generation"
        )
        sys.exit(0)
    if any(not isinstance(arg, str) or re.search(r"[\x00-\x1f\x7f-\x9f]", arg) for arg in args):
        print("[ERROR] CLI arguments must be control-free strings.", file=sys.stderr)
        sys.exit(2)
    pos_args: list[str] = []
    explicit_risk: str | None = None
    explicit_model: str | None = None
    explicit_subagent_model: str | None = None
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
        if arg == "--model":
            if explicit_model is not None:
                print("[ERROR] Duplicate --model flag provided.", file=sys.stderr)
                sys.exit(2)
            if i + 1 >= len(args):
                print("[ERROR] Flag --model requires a model string value.", file=sys.stderr)
                sys.exit(2)
            explicit_model = args[i + 1]
            i += 2
            continue
        if arg == "--subagent-model":
            if explicit_subagent_model is not None:
                print("[ERROR] Duplicate --subagent-model flag provided.", file=sys.stderr)
                sys.exit(2)
            if i + 1 >= len(args):
                print("[ERROR] Flag --subagent-model requires a model string value.", file=sys.stderr)
                sys.exit(2)
            explicit_subagent_model = args[i + 1]
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
            "<l2_session_id> <l2_role_name> <scope> [--risk low|high] [--model <model>] [--subagent-model <model>] [--run]",
            file=sys.stderr,
        )
        sys.exit(2)

    return ParsedL3Args(pos_args[0], pos_args[1], pos_args[2], pos_args[3], pos_args[4], explicit_risk, run_mode, model=explicit_model, subagent_model=explicit_subagent_model)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # C2: strict argv parsing BEFORE any filesystem side effect, role lookup,
    # report placeholder creation, prompt creation, or run-mode activation.
    args = parse_cli_args(sys.argv[1:])
    l3_role_name, gate_name, l2_session_id, l2_role_name, scope, explicit_risk, run_mode = args
    explicit_model = getattr(args, "model", None)

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

    if explicit_model:
        model_aliases = {
            "sol": "cx/gpt-5.6-sol",
            "sol(low)": "cx/gpt-5.6-sol(low)",
            "sol(medium)": "cx/gpt-5.6-sol(medium)",
            "sol(xhigh)": "cx/gpt-5.6-sol(xhigh)",
            "terra": "cx/gpt-5.6-terra",
            "terra(xhigh)": "cx/gpt-5.6-terra(xhigh)",
            "terra-xhigh": "cx/gpt-5.6-terra(xhigh)",
            "astra": "cx/gpt-6-astra(low)",
            "astra(low)": "cx/gpt-6-astra(low)",
        }
        model = model_aliases.get(explicit_model.lower(), explicit_model)
    else:
        model = MODELS[risk]

    subagent_aliases = {
        "gemini": "9router/ag/gemini-3.8-flash-high",
        "gemini-3.8": "9router/ag/gemini-3.8-flash-high",
        "gemini3.8": "9router/ag/gemini-3.8-flash-high",
        "flash": "9router/ag/gemini-3.8-flash-high",
        "auto": "9router/ag/gemini-3.8-flash-high",
    }
    explicit_subagent_model = getattr(args, "subagent_model", None)
    if explicit_subagent_model:
        subagent_model = subagent_aliases.get(explicit_subagent_model.lower(), explicit_subagent_model)
    else:
        subagent_model = L3_SUBAGENT_MODELS[0]
    if model not in set(L3_LEAD_MODELS.values()) or subagent_model not in L3_SUBAGENT_MODELS:
        print("[ERROR] invalid L3 lead or subagent model; cross-tier model rejected", file=sys.stderr)
        sys.exit(2)

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
        l2_report_file = REPO_ROOT / ".ly_state" / "session" / f"{l2_session_id}.md"
        if l2_report_file.is_file():
            val_res = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "validate_l2_report.py"), l2_session_id, str(l2_role_id), l2_role_name],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
            )
            if val_res.returncode != 0:
                print(f"[ERROR] Pre-L3 validation failed for L2 report {l2_session_id}:\n{val_res.stdout}\n{val_res.stderr}", file=sys.stderr)
                sys.exit(2)
        _dispatch_l3_body(
            l3_role_name, l2_role_name, gate_name, l2_session_id, scope,
            l3_role_id, l2_role_id, l3_session_id, report_path,
            risk, risk_reason, model, explicit_risk is not None, run_mode, graph_evidence,
            subagent_model=subagent_model,
        )
    finally:
        release_session_lock(lock_path)


def extract_prior_audit_outcomes(
    gate_name: str, l3_role_id: int, repo_root: Path, current_report_path: Path
) -> tuple[list[tuple[int, str]], list[tuple[int, str]], Path | None]:
    """Locate prior audit report for the gate and parse the 16-Dimension table.
    Returns (passed_dimensions, failed_dimensions, prior_report_path)."""
    candidate_paths: list[Path] = []

    # 1. Check current report path if it already has content
    if current_report_path.is_file() and current_report_path.stat().st_size > 100:
        candidate_paths.append(current_report_path)

    # 2. Check phase_gates.json for gate_name
    pg_path = repo_root / ".ly_state" / "session" / "phase_gates.json"
    if pg_path.is_file():
        try:
            gates = json.loads(pg_path.read_text(encoding="utf-8"))
            g_entry = gates.get(gate_name, {})
            p = g_entry.get("audit_report_path")
            if p:
                cand = repo_root / p
                if cand.is_file() and cand.stat().st_size > 100 and cand not in candidate_paths:
                    candidate_paths.append(cand)
        except Exception:
            pass

    # 3. Check audit_reports directory for prior reports of this gate
    audit_dir = repo_root / ".ly_state" / "session" / "audit_reports"
    gate_slug = gate_name.lower()
    if audit_dir.is_dir():
        for f in audit_dir.glob(f"*{gate_slug}*.md"):
            if f.is_file() and f.stat().st_size > 100 and f not in candidate_paths:
                candidate_paths.append(f)

    # Find candidate that contains the 16-Dimension matrix
    for path in candidate_paths:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if "16-Dimension Adversarial Matrix" not in content:
            continue

        passed = {}
        failed = {}
        in_matrix = False
        for line in content.splitlines():
            if "16-Dimension Adversarial Matrix" in line:
                in_matrix = True
                continue
            if in_matrix:
                if line.startswith("## ") and "16-Dimension" not in line:
                    break
                m = re.match(r"^\|\s*(\d{1,2})\s*\|\s*([^|]+)\|\s*([^|]+)\|", line)
                if m:
                    num = int(m.group(1))
                    name = m.group(2).strip()
                    res = m.group(3).strip().upper()
                    state = "PASS" if "[PASS]" in res or res == "PASS" else "FAIL" if "[FAIL]" in res or res == "FAIL" else None
                    if state is not None:
                        target = passed if state == "PASS" else failed
                        other = failed if state == "PASS" else passed
                        if (num in target and target[num] != name) or num in other:
                            raise RuntimeError(f"conflicting audit dimension {num}: {path}")
                        target[num] = name
                else:
                    m_list = re.match(r"^\s*(\d{1,2})\.\s*([^:]+):\s*(.+)$", line)
                    if m_list:
                        num = int(m_list.group(1))
                        name = m_list.group(2).strip()
                        res = m_list.group(3).strip().upper()
                        state = "PASS" if "PASS" in res else "FAIL" if "FAIL" in res else None
                        if state is not None:
                            target = passed if state == "PASS" else failed
                            other = failed if state == "PASS" else passed
                            if (num in target and target[num] != name) or num in other:
                                raise RuntimeError(f"conflicting audit dimension {num}: {path}")
                            target[num] = name

        if passed or failed:
            return sorted(passed.items()), sorted(failed.items()), path

    return [], [], None


def _dispatch_l3_body(l3_role_name, l2_role_name, gate_name, l2_session_id, scope,
                      l3_role_id, l2_role_id, l3_session_id, report_path,
                      risk, risk_reason, model, _explicit_flag, run_mode, graph_evidence,
                      subagent_model: str = "cx/gpt-6-astra(low)"):
    # 4. Pre-create audit report file (containment-checked inside .ly_state/session)
    report_full = ensure_session_containment(REPO_ROOT / report_path, REPO_ROOT)

    # Prior audit check: from 2nd audit onwards, exclude already-passed dimensions
    passed_dims, failed_dims, prior_report_file = extract_prior_audit_outcomes(
        gate_name, l3_role_id, REPO_ROOT, report_full
    )

    # Backup prior report file before touching if it has content
    if report_full.is_file() and report_full.stat().st_size > 100:
        prior_content = report_full.read_text(encoding="utf-8", errors="replace")
        idx = 1
        while (report_full.parent / f"{report_full.stem}_cycle{idx}.md").exists():
            idx += 1
        backup_path = report_full.parent / f"{report_full.stem}_cycle{idx}.md"
        backup_path.write_text(prior_content, encoding="utf-8")

    report_full.parent.mkdir(parents=True, exist_ok=True)
    report_full.touch()

    # 5. Get lessons as sanitized structured DATA only
    entries = load_sanitized_lesson_entries(l3_role_id, gate_name)
    lessons_block = build_lessons_data_block(entries)

    # 6. Build prompt (optimized incremental directive for Round 2+)
    if passed_dims:
        passed_summary = ", ".join(f"Dim {num} ({name})" for num, name in passed_dims)
        failed_summary = ", ".join(f"Dim {num} ({name})" for num, name in failed_dims)
        prior_name = prior_report_file.name if prior_report_file else "previous round"
        adversarial_directive = (
            f"MANDATORY FOCUSED RE-AUDIT ADVERSARIAL DIRECTIVE (Audit Round 2+ Incremental): "
            f"In the prior audit cycle ({prior_name}), the following {len(passed_dims)} dimensions were independently verified [PASS]: [{passed_summary}]. "
            f"EXCLUSION RULE: You DO NOT need to reconstruct full adversarial test cases or re-run exhaustive suites for these already-passed dimensions. "
            f"In your '## 16-Dimension Adversarial Matrix' table, include all 16 rows, carrying forward the verified [PASS] for these dimensions with note 'PASS - verified in prior cycle; zero regression on scope diff'. "
            f"MANDATORY ACTIVE RE-AUDIT FOCUS: You MUST concentrate deep adversarial verification and provide explicit fresh independent evidence for the {len(failed_dims)} previously FAILED/UNVERIFIED dimensions: [{failed_summary}], "
            f"and verify zero regression across the approved scope diff. "
            f"TEST EXECUTION EFFICIENCY: Prioritize scoped unit/integration test files directly. Do not run unrelated repository-wide test suites. Scope regression is strictly bounded to the approved scope and its direct callers/dependents. Pre-existing failures in unrelated modules outside approved scope diff must not block gate approval."
        )
        test_checklist_item = (
            f"3. Run focused tests covering approved scope and previously failed dimensions: [{', '.join(str(n) for n, _ in failed_dims)}], plus scope regression. Do not run unrelated test suites outside scope. "
        )
    else:
        adversarial_directive = ADVERSARIAL_DIRECTIVE_16D + " TEST EXECUTION EFFICIENCY: Prioritize scoped unit/integration test files directly. Do not run unrelated repository-wide test suites."
        test_checklist_item = "3. Run focused tests covering approved scope and related suites. Do not run unrelated repository-wide test suites. "

    subagent_clause = (
        f"MANDATORY HIERARCHICAL SUBAGENT AUDIT DIRECTIVE (HIERARCHICAL_SUBAGENT_OPTIMIZATION_20260913):\n"
        f"Lead Auditor operates on MODEL={model}. Subagents run on SUBAGENT_MODEL={subagent_model}.\n"
        f"To minimize high-reasoning token cost and maximize audit throughput, Lead Auditor MUST delegate subordinate probes using `spawn_agent`:\n"
        f"- PROBE 1 (16D STATIC & AST SCAN): Delegate regex checks for 16-Dimension invariants (secret leak, timezone look-ahead, mock leak, exit codes) via `spawn_agent(task_name='probe_16d_scan', task=..., model=\"{subagent_model}\")`.\n"
        f"- PROBE 2 (TEST SUITE EXECUTION): Delegate running scoped pytest slices and collecting failure tracebacks via `spawn_agent(task_name='probe_test_exec', task=..., model=\"{subagent_model}\")`.\n"
        f"- PROBE 3 (ROLLBACK & INTEGRITY VERIFICATION): Delegate verification of atomic file replace (.tmp -> final), artifact checksums, and DB rollback via `spawn_agent(task_name='probe_atomicity', task=..., model=\"{subagent_model}\")`.\n"
        f"Do NOT execute massive repetitive grep scans or test sweeps directly on the Lead Auditor thread. Retrieve probe results via `wait_agent` and synthesize findings. The final 16-Dimension evaluation and [APPROVED]/[NEEDS_FIX] verdict must remain solely with the Lead Auditor.\n"
    )

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
        f"ANTI-POLLING & ZERO-IDLE DIRECTIVE (ANTI_POLLING_ZERO_IDLE_20260918): NEVER poll, loop, or repeatedly run git status, task status, or audit scripts to wait for background execution; stop calling tools immediately and end the turn when waiting for commands. "
        f"{adversarial_directive} "
        f"{subagent_clause}"
        f"AUDIT EVIDENCE CHECKLIST: "
        f"1. Verify l2_role_id={l2_role_id} != l3_role_id={l3_role_id}. "
        f"2. Verify code changes match approved scope. "
        f"{test_checklist_item}"
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
            f'if (-not (Test-Path {ps_quote(report_path.replace("/", chr(92)))})) {{ New-Item -ItemType File -Path {ps_quote(report_path.replace("/", chr(92)))} -Force | Out-Null }}; '
            f'{read_stmt} echo "" | codex exec -m "{model}" --enable multi_agent -s danger-full-access '
            f'--dangerously-bypass-approvals-and-sandbox $__OMEGA_PROMPT; '
            f'if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 2) {{ '
            f'python scripts/run_l3_audit.py {gate_name} --prompt-file {ps_quote(str(prompt_path))} --model gpt-5-6-thinking '
            f'}}'
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
    print(f"SUBAGENT_MODEL={subagent_model}")
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
                encoding="utf-8", errors="replace",
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
