"""Shared alpha LLM configuration resolution."""

from __future__ import annotations

import json
import os
import hashlib
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUPPORTED_LLM_PROVIDERS = {"mock", "openai-compatible", "jev"}
ALPHA_LLM_CONFIG_ENV = "OMEGA_ALPHA_LLM_CONFIG_PATH"


def classify_jev(
    *, domain: str, facts: dict[str, Any], choices: dict[str, tuple[str, ...]],
    cache_path: Path, as_of: datetime, available_at: datetime, model: str,
) -> dict[str, Any]:
    """Phan loai JEV voi dau vet PIT va cache SQLite co giao dich."""
    if as_of.tzinfo is None or available_at.tzinfo is None or available_at > as_of:
        raise ValueError("JEV source not available at cutoff")
    if not choices or any(not options or len(set(options)) != len(options) for options in choices.values()):
        raise ValueError("invalid JEV choice allowlist")
    payload = {"version": 1, "domain": domain, "facts": facts, "choices": choices,
               "as_of": as_of.isoformat(), "available_at": available_at.isoformat(), "model": model}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    fingerprint = hashlib.sha256(raw).hexdigest()
    if cache_path.exists() and not cache_path.is_file():
        raise ValueError("JEV cache path must be a file")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(cache_path, timeout=5) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS decisions (fingerprint TEXT PRIMARY KEY, envelope TEXT NOT NULL)")
        row = db.execute("SELECT envelope FROM decisions WHERE fingerprint=?", (fingerprint,)).fetchone()
        if row:
            envelope = json.loads(row[0])
            _validate_jev_envelope(envelope, fingerprint, domain, choices, as_of, available_at, model)
            return envelope
    from typesafe_sdk import Choice, TypeSafeClient, TypeSafeAPIConnectionError, TypeSafeAPITimeoutError, TypeSafeInternalServerError

    questions = {key: Choice(instructions=f"Select {key} from evidence only", criteria={option: None for option in options}) for key, options in choices.items()}
    for attempt in range(1, 3):
        try:
            with TypeSafeClient(timeout=10.0) as client:
                response = client.system_one(state={"domain": domain, "facts": facts}, questions=questions)
            selected = {key: response.choices[key].choice for key in choices}
            if any(type(selected[key]) is not str or selected[key] not in options for key, options in choices.items()):
                raise ValueError("JEV choice outside allowlist")
            break
        except (TypeSafeAPIConnectionError, TypeSafeAPITimeoutError, TypeSafeInternalServerError):
            if attempt == 2:
                raise RuntimeError("JEV unavailable after two attempts") from None
            time.sleep(2.0)
    envelope = {"version": 1, "fingerprint": fingerprint, "domain": domain,
                "choices": {k: list(v) for k, v in choices.items()}, "selected": selected,
                "as_of": as_of.isoformat(), "available_at": available_at.isoformat(),
                "decided_at": datetime.now(timezone.utc).isoformat(), "model": model, "attempts": attempt}
    with sqlite3.connect(cache_path, timeout=5) as db:
        db.execute("INSERT OR IGNORE INTO decisions VALUES (?, ?)", (fingerprint, json.dumps(envelope, sort_keys=True)))
        stored = db.execute("SELECT envelope FROM decisions WHERE fingerprint=?", (fingerprint,)).fetchone()
    result = json.loads(stored[0])
    _validate_jev_envelope(result, fingerprint, domain, choices, as_of, available_at, model)
    return result


def _validate_jev_envelope(
    envelope: Any, fingerprint: str, domain: str, choices: dict[str, tuple[str, ...]],
    as_of: datetime, available_at: datetime, model: str,
) -> None:
    """Tu choi metadata cache sai lech hoac vi pham moc thoi gian PIT."""
    expected = {"version", "fingerprint", "domain", "choices", "selected", "as_of", "available_at", "decided_at", "model", "attempts"}
    if not isinstance(envelope, dict) or envelope.keys() != expected:
        raise ValueError("invalid JEV cache envelope")
    try:
        timestamps = [datetime.fromisoformat(envelope[key]) for key in ("as_of", "available_at", "decided_at")]
        valid = (
            type(envelope["version"]) is int and envelope["version"] == 1
            and type(envelope["fingerprint"]) is str and envelope["fingerprint"] == fingerprint
            and type(envelope["domain"]) is str and envelope["domain"] == domain
            and type(envelope["model"]) is str and envelope["model"] == model
            and type(envelope["attempts"]) is int
            and 1 <= envelope["attempts"] <= 2
            and type(envelope["as_of"]) is str and type(envelope["available_at"]) is str
            and type(envelope["decided_at"]) is str
            and all(ts.tzinfo is not None and ts.utcoffset() is not None for ts in timestamps)
            and timestamps[0] == as_of and timestamps[1] == available_at
            and timestamps[1] <= timestamps[0]
            and timestamps[2] >= timestamps[1]
            and type(envelope["choices"]) is dict
            and envelope["choices"] == {k: list(v) for k, v in choices.items()}
            and isinstance(envelope["selected"], dict)
            and envelope["selected"].keys() == choices.keys()
            and all(type(envelope["selected"][k]) is str and envelope["selected"][k] in v for k, v in choices.items())
        )
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
        raise ValueError("invalid JEV cache envelope") from exc
    if not valid:
        raise ValueError("invalid JEV cache envelope")


def load_external_alpha_config(repo_root: Path) -> dict[str, Any]:
    config_path = os.environ.get(ALPHA_LLM_CONFIG_ENV)
    if not config_path:
        return {}
    try:
        path = Path(config_path)
        resolved = path.resolve(strict=True)
        if not path.is_absolute() or str(path) != str(resolved) or resolved.is_relative_to(repo_root.resolve()):
            return {}
        config = json.loads(path.read_text(encoding="utf-8"))
        provider = config.get("provider") if isinstance(config, dict) else None
        if not isinstance(config, dict) or (provider is not None and str(provider).strip().lower() not in SUPPORTED_LLM_PROVIDERS):
            return {}
        return config
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, TypeError):
        return {}


def resolve_alpha_llm_config(repo_root: Path, provider_override: str | None = None) -> dict[str, Any]:
    file_config = load_external_alpha_config(repo_root)
    selected = provider_override or file_config.get("provider") or os.environ.get("OMEGA_LLM_PROVIDER")
    if selected is None:
        selected = "openai-compatible" if (file_config.get("api_key") or os.environ.get("OMEGA_LLM_API_KEY")) else "mock"
    provider = str(selected).strip().lower()
    if provider not in SUPPORTED_LLM_PROVIDERS:
        source = "provider" if provider_override is not None else "OMEGA_LLM_PROVIDER"
        raise ValueError(f"Unsupported provider in {source}: {provider}")
    return {
        "provider": provider,
        "api_key": file_config.get("api_key") or os.environ.get("OMEGA_LLM_API_KEY"),
        "base_url": file_config.get("base_url") or os.environ.get("OMEGA_LLM_BASE_URL"),
        "model": file_config.get("model") or os.environ.get("OMEGA_LLM_MODEL", "gpt-4"),
    }


def sanitize_llm_config(config: dict[str, Any]) -> dict[str, Any]:
    return {"provider": config.get("provider"), "base_url": config.get("base_url"), "model": config.get("model"), "api_key_present": bool(config.get("api_key"))}
