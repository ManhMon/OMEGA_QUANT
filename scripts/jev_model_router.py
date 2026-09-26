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
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any

L2_LEAD_ALLOWLIST = ("9router/cx/gpt-6-sol", "9router/cx/gpt-6-luna")
L2_SUBAGENT_ALLOWLIST = ("ag/gemini",)
L3_LEAD_ALLOWLIST = ("cx/gpt-6-sol", "cx/gpt-6-sol(medium)")
L3_SUBAGENT_ALLOWLIST = ("cx/gpt-6-luna",)
TIMEOUT_ALLOWLIST = (120, 180, 300)
MAX_CYCLES = 3
MAX_RESPONSE_BYTES = 1_048_576


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


def strict_json_loads(raw: bytes | str) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    value = json.loads(raw, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
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


def _findings(predecessor_report: str | Path | None) -> list[str]:
    if not predecessor_report:
        return []
    path = Path(predecessor_report)
    try:
        if path.is_file():
            if path.stat().st_size > MAX_RESPONSE_BYTES:
                raise ValueError("predecessor report exceeds size bound")
            text = path.read_text(encoding="utf-8")
        else:
            text = str(predecessor_report)
    except OSError:
        text = str(predecessor_report)
    return list(dict.fromkeys(re.findall(r"\bF-\d{3}\b", text)))


def _escalated(predecessor_report: str | Path | None) -> bool:
    if not predecessor_report:
        return False
    path = Path(predecessor_report)
    try:
        if path.is_file():
            if path.stat().st_size > MAX_RESPONSE_BYTES:
                raise ValueError("predecessor report exceeds size bound")
            text = path.read_text(encoding="utf-8")
        else:
            text = str(predecessor_report)
    except OSError:
        text = str(predecessor_report)
    return bool(re.search(r"(?i)(?:CRITICAL|HIGH)", text) and _findings(text))


def atomic_publish_decision(envelope: dict[str, Any], path: str | Path) -> tuple[Path, str]:
    target = Path(path)
    if target.exists() and not target.is_file():
        raise ValueError("decision path must be regular file")
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(_finite(envelope), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    lock = target.with_name(".jev_model_decision.lock")
    fd = None
    for attempt in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.fsync(fd)
            break
        except FileExistsError:
            if attempt:
                raise
            try:
                stat = lock.stat()
                owner = int(lock.read_text(encoding="ascii"))
                alive = False
                if os.name == "nt":
                    import ctypes

                    SYNCHRONIZE = 0x00100000
                    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, owner)
                    if handle:
                        alive = True
                        ctypes.windll.kernel32.CloseHandle(handle)
                    else:
                        alive = False
                else:
                    try:
                        os.kill(owner, 0)
                        alive = True
                    except OSError as exc:
                        alive = exc.errno == errno.EPERM
                if not alive:
                    current = lock.stat()
                    if (current.st_dev, current.st_ino, current.st_mtime_ns) == (stat.st_dev, stat.st_ino, stat.st_mtime_ns):
                        lock.unlink()
            except (OSError, ValueError):
                raise FileExistsError(f"decision lock busy or unreadable: {lock}")
    assert fd is not None
    try:
        with open(temp, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
        if os.name != "nt":
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        os.close(fd)
        try:
            current = lock.read_text(encoding="ascii")
            if current == str(os.getpid()):
                lock.unlink(missing_ok=True)
        except OSError:
            pass
        temp.unlink(missing_ok=True)
    return target, hashlib.sha256(raw).hexdigest()


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
                "fallback_used": True,
                "fallback_reason": "typesafe-sdk not installed",
            }
        raise RuntimeError("typesafe-sdk not installed; fail-closed on high-risk or remediation") from exc

    state = {
        "task_context": escape_xml_data(task),
        "scope_manifest": [escape_xml_data(f) for f in (scope or [])],
        "prior_findings": [escape_xml_data(f) for f in (predecessor_findings or [])],
        "role": role,
        "risk": risk,
        "cycle": cycle,
    }

    if role == "l2":
        lead_inst = (
            "Select the lead model for L2 implementation work based on task complexity, blast radius, and findings. "
            "Use 9router/cx/gpt-6-sol for high complexity, large blast radius, or critical findings; "
            "use 9router/cx/gpt-6-luna for standard, routine, or low-risk tasks."
        )
        subagent_inst = "Select worker subagent model for L2 exploration and boilerplate."
    else:
        lead_inst = (
            "Select the lead auditor model for L3 independent audit. "
            "Use cx/gpt-6-sol for high-risk or complex audits; "
            "use cx/gpt-6-sol(medium) for routine or low-risk audits."
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
    }

    for attempt in range(2):
        try:
            with TypeSafeClient(timeout=10.0) as client:
                resp = client.system_one(state=state, questions=questions)
            lead = resp.choices["lead_model"].choice
            subagent = resp.choices["subagent_model"].choice
            timeout = int(resp.choices["execution_timeout"].choice)
            if lead not in lead_choices or subagent not in subagent_choices or timeout not in TIMEOUT_ALLOWLIST:
                raise ValueError("TypeSafe Jev API returned value outside allowlist")
            return {
                "lead_model": lead,
                "subagent_model": subagent,
                "execution_timeout": timeout,
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
    if response is not None and len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("response payload exceeds 1MB")

    escalated = _escalated(predecessor_report)
    findings = _findings(predecessor_report)
    lead_choices = L2_LEAD_ALLOWLIST if role == "l2" else L3_LEAD_ALLOWLIST
    subagent_choices = L2_SUBAGENT_ALLOWLIST if role == "l2" else L3_SUBAGENT_ALLOWLIST

    fallback_used = False
    fallback_reason = None

    if response is not None:
        lead = response.get("lead_model") or (lead_choices[0] if escalated else lead_choices[1])
        subagent = response.get("subagent_model") or subagent_choices[0]
        timeout = response.get("execution_timeout", 180)
        fallback_used = bool(response.get("fallback_used", False))
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
        fallback_used = api_result["fallback_used"]
        fallback_reason = api_result["fallback_reason"]

    _validate_decision_models(role, lead, subagent, timeout)

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
        "task": escape_xml_data(task),
        "lead_model": lead,
        "subagent_model": subagent,
        "execution_timeout": timeout,
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
    if not target.is_file():
        raise FileNotFoundError(f"decision file not found: {target}")
    if target.stat().st_size > MAX_RESPONSE_BYTES:
        raise ValueError("decision payload exceeds size bound")
    raw = target.read_bytes()
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
    optional = {"fallback_used", "fallback_reason"}
    keys = set(decision)
    if not (required <= keys <= (required | optional)):
        raise ValueError("model decision schema mismatch")
    if decision["schema_version"] != "2.0" or decision["role"] not in ("l2", "l3"):
        raise ValueError("model decision schema mismatch")
    if decision["risk"] not in ("low", "high") or type(decision["cycle"]) is not int:
        raise ValueError("model decision field types mismatch")
    if not isinstance(decision["gate"], str) or not isinstance(decision["session_id"], str):
        raise ValueError("model decision context types mismatch")
    if not isinstance(decision["predecessor_findings"], list) or type(decision["escalated"]) is not bool:
        raise ValueError("model decision field types mismatch")
    _validate_decision_models(decision["role"], decision["lead_model"], decision["subagent_model"], decision["execution_timeout"])
    checks = (("role", expected_role), ("gate", expected_gate), ("session_id", expected_session_id), ("risk", expected_risk))
    if any(expected is not None and decision[field] != expected for field, expected in checks):
        raise ValueError("model decision context mismatch")
    return decision
