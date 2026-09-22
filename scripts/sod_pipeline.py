#!/usr/bin/env python3
"""Run the bounded L2 -> validation -> L3 -> enforcer SoD pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import os
import secrets
from datetime import timezone
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_REMEDIATIONS = 3
GRAPH_EVIDENCE_SCHEMA = {
    "affected_files", "blast_radius", "dependencies", "detail_files", "detail_files_truncated",
    "generated_at", "graph_commit", "graph_db", "graph_tool_root", "impact_query", "rebuilt",
    "relationships", "repo_commit", "schema_version", "scope_content_hashes", "scope_dirty",
    "scope_files", "session_id",
}
DISPATCH_L2_KEYS = {"SESSION_ID", "ROLE_ID", "ROLE_NAME", "CO_ROLE_IDS", "CO_ROLE_NAMES", "GATE", "MODEL", "SUBAGENT_MODEL", "RISK", "ANTI_DRIP_MODE", "ANTI_DRIP_CONTRACT", "ANTI_DRIP_CONTRACT_SHA256"}
DISPATCH_L3_KEYS = {"L3_SESSION_ID", "L3_ROLE_ID", "L3_ROLE_NAME", "L2_ROLE_ID", "L2_ROLE_NAME", "MODEL", "SUBAGENT_MODEL", "RISK", "REPORT", "GATE"}
PLAN_MAX_BYTES = 1_048_576
PLANNER_STREAM_MAX_BYTES = 64 * 1024
SECRET_PATTERN = re.compile(r"(?i)(bearer\s+[^\s,;]+|(?:api[_-]?key|token|secret|password)\s*[=:]\s*[^\s,;]+|sk-[A-Za-z0-9_-]+)")
PLANNER_MODEL = "cx/gpt-6-astra(low)"
PLAN_HEADINGS = (
    ("Planning Run ID",),
    ("Gate",),
    ("Goal", "Muc tieu"),
    ("Authorized Scope", "Ranh gioi SoD va pham vi"),
    ("Technical Design", "Thiet ke ky thuat"),
    ("Verification Plan", "Ke hoach xac minh"),
)


class ReportSnapshot(NamedTuple):
    state: str
    content: str | None


def verify_graph_evidence(
    path_value: str,
    expected_sha256: str | None = None,
    expected_session: str | None = None,
    expected_scope: list[str] | None = None,
    allow_dirty: bool = False,
) -> dict[str, object]:
    """Verify the exact authoritative graph artifact before pipeline use."""
    evidence_path = path_value
    expected_digest = expected_sha256 or _read_graph_evidence_sha256(evidence_path)
    path = (REPO_ROOT / evidence_path).resolve()
    if not path.is_file() or not path.is_relative_to(REPO_ROOT):
        raise RuntimeError(f"missing graph evidence: {evidence_path}")
    with open(path, "rb") as handle:
        raw = handle.read()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_digest:
        raise RuntimeError(f"graph evidence integrity mismatch: {evidence_path}")
    try:
        evidence = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid graph evidence: {evidence_path}") from exc
    if not isinstance(evidence, dict) or set(evidence) != GRAPH_EVIDENCE_SCHEMA:
        raise RuntimeError(f"graph evidence schema mismatch: {evidence_path}")
    scope = evidence["scope_files"]
    if evidence["schema_version"] != 1 or (expected_session and evidence["session_id"] != expected_session):
        raise RuntimeError(f"graph evidence identity mismatch: {evidence_path}")
    if type(evidence["schema_version"]) is not int or not all(isinstance(evidence[key], str) for key in ("generated_at", "graph_commit", "graph_db", "graph_tool_root", "repo_commit", "session_id")) or type(evidence["rebuilt"]) is not bool or type(evidence["scope_dirty"]) is not bool or type(evidence["detail_files_truncated"]) is not bool:
        raise RuntimeError(f"graph evidence field types mismatch: {evidence_path}")
    if (expected_scope and scope != expected_scope) or any(not isinstance(item, str) for item in scope) or evidence["detail_files"] != scope or evidence["graph_commit"] != evidence["repo_commit"] or (evidence["scope_dirty"] is not False and not allow_dirty):
        raise RuntimeError(f"graph evidence scope mismatch: {evidence_path}")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    if evidence["repo_commit"] != commit:
        raise RuntimeError(f"graph evidence commit mismatch: {evidence_path}")
    if not isinstance(evidence["scope_content_hashes"], dict) or set(evidence["scope_content_hashes"]) != set(scope):
        raise RuntimeError(f"graph evidence content hash schema mismatch: {evidence_path}")
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in evidence["scope_content_hashes"].values()):
        raise RuntimeError(f"graph evidence content hash types mismatch: {evidence_path}")
    actual_hashes = {}
    for relative_path in scope:
        file_path = (REPO_ROOT / relative_path).resolve()
        if not file_path.is_file() or not file_path.is_relative_to(REPO_ROOT):
            raise RuntimeError(f"graph evidence scope file missing: {relative_path}")
        actual_hashes[relative_path] = hashlib.sha256(file_path.read_bytes()).hexdigest()
    if actual_hashes != evidence["scope_content_hashes"] and not allow_dirty:
        raise RuntimeError(f"graph evidence content hash mismatch: {evidence_path}")
    for section in ("affected_files", "dependencies"):
        if not isinstance(evidence[section], dict) or set(evidence[section]) != set(scope):
            raise RuntimeError(f"graph evidence {section} scope mismatch: {evidence_path}")
    def valid_leaf(item: object) -> bool:
        return (
            isinstance(item, dict)
            and set(item) == {"files", "result_count", "summary"}
            and isinstance(item["files"], list)
            and all(isinstance(file, str) for file in item["files"])
            and type(item["result_count"]) is int
            and item["result_count"] >= 0
            and isinstance(item["summary"], str)
        )

    def valid_count(item: dict[str, object]) -> bool:
        match = re.fullmatch(r"Found (\d+) result\(s\) for .+", item["summary"])
        return bool(match) and int(match.group(1)) == item["result_count"]

    for item in evidence["affected_files"].values():
        if not valid_leaf(item):
            raise RuntimeError(f"graph evidence affected schema mismatch: {evidence_path}")
    if any(
        evidence["affected_files"][key]["files"] != [key]
        or evidence["affected_files"][key]["result_count"] < len(evidence["affected_files"][key]["files"])
        or not valid_count(evidence["affected_files"][key])
        for key in scope
    ):
        raise RuntimeError(f"graph evidence affected file binding mismatch: {evidence_path}")
    for item in evidence["dependencies"].values():
        if not isinstance(item, dict) or set(item) != {"importers", "imports"} or any(not valid_leaf(value) for value in item.values()):
            raise RuntimeError(f"graph evidence dependency schema mismatch: {evidence_path}")
    if not isinstance(evidence["relationships"], dict) or any(
        not isinstance(node, dict)
        or not node
        or any(not valid_leaf(leaf) for leaf in node.values())
        for node in evidence["relationships"].values()
    ):
        raise RuntimeError(f"graph evidence relationship schema mismatch: {evidence_path}")
    blast = evidence["blast_radius"]
    if not isinstance(blast, dict) or set(blast) != {"impacted_files", "summary", "total_impacted", "truncated"}:
        raise RuntimeError(f"graph evidence blast schema mismatch: {evidence_path}")
    if not isinstance(blast["impacted_files"], list) or not all(isinstance(item, str) for item in blast["impacted_files"]):
        raise RuntimeError(f"graph evidence impact types mismatch: {evidence_path}")
    if type(blast["total_impacted"]) is not int or blast["total_impacted"] < len(blast["impacted_files"]) or type(blast["truncated"]) is not bool:
        raise RuntimeError(f"graph evidence impact count mismatch: {evidence_path}")
    impact = evidence["impact_query"]
    if not isinstance(impact, dict) or set(impact) != {"batch_count", "batches", "complete", "covered_scope_count", "protocol", "requested_scope_count"}:
        raise RuntimeError(f"graph evidence query schema mismatch: {evidence_path}")
    if any(type(impact[key]) is not int for key in ("batch_count", "covered_scope_count", "requested_scope_count")) or type(impact["complete"]) is not bool or not isinstance(impact["batches"], list) or not isinstance(impact["protocol"], str) or not impact["protocol"] or impact["batch_count"] != len(impact["batches"]) or impact["requested_scope_count"] != len(scope) or impact["covered_scope_count"] != len(scope) or impact["complete"] is not True:
        raise RuntimeError(f"graph evidence query completeness mismatch: {evidence_path}")
    for index, batch in enumerate(impact["batches"], 1):
        if not isinstance(batch, dict) or set(batch) != {"batch_index", "impacted_file_count", "response_bytes", "response_sha256", "scope_count", "scope_files", "total_impacted", "truncated"}:
            raise RuntimeError(f"graph evidence batch schema mismatch: {evidence_path}")
        if any(type(batch[key]) is not int or batch[key] < 0 for key in ("batch_index", "impacted_file_count", "response_bytes", "scope_count", "total_impacted")) or batch["batch_index"] != index or not re.fullmatch(r"[0-9a-f]{64}", batch["response_sha256"]) or type(batch["truncated"]) is not bool or not isinstance(batch["scope_files"], list) or any(not isinstance(item, str) for item in batch["scope_files"]) or batch["scope_count"] != len(batch["scope_files"]) or batch["total_impacted"] < batch["impacted_file_count"]:
            raise RuntimeError(f"graph evidence batch scope mismatch: {evidence_path}")
    if [item for batch in impact["batches"] for item in batch["scope_files"]] != scope:
        raise RuntimeError(f"graph evidence batch scope mismatch: {evidence_path}")
    if blast["total_impacted"] != sum(batch["total_impacted"] for batch in impact["batches"]) or blast["truncated"] != any(batch["truncated"] for batch in impact["batches"]):
        raise RuntimeError(f"graph evidence blast/query mismatch: {evidence_path}")
    return {"path": evidence_path, "sha256": expected_digest, **evidence}


def _read_graph_evidence_sha256(evidence_path: str) -> str:
    sidecar = (REPO_ROOT / evidence_path).with_suffix(".sha256")
    if not sidecar.is_file():
        raise RuntimeError(f"graph evidence sidecar missing: {sidecar}")
    digest = sidecar.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RuntimeError(f"graph evidence sidecar digest invalid: {sidecar}")
    return digest


def _current_graph_binding(slug: str, evidence_path: str | None = None) -> tuple[str, str]:
    if evidence_path is None:
        candidates = sorted((REPO_ROOT / ".ly_state" / "session").glob(f"graph_evidence_*_{slug}_*.json"))
        if len(candidates) != 1:
            raise RuntimeError(f"expected one graph evidence artifact for slug: {slug}")
        evidence_path = candidates[0].relative_to(REPO_ROOT).as_posix()
    return evidence_path, _read_graph_evidence_sha256(evidence_path)


def run(cmd: str | list[str], desc: str, check: bool = True) -> int:
    """Run one stage without shell interpolation or a nested PowerShell scope."""
    print(f"\n{'=' * 60}\n  STAGE: {desc}\n{'=' * 60}")
    if isinstance(cmd, list):
        result = subprocess.run(cmd, cwd=REPO_ROOT, text=True)
    elif _is_powershell(cmd):
        result = _run_powershell(cmd)
    else:
        raise ValueError("run() accepts argv lists or PowerShell commands only")
    if check and result.returncode:
        print(f"\n[FAIL] {desc} — exit code {result.returncode}")
    return result.returncode


def _is_powershell(command: str) -> bool:
    return command.lstrip().startswith(("try {", "if (", "$", "throw ", "& ", "echo \"\" |"))


def _run_powershell(command: str) -> subprocess.CompletedProcess:
    """Execute generated PowerShell directly; no child scope masks exit state."""
    session_dir = REPO_ROOT / ".ly_state" / "session"
    session_dir.mkdir(parents=True, exist_ok=True)
    script_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".ps1", prefix="_pipeline_step_",
            dir=session_dir, delete=False,
        ) as handle:
            handle.write("$ErrorActionPreference = 'Stop'\n")
            handle.write(command)
            handle.write("\nif (-not $?) { exit $LASTEXITCODE }\n")
            script_path = Path(handle.name)
        return subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
            cwd=REPO_ROOT, text=True,
        )
    finally:
        if script_path:
            try:
                script_path.unlink(missing_ok=True)
            except OSError:
                pass


def capture(cmd: list[str]) -> tuple[int, str]:
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    return result.returncode, (result.stdout or "").strip()


def parse_dispatch_output(output: str, *, required: set[str] | None = None) -> dict[str, str]:
    metadata: dict[str, str] = {}
    allowed = DISPATCH_L2_KEYS | DISPATCH_L3_KEYS
    for line in output.split("---COMMAND---", 1)[0].splitlines():
        if "=" not in line or line.startswith("---"):
            continue
        raw_key, raw_value = line.split("=", 1)
        key, value = raw_key.strip(), raw_value.strip()
        if not key or key not in allowed or key in metadata or (not value and key not in {"CO_ROLE_IDS", "CO_ROLE_NAMES"}):
            raise ValueError("invalid dispatch metadata")
        metadata[key] = value
    if required is None:
        required = {"L3_SESSION_ID", "L3_ROLE_ID", "REPORT"} if any(key.startswith("L3_") or key == "REPORT" for key in metadata) else {"SESSION_ID", "ROLE_ID"}
    if not required <= metadata.keys():
        raise ValueError("missing dispatch metadata")
    schema = DISPATCH_L3_KEYS if required <= DISPATCH_L3_KEYS else DISPATCH_L2_KEYS
    if set(metadata) - schema:
        raise ValueError("mixed dispatch metadata schema")
    return metadata


def extract_findings(report_path: str) -> str:
    if not report_path:
        return "Address all L3 audit findings and regressions."
    path = (REPO_ROOT / report_path).resolve()
    if not path.is_file() or not path.is_relative_to(REPO_ROOT):
        return "Address all L3 audit findings and regressions."
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "Address all L3 audit findings and regressions."
    findings = [re.sub(r"[\r\n\t]+", " ", line.lstrip("# -*").strip())
                for line in text.splitlines() if re.match(r"^\s*[-*#]*\s*F-\d{3}\b", line)]
    return "; ".join(dict.fromkeys(findings))[:4000] or "Address all L3 audit findings and regressions."


def _read_fresh_report(report_path: str, previous_snapshot: ReportSnapshot) -> str | None:
    if not report_path:
        return None
    if previous_snapshot.state == "unreadable":
        return None
    try:
        path = (REPO_ROOT / report_path).resolve()
        if not path.is_relative_to(REPO_ROOT) or not path.is_file():
            return None
        report = path.read_text(encoding="utf-8")
        return None if previous_snapshot.content is not None and report == previous_snapshot.content else report
    except (OSError, UnicodeDecodeError):
        return None


def _read_report_snapshot(report_path: str) -> ReportSnapshot:
    if not report_path:
        return ReportSnapshot("unreadable", None)
    try:
        path = (REPO_ROOT / report_path).resolve()
        if not path.is_relative_to(REPO_ROOT):
            return ReportSnapshot("unreadable", None)
        if not path.exists():
            return ReportSnapshot("missing", None)
        if not path.is_file():
            return ReportSnapshot("unreadable", None)
        return ReportSnapshot("readable", path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return ReportSnapshot("unreadable", None)


def _dispatch_l2(args: argparse.Namespace, task: str) -> tuple[dict[str, str], str]:
    command = [sys.executable, "scripts/dispatch_l2.py", args.l2_role, args.gate, args.slug, task, args.scope]
    if args.risk:
        command += ["--risk", args.risk]
    if args.model:
        command += ["--model", args.model]
    if args.dry_run:
        command.append("--dry-run")
    if args.graph_evidence:
        command += ["--graph-evidence", args.graph_evidence]
    rc, output = capture(command)
    if rc:
        raise SystemExit(f"[FAIL] dispatch_l2.py failed: {output}")
    meta = parse_dispatch_output(output, required={"SESSION_ID", "ROLE_ID", "ROLE_NAME", "GATE", "MODEL", "RISK", "ANTI_DRIP_MODE", "ANTI_DRIP_CONTRACT", "ANTI_DRIP_CONTRACT_SHA256"})
    marker = "---COMMAND---\n"
    if marker not in output:
        raise SystemExit("[FAIL] Could not extract L2 command")
    return meta, output.split(marker, 1)[1].strip()


def _dispatch_l3(args: argparse.Namespace, session_id: str) -> tuple[dict[str, str], str]:
    command = [sys.executable, "scripts/dispatch_l3.py", args.l3_role, args.gate, session_id, args.l2_role, args.scope]
    if args.risk:
        command += ["--risk", args.risk]
    if args.model:
        command += ["--model", args.model]
    if args.subagent_model:
        command += ["--subagent-model", args.subagent_model]
    rc, output = capture(command)
    if rc:
        raise SystemExit(f"[FAIL] dispatch_l3.py failed: {output}")
    marker = "---COMMAND---\n"
    if marker not in output:
        raise SystemExit("[FAIL] Could not extract L3 command")
    return parse_dispatch_output(output, required={"L3_SESSION_ID", "L3_ROLE_ID", "L3_ROLE_NAME", "L2_ROLE_ID", "L2_ROLE_NAME", "MODEL", "SUBAGENT_MODEL", "RISK", "REPORT", "GATE"}), output.split(marker, 1)[1].strip()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("l2_role")
    parser.add_argument("l3_role")
    parser.add_argument("gate")
    parser.add_argument("slug")
    parser.add_argument("task")
    parser.add_argument("scope")
    parser.add_argument("--risk", choices=("low", "high"), default="high")
    parser.add_argument("--model")
    parser.add_argument("--subagent-model")
    parser.add_argument("--max-remediations", type=int, default=MAX_REMEDIATIONS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--graph-evidence")
    parser.add_argument("--with-plan", "--plan", action="store_true", dest="with_plan")
    return parser.parse_args(argv)


def _plan_path() -> Path:
    session_root = (REPO_ROOT / ".ly_state" / "session").resolve()
    path = session_root / "implementation_plan.md"
    if path.parent != session_root or not path.is_relative_to(session_root):
        raise RuntimeError("plan path escapes session root")
    if path.exists():
        stat = path.lstat()
        if path.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400 or getattr(stat, "st_nlink", 1) > 1:
            raise RuntimeError("plan path identity invalid")
    return path


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _redact(text: bytes) -> str:
    return SECRET_PATTERN.sub("[REDACTED]", text.decode("utf-8", errors="replace")[:PLANNER_STREAM_MAX_BYTES])


def _plan_sections(raw: str) -> dict[str, list[str]]:
    if not raw or raw.startswith("\ufeff") or "\x00" in raw or any(ord(c) < 32 and c not in "\n\r\t" for c in raw):
        raise RuntimeError("invalid plan encoding")
    lines = raw.splitlines()
    if len(raw.encode("utf-8")) > PLAN_MAX_BYTES or not lines or lines[0] not in ("# Implementation Plan", "# Ke hoach trien khai"):
        raise RuntimeError("invalid plan header or size")
    headings = [(line[3:], index) for index, line in enumerate(lines) if line.startswith("## ")]
    if len(headings) != len(PLAN_HEADINGS):
        raise RuntimeError("invalid plan heading cardinality")
    selected: dict[str, list[str]] = {}
    for index, ((aliases), (title, _)) in enumerate(zip(PLAN_HEADINGS, headings)):
        if title not in aliases:
            raise RuntimeError("invalid plan heading order")
        end = headings[index + 1][1] if index + 1 < len(headings) else len(lines)
        selected[aliases[0]] = lines[headings[index][1] + 1:end]
    return selected


def _scalar_section(lines: list[str], field: str) -> str:
    values = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]
    if len(values) != 1:
        raise RuntimeError(f"invalid plan {field}")
    value = values[0].strip("`").strip()
    if any(ord(c) < 32 and c not in "\t" for c in value):
        raise RuntimeError(f"invalid plan {field}")
    return value


def _validate_plan(raw: str, run_id: str, gate: str, scope: str) -> str:
    sections = _plan_sections(raw)
    if _scalar_section(sections["Planning Run ID"], "run id") != run_id:
        raise RuntimeError("plan run id mismatch")
    if _scalar_section(sections["Gate"], "gate") != gate:
        raise RuntimeError("plan gate mismatch")
    from scripts.dispatch_l2 import _scope_files
    listed = []
    for line in sections["Authorized Scope"]:
        value = line.strip().lstrip("-*").strip().strip("`")
        if value:
            listed.append(value)
    if len(listed) != len(set(listed)) or _scope_files(" ".join(listed), REPO_ROOT) != _scope_files(scope, REPO_ROOT):
        raise RuntimeError("plan scope mismatch")
    for name in ("Goal", "Technical Design", "Verification Plan"):
        if not any(line.strip() for line in sections[name]):
            raise RuntimeError(f"empty plan section: {name}")
    return raw


def _run_planning_phase(args: argparse.Namespace) -> None:
    run_id = f"planning_{args.slug}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{secrets.token_hex(8)}"
    plan_path = _plan_path()
    prompt = (
        f"REPO_ROOT: {REPO_ROOT}\nROLE: 26 planning-architect\nGATE: {args.gate}\n"
        f"PLANNING_RUN_ID: {run_id}\nAUTHORIZED_SCOPE: {args.scope}\nTASK: {args.task}\n"
        "Write only the exact markdown plan to stdout. Use the required six sections, put the exact run ID and gate in scalar sections, and list one authorized repo-relative file per line."
    )
    session_dir = plan_path.parent
    session_dir.mkdir(parents=True, exist_ok=True)
    lock_path = session_dir / f".{plan_path.name}.lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError("planning transaction lock contention") from exc
    try:
        if plan_path.exists() and not plan_path.is_file():
            raise RuntimeError("plan path is not a regular file")
        if plan_path.exists():
            plan_path.unlink()
            _fsync_directory(session_dir)
        if args.dry_run:
            print(f"PLAN_RUN_ID={run_id}\nPLAN_MODEL={PLANNER_MODEL}\nPLAN_SHA256={hashlib.sha256(prompt.encode()).hexdigest()}")
            return
        prompt_bytes = prompt.encode("utf-8")
        result = subprocess.run(
            ["codex", "exec", "-m", PLANNER_MODEL, "--dangerously-bypass-approvals-and-sandbox"],
            cwd=REPO_ROOT, input=prompt_bytes, capture_output=True, timeout=900, shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"planning process failed: {_redact(result.stderr or b'')}")
        raw_bytes = (result.stdout or b"")[:PLANNER_STREAM_MAX_BYTES]
        try:
            raw = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("planning output is not valid UTF-8") from exc
        _validate_plan(raw, run_id, args.gate, args.scope)
        tmp = plan_path.with_name(f".{plan_path.name}.{run_id}.tmp")
        with open(tmp, "wb") as handle:
            handle.write(raw.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, plan_path)
        _fsync_directory(session_dir)
        published = plan_path.read_bytes()
        if hashlib.sha256(published).hexdigest() != hashlib.sha256(raw.encode("utf-8")).hexdigest():
            raise RuntimeError("published plan digest mismatch")
        _validate_plan(published.decode("utf-8"), run_id, args.gate, args.scope)
    finally:
        os.close(fd)
        lock_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    baseline_binding = None
    if args.graph_evidence:
        baseline_binding = _current_graph_binding(args.slug, args.graph_evidence)
    if baseline_binding:
        verify_graph_evidence(*baseline_binding, expected_scope=args.scope.split(), allow_dirty=args.dry_run)
    if not 0 <= args.max_remediations <= MAX_REMEDIATIONS:
        raise SystemExit("--max-remediations must be between 0 and 3")
    task = args.task
    if args.with_plan:
        try:
            _run_planning_phase(args)
        except (OSError, RuntimeError, subprocess.SubprocessError, TimeoutError) as exc:
            print(f"[FAIL] Phase 0 planning: {exc}", file=sys.stderr)
            return 2
        if args.dry_run:
            return 0
    for cycle in range(args.max_remediations + 1):
        l2_meta, l2_command = _dispatch_l2(args, task)
        if args.dry_run:
            print(l2_command)
            return 0
        if run(l2_command, f"L2 OpenCode: {args.l2_role}"):
            return 1
        if baseline_binding:
            candidate_binding = _current_graph_binding(args.slug, args.graph_evidence)
            verify_graph_evidence(*candidate_binding, expected_scope=args.scope.split())
            if candidate_binding == baseline_binding:
                raise SystemExit("[FAIL] candidate graph evidence was not regenerated")
        session_id = l2_meta.get("SESSION_ID", f"l2_role0_{args.slug}_{datetime.now():%Y%m%d}")
        role_id = l2_meta.get("ROLE_ID", "0")
        if run([sys.executable, "scripts/validate_l2_report.py", session_id, role_id, args.l2_role], "Pre-L3 Validation"):
            return 1

        l3_meta, l3_command = _dispatch_l3(args, session_id)
        report_path = l3_meta.get("REPORT", "")
        previous_snapshot = _read_report_snapshot(report_path)
        l3_rc = run(l3_command, f"L3 Codex Audit: {args.l3_role}", check=False)
        report = _read_fresh_report(report_path, previous_snapshot)
        if l3_rc == 0 and report and "[APPROVED]" in report and "[NEEDS_FIX]" not in report:
            return 0 if run([sys.executable, "scripts/sod_gate_enforcer.py"], "SoD Gate Enforcer") == 0 else 3
        if run([sys.executable, "scripts/extract_lessons.py"], "Lesson Extraction Hard Gate", check=False):
            return 2
        if cycle == args.max_remediations:
            return 2
        task = f"{args.task}. REMEDIATION FIX FOR L3 AUDIT FINDINGS (Cycle {cycle + 2}): {extract_findings(report_path)}"
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

