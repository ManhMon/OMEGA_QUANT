"""Create immutable, binary acceptance evidence for macro/micro V8."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = "macro_micro_data_v8_implementation"
RUN_ROOT = ROOT / ".ly_state" / "session" / "acceptance" / GATE
PINS = {"python": "3.14.4", "pyarrow": "23.0.1", "playwright": "1.62.0"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_new(path: Path, value: object) -> None:
    with path.open("xb") as handle:
        handle.write(_canonical(value))
        handle.flush()
        os.fsync(handle.fileno())


def _validate_runtime() -> dict[str, str]:
    if sys.implementation.name != "cpython" or sys.version_info[:5] != (3, 14, 4, "final", 0):
        raise RuntimeError("CPython 3.14.4 is required")
    import pyarrow
    from importlib.metadata import version

    if pyarrow.__version__ != PINS["pyarrow"] or version("playwright") != PINS["playwright"]:
        raise RuntimeError("pinned package version drift")
    return {"python": sys.version, "pyarrow": pyarrow.__version__, "playwright": version("playwright")}


def _commands(phase: str) -> list[list[str]]:
    python = sys.executable
    if phase == "l2":
        return [
            [python, "-m", "pytest", "tests/test_fetch_financial_statements.py", "tests/test_macro_pipeline.py", "tests/test_financial_loader.py", "tests/test_macro_micro_release.py", "tests/test_macro_micro_acceptance_runner.py", "tests/test_strict_repo_local_skill_loading.py", "-q"],
            [python, "-m", "pytest", "tests/test_strict_repo_local_skill_loading.py", "-q"],
            [python, "-m", "pytest", "-q"],
            [python, ".agents/scripts/checklist.py", ".", "--skip-performance"],
        ]
    return [[python, "scripts/sod_gate_enforcer.py"]]


def _gate_is_ready() -> bool:
    path = ROOT / ".ly_state" / "session" / "phase_gates.json"
    if not path.is_file():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    gate = payload.get(GATE, {}) if isinstance(payload, dict) else next((item for item in payload if item.get("phase_name") == GATE), {})
    key = gate.get("l3_session_key")
    return gate.get("l2_completed") is True and isinstance(key, str) and key.strip().lower() not in {"", "pending", "unknown", "todo", "tbd"}


def run(phase: str, accepted_l2_transcript_path: str | None = None, accepted_l2_transcript_sha256: str | None = None) -> dict[str, object]:
    runtime = _validate_runtime()
    if phase == "post-l3" and not _gate_is_ready():
        raise RuntimeError("implementation gate lacks concrete L3 approval metadata")
    if phase == "post-l3":
        if not accepted_l2_transcript_path or not accepted_l2_transcript_sha256:
            raise RuntimeError("accepted L2 transcript is required")
        transcript = ROOT / accepted_l2_transcript_path
        if not transcript.is_file() or _sha256(transcript) != accepted_l2_transcript_sha256:
            raise RuntimeError("accepted L2 transcript hash mismatch")
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex
    directory = RUN_ROOT / run_id
    directory.mkdir()
    environment = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    commands = _commands(phase)
    _write_new(directory / "run.json", {"phase": phase, "run_id": run_id, "commands": commands, "runtime": runtime, "environment_overrides": {key: environment[key] for key in ("PYTHONUTF8", "PYTHONIOENCODING", "PYTHONUNBUFFERED")}})
    results = []
    for ordinal, argv in enumerate(commands, 1):
        command_dir = directory / f"command_{ordinal:02d}"
        command_dir.mkdir()
        stdout_path, stderr_path = command_dir / "stdout.bin", command_dir / "stderr.bin"
        started = _utc_now()
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(argv, shell=False, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, env=environment)
            exit_code = process.wait()
            stdout.flush(); os.fsync(stdout.fileno())
            stderr.flush(); os.fsync(stderr.fileno())
        result = {"ordinal": ordinal, "argv": argv, "started_at": started, "ended_at": _utc_now(), "exit_code": exit_code, "stdout_path": stdout_path.relative_to(ROOT).as_posix(), "stderr_path": stderr_path.relative_to(ROOT).as_posix(), "stdout_bytes": stdout_path.stat().st_size, "stderr_bytes": stderr_path.stat().st_size, "stdout_sha256": _sha256(stdout_path), "stderr_sha256": _sha256(stderr_path)}
        result_path = command_dir / "result.json"
        _write_new(result_path, result)
        results.append({"path": result_path.relative_to(ROOT).as_posix(), "sha256": _sha256(result_path), "exit_code": exit_code})
        if exit_code:
            break
    transcript = {"phase": phase, "run_id": run_id, "runtime": runtime, "results": results, "accepted_l2_transcript_path": accepted_l2_transcript_path}
    transcript_path = directory / "transcript.json"
    _write_new(transcript_path, transcript)
    return {"run_id": run_id, "transcript_path": transcript_path.relative_to(ROOT).as_posix(), "transcript_sha256": _sha256(transcript_path), "transcript_bytes": transcript_path.stat().st_size, "success": len(results) == len(commands) and all(item["exit_code"] == 0 for item in results)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("l2", "post-l3"), required=True)
    parser.add_argument("--accepted-l2-transcript-path")
    parser.add_argument("--accepted-l2-transcript-sha256")
    args = parser.parse_args()
    result = run(args.phase, args.accepted_l2_transcript_path, args.accepted_l2_transcript_sha256)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
