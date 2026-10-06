"""TypeSafe Jev dynamic model routing and durable decision envelopes.

Security invariants: standalone verdict validation and exclusive atomic publication.
"""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import re
import stat
import time
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

L2_LEAD_ALLOWLIST = ("9router/cx/gpt-6.1-sol", "9router/cx/gpt-6-luna")
L2_SUBAGENT_ALLOWLIST = ("9router/cx/gpt-6-luna", "cx/gpt-6-luna", "ag/gemini")
L3_LEAD_ALLOWLIST = (
    "cx/gpt-6.1-sol",
    "cx/gpt-6.1-sol(medium)",
    "cx/gpt-6.1-sol(high)",
    "cx/gpt-6.1-sol(xhigh)",
)
L3_SUBAGENT_ALLOWLIST = ("cx/gpt-6-luna",)
TIMEOUT_ALLOWLIST = (120, 180, 300)
MAX_CYCLES = 3
MAX_RESPONSE_BYTES = 1_048_576
DIMENSION_CATALOG = (
    (1, "Malformed/out-of-bounds types", "NaN, Inf, strings, lists, and bounded input validation."),
    (2, "Invalid/directory I/O paths", "Regular-file checks, strict UTF-8, BOM, and CRLF handling."),
    (3, "Corrupted/duplicate/partial checkpoint shards", "Integrity checks before state mutation."),
    (4, "Fail-closed exit codes & error states", "Non-zero failure states; no silent continuation."),
    (5, "Rollback/atomicity failures", "Atomic replacement, rollback, and durability."),
    (6, "PIT & look-ahead safety", "as_of <= available_at with explicit timezone boundaries."),
    (7, "Trading calendar & holiday boundaries", "Vietnam exchange sessions, holidays, and closures."),
    (8, "Numeric precision & zero-division overflow", "Finite arithmetic, precision, and zero guards."),
    (9, "Concurrency & race condition resistance", "Lock ownership, worker isolation, and race safety."),
    (10, "VND_FULL price scale & unit invariance", "Dong-scale consistency without thousand-dong confusion."),
    (11, "Survivorship & delisting anomalies", "Delisted/frozen instruments without look-ahead."),
    (12, "CLI injection & flag smuggling sanitization", "Allowlisted identifiers and shell-safe arguments."),
    (13, "Schema drift & unexpected column mutation", "Strict schemas and immutable contracts."),
    (14, "Resource exhaustion & memory bounds", "Bounded input, response, and memory use."),
    (15, "Network timeout & 429 retry exhaustion", "Bounded retries and safe provider failure behavior."),
    (16, "Secret redaction & credential leak prevention", "Credential-safe logs, reports, and artifacts."),
    (17, "JEV routing input validation", "Role, risk, cycle, and model-focus type/range validation."),
    (18, "Model catalog & cross-tier allowlisting", "Lead/subagent choices remain role-specific and allowlisted."),
    (19, "Decision context binding & replay prevention", "Gate, role, risk, and session binding."),
    (20, "Decision schema & digest integrity", "Exact fields, canonical bytes, and SHA-256 verification."),
    (21, "Decision publication durability & rollback", "Temporary-file fsync, atomic replace, and cleanup."),
    (22, "Decision lock ownership & concurrency", "Live/stale owner checks and concurrent publisher isolation."),
    (23, "Provider retry & fallback safety", "Bounded 429/timeout retry and low-risk-only fallback."),
    (24, "JEV secret-safe prompt routing", "Sanitized task context and credential-safe routing evidence."),
)
DIMENSION_COUNT = len(DIMENSION_CATALOG)
LEGACY_DIMENSION_COUNTS = (16,)
DIMENSION_MATRIX_COUNTS = tuple(sorted({DIMENSION_COUNT, *LEGACY_DIMENSION_COUNTS}))
DIMENSION_MATRIX_HEADING_RE = re.compile(
    rf"(?im)^##[ \t]+(?:{'|'.join(map(str, DIMENSION_MATRIX_COUNTS))})-Dimension (?:Adversarial Matrix|Evaluation)[ \t]*$"
)


def build_adversarial_directive() -> str:
    dimensions = ", ".join(
        f"({number}) {name.lower()}: {description}" for number, name, description in DIMENSION_CATALOG
    )
    return (
        "MANDATORY 24-DIMENSION ADVERSARIAL TESTING DIRECTIVE: "
        f"Act adversarially across all {DIMENSION_COUNT} catalog dimensions before submitting report: {dimensions} "
    )


