"""Shared alpha LLM configuration resolution."""

from __future__ import annotations

import json
import os
import hashlib
import math
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SUPPORTED_LLM_PROVIDERS = {"mock", "openai-compatible", "jev"}
ALPHA_LLM_CONFIG_ENV = "OMEGA_ALPHA_LLM_CONFIG_PATH"
JEV_SCHEMA_VERSION = 2
MAX_JEV_PAYLOAD = 1_048_576
MAX_JEV_ROWS = 10_000
JEV_USAGE_RETENTION_DAYS = 30
DOMAIN_REGISTRY = {
    "regime_arbitration": {"regime": ("BULL", "BEAR", "SIDEWAYS")},
    "alpha_weight_regime": {"weight_regime": ("momentum_heavy", "mean_reversion_heavy", "balanced", "defensive")},
    "alpha_disagreement": {"outcome": ("trend_supported", "reversal_supported", "mixed", "insufficient")},
    "event_novelty": {"novelty": ("new_material", "repeat", "unresolved", "irrelevant")},
    "forensic_audit": {"audit_verdict": ("clean", "qualified_exception", "disclaimer", "adverse"),
                       "revenue_quality": ("organic_cash_backed", "unbilled_receivable_inflation", "channel_stuffing"),
                       "asset_siphoning_risk": ("low", "unusual_lending_to_affiliates", "cross_pledge_collateral")},
    "corporate_action": {"action": ("cash_dividend", "stock_dividend", "dilutive_rights_issue", "esop_excessive", "private_placement_discount")},
    "data_anomaly": {"anomaly": ("valid_market_breakout", "unadjusted_corporate_action_gap", "block_trade_noise", "stale_feed_error")},
    "risk_sentinel": {"action": ("hold", "reduce_exposure", "halt_new_entries", "full_de_risk"),
                      "recovery": ("wait", "resume_gradual", "resume_full")},
    "shared_event_driver": {"driver": ("shared_driver", "independent", "unclear")},
    "execution_context": {"context": ("routine", "event_sensitive", "unclear")},
    "drift_decay": {"drift": ("structural_microstructure_change", "cyclical_regime_rotation", "noise"),
                    "recommendation": ("full_retrain", "incremental_update", "wait")},
}
# Existing consumers retain their versioned adapter contracts; unimplemented research domains cannot gain authority.
LEGACY_DOMAINS = {"macro", "micro", "macro_news", "copilot-router-v1", "copilot", "test"}
_SECRET = re.compile(r"(?:api[_-]?key|authorization|password|secret|token|bearer|credential|private[_-]?key|cookie|session(?:[_-]?(?:id|key|token))?|set-cookie|sk-[a-zA-Z0-9_-]+|gh[pousr]_[a-zA-Z0-9]+|https?://[^\s/]+:[^\s/@]+@)", re.I)
_PROVIDER_SECRET = re.compile(
    r"(?i)(https?://)[^/@\s]+@|"
    r"(\b(?:api[_-]?key|authorization|password|secret|token|bearer|credential|private[_-]?key|cookie|session(?:[_-]?(?:id|key|token))?|set-cookie)\s*[:=]\s*(?:bearer\s+)?|\bbearer\s+)[^\s,;&]+|"
    r"\b(?:sk-[a-zA-Z0-9_-]+|gh[pousr]_[a-zA-Z0-9]+)\b"
)


def _redact_provider_error(error: Exception) -> str:
    text = str(error)
    return _PROVIDER_SECRET.sub(lambda match: (match.group(1) or match.group(2) or "") + "[REDACTED]", text)


