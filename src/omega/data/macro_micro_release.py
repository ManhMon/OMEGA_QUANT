"""V8 macro/micro release-domain contracts."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "macro_micro/v8"
GENESIS_POINTER_SHA256 = "76e8640526230d285d6a317461729fe2f6e5f09130950179bb0ca2b4ca0a4fdd"
MEMBERSHIP_FIELDS = frozenset({"release_id", "materialized_at"})


class MacroMicroContractError(ValueError):
    pass


class ProviderContractError(MacroMicroContractError):
    pass


class CompletenessError(MacroMicroContractError):
    pass


class EvidenceIntegrityError(MacroMicroContractError):
    pass


class FilesystemContainmentError(MacroMicroContractError):
    pass


class ReleaseQuorumError(MacroMicroContractError):
    pass


class PlanningAuthorityError(MacroMicroContractError):
    pass


class PublicationError(MacroMicroContractError):
    pass


class PointerLockError(MacroMicroContractError):
    pass


class MigrationError(MacroMicroContractError):
    pass


class RevisionConflictError(MacroMicroContractError):
    pass


class ReconciliationKnowledgeError(MacroMicroContractError):
    pass


class PointerCASConflict(MacroMicroContractError):
    pass


class PointerRecoveryDivergence(MacroMicroContractError):
    pass


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise MacroMicroContractError("nonfinite decimal")
    if value.is_zero():
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized = {unicodedata.normalize("NFC", str(key)): _canonical_value(item) for key, item in value.items()}
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MacroMicroContractError("nonfinite float")
        return _decimal_text(Decimal(str(value)))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise MacroMicroContractError("timestamp must be timezone-aware")
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode("ascii")}
    if value is None or isinstance(value, (bool, int)):
        return value
    raise MacroMicroContractError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json_v1(value: Any) -> bytes:
    """Compact, NFC-normalized UTF-8 JSON for immutable V8 identities."""
    return json.dumps(_canonical_value(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_json_v1(value)).hexdigest()


def canonical_consumer_json_v1(row: Mapping[str, Any]) -> bytes:
    missing = MEMBERSHIP_FIELDS - row.keys()
    if missing:
        raise MacroMicroContractError(f"missing membership fields: {sorted(missing)}")
    return canonical_json_v1({key: value for key, value in row.items() if key not in MEMBERSHIP_FIELDS})


RAW_RECEIPT_FIELDS = (
    "schema_version", "release_id", "materialized_at", "origin_release_id", "origin_ingested_at",
    "source_receipt_id", "attempt_id", "work_item_id", "acquisition_ordinal", "provider_id",
    "adapter_id", "adapter_version", "completeness_mode", "request_method", "request_url",
    "request_scope_json", "request_headers_json", "requested_at", "response_started_at", "received_at",
    "body_hashed_at", "response_status", "response_url", "redirect_chain_json", "response_headers_json",
    "content_type", "completeness_proof_json", "raw_body", "raw_body_size", "raw_body_sha256", "receipt_sha256",
)


def source_receipt_id_v1(receipt: Mapping[str, Any]) -> str:
    required = ("attempt_id", "work_item_id", "acquisition_ordinal", "provider_id", "adapter_id", "adapter_version", "request_method", "request_url", "request_scope_json")
    if any(key not in receipt for key in required):
        raise EvidenceIntegrityError("RECEIPT_ID_CONFLICT")
    payload = {"schema_version": "source_receipt_id/v1", **{key: receipt[key] for key in required}}
    return sha256_canonical(payload)


def receipt_sha256_v1(receipt: Mapping[str, Any]) -> str:
    unknown = set(receipt) - set(RAW_RECEIPT_FIELDS)
    if unknown or set(RAW_RECEIPT_FIELDS) - set(receipt):
        raise EvidenceIntegrityError("RawReceiptV1 schema mismatch")
    body = receipt["raw_body"]
    if not isinstance(body, bytes) or receipt["raw_body_size"] != len(body):
        raise EvidenceIntegrityError("raw body size mismatch")
    raw_hash = hashlib.sha256(body).hexdigest()
    if receipt["raw_body_sha256"] != raw_hash:
        raise EvidenceIntegrityError("raw body hash mismatch")
    metadata = {key: receipt[key] for key in RAW_RECEIPT_FIELDS if key not in {"release_id", "materialized_at", "raw_body", "receipt_sha256"}}
    encoded = canonical_json_v1(metadata)
    return hashlib.sha256(b"RawReceiptV1\0" + len(encoded).to_bytes(8, "big") + encoded + len(body).to_bytes(8, "big") + body).hexdigest()


@dataclass(frozen=True)
class RawReceiptV1:
    values: Mapping[str, Any]

    def validate(self) -> None:
        receipt = dict(self.values)
        if receipt.get("schema_version") != "macro_micro_raw_receipt/v1":
            raise EvidenceIntegrityError("RawReceiptV1 schema version")
        if receipt.get("source_receipt_id") != source_receipt_id_v1(receipt):
            raise EvidenceIntegrityError("RECEIPT_ID_CONFLICT")
        if receipt.get("receipt_sha256") != receipt_sha256_v1(receipt):
            raise EvidenceIntegrityError("receipt hash mismatch")


def open_contained_no_follow(root: str | Path, relative_path: str, mode: str = "rb"):
    if not isinstance(relative_path, str) or not relative_path or "\x00" in relative_path or "\\" in relative_path:
        raise FilesystemContainmentError("unsafe path")
    if relative_path.startswith(("/", "//")) or ":" in relative_path:
        raise FilesystemContainmentError("unsafe path")
    parts = relative_path.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if any(part in {"", ".", ".."} or part.endswith((".", " ")) or part.split(".")[0].upper() in reserved for part in parts):
        raise FilesystemContainmentError("unsafe path")
    root_path = Path(root)
    if root_path.is_symlink():
        raise FilesystemContainmentError("unsafe root")
    current = root_path
    for part in parts[:-1]:
        current /= part
        if current.is_symlink():
            raise FilesystemContainmentError("symlink path")
    target = current / parts[-1]
    if target.is_symlink():
        raise FilesystemContainmentError("symlink path")
    return target.open(mode)


def partition_vci_ratio_rows(rows: Sequence[Mapping[str, Any]], symbol: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(rows, list) or not rows:
        raise ProviderContractError("VCI_RATIO_PARTITION_VIOLATION: rows must be nonempty list")
    annual, quarterly = [], []
    required = {"year", "yearReport", "quarter", "ratioType", "organCode", "ratioTTMId"}
    for row in rows:
        if not isinstance(row, Mapping) or required - row.keys() or row["organCode"] != symbol:
            raise ProviderContractError("VCI_RATIO_PARTITION_VIOLATION")
        year = str(row["year"])
        if len(year) != 4 or not year.isdecimal() or row["yearReport"] != int(year):
            raise ProviderContractError("VCI_RATIO_PARTITION_VIOLATION")
        is_annual = row["ratioType"] == "RATIO_YEAR" and row["quarter"] == 5 and row.get("ratioYearId") is not None
        is_quarterly = row["ratioType"] == "RATIO_TTM" and row["quarter"] in {1, 2, 3, 4} and row.get("ratioYearId") is None
        if is_annual == is_quarterly:
            raise ProviderContractError("VCI_RATIO_PARTITION_VIOLATION")
        (annual if is_annual else quarterly).append(dict(row))
    annual.sort(key=lambda row: (int(row["year"]), row["ratioYearId"]))
    quarterly.sort(key=lambda row: (int(row["year"]), int(row["quarter"]), row["ratioTTMId"]))
    identities = [(row["year"], row["ratioType"], row["quarter"], row["ratioYearId"] if row["ratioType"] == "RATIO_YEAR" else row["ratioTTMId"]) for row in annual + quarterly]
    if len(identities) != len(set(identities)):
        raise ProviderContractError("VCI_RATIO_PARTITION_VIOLATION")
    return annual, quarterly


def classify_forecast_record(record: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Classify only explicit provider evidence; dates never imply forecasts."""
    markers = {str(item).lower() for item in evidence.get("forecast_markers", [])}
    marker = str(record.get("provider_marker", "")).lower()
    if marker in {"forecast", "estimate", "guidance", "consensus"} or markers & {"forecast", "estimate", "guidance", "consensus"}:
        return {"destination": "forecast", "reason": "SOURCE_MARKED_FORECAST"}
    if record.get("period_is_future") is True:
        return {"destination": "quarantine", "reason": "FUTURE_PERIOD_UNCONFIRMED"}
    return {"destination": "actual", "reason": None}