ADVERSARIAL_DIRECTIVE_24D = build_adversarial_directive()


def build_dimension_focus_clause(dimension_focus: int | None) -> str:
    if dimension_focus is None:
        return ""
    if type(dimension_focus) is not int or not 1 <= dimension_focus <= DIMENSION_COUNT:
        raise ValueError("dimension_focus outside dynamic catalog")
    _, name, description = next(item for item in DIMENSION_CATALOG if item[0] == dimension_focus)
    return (
        f"JEV DIMENSION ROUTING: Give dimension {dimension_focus} ({name}) extra verification focus: "
        f"{description} This focus supplements the complete {DIMENSION_COUNT}-dimension matrix; it never excludes other dimensions."
    )



def validate_standalone_verdict(report: str) -> str:
    """Accept exactly one standalone L3 verdict token; reject prose/conflicts."""
    match = re.fullmatch(r"[ \t\r\n]*\[(APPROVED|NEEDS_FIX)\][ \t\r\n]*", report)
    if match is None:
        raise ValueError("invalid standalone verdict")
    return match.group(1)


def _finite(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numeric value")
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def strict_json_loads(raw: bytes | str) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    if not isinstance(value, dict):
        raise ValueError("decision envelope must be object")
    return _finite(value)


def escape_xml_data(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value))
    if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
        raise ValueError("control characters forbidden in prompt data")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _read_predecessor_report(predecessor_report: str | Path | None) -> str | None:
    if predecessor_report is None:
        return None
    if not isinstance(predecessor_report, (str, Path)) or not str(predecessor_report):
        raise ValueError("predecessor report path is invalid")
    path = Path(predecessor_report)
    try:
        current = Path(path.absolute().anchor)
        for part in path.absolute().parts[1:]:
            current /= part
            if stat.S_ISLNK(current.lstat().st_mode):
                raise ValueError("predecessor report path contains a symlink")
        before = path.lstat()
    except ValueError as exc:
        if "symlink" in str(exc):
            raise ValueError("predecessor report path must not contain symlinks") from exc
        raise ValueError("predecessor report is unreadable") from exc
    except (OSError, RuntimeError, TypeError) as exc:
        raise ValueError("predecessor report is unreadable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("predecessor report path must be a regular non-symlink file")
    if before.st_size > MAX_RESPONSE_BYTES:
        raise ValueError("predecessor report exceeds size bound")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "r", encoding="utf-8", errors="strict") as handle:
            opened = os.fstat(handle.fileno())
            current = path.lstat()
            if (stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                    or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)):
                raise ValueError("predecessor report path changed during validation")
            text = handle.read(MAX_RESPONSE_BYTES + 1)
        if len(text.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise ValueError("predecessor report exceeds size bound")
        return text
    except (OSError, UnicodeError, RuntimeError, TypeError) as exc:
        raise ValueError("predecessor report is unreadable") from exc


def _findings(report_text: str | None) -> list[str]:
    if report_text is None:
        return []
    return list(dict.fromkeys(re.findall(r"\bF-\d{3}\b", report_text)))


def _escalated(report_text: str | None) -> bool:
    return bool(report_text and re.search(r"(?i)(?:CRITICAL|HIGH)", report_text) and _findings(report_text))


def _redact_credentials(text: str) -> str:
    try:
        from scripts.dispatch_l2 import redact_credentials
    except ImportError:
        from dispatch_l2 import redact_credentials
    return redact_credentials(text)


def _acquire_posix_lock(lock: Path, marker: bytes, owner_bytes: bytes, label: str) -> int:
    import fcntl

    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    owns_lock = False
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise FileExistsError(f"{label} lock must be a regular file: {lock}")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise FileExistsError(f"{label} lock busy: {lock}") from exc
        existing = os.read(fd, 256)
        if existing and not existing.startswith(marker) and not marker.startswith(existing):
            try:
                owner = int(existing)
            except ValueError as exc:
                raise FileExistsError(f"{label} lock busy or unreadable: {lock}") from exc
            try:
                os.kill(owner, 0)
            except ProcessLookupError:
                pass
            except OSError as exc:
                raise FileExistsError(f"{label} lock busy or unreadable: {lock}") from exc
            else:
                raise FileExistsError(f"{label} lock busy: {lock}")
        owns_lock = True
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        written = 0
        while written < len(owner_bytes):
            count = os.write(fd, owner_bytes[written:])
            if count <= 0:
                raise OSError("decision lock owner write made no progress")
            written += count
        os.fsync(fd)
        return fd
    except BaseException:
        if owns_lock:
            try:
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, marker + b"failed")
            except OSError:
                pass
        os.close(fd)
        raise