def _utc(value: datetime) -> str:
    if not hasattr(value, "astimezone") or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("JEV timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _canonical(value: Any) -> bytes:
    def check(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if type(key) is not str or _SECRET.search(key):
                    raise ValueError("invalid JEV facts")
                check(child)
        elif isinstance(item, (tuple, list)):
            for child in item:
                check(child)
        elif type(item) is str:
            if _SECRET.search(item):
                raise ValueError("invalid JEV facts")
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError("invalid JEV facts")
        elif item is not None and type(item) not in (bool, int):
            raise ValueError("invalid JEV facts")

    check(value)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_JEV_PAYLOAD:
        raise ValueError("JEV request exceeds size bound")
    return raw


def _validate_domain(domain: str, choices: dict[str, tuple[str, ...]]) -> None:
    if type(domain) is not str or domain not in DOMAIN_REGISTRY and domain not in LEGACY_DOMAINS:
        raise ValueError("unregistered JEV domain")
    if (type(choices) is not dict or not choices or len(choices) > 8 or
            any(type(key) is not str or not key or type(options) is not tuple or not options
                or len(options) > 32 or any(type(option) is not str or not option or len(option) > 100
                                       for option in options) or len(set(options)) != len(options)
                for key, options in choices.items())):
        raise ValueError("invalid JEV choice allowlist")
    if domain in DOMAIN_REGISTRY and choices != DOMAIN_REGISTRY[domain]:
        raise ValueError("invalid JEV domain contract")


def _selective_reason(*, novelty: bool, disagreement: bool, materiality: bool,
                      rule_sufficient: bool, estimated_benefit: float | None, estimated_cost: float) -> str | None:
    if rule_sufficient:
        return "rule_sufficient"
    if not (novelty or disagreement) or not materiality:
        return "no_new_information"
    if estimated_benefit is None or estimated_benefit <= estimated_cost:
        return "benefit_unproven"
    return None


def classify_jev(
    *, domain: str, facts: dict[str, Any], choices: dict[str, tuple[str, ...]],
    cache_path: Path, as_of: datetime, available_at: datetime, model: str,
    entity_ids: tuple[str, ...] = (), source_revisions: tuple[str, ...] = (),
    gate_id: str = "research", mode: str = "live", prompt_version: str = "v1",
    policy_version: str = "v1", profile_version: str = "v1", feature_version: str = "v1",
    dataset_manifest: str = "unspecified", code_revision: str = "unspecified",
    max_calls: int = 100, max_spend: float = 0.0, estimated_cost: float = 0.0,
    novelty: bool = True, disagreement: bool = False, materiality: bool = True,
    rule_sufficient: bool = False, estimated_benefit: float | None = None,
    schema_version: int = 1,
) -> dict[str, Any]:
    """Classify PIT-safe evidence, with a bounded, versioned decision ledger."""
    cutoff, source_time = _utc(as_of), _utc(available_at)
    if available_at > as_of:
        raise ValueError("JEV source not available at cutoff")
    _validate_domain(domain, choices)
    if type(schema_version) is not int or schema_version not in (1, JEV_SCHEMA_VERSION):
        raise ValueError("invalid JEV schema version")
    if domain in DOMAIN_REGISTRY and schema_version != JEV_SCHEMA_VERSION:
        schema_version = JEV_SCHEMA_VERSION
    if schema_version == JEV_SCHEMA_VERSION and mode in ("live", "selective") and as_of < datetime.now(timezone.utc):
        raise ValueError("JEV decision cutoff precedes invocation")
    identifiers = (gate_id, model, prompt_version, policy_version, profile_version, feature_version, dataset_manifest, code_revision)
    if (any(type(item) is not str or not item or len(item) > 128 or _SECRET.search(item) for item in identifiers)
            or mode not in ("live", "replay", "cache_only", "off", "selective")
            or type(entity_ids) is not tuple or type(source_revisions) is not tuple
            or len(entity_ids) > 100 or len(source_revisions) > 100
            or any(type(item) is not str or not item or len(item) > 128 or _SECRET.search(item)
                   for item in (*entity_ids, *source_revisions))
            or type(max_calls) is not int or not 0 <= max_calls <= 100
            or type(max_spend) not in (int, float) or not math.isfinite(max_spend) or max_spend < 0
            or type(estimated_cost) not in (int, float) or not math.isfinite(estimated_cost) or estimated_cost < 0
            or estimated_benefit is not None and (type(estimated_benefit) not in (int, float)
                                                  or not math.isfinite(estimated_benefit) or estimated_benefit < 0)
            or any(type(flag) is not bool for flag in (novelty, disagreement, materiality, rule_sufficient))):
        raise ValueError("invalid JEV policy")
    if type(facts) is not dict:
        raise ValueError("invalid JEV facts")
    payload = {"schema_version": schema_version, "domain": domain, "facts": facts, "choices": choices,
               "decision_cutoff": cutoff if schema_version == JEV_SCHEMA_VERSION else cutoff[:10],
               "available_at": source_time if schema_version == JEV_SCHEMA_VERSION else source_time[:10], "entity_ids": entity_ids,
               "source_revisions": source_revisions, "gate_id": gate_id, "model": model,
               "prompt_version": prompt_version, "policy_version": policy_version,
               "profile_version": profile_version, "feature_version": feature_version,
               "dataset_manifest": dataset_manifest, "code_revision": code_revision}
    fingerprint = hashlib.sha256(_canonical(payload)).hexdigest()
    facts_hash = hashlib.sha256(_canonical(facts)).hexdigest()
    if not isinstance(cache_path, Path) or cache_path.exists() and not cache_path.is_file():
        raise ValueError("JEV cache path must be a file")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if schema_version == 1:
        # ponytail: Probe legacy cache before the writer lock; locked read below remains authoritative.
        with sqlite3.connect(cache_path, timeout=5):
            pass
    with sqlite3.connect(cache_path, timeout=5) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS decisions (fingerprint TEXT PRIMARY KEY, envelope TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS usage (day TEXT NOT NULL, gate_id TEXT NOT NULL, cost REAL NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM usage WHERE day < ?", ((datetime.now(timezone.utc) - timedelta(days=JEV_USAGE_RETENTION_DAYS)).date().isoformat(),))
        db.commit()
        row = db.execute("SELECT envelope FROM decisions WHERE fingerprint=?", (fingerprint,)).fetchone()
        if row:
            try:
                envelope = json.loads(row[0], parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                _validate_jev_envelope(envelope, fingerprint, domain, choices, as_of, available_at, model,
                                       cached=True, gate_id=gate_id, mode=mode, payload=payload, facts_hash=facts_hash,
                                       schema_version=schema_version)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("invalid JEV cache envelope") from exc
            return envelope
        if mode in ("replay", "cache_only", "off"):
            raise ValueError("JEV cache miss: provider disabled")
        if mode == "selective":
            reason = _selective_reason(novelty=novelty, disagreement=disagreement, materiality=materiality,
                                       rule_sufficient=rule_sufficient, estimated_benefit=estimated_benefit,
                                       estimated_cost=estimated_cost)
            if reason:
                raise ValueError(f"JEV skipped: {reason}")
        import typesafe_sdk as sdk
        Choice, TypeSafeClient = sdk.Choice, sdk.TypeSafeClient
        transient_errors = tuple(getattr(sdk, name) for name in (
            "TypeSafeAPIConnectionError", "TypeSafeAPITimeoutError", "TypeSafeInternalServerError",
            "TypeSafeRateLimitError") if hasattr(sdk, name))

        questions = {key: Choice(instructions=f"Select {key} from evidence only", criteria={option: None for option in options}) for key, options in choices.items()}
        day = cutoff[:10]
        # ponytail: Concurrent misses can make duplicate paid calls; add a leased reservation if deduplication becomes necessary.
        for attempt in range(1, 3):
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT envelope FROM decisions WHERE fingerprint=?", (fingerprint,)).fetchone()
            if row:
                db.rollback()
                try:
                    envelope = json.loads(row[0], parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    _validate_jev_envelope(envelope, fingerprint, domain, choices, as_of, available_at, model,
                                           cached=True, gate_id=gate_id, mode=mode, payload=payload, facts_hash=facts_hash,
                                           schema_version=schema_version)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError("invalid JEV cache envelope") from exc
                return envelope
            if db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] >= MAX_JEV_ROWS:
                raise ValueError("JEV cache row limit reached")
            count, spent = db.execute("SELECT COUNT(*), COALESCE(SUM(cost), 0) FROM usage WHERE day=? AND gate_id=?",
                                      (day, gate_id)).fetchone()
            if count >= max_calls or max_spend and spent + estimated_cost > max_spend:
                raise ValueError("JEV budget exhausted")
            if db.execute("SELECT COUNT(*) FROM usage").fetchone()[0] >= MAX_JEV_ROWS:
                raise ValueError("JEV usage row limit reached")
            db.execute("INSERT INTO usage VALUES (?, ?, ?)", (day, gate_id, estimated_cost))
            db.commit()
            started = time.monotonic()
            try:
                with TypeSafeClient(timeout=10.0) as client:
                    response = client.system_one(state={"domain": domain, "facts": facts}, questions=questions)
                selected = {key: response.choices[key].choice for key in choices}
                if any(type(selected[key]) is not str or selected[key] not in options for key, options in choices.items()):
                    raise ValueError("JEV choice outside allowlist")
                break
            except transient_errors:
                if attempt == 2:
                    raise RuntimeError("JEV unavailable after two attempts") from None
                time.sleep(2.0)
                continue
            except Exception as exc:
                if type(exc) is ValueError and str(exc) == "JEV choice outside allowlist":
                    raise
                safe_message = _redact_provider_error(exc)
            raise RuntimeError(safe_message)
        decided = datetime.now(timezone.utc)
        envelope = {"version": schema_version, "schema_version": schema_version,
                    "decision_id": fingerprint, "request_fingerprint": fingerprint, "fingerprint": fingerprint,
                    "domain": domain, "gate_id": gate_id, "mode": mode, "entity_ids": list(entity_ids),
                    "source_revisions": list(source_revisions), "choices": {k: list(v) for k, v in choices.items()},
                    "source_hash": facts_hash, "source_id": domain, "ingested_at": source_time,
                    "evidence_refs": list(source_revisions),
                    "selected": selected, "as_of": cutoff, "decision_cutoff": cutoff,
                    "event_time": source_time, "available_at": source_time,
                    "decided_at": _utc(decided), "decision_time": _utc(decided), "generated_at": _utc(decided),
                    "expires_at": None, "model": model, "provider": "jev", "prompt_version": prompt_version,
                    "policy_version": policy_version, "profile_version": profile_version,
                    "feature_version": feature_version, "dataset_manifest": dataset_manifest,
                    "code_revision": code_revision, "attempts": attempt, "status": "accepted",
                    "reason_code": "classified", "cache_hit": False,
                    "latency_ms": max(0, int((time.monotonic() - started) * 1000)),
                    "estimated_cost": estimated_cost * attempt, "authority": "research_only"}
        _validate_jev_envelope(envelope, fingerprint, domain, choices, as_of, available_at, model,
                               gate_id=gate_id, mode=mode, payload=payload, facts_hash=facts_hash,
                               schema_version=schema_version)
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO decisions VALUES (?, ?)", (fingerprint, json.dumps(envelope, sort_keys=True)))
        # ponytail: Concurrent misses may race to publish; the first validated decision remains authoritative.
        stored = json.loads(db.execute("SELECT envelope FROM decisions WHERE fingerprint=?", (fingerprint,)).fetchone()[0])
        _validate_jev_envelope(stored, fingerprint, domain, choices, as_of, available_at, model,
                                gate_id=gate_id, mode=mode, payload=payload, facts_hash=facts_hash,
                                schema_version=schema_version)
        return stored


def _validate_jev_envelope(
    envelope: Any, fingerprint: str, domain: str, choices: dict[str, tuple[str, ...]],
    as_of: datetime, available_at: datetime, model: str, cached: bool = False,
    gate_id: str = "research", mode: str = "live", payload: dict[str, Any] | None = None,
    facts_hash: str | None = None, schema_version: int = 1,
) -> None:
    """Tu choi metadata cache sai lech hoac vi pham moc thoi gian PIT."""
    expected = {"version", "schema_version", "decision_id", "request_fingerprint", "fingerprint", "domain",
                "gate_id", "mode", "entity_ids", "source_revisions", "source_hash", "source_id",
                "ingested_at", "evidence_refs", "choices", "selected", "as_of",
                "decision_cutoff", "event_time", "available_at", "decided_at", "decision_time",
                "generated_at", "expires_at", "model", "provider", "prompt_version", "policy_version",
                "profile_version", "feature_version", "dataset_manifest", "code_revision", "attempts",
                "status", "reason_code", "cache_hit", "latency_ms", "estimated_cost", "authority"}
    if not isinstance(envelope, dict) or envelope.keys() != expected:
        raise ValueError("invalid JEV cache envelope")
    try:
        timestamps = [datetime.fromisoformat(envelope[key]) for key in ("as_of", "available_at", "decided_at")]
        valid = (
            type(envelope["version"]) is int and envelope["version"] == schema_version
            and type(envelope["schema_version"]) is int and envelope["schema_version"] == schema_version
            and all(type(envelope[k]) is str and envelope[k] == fingerprint
                    for k in ("fingerprint", "decision_id", "request_fingerprint"))
            and type(envelope["domain"]) is str and envelope["domain"] == domain
            and envelope["gate_id"] == gate_id and (envelope["mode"] == mode or cached and mode in ("replay", "cache_only"))
            and type(envelope["model"]) is str and envelope["model"] == model
            and type(envelope["attempts"]) is int
            and 1 <= envelope["attempts"] <= 2
            and type(envelope["as_of"]) is str and type(envelope["available_at"]) is str
            and type(envelope["decided_at"]) is str
            and all(ts.tzinfo is not None and ts.utcoffset() is not None for ts in timestamps)
            and (envelope["as_of"] == _utc(as_of) and envelope["available_at"] == _utc(available_at)
                 if schema_version == JEV_SCHEMA_VERSION else
                 timestamps[0].date() == as_of.date() and timestamps[1].date() == available_at.date())
            and envelope["decision_cutoff"] == envelope["as_of"]
            and envelope["event_time"] == envelope["available_at"]
            and envelope["ingested_at"] == envelope["available_at"]
            and envelope["decision_time"] == envelope["decided_at"] == envelope["generated_at"]
            and envelope["expires_at"] is None
            and timestamps[0] <= as_of and timestamps[1] <= available_at
            and timestamps[1] <= timestamps[0]
            and timestamps[2] >= timestamps[1]
             and (timestamps[2] <= as_of if schema_version == JEV_SCHEMA_VERSION else
                  not cached or
                  timestamps[2] <= as_of or timestamps[2] == timestamps[1] or
                 timestamps[2] > as_of and as_of.date() < datetime.now(timezone.utc).date()
                 and timestamps[2] <= datetime.now(timezone.utc))
            and type(envelope["choices"]) is dict
            and envelope["choices"] == {k: list(v) for k, v in choices.items()}
            and isinstance(envelope["selected"], dict)
            and envelope["selected"].keys() == choices.keys()
            and all(type(envelope["selected"][k]) is str and envelope["selected"][k] in v for k, v in choices.items())
            and envelope["provider"] == "jev" and envelope["status"] == "accepted"
            and envelope["reason_code"] == "classified" and type(envelope["cache_hit"]) is bool
            and envelope["cache_hit"] is False and envelope["authority"] == "research_only"
            and type(envelope["entity_ids"]) is list and type(envelope["source_revisions"]) is list
            and envelope["evidence_refs"] == envelope["source_revisions"]
            and envelope["source_id"] == domain and type(envelope["source_hash"]) is str
            and len(envelope["source_hash"]) == 64
            and (facts_hash is None or envelope["source_hash"] == facts_hash)
            and type(envelope["latency_ms"]) is int and 0 <= envelope["latency_ms"] <= 120_000
            and type(envelope["estimated_cost"]) in (int, float)
            and math.isfinite(envelope["estimated_cost"]) and envelope["estimated_cost"] >= 0
            and all(type(envelope[k]) is str and envelope[k] and len(envelope[k]) <= 128
                    for k in ("prompt_version", "policy_version", "profile_version", "feature_version",
                              "dataset_manifest", "code_revision"))
            and (payload is None or all(envelope[k] == list(payload[k]) if k in ("entity_ids", "source_revisions")
                                        else envelope[k] == payload[k]
                                        for k in ("entity_ids", "source_revisions", "gate_id", "prompt_version",
                                                  "policy_version", "profile_version", "feature_version",
                                                  "dataset_manifest", "code_revision")))
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
