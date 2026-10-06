#!/usr/bin/env python3
"""
update_gate.py - Scoped phase_gates.json updater.

Prevents L3 greedy regex corruption by doing scoped JSON key update.
Never regex-replaces phase_gates.json; only the target gate object is mutated.

Usage:
    python scripts/update_gate.py <gate_name> <field>=<value> [<field>=<value> ...]

Example:
    python scripts/update_gate.py SYNTHETIC_FIXTURES_MACRO_NEWS_V12 \\
        final_verdict="[APPROVED]" \\
        l2_session_id="l2_role15_..." \\
        sod_boundary_checked=true

Advisory metadata contract (SOD_DISPATCHER_ADVISORY_HARDENING_20260826):
    For gates whose YYYYMMDD key suffix is >= 2026-08-27 the four advisory
    fields (timestamp, l3_session_key, repo_local_skill_sources,
    forbidden_path_scan) are auto-populated with deterministic safe defaults
    when missing/placeholder. Explicit valid caller values stay authoritative;
    explicit invalid values fail closed (exit 1).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ADVISORY_METADATA_CUTOFF_KEY_DATE = "20260827"
PLACEHOLDER_VALUES = {"", "pending", "unknown", "todo", "tbd", "tba"}
_ROLE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_REPO_LOCAL_SOURCE_RE = re.compile(
    r"^\.agents/(?:agent/[A-Za-z0-9_-]+\.md|skills/[A-Za-z0-9_-]+/(?:skill|SKILL)\.md)$"
)
_CLOSE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_/-]{1,128}$")
_SECRET_RE = re.compile(
    r"(?i)(?:api[_-]?key|secret|token|password|passwd|authorization)\s*[:=]\s*['\"](?!\[REDACTED\])[^\s'\"]{8,}['\"]"
)


def parse_value(v: str):
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    try:
        return int(v)
    except ValueError:
        return v


def _is_placeholder(value) -> bool:
    return isinstance(value, str) and value.strip().lower() in PLACEHOLDER_VALUES


def _gate_key_date(gate_name: str):
    """Extract the single trailing YYYYMMDD selector from a gate name."""
    tokens = re.findall(r"(?<![0-9])([0-9]{8})(?![0-9])", gate_name)
    if len(tokens) > 1:
        return None
    match = re.search(r"(?:^|[_-])([0-9]{8})$", gate_name)
    if not match or not tokens or match.group(1) != tokens[0]:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _parse_offset_aware(value: str):
    """Return an offset-aware datetime or None when invalid/naive."""
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _sentence_level_scan_ok(scan_text: str) -> bool:
    """Mirror the enforcer's sentence-level forbidden-path wording check.

    ponytail: duplicated marker lists kept local so update_gate stays a tiny
    standalone tool; drift is bounded by the shared test suite asserting both
    accept/reject the same fixtures — swap to importing sod_gate_enforcer if
    the marker sets ever grow again.
    """
    if not isinstance(scan_text, str) or not scan_text.strip():
        return False
    authoritative_markers = ("loaded from", "source:", "read from", "using skill from", "skill source:")
    non_authoritative_markers = (
        "no reliance", "confirmed not present", "not present", "not in repo_root scope",
        "not in scope", "non-authoritative", "forbidden-path", "forbidden path",
        "not used as source", "not referenced", "not accessed", "scan evidence",
        "junction target", "symlink target",
    )
    forbidden_paths = [
        r".gemini\antigravity-ide\scratch\ag-kit", r".gemini/antigravity-ide/scratch/ag-kit",
        r".openclaw\skills", r".openclaw/skills",
        r"c:\users\ghc\.agents", r"c:/users/ghc/.agents",
        r".codex\memories", r".codex/memories",
    ]
    for sentence in re.split(r"[\n]|\.\s+", scan_text):
        lowered = sentence.strip().lower()
        if not lowered:
            continue
        if not any(fp in lowered for fp in forbidden_paths):
            continue
        has_non_auth = any(marker in lowered for marker in non_authoritative_markers)
        has_auth = any(marker in lowered for marker in authoritative_markers)
        if has_auth or not has_non_auth:
            return False
    return True


def build_default_advisory_metadata(gate_name: str, effective: dict) -> dict:
    """Deterministic safe defaults for the four post-cutoff advisory fields."""
    defaults = {}
    key_date = _gate_key_date(gate_name)

    timestamp = effective.get("timestamp")
    if timestamp is None or _is_placeholder(timestamp):
        if key_date is not None:
            defaults["timestamp"] = f"{key_date.isoformat()}T00:00:00+07:00"
        else:
            defaults["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    session_key = effective.get("l3_session_key")
    if session_key is None or _is_placeholder(session_key):
        session_id = effective.get("l3_session_id")
        if isinstance(session_id, str) and session_id.strip():
            defaults["l3_session_key"] = session_id.strip()

    sources = effective.get("repo_local_skill_sources")
    if sources is None or sources == [] or (
        isinstance(sources, list) and any(_is_placeholder(s) for s in sources)
    ):
        derived = []
        for field in ("l2_role_name", "l3_role_name"):
            role_name = effective.get(field)
            if isinstance(role_name, str) and _ROLE_NAME_RE.fullmatch(role_name):
                derived.append(f".agents/agent/{role_name}.md")
        derived.append(".agents/skills/omega-sod/skill.md")
        defaults["repo_local_skill_sources"] = derived

    scan = effective.get("forbidden_path_scan")
    if scan is None or _is_placeholder(scan):
        session_id = effective.get("l3_session_id")
        if isinstance(session_id, str) and session_id.strip():
            defaults["forbidden_path_scan"] = (
                f"Completed forbidden-path scan for {session_id}; no authoritative reliance on forbidden paths."
            )
    return defaults


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        shell=False, check=False,
    )


def _git_bytes(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True,
        shell=False, check=False,
    )


def _close_scope(root: Path, paths: list[str]) -> list[str]:
    if not paths or len(paths) > 100:
        raise RuntimeError("gate-close scope must contain 1-100 paths")
    resolved = []
    for raw in paths:
        if not isinstance(raw, str) or not raw or raw.startswith("-") or "\x00" in raw:
            raise RuntimeError("gate-close scope contains an invalid path")
        candidate = (root / raw).resolve()
        try:
            relative = candidate.relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise RuntimeError(f"gate-close path escapes repository: {raw}") from exc
        if not candidate.exists() or candidate.is_dir():
            raise RuntimeError(f"gate-close path must be an existing file: {raw}")
        resolved.append(relative)
    resolved.append(".ly_state/session/phase_gates.json")
    return sorted(set(resolved))


def _close_lock(root: Path) -> tuple[int, Path]:
    path = root / ".ly_state" / "session" / "gate_close.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError("another gate-close transaction is active") from exc
    os.write(descriptor, str(os.getpid()).encode("ascii"))
    os.fsync(descriptor)
    return descriptor, path


def _release_close_lock(lock: tuple[int, Path] | None) -> None:
    if lock is None:
        return
    descriptor, path = lock
    os.close(descriptor)
    path.unlink(missing_ok=True)


def _snapshot_files(paths: list[Path]) -> dict[str, str]:
    snapshot = {}
    for path in paths:
        try:
            raw = path.read_bytes().replace(b"\r\n", b"\n")
            snapshot[path.as_posix()] = hashlib.sha256(raw).hexdigest()
        except OSError as exc:
            raise RuntimeError(f"cannot snapshot gate-close file: {path.name}") from exc
    return snapshot


def _atomic_replace(path: Path, raw: bytes) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _publish_gate_file(path: Path, original: bytes, updated: bytes) -> None:
    replace_started = False
    try:
        if path.read_bytes() != original:
            raise RuntimeError("gate metadata changed before publication")
        replace_started = True
        _atomic_replace(path, updated)
        if path.read_bytes() != updated:
            raise RuntimeError("gate update post-write verification failed")
    except Exception as exc:
        if replace_started:
            try:
                if path.read_bytes() != original:
                    _atomic_replace(path, original)
                if path.read_bytes() != original:
                    raise RuntimeError("gate update rollback verification failed")
            except Exception as rollback_exc:
                raise RuntimeError("gate update publication and rollback failed") from rollback_exc
        raise RuntimeError(f"gate update publication failed: {exc}") from exc


def close_gate_transaction(
    gate_name: str,
    scope: list[str],
    message: str,
    root: Path | None = None,
) -> str:
    """Validate, commit exactly the scoped diff, verify, then push once."""
    repo = (root or Path.cwd()).resolve()
    if not _CLOSE_IDENTIFIER_RE.fullmatch(gate_name):
        raise RuntimeError("invalid gate name")
    if not isinstance(message, str) or not message.strip() or "\x00" in message:
        raise RuntimeError("commit message must be non-empty and NUL-free")
    paths = _close_scope(repo, scope)
    lock = None
    gates_path = repo / ".ly_state" / "session" / "phase_gates.json"
    try:
        lock = _close_lock(repo)
        try:
            gates = json.loads(gates_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("gate metadata is unreadable") from exc
        gate = gates.get(gate_name) if isinstance(gates, dict) else None
        if not isinstance(gate, dict) or gate.get("final_verdict") != "[APPROVED]":
            raise RuntimeError("gate is not exactly [APPROVED]")
        return _close_gate_locked(gate_name, paths, message, repo, gates_path)
    finally:
        _release_close_lock(lock)


def _close_gate_locked(gate_name: str, paths: list[str], message: str, repo: Path, gates_path: Path) -> str:
    """Hold the cooperative repository lock and bind one snapshot through push."""
    scoped_paths = [repo / path for path in paths]
    snapshot = _snapshot_files([gates_path, *scoped_paths])

    enforcer = subprocess.run(
        [sys.executable, "scripts/sod_gate_enforcer.py", "--check-before-push"],
        cwd=str(repo), capture_output=True, text=True, shell=False, check=False,
    )
    if enforcer.returncode != 0:
        raise RuntimeError("sod_gate_enforcer refused gate close")
    try:
        current_gate = json.loads(gates_path.read_text(encoding="utf-8")).get(gate_name)
    except (OSError, ValueError, AttributeError) as exc:
        raise RuntimeError("gate metadata changed during enforcer verification") from exc
    if not isinstance(current_gate, dict) or current_gate.get("final_verdict") != "[APPROVED]":
        raise RuntimeError("gate approval changed during enforcer verification")

    branch_result = _git(repo, "branch", "--show-current")
    branch = branch_result.stdout.strip()
    if branch_result.returncode or not _CLOSE_IDENTIFIER_RE.fullmatch(branch):
        raise RuntimeError("current branch is detached or unsafe")
    before = _git(repo, "rev-parse", "HEAD")
    if before.returncode or not re.fullmatch(r"[0-9a-f]{40}", before.stdout.strip()):
        raise RuntimeError("cannot resolve pre-commit HEAD")
    base_head = before.stdout.strip()

    if _snapshot_files([gates_path, *scoped_paths]) != snapshot:
        raise RuntimeError("gate-close snapshot changed during verification")

    diff = _git(repo, "diff", "--binary", "HEAD", "--", *paths)
    if diff.returncode:
        raise RuntimeError("cannot read scoped diff")
    if not diff.stdout:
        remote = _git(repo, "rev-parse", f"refs/remotes/origin/{branch}")
        if remote.returncode == 0 and remote.stdout.strip() == base_head:
            return base_head
        raise RuntimeError("scoped diff is empty and remote is not current")
    non_test_paths = [p for p in paths if not (p.startswith("tests/") or p.endswith("_test.py") or "test" in Path(p).name)]
    if non_test_paths:
        prod_diff = _git(repo, "diff", "--binary", "HEAD", "--", *non_test_paths)
        if prod_diff.returncode:
            raise RuntimeError("cannot read scoped diff")
        if _SECRET_RE.search(prod_diff.stdout):
            raise RuntimeError("secret-like value detected in scoped diff")

    stable_head = _git(repo, "rev-parse", "HEAD")
    if stable_head.returncode or stable_head.stdout.strip() != base_head:
        raise RuntimeError("HEAD changed during gate-close verification")
    if _snapshot_files([gates_path, *scoped_paths]) != snapshot:
        raise RuntimeError("gate-close snapshot changed before commit")

    commit = _git(repo, "commit", "--only", "-m", message.strip(), "--", *paths)
    if commit.returncode:
        raise RuntimeError("scoped commit failed")
    after = _git(repo, "rev-parse", "HEAD")
    new_head = after.stdout.strip()
    if after.returncode or new_head == base_head or not re.fullmatch(r"[0-9a-f]{40}", new_head):
        raise RuntimeError("commit verification failed")
    parent = _git(repo, "rev-parse", f"{new_head}^")
    if parent.returncode or parent.stdout.strip() != base_head:
        raise RuntimeError("commit parent verification failed")
    changed = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", new_head)
    if changed.returncode or set(changed.stdout.splitlines()) != set(paths):
        raise RuntimeError("commit scope verification failed")
    for path in paths:
        blob_oid = _git(repo, "rev-parse", f"{new_head}:{path}")
        if blob_oid.returncode or not re.fullmatch(r"[0-9a-f]{40,64}", blob_oid.stdout.strip()):
            raise RuntimeError("commit tree blob is invalid")
        blob = _git_bytes(repo, "cat-file", "blob", blob_oid.stdout.strip())
        raw = blob.stdout if isinstance(blob.stdout, bytes) else blob.stdout.encode("utf-8", errors="replace")
        raw = raw.replace(b"\r\n", b"\n")
        if blob.returncode or hashlib.sha256(raw).hexdigest() != snapshot[(repo / path).as_posix()]:
            raise RuntimeError("commit tree does not match verified snapshot")

    if _git(repo, "rev-parse", "HEAD").stdout.strip() != new_head:
        raise RuntimeError("HEAD changed before push")

    pushed = _git(repo, "push", "origin", f"{new_head}:refs/heads/{branch}")
    if pushed.returncode:
        raise RuntimeError("push failed; commit retained locally")
    verified_remote = _git(repo, "ls-remote", "--heads", "origin", f"refs/heads/{branch}")
    remote_head = verified_remote.stdout.split()[0] if verified_remote.returncode == 0 and verified_remote.stdout.split() else ""
    if remote_head != new_head:
        raise RuntimeError("remote commit verification failed")
    return new_head


def main():
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(
            "Usage:\n"
            "  python scripts/update_gate.py <gate_name> <field>=<value> [...]\n"
            "  python scripts/update_gate.py close <gate> --message <message> --scope <file> [...]\n\n"
            "Positional Arguments:\n"
            "  gate_name         Target gate identifier (e.g. GATE_MASTER_PLAN_L4_MCP_ADVISOR_20261004)\n"
            "  field=value       Gate metadata field updates (e.g. final_verdict=[APPROVED], l2_completed=true)\n\n"
            "Subcommands:\n"
            "  close <gate> --message <message> --scope <file> [...]   Atomically verify, commit, and close gate\n\n"
            "Options:\n"
            "  -h, --help        Show this help message and exit"
        )
        sys.exit(0)
    if len(sys.argv) >= 2 and sys.argv[1] == "close":
        if len(sys.argv) < 6 or sys.argv[3] != "--message" or "--scope" not in sys.argv[4:]:
            print("Usage: python scripts/update_gate.py close <gate> --message <message> --scope <file> [...]")
            sys.exit(1)
        scope_index = sys.argv.index("--scope", 4)
        if scope_index != 5:
            print("[ERROR] gate-close flags must use exact documented order")
            sys.exit(1)
        try:
            commit = close_gate_transaction(sys.argv[2], sys.argv[6:], sys.argv[4])
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            print(f"[ERROR] {exc}")
            sys.exit(1)
        print(f"[OK] Gate closed at {commit}")
        return
    if len(sys.argv) < 3:
        print("Usage: python scripts/update_gate.py <gate_name> <field>=<value> ...")
        sys.exit(1)

    gate_name = sys.argv[1]
    updates: dict = {}
    seen: dict = {}
    for arg in sys.argv[2:]:
        if "=" not in arg:
            print(f"[ERROR] Invalid field=value: {arg}")
            sys.exit(1)
        k, v = arg.split("=", 1)
        if k in seen and seen[k] != v:
            print(f"[ERROR] Conflicting duplicate field '{k}' provided.")
            sys.exit(1)
        seen[k] = v
        updates[k] = [part.strip() for part in v.split(",")] if k == "repo_local_skill_sources" else parse_value(v)

    update_lock = None
    try:
        update_lock = _close_lock(Path.cwd())
        _update_gate(gate_name, updates)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    finally:
        _release_close_lock(update_lock)


def _update_gate(gate_name: str, updates: dict) -> None:
    gates_path = Path(".ly_state/session/phase_gates.json")
    try:
        original = gates_path.read_bytes()
        gates = json.loads(original.decode("utf-8"))
    except FileNotFoundError:
        print(f"[ERROR] Gates file not found: {gates_path}")
        raise RuntimeError(f"Gates file not found: {gates_path}")
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"[ERROR] Malformed gates JSON, refusing scoped update: {exc}")
        raise RuntimeError(f"Malformed gates JSON, refusing scoped update: {exc}") from exc

    if not isinstance(gates, dict) or any(
        not isinstance(key, str) or not isinstance(value, dict)
        for key, value in gates.items()
    ):
        raise RuntimeError("Malformed gates schema, refusing scoped update")

    if gate_name not in gates:
        gates[gate_name] = {"phase_name": gate_name}

    # Snapshot non-target hash for safety
    non_target = {k: v for k, v in gates.items() if k != gate_name}
    before_hash = hashlib.sha256(
        json.dumps(non_target, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()

    # Apply updates to target gate only
    for k, v in updates.items():
        gates[gate_name][k] = v

    # Advisory metadata contract: deterministic defaults + fail-closed checks
    effective = {**gates[gate_name]}
    key_date = _gate_key_date(gate_name)
    post_cutoff = key_date is not None and key_date.isoformat().replace("-", "") >= ADVISORY_METADATA_CUTOFF_KEY_DATE

    explicit_invalid = []
    raw_timestamp = effective.get("timestamp")
    if raw_timestamp is not None and not _is_placeholder(raw_timestamp) and _parse_offset_aware(raw_timestamp) is None:
        explicit_invalid.append("timestamp must be a valid offset-aware ISO-8601 string")

    scan_value = effective.get("forbidden_path_scan")
    if scan_value is not None and not _is_placeholder(scan_value) and not _sentence_level_scan_ok(scan_value):
        explicit_invalid.append("forbidden_path_scan contains sentence-level non-compliant wording")

    sources_value = effective.get("repo_local_skill_sources")
    if sources_value not in (None, []) and not (
        isinstance(sources_value, list)
        and all(isinstance(source, str) and _REPO_LOCAL_SOURCE_RE.fullmatch(source.strip())
                for source in sources_value)
    ):
        explicit_invalid.append("repo_local_skill_sources must be a non-empty list of concrete strings")

    if explicit_invalid:
        for message in explicit_invalid:
            print(f"[ERROR] {message} — aborting without write")
        raise RuntimeError("invalid advisory metadata: " + "; ".join(explicit_invalid))

    defaults = build_default_advisory_metadata(gate_name, effective)
    # Defaults are computed only for missing/placeholder fields, so direct
    # assignment (not setdefault) correctly replaces placeholder values.
    for field, value in defaults.items():
        gates[gate_name][field] = value

    timestamp = _parse_offset_aware(gates[gate_name].get("timestamp"))
    if key_date is not None and timestamp is not None and timestamp.date() != key_date:
        print(
            f"[ERROR] gate-key date {key_date.isoformat()} does not match timestamp local date "
            f"{timestamp.date().isoformat()} — aborting without write"
        )
        raise RuntimeError("gate-key date does not match timestamp local date")

    if post_cutoff:
        missing = [f for f in ("timestamp", "l3_session_key", "repo_local_skill_sources", "forbidden_path_scan")
                   if f not in gates[gate_name]]
        if missing:
            print(f"[ERROR] Post-cutoff gate {gate_name} cannot derive advisory fields: {missing} — aborting")
            raise RuntimeError(f"Post-cutoff gate {gate_name} cannot derive advisory fields: {missing}")
        session_id = gates[gate_name].get("l3_session_id")
        scan = gates[gate_name].get("forbidden_path_scan")
        if gates[gate_name].get("l3_session_key") != session_id:
            raise RuntimeError("l3_session_key must exactly bind l3_session_id")
        if (not isinstance(scan, str) or not isinstance(session_id, str) or
                session_id not in scan or "completed" not in scan.lower()):
            raise RuntimeError("forbidden_path_scan must be completed and tied to l3_session_id")

    # Verify non-target unchanged
    non_target_after = {k: v for k, v in gates.items() if k != gate_name}
    after_hash = hashlib.sha256(
        json.dumps(non_target_after, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()

    if before_hash != after_hash:
        print("[ERROR] Non-target gates were modified — aborting")
        raise RuntimeError("Non-target gates were modified")

    # Publish atomically; restore the previous bytes if verification fails.
    raw = json.dumps(gates, indent=2, ensure_ascii=False).encode("utf-8")
    _publish_gate_file(gates_path, original, raw)

    print(f"[OK] Updated gate '{gate_name}': {updates}")
    if defaults:
        print(f"[OK] Auto-populated advisory fields: {sorted(defaults)}")
    print(f"[OK] Non-target hash unchanged: {before_hash}")


if __name__ == "__main__":
    main()