def accept_singleton_revision(accepted: Sequence[Mapping[str, Any]], candidate: Mapping[str, Any]) -> dict[str, Any]:
    if candidate.get("revision_order_kind") != "singleton_immutable_evidence" or candidate.get("source_revision_at") is not None or candidate.get("revision_seq") is not None:
        raise RevisionConflictError("singleton revision fields invalid")
    same = [row for row in accepted if row.get("revision_id") == candidate.get("revision_id")]
    if same and same[0].get("record_evidence_sha256") == candidate.get("record_evidence_sha256"):
        return {"status": "noop", "record": dict(same[0])}
    if accepted:
        return {"status": "quarantine", "reason": "REVISION_SINGLETON_CONFLICT", "record": dict(candidate)}
    return {"status": "accepted", "record": dict(candidate)}


def _as_utc(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise MacroMicroContractError("cutoff timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def select_provider_revision_as_of(rows: Sequence[Mapping[str, Any]], cutoff: Any) -> dict[str, Any] | None:
    cutoff_at = _as_utc(cutoff)
    eligible = [dict(row) for row in rows if row.get("record_type", "actual") == "actual" and _as_utc(row["available_at"]) <= cutoff_at and _as_utc(row["origin_ingested_at"]) <= cutoff_at]
    if not eligible:
        return None
    kinds = {row.get("revision_order_kind") for row in eligible}
    if len(kinds) != 1:
        raise RevisionConflictError("mixed revision order kinds")
    kind = kinds.pop()
    if kind == "singleton_immutable_evidence":
        if len({row["revision_id"] for row in eligible}) != 1:
            raise RevisionConflictError("REVISION_SINGLETON_CONFLICT")
        return eligible[0]
    field = "source_revision_at" if kind == "source_revision_at" else "revision_seq" if kind == "revision_seq" else None
    if field is None or any(row.get(field) is None for row in eligible):
        raise RevisionConflictError("REVISION_ORDER_MISSING")
    order = lambda row: _as_utc(row[field]) if field == "source_revision_at" else int(row[field])
    highest = max(order(row) for row in eligible)
    winners = [row for row in eligible if order(row) == highest]
    if len(winners) != 1:
        raise RevisionConflictError("REVISION_ORDER_COLLISION")
    return winners[0]


def select_reconciled_revision_as_of(native_rows: Sequence[Mapping[str, Any]], decisions: Sequence[Mapping[str, Any]], cutoff: Any) -> dict[str, Any] | None:
    cutoff_at = _as_utc(cutoff)
    native = {row["revision_id"]: row for row in native_rows if _as_utc(row["available_at"]) <= cutoff_at and _as_utc(row["origin_ingested_at"]) <= cutoff_at}
    for decision in decisions:
        times = [decision.get(key) for key in ("policy_effective_at", "policy_available_at", "policy_origin_ingested_at", "decision_created_at", "decision_recorded_at", "decision_origin_ingested_at")]
        times.extend(decision.get("candidate_available_at", []))
        times.extend(decision.get("candidate_origin_ingested_at", []))
        if decision.get("decision_status") != "selected" or any(value is None or _as_utc(value) > cutoff_at for value in times):
            continue
        revisions = decision.get("candidate_revision_ids", [])
        if set(revisions) != set(native) or decision.get("selected_revision_id") not in native:
            continue
        return dict(native[decision["selected_revision_id"]])
    return None


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def seal_manifest(candidate_dir: str | Path, *, release_id: str | None = None, release_sequence: int = 1) -> dict[str, Any]:
    directory = Path(candidate_dir)
    if (directory / "manifest.json").exists():
        raise MacroMicroContractError("sealed manifest already exists")
    files = sorted(path for path in directory.rglob("*") if path.is_file() and path.name != "manifest.json")
    artifacts = [{"path": path.relative_to(directory).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size} for path in files]
    if any(item["path"] == "manifest.json" for item in artifacts):
        raise MacroMicroContractError("manifest self-inventory")
    manifest = {"schema_version": "release_manifest/v1", "state": "sealed", "release_id": release_id or directory.name, "release_sequence": release_sequence, "artifacts": artifacts}
    _atomic_write(directory / "manifest.json", canonical_json_v1(manifest))
    return manifest


def _read_pointer(pointer_path: Path) -> tuple[bytes, dict[str, Any], str]:
    payload = pointer_path.read_bytes()
    try:
        pointer = json.loads(payload)
    except json.JSONDecodeError as error:
        raise MacroMicroContractError("malformed pointer") from error
    return payload, pointer, hashlib.sha256(payload).hexdigest()


def initialize_genesis_pointer(pointer_path: str | Path) -> dict[str, Any]:
    path = Path(pointer_path)
    payload = canonical_json_v1({"activated_at": None, "activation_attempt_id": None, "activation_kind": "genesis", "active_manifest_path": None, "active_manifest_sha256": None, "active_release_id": None, "active_release_sequence": 0, "legacy_fallback_allowed": True, "pointer_generation": 0, "pointer_schema_version": "macro_micro_pointer/v1", "previous_pointer_sha256": None, "rollback_floor_release_sequence": 0})
    if hashlib.sha256(payload).hexdigest() != GENESIS_POINTER_SHA256:
        raise AssertionError("genesis pointer contract drift")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise PointerCASConflict("pointer already exists")
    return json.loads(payload)


def activate_release_cas(expected_pointer_hash: str, sealed_manifest: Mapping[str, Any], pointer_path: str | Path, attempts_dir: str | Path, *, activation_attempt_id: str | None = None) -> dict[str, Any]:
    pointer_file, attempts = Path(pointer_path), Path(attempts_dir)
    prior_bytes, prior, prior_hash = _read_pointer(pointer_file)
    if prior_hash != expected_pointer_hash:
        raise PointerCASConflict("pointer hash changed")
    manifest_bytes = canonical_json_v1(sealed_manifest)
    target = {"pointer_schema_version": "macro_micro_pointer/v1", "pointer_generation": prior["pointer_generation"] + 1, "active_release_id": sealed_manifest["release_id"], "active_release_sequence": sealed_manifest["release_sequence"], "active_manifest_path": "manifest.json", "active_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(), "rollback_floor_release_sequence": prior["rollback_floor_release_sequence"], "previous_pointer_sha256": prior_hash, "activation_kind": "activate", "activation_attempt_id": activation_attempt_id or str(uuid.uuid4()), "activated_at": None, "legacy_fallback_allowed": prior["legacy_fallback_allowed"]}
    target_bytes, target_hash = canonical_json_v1(target), sha256_canonical(target)
    attempt = attempts / target["activation_attempt_id"]
    prepared = {"schema_version": "activation_prepared/v1", "activation_attempt_id": target["activation_attempt_id"], "prior_pointer_bytes_base64": base64.b64encode(prior_bytes).decode("ascii"), "prior_pointer_sha256": prior_hash, "target_pointer_bytes_base64": base64.b64encode(target_bytes).decode("ascii"), "target_pointer_sha256": target_hash}
    prepared["prepared_record_sha256"] = sha256_canonical(prepared)
    _atomic_write(attempt / "activation_prepared.json", canonical_json_v1(prepared))
    _atomic_write(pointer_file, target_bytes)
    observed_bytes, _, observed_hash = _read_pointer(pointer_file)
    if observed_bytes != target_bytes or observed_hash != target_hash:
        raise PointerRecoveryDivergence("pointer replacement diverged")
    _atomic_write(attempt / "activation_committed.json", canonical_json_v1({"schema_version": "activation_committed/v1", "activation_attempt_id": target["activation_attempt_id"], "prepared_record_sha256": prepared["prepared_record_sha256"], "target_pointer_sha256": target_hash, "observed_pointer_sha256": observed_hash, "recovered": False}))
    return target


def recover_prepared_activation(pointer_path: str | Path, attempts_dir: str | Path) -> list[str]:
    pointer_file = Path(pointer_path)
    recovered = []
    for prepared_file in sorted(Path(attempts_dir).glob("*/activation_prepared.json")):
        attempt = prepared_file.parent
        if (attempt / "activation_committed.json").exists() or (attempt / "activation_aborted.json").exists():
            continue
        prepared = json.loads(prepared_file.read_bytes())
        observed, _, observed_hash = _read_pointer(pointer_file)
        target = base64.b64decode(prepared["target_pointer_bytes_base64"])
        prior = base64.b64decode(prepared["prior_pointer_bytes_base64"])
        if observed == target and observed_hash == prepared["target_pointer_sha256"]:
            name, result = "activation_committed.json", {"schema_version": "activation_committed/v1", "activation_attempt_id": prepared["activation_attempt_id"], "prepared_record_sha256": prepared["prepared_record_sha256"], "target_pointer_sha256": observed_hash, "observed_pointer_sha256": observed_hash, "recovered": True}
        elif observed == prior and observed_hash == prepared["prior_pointer_sha256"]:
            name, result = "activation_aborted.json", {"schema_version": "activation_aborted/v1", "activation_attempt_id": prepared["activation_attempt_id"], "prepared_record_sha256": prepared["prepared_record_sha256"], "recovered": True}
        else:
            raise PointerRecoveryDivergence("POINTER_RECOVERY_DIVERGENCE")
        _atomic_write(attempt / name, canonical_json_v1(result))
        recovered.append(prepared["activation_attempt_id"])
    return recovered