def _release_posix_lock(fd: int) -> None:
    os.close(fd)


@contextmanager
def _windows_lock_guard(lock: Path):
    """Serialize Windows lock creation, stale reclamation, and release."""
    import msvcrt

    fd = os.open(lock.with_name(lock.name + ".guard"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        for _ in range(100):
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.01)
        else:
            raise FileExistsError(f"lock guard busy: {lock}")
        try:
            yield
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.fdopen(fd, "rb").close()


def atomic_publish_decision(envelope: dict[str, Any], path: str | Path) -> tuple[Path, str]:
    target = Path(path)
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError("decision path must be regular file")
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(_finite(envelope), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    lock = target.with_name(".jev_model_decision.lock")
    fd = None
    lock_identity = None
    lock_owner_bytes = (
        f"jev-flock-v1:{os.getpid()}" if os.name != "nt" else str(os.getpid())
    ).encode("ascii")
    lock_write_complete = False
    try:
        if os.name != "nt":
            fd = _acquire_posix_lock(lock, b"jev-flock-v1:", lock_owner_bytes, "decision")
            lock_identity = os.fstat(fd)
            lock_write_complete = True
        else:
            for attempt in range(2):
                with _windows_lock_guard(lock):
                    try:
                        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    except FileExistsError:
                        if attempt:
                            raise
                        try:
                            previous = lock.stat()
                            owner = int(lock.read_text(encoding="ascii"))
                            import ctypes

                            handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, owner)
                            if handle:
                                ctypes.windll.kernel32.CloseHandle(handle)
                                raise FileExistsError(f"decision lock busy: {lock}")
                            if ctypes.GetLastError() != 87:
                                raise FileExistsError(f"decision lock busy: {lock}")
                            current = lock.stat()
                            if (current.st_dev, current.st_ino) != (previous.st_dev, previous.st_ino) or lock.read_text(encoding="ascii") != str(owner):
                                raise FileExistsError(f"decision lock changed: {lock}")
                            lock.unlink()
                            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                        except (OSError, ValueError) as exc:
                            raise FileExistsError(f"decision lock busy or unreadable: {lock}") from exc
                lock_identity = os.fstat(fd)
                written = 0
                while written < len(lock_owner_bytes):
                    count = os.write(fd, lock_owner_bytes[written:])
                    if count <= 0:
                        raise OSError("decision lock owner write made no progress")
                    written += count
                lock_write_complete = True
                os.fsync(fd)
                break
        assert fd is not None
        previous_stat = target.stat() if target.exists() else None
        previous = _read_bounded_decision(target) if previous_stat is not None else None
        if previous is not None:
            current_stat = target.stat()
            if (current_stat.st_dev, current_stat.st_ino) != (previous_stat.st_dev, previous_stat.st_ino):
                raise RuntimeError("decision predecessor changed during snapshot")
            if len(previous) != current_stat.st_size:
                raise RuntimeError("decision predecessor changed during snapshot")
        with open(temp, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
            staged = os.fstat(handle.fileno())
        try:
            replaced = False
            os.replace(temp, target)
            replaced = True
            _fsync_decision_directory(target.parent)
        except BaseException:
            try:
                current_stat = target.stat() if target.exists() else None
                current_identity = (current_stat.st_dev, current_stat.st_ino) if current_stat else None
                staged_identity = (staged.st_dev, staged.st_ino)
                if replaced or current_identity == staged_identity:
                    if previous is None:
                        target.unlink(missing_ok=True)
                    else:
                        with open(temp, "wb") as handle:
                            handle.write(previous)
                            handle.flush()
                            os.fsync(handle.fileno())
                        os.replace(temp, target)
                    _fsync_decision_directory(target.parent)
            except BaseException as rollback_exc:
                raise RuntimeError("decision publication and rollback failed") from rollback_exc
            raise
    finally:
        try:
            if fd is not None:
                if os.name != "nt":
                    _release_posix_lock(fd)
                else:
                    os.close(fd)
        finally:
            try:
                if os.name == "nt":
                    with _windows_lock_guard(lock):
                        current = lock.stat()
                        owns_lock = lock_identity is not None and (current.st_dev, current.st_ino) == (lock_identity.st_dev, lock_identity.st_ino)
                        contents = lock.read_bytes() if owns_lock else None
                        if owns_lock and (contents == lock_owner_bytes or (not lock_write_complete and lock_owner_bytes.startswith(contents))):
                            lock.unlink(missing_ok=True)
            except (OSError, UnicodeError):
                pass
            finally:
                temp.unlink(missing_ok=True)
    return target, hashlib.sha256(raw).hexdigest()


def _fsync_decision_directory(directory: Path) -> None:
    if os.name != "nt":
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def _read_bounded_decision(target: Path) -> bytes:
    with os.fdopen(os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise FileNotFoundError(f"decision file not found: {target}")
        raw = handle.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("decision payload exceeds size bound")
    return raw


def _validate_decision_models(role: str, lead: Any, subagent: Any, timeout: Any) -> None:
    lead_choices = L2_LEAD_ALLOWLIST if role == "l2" else L3_LEAD_ALLOWLIST
    subagent_choices = L2_SUBAGENT_ALLOWLIST if role == "l2" else L3_SUBAGENT_ALLOWLIST
    if (type(lead) is not str or lead not in lead_choices
            or type(subagent) is not str or subagent not in subagent_choices
            or type(timeout) is not int or timeout not in TIMEOUT_ALLOWLIST):
        raise ValueError("model decision outside allowlist")


def _query_jev_api(
    *,
    role: str,
    risk: str,
    task: str,
    scope: list[str] | None = None,
    predecessor_findings: list[str] | None = None,
    cycle: int = 1,
) -> dict[str, Any]:
    """Query TypeSafe Jev API via system_one with Choice questions."""
    lead_choices = L2_LEAD_ALLOWLIST if role == "l2" else L3_LEAD_ALLOWLIST
    subagent_choices = L2_SUBAGENT_ALLOWLIST if role == "l2" else L3_SUBAGENT_ALLOWLIST

    try:
        from typesafe_sdk import (  # type: ignore[import-untyped]
            Choice,
            TypeSafeAPIConnectionError,
            TypeSafeAPITimeoutError,
            TypeSafeClient,
            TypeSafeInternalServerError,
        )
    except ImportError as exc:
        if risk == "low" and cycle == 1:
            return {
                "lead_model": lead_choices[1] if len(lead_choices) > 1 else lead_choices[0],
                "subagent_model": subagent_choices[0],
                "execution_timeout": 180,
                "dimension_focus": None,
                "fallback_used": True,
                "fallback_reason": "typesafe-sdk not installed",
            }
        raise RuntimeError("typesafe-sdk not installed; fail-closed on high-risk or remediation") from exc

    state = {
        "task_context": escape_xml_data(_redact_credentials(task)),
        "scope_manifest": [escape_xml_data(_redact_credentials(f)) for f in (scope or [])],
        "prior_findings": [escape_xml_data(_redact_credentials(f)) for f in (predecessor_findings or [])],
        "dimension_catalog": [
            {"id": number, "name": name, "description": description}
            for number, name, description in DIMENSION_CATALOG
        ],
        "role": role,
        "risk": risk,
        "cycle": cycle,
    }

    if role == "l2":
        lead_inst = (
            "Select the lead model for L2 implementation work based on task complexity, blast radius, and findings. "
            "Use 9router/cx/gpt-6.1-sol for high complexity, large blast radius, or critical findings; "
            "use 9router/cx/gpt-6-luna for standard, routine, or low-risk tasks."
        )
        subagent_inst = "Select worker subagent model for L2 exploration and boilerplate."
    else:
        lead_inst = (
            "Select the lead auditor model for L3 independent audit. "
            "Use cx/gpt-6.1-sol for high-risk or complex audits; "
            "use cx/gpt-6.1-sol(medium) for routine or low-risk audits."
        )
        subagent_inst = "Select subagent model for L3 audit probes."

    questions = {
        "lead_model": Choice(
            instructions=lead_inst,
            criteria={m: None for m in lead_choices},
        ),
        "subagent_model": Choice(
            instructions=subagent_inst,
            criteria={m: None for m in subagent_choices},
        ),
        "execution_timeout": Choice(
            instructions="Select execution timeout in seconds based on test suite depth (120, 180, or 300).",
            criteria={str(t): None for t in TIMEOUT_ALLOWLIST},
        ),
        "dimension_focus": Choice(
            instructions="Select the single highest-priority adversarial dimension ID from the supplied dynamic catalog. This is extra focus only; all dimensions remain required.",
            criteria={str(number): None for number, _, _ in DIMENSION_CATALOG},
        ),
    }

    for attempt in range(2):
        try:
            with TypeSafeClient(timeout=10.0) as client:
                resp = client.system_one(state=state, questions=questions)
            lead = resp.choices["lead_model"].choice
            subagent = resp.choices["subagent_model"].choice
            timeout = int(resp.choices["execution_timeout"].choice)
            focus = getattr(resp.choices.get("dimension_focus"), "choice", None)
            if type(focus) is not str or focus not in {str(number) for number, _, _ in DIMENSION_CATALOG}:
                raise ValueError("TypeSafe Jev API returned dimension outside dynamic catalog")
            dimension_focus = int(focus)
            if lead not in lead_choices or subagent not in subagent_choices or timeout not in TIMEOUT_ALLOWLIST:
                raise ValueError("TypeSafe Jev API returned value outside allowlist")
            if dimension_focus is not None and not 1 <= dimension_focus <= DIMENSION_COUNT:
                raise ValueError("TypeSafe Jev API returned dimension outside dynamic catalog")
            return {
                "lead_model": lead,
                "subagent_model": subagent,
                "execution_timeout": timeout,
                "dimension_focus": dimension_focus,
                "fallback_used": False,
                "fallback_reason": None,
            }
        except Exception as exc:
            is_retryable = (
                isinstance(exc, (TypeSafeAPIConnectionError, TypeSafeAPITimeoutError))
                or (isinstance(exc, TypeSafeInternalServerError) and getattr(exc, "status", None) == 503)
                or bool(re.search(r"\b429\b|too many requests|rate limit|connect|timeout", str(exc), re.IGNORECASE))
            )
            if is_retryable and attempt == 0:
                time.sleep(2.0)
                continue
            if risk == "low" and cycle == 1 and is_retryable:
                return {
                    "lead_model": lead_choices[1] if len(lead_choices) > 1 else lead_choices[0],
                    "subagent_model": subagent_choices[0],
                    "execution_timeout": 180,
                    "dimension_focus": None,
                    "fallback_used": True,
                    "fallback_reason": str(exc),
                }
            raise


def evaluate_model_decision(
    *,
    role: str,
    risk: str,
    cycle: int = 1,
    gate: str = "",
    session_id: str = "",
    task: str = "",
    scope: list[str] | None = None,
    predecessor_report: str | Path | None = None,
    response: dict[str, Any] | None = None,
    decision_path: str | Path | None = None,
) -> dict[str, Any]:
    if role not in ("l2", "l3") or risk not in ("low", "high") or type(cycle) is not int:
        raise ValueError("invalid routing inputs")
    if cycle < 1 or cycle > MAX_CYCLES:
        raise RuntimeError("MAX_REMEDIATIONS_EXCEEDED")
    if response is not None:
        if not isinstance(response, dict):
            raise ValueError("model response must be an object")
        if "dimension_focus" in response:
            build_dimension_focus_clause(response["dimension_focus"])
        if len(json.dumps(response, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise ValueError("response payload exceeds 1MB")

    report_text = _read_predecessor_report(predecessor_report)
    escalated = _escalated(report_text)
    findings = _findings(report_text)
    lead_choices = L2_LEAD_ALLOWLIST if role == "l2" else L3_LEAD_ALLOWLIST
    subagent_choices = L2_SUBAGENT_ALLOWLIST if role == "l2" else L3_SUBAGENT_ALLOWLIST

    fallback_used = False
    fallback_reason = None

    if response is not None:
        lead = response["lead_model"] if "lead_model" in response else (lead_choices[0] if escalated else lead_choices[1])
        subagent = response["subagent_model"] if "subagent_model" in response else subagent_choices[0]
        timeout = response.get("execution_timeout", 180)
        dimension_focus = response.get("dimension_focus")
        fallback_used = response.get("fallback_used", False)
        fallback_reason = response.get("fallback_reason")
    else:
        api_result = _query_jev_api(
            role=role,
            risk=risk,
            task=task,
            scope=scope,
            predecessor_findings=findings,
            cycle=cycle,
        )
        lead = api_result["lead_model"]
        subagent = api_result["subagent_model"]
        timeout = api_result["execution_timeout"]
        dimension_focus = api_result.get("dimension_focus")
        fallback_used = api_result["fallback_used"]
        fallback_reason = api_result["fallback_reason"]

    _validate_decision_models(role, lead, subagent, timeout)
    build_dimension_focus_clause(dimension_focus)
    if (type(fallback_used) is not bool or
            (fallback_used and (risk != "low" or cycle != 1 or type(fallback_reason) is not str or not fallback_reason.strip())) or
            (not fallback_used and (fallback_reason is not None or (response is not None and "fallback_reason" in response))) or
            (response is not None and "fallback_reason" in response and "fallback_used" not in response)):
        raise ValueError("model decision fallback fields mismatch")

    # Monotonic escalation guard: cannot downgrade if escalated
    if escalated and lead != lead_choices[0]:
        lead = lead_choices[0]

    if fallback_reason is not None:
        try:
            from scripts.dispatch_l2 import redact_credentials
        except ImportError:
            from dispatch_l2 import redact_credentials
        fallback_reason = redact_credentials(str(fallback_reason))

    envelope: dict[str, Any] = {
        "schema_version": "2.0",
        "gate": gate,
        "session_id": session_id,
        "role": role,
        "risk": risk,
        "cycle": cycle,
        "task": escape_xml_data(_redact_credentials(task)),
        "lead_model": lead,
        "subagent_model": subagent,
        "execution_timeout": timeout,
        "dimension_focus": dimension_focus,
        "predecessor_findings": findings,
        "escalated": escalated,
    }
    if fallback_used:
        envelope["fallback_used"] = fallback_used
        envelope["fallback_reason"] = fallback_reason

    if decision_path is not None:
        path, digest = atomic_publish_decision(envelope, decision_path)
        envelope["decision_path"] = path.as_posix()
        envelope["decision_digest"] = digest
    return envelope


def load_decision(
    path: str | Path,
    expected_digest: str,
    *,
    expected_role: str | None = None,
    expected_gate: str | None = None,
    expected_session_id: str | None = None,
    expected_risk: str | None = None,
) -> dict[str, Any]:
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise FileNotFoundError(f"decision file not found: {target}")
    raw = _read_bounded_decision(target)
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest) or hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ValueError("model decision digest mismatch")
    decision = strict_json_loads(raw)
    required = {
        "schema_version",
        "gate",
        "session_id",
        "role",
        "risk",
        "cycle",
        "task",
        "lead_model",
        "subagent_model",
        "execution_timeout",
        "predecessor_findings",
        "escalated",
    }
    optional = {"fallback_used", "fallback_reason", "dimension_focus"}
    keys = set(decision)
    if not (required <= keys <= (required | optional)):
        raise ValueError("model decision schema mismatch")
    if decision["schema_version"] != "2.0" or decision["role"] not in ("l2", "l3"):
        raise ValueError("model decision schema mismatch")
    if (decision["risk"] not in ("low", "high") or type(decision["cycle"]) is not int
            or not 1 <= decision["cycle"] <= MAX_CYCLES):
        raise ValueError("model decision field types mismatch")
    if any(type(decision[field]) is not str or not decision[field].strip() for field in ("gate", "session_id", "task")):
        raise ValueError("model decision context types mismatch")
    findings = decision["predecessor_findings"]
    if (type(findings) is not list
            or any(type(item) is not str or not re.fullmatch(r"F-\d{3}", item) for item in findings)
            or len(findings) != len(set(findings)) or type(decision["escalated"]) is not bool):
        raise ValueError("model decision field types mismatch")
    if "fallback_used" in decision or "fallback_reason" in decision:
        if (not {"fallback_used", "fallback_reason"} <= keys or decision["fallback_used"] is not True
                or type(decision["fallback_used"]) is not bool):
            raise ValueError("model decision fallback fields mismatch")
        reason = decision["fallback_reason"]
        if type(reason) is not str or not reason.strip():
            raise ValueError("model decision fallback fields mismatch")
    _validate_decision_models(decision["role"], decision["lead_model"], decision["subagent_model"], decision["execution_timeout"])
    if "dimension_focus" in decision:
        build_dimension_focus_clause(decision["dimension_focus"])
    checks = (("role", expected_role), ("gate", expected_gate), ("session_id", expected_session_id), ("risk", expected_risk))
    if any(expected is not None and decision[field] != expected for field, expected in checks):
        raise ValueError("model decision context mismatch")
    return decision
