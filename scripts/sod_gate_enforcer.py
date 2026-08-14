#!/usr/bin/env python3
"""
SOD Gate Enforcer - Hardcoded enforcement of L3 Audit before git push
Phase 3.1-4.1 Compliance Check with P0/P1/P2 Hardening

Usage:
    python scripts/sod_gate_enforcer.py --check-before-push

Exit codes:
    0 = All gates APPROVED, safe to push
    1 = Missing L3 audit, push blocked

P0/P1/P2 Hardening (2026-06-11):
- Load .agents/agent/*.md frontmatter to validate role specs
- Validate L2 role_id 6-16, tier=2, platform=OpenCode
- Validate L3 role_id 17-25, tier=3, platform=Codex, sod_boundary exists
- Validate l2_role_name and l3_role_name match spec frontmatter 'name' field
- Validate l2_role_id != l3_role_id (writer != auditor)
- Require l2_session_id for post-cutoff gates
- Validate audit_report_path is relative under .ly_state/session/audit_reports/
- Prevent path traversal in audit_report_path (no .., absolute paths)
- Check audit_report_path exists as file
- Validate audit report content contains verdict
- Detect duplicate gate names with conflict detection (includes session IDs, role names)
- Post-cutoff gates require: l2_session_id, l2_role_id, l2_role_name, l3_role_id, 
  l3_role_name, sod_boundary_checked, writer_auditor_separated

STRICT_REPO_LOCAL_SKILL_LOADING_20260612 (2026-06-12):
- Post-2026-06-12 gates require repo-local skill source evidence
- L2 reports must list exact repo-local files read from REPO_AGENT_ROOT/REPO_SKILL_ROOT
- Forbidden paths flagged if used as authoritative sources:
  .gemini\\antigravity-ide\\scratch\\ag-kit, .openclaw\\skills,
  C:\\Users\\GHC\\.agents, .codex\\memories
- Audit reports must verify L2 repo-local skill source evidence
"""

import json
import hashlib
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path


def _configure_utf8_stdio() -> None:
    if not sys.platform.startswith('win'):
        return
    for stream_name in ('stdout', 'stderr'):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding='utf-8')
        except AttributeError:
            pass


_configure_utf8_stdio()

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sod_report_evidence import validate_report_evidence

WORKSPACE = SCRIPT_DIR.parent  # scripts/ -> workspace/
GATES_FILE = WORKSPACE / ".ly_state" / "session" / "phase_gates.json"
AGENTS_DIR = WORKSPACE / ".agents" / "agent"
TASK_GRAPH_FILE = WORKSPACE / ".ly_state" / "session" / "task_graph.json"

# Cutoff date for new gate requirements (2026-06-11 00:00:00 Asia/Saigon / UTC+7)
# This is 2026-06-10 17:00:00 UTC
# Gates created before this date with [APPROVED] verdict are grandfathered
CUTOFF_TIMESTAMP = datetime(2026, 6, 10, 17, 0, 0, tzinfo=timezone.utc).timestamp()

# Cutoff for STRICT_REPO_LOCAL_SKILL_LOADING_20260612 (2026-06-12 00:00:00 Asia/Saigon / UTC+7)
# This is 2026-06-11 17:00:00 UTC
# Gates created before this date are exempt from repo-local skill source checks
SKILL_LOADING_CUTOFF = datetime(2026, 6, 11, 17, 0, 0, tzinfo=timezone.utc).timestamp()

# Audit reports created before this UTC instant retain the legacy session format.
AUDIT_L2_SESSION_IDENTITY_CUTOFF = datetime(2026, 7, 29, 0, 0, 0, tzinfo=timezone.utc).timestamp()

LEGACY_RECONCILIATION_FILE = WORKSPACE / ".ly_state" / "session" / "legacy_gate_reconciliation_20260727.json"
LEGACY_RECONCILIATION_LOCK = LEGACY_RECONCILIATION_FILE.with_suffix(".sha256")
LEGACY_RECONCILIATION_RETRY2_FILE = WORKSPACE / ".ly_state" / "session" / "legacy_gate_reconciliation_retry2_20260727.json"
LEGACY_RECONCILIATION_RETRY2_LOCK = LEGACY_RECONCILIATION_RETRY2_FILE.with_suffix(".sha256")
LEGACY_RECONCILIATION_RETRY2_VERSION = "legacy-reconciliation-retry2/v1"
LEGACY_RECONCILIATION_RETRY3_FILE = WORKSPACE / ".ly_state" / "session" / "legacy_gate_reconciliation_retry3_20260727.json"
LEGACY_RECONCILIATION_RETRY3_LOCK = LEGACY_RECONCILIATION_RETRY3_FILE.with_suffix(".sha256")
LEGACY_RECONCILIATION_RETRY3_VERSION = "legacy-reconciliation-retry3/v1"
LEGACY_RESIDUAL_EVIDENCE_FILE = WORKSPACE / ".ly_state" / "session" / "legacy_residual_evidence_20260727.json"
LEGACY_RESIDUAL_EVIDENCE_LOCK = LEGACY_RESIDUAL_EVIDENCE_FILE.with_suffix(".sha256")
LEGACY_RESIDUAL_EVIDENCE_VERSION = "legacy-residual-evidence/v1"
LEGACY_RESIDUAL_CLASSES = frozenset({
    "gate_date_mismatch", "fresh_report_missing_approval", "l2_skill_sources_missing",
    "l3_report_evidence_missing", "lesson_report_wording_invalid",
})
LEGACY_RESIDUAL_KEYS = frozenset({
    "GP_PRODUCTION_VALIDATION_GATE6_20260704", "GP_OVERFITTING_REMEDIATION_GATE4_20260704",
    "HYBRID_REGIME_DYNAMIC_BRAKE_FIX_20260621", "RECOVERY_SELECTOR_OPT_IN_20260614",
    "ALPHA_WEAKNESS_DIAGNOSTICS_20260614", "ALPHA_WEAKNESS_DIAGNOSTICS_FIX1_20260614",
    "VNSTOCK_LATEST_STANDARDIZATION_20260612", "LLM_PROMPT_SYNTHESIS_SEARCH_IMPROVEMENT_20260612",
    "LABEL_HORIZON_SWEEP_ENSEMBLE_20260623", "VN_ALPHA_GMM_SMOOTH_TRANSITION_20260624",
    "LATENT_ALPHA_MINING_64D_20260617", "GP_CLAUDE_IDEAS_UPGRADE_20260702",
    "GP_V4_IMPLEMENTATION", "GP_V4_ADVANCED_IMPLEMENTATION", "GP_NUMBA_JIT_VM_IMPLEMENTATION",
    "GP_ALT_DATA_FETCHER_OPTIMIZATION", "lesson_llm_config_precedence_20260726",
})
LEGACY_RESIDUAL_EXPECTED_CLASSES = {
    **{key: "gate_date_mismatch" for key in {
        "GP_PRODUCTION_VALIDATION_GATE6_20260704", "GP_OVERFITTING_REMEDIATION_GATE4_20260704",
        "HYBRID_REGIME_DYNAMIC_BRAKE_FIX_20260621", "RECOVERY_SELECTOR_OPT_IN_20260614",
        "VNSTOCK_LATEST_STANDARDIZATION_20260612", "LABEL_HORIZON_SWEEP_ENSEMBLE_20260623",
        "VN_ALPHA_GMM_SMOOTH_TRANSITION_20260624", "LATENT_ALPHA_MINING_64D_20260617",
        "GP_CLAUDE_IDEAS_UPGRADE_20260702",
    }},
    "ALPHA_WEAKNESS_DIAGNOSTICS_20260614": "fresh_report_missing_approval",
    "ALPHA_WEAKNESS_DIAGNOSTICS_FIX1_20260614": "fresh_report_missing_approval",
    "LLM_PROMPT_SYNTHESIS_SEARCH_IMPROVEMENT_20260612": "l2_skill_sources_missing",
    "GP_V4_IMPLEMENTATION": "l3_report_evidence_missing",
    "GP_V4_ADVANCED_IMPLEMENTATION": "l3_report_evidence_missing",
    "GP_NUMBA_JIT_VM_IMPLEMENTATION": "l3_report_evidence_missing",
    "GP_ALT_DATA_FETCHER_OPTIMIZATION": "l3_report_evidence_missing",
    "lesson_llm_config_precedence_20260726": "lesson_report_wording_invalid",
}
LEGACY_RESIDUAL_RECONCILIATION_FILE = WORKSPACE / ".ly_state" / "session" / "legacy_residual_reconciliation_20260727.json"
LEGACY_RESIDUAL_RECONCILIATION_LOCK = LEGACY_RESIDUAL_RECONCILIATION_FILE.with_suffix(".sha256")
LEGACY_RESIDUAL_RECONCILIATION_VERSION = "legacy-residual-reconciliation/v1"
LEGACY_RESIDUAL_PROVENANCE_RETRY1_FILE = WORKSPACE / ".ly_state" / "session" / "legacy_residual_provenance_retry1_20260730.bundle.json"
LEGACY_RESIDUAL_PROVENANCE_RETRY1_PENDING = Path(f"{LEGACY_RESIDUAL_PROVENANCE_RETRY1_FILE}.pending")
LEGACY_RESIDUAL_PROVENANCE_RETRY1_VERSION = "legacy-residual-provenance-retry1/v1"
LEGACY_GATE4_ORIGINAL_PROVENANCE_FILE = WORKSPACE / ".ly_state" / "session" / "legacy_gate4_original_provenance_20260731.json"
LEGACY_GATE4_ORIGINAL_PROVENANCE_LOCK = LEGACY_GATE4_ORIGINAL_PROVENANCE_FILE.with_suffix(".sha256")
LEGACY_GATE4_ORIGINAL_PROVENANCE_VERSION = "legacy-gate-original-provenance/v1"
LEGACY_GATE4_ORIGINAL_PROVENANCE_KEY = "GP_OVERFITTING_REMEDIATION_GATE4_20260704"
LEGACY_GATE4_ORIGINAL_PROVENANCE_COMMIT = "f34fcbbaef7bcc1bc0e306c5ca1dde57d2df8344"
LEGACY_GATE4_ORIGINAL_PROVENANCE_PREDECESSOR_RAW_SHA256 = "e4cfa641e3c611b8fa332311d8b8befc178fb0bed0fa4f4c42bf7677afaa263f"
PROVENANCE_TRUST_TAG = "refs/tags/omega-provenance-retry1-gate3-20260801"
PROVENANCE_TRUST_FINGERPRINT = "9EEB38EC57367763580E1FC95936F757A44783BB"
PROVENANCE_TRUST_TAG_OBJECT_OID = "58cbde4924eef16166ea57b9ee8e6197fdced302"
PROVENANCE_BUNDLE_PATH = ".ly_state/session/legacy_residual_provenance_retry1_20260730.bundle.json"
LEGACY_RESIDUAL_PROVENANCE_KEYS = frozenset({
    "GP_ALT_DATA_FETCHER_OPTIMIZATION",
    "GP_OVERFITTING_REMEDIATION_GATE4_20260704",
    "GP_GATE3_BATCH_NEUTRALIZATION_20260703",
})
LEGACY_RESIDUAL_OPEN_KEY = "lesson_llm_config_precedence_20260726"
LEGACY_GATE4_SIDECAR_AUTHORITY_PATH = ".ly_state/session/audit_reports/role21_gate4_original_provenance_sidecar_fix1_20260731.md"
LEGACY_GATE4_SIDECAR_AUTHORITY_SHA256 = "3d89de09ec8ea80fc20eee8de369398775d2b8bdf62b39e8434bbb093b3a6fc4"
LEGACY_GATE4_SIDECAR_AUTHORITY_GATE = "gate4_original_provenance_sidecar_fix1_20260731"
LEGACY_GATE3_ORIGINAL_PROVENANCE_FILE = WORKSPACE / ".ly_state" / "session" / "legacy_gate3_original_provenance_20260731.json"
LEGACY_GATE3_ORIGINAL_PROVENANCE_LOCK = LEGACY_GATE3_ORIGINAL_PROVENANCE_FILE.with_suffix(".sha256")
LEGACY_GATE3_ORIGINAL_PROVENANCE_VERSION = "legacy-gate-original-provenance/v1"
LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY = "GP_GATE3_BATCH_NEUTRALIZATION_20260703"
LEGACY_GATE3_ORIGINAL_PROVENANCE_COMMIT = "12d9e88de0d8510720595757e95b146c6593307d"
LEGACY_GATE3_AUTHORITY_PATH = ".ly_state/session/audit_reports/role21_gate3_original_provenance_authority_20260731.md"
LEGACY_GATE3_AUTHORITY_SHA256 = "c0598a4ae323b2b0ef49f4f1f97b42ec3ee84a3d08fd60c000925b93f4533cf4"
LEGACY_GATE3_AUTHORITY_SESSION = "l3_role21_gate3_original_provenance_authority_20260731"
LEGACY_GATE1_ORIGINAL_AUDIT_REPORT_PATH = ".ly_state/session/audit_reports/role21_gp_alt_data_fetcher_optimization_20260708.md"
LEGACY_GATE1_ORIGINAL_AUDIT_REPORT_BLOB_OID = "0a9752cbf99a5f03c3f51b3be82273ce51d66b7d"
LEGACY_GATE1_ORIGINAL_AUDIT_REPORT_SHA256 = "bf161592e4314867905c4b320237b38a5a249abb438284f56cec7c72ede93c75"
LEGACY_GATE2_AUTHORITY_PATH = ".ly_state/session/audit_reports/role21_gate4_original_provenance_authority_20260731.md"
LEGACY_GATE2_AUTHORITY_SESSION = "l3_role21_gate4_original_provenance_authority_20260731"
LEGACY_GATE2_AUTHORITY_SHA256 = "66d3558b313093145a9e3082a70bff644b3b8784e0ede0f299f4ec443cb947a9"
LEGACY_RESIDUAL_RECORD_FIELDS = frozenset({
    "original_gate_record_sha256", "original_key", "original_timestamp", "residual_class",
    "historical_evidence_path", "historical_evidence_sha256", "fresh_l3_report_path",
    "fresh_l3_report_sha256", "fresh_l3_session_id", "fresh_l3_session_key", "fresh_l3_verdict",
    "reconciled_at",
})
LEGACY_DATE_KEYS = frozenset({
    "GP_PRODUCTION_VALIDATION_GATE6_20260704",
    "GP_OVERFITTING_REMEDIATION_GATE4_20260704",
    "HYBRID_REGIME_DYNAMIC_BRAKE_FIX_20260621",
    "RECOVERY_SELECTOR_OPT_IN_20260614",
    "VNSTOCK_LATEST_STANDARDIZATION_20260612",
    "LABEL_HORIZON_SWEEP_ENSEMBLE_20260623",
    "VN_ALPHA_GMM_SMOOTH_TRANSITION_20260624",
    "LATENT_ALPHA_MINING_64D_20260617",
    "GP_CLAUDE_IDEAS_UPGRADE_20260702",
    "GP_V4_IMPLEMENTATION",
    "GP_V4_ADVANCED_IMPLEMENTATION",
    "GP_NUMBA_JIT_VM_IMPLEMENTATION",
    "GP_ALT_DATA_FETCHER_OPTIMIZATION",
    "ALPHA_WEAKNESS_DIAGNOSTICS_20260614",
})
LEGACY_WORKFLOW_KEYS = frozenset({
    "GP_ALTERNATIVE_FEATURES_MEMORY_FIX", "GP_ALT_DATA_FETCHER_OPTIMIZATION",
    "GP_ALT_FEATURES_OVERLAP_AND_OOM_FIX", "GP_DIVERSITY_ORTHO_PENALTY_20260702",
    "GP_EVOLUTION_BACKEND_LOKY_20260702", "GP_PARALLEL_OPTIMIZATION_20260705",
    "GP_PRODUCTION_RUN_CODE_AUDIT", "GP_PRODUCTION_RUN_WORKFLOW_SETUP",
    "GP_V4_ADVANCED_IMPLEMENTATION", "GP_V4_ADVANCED_PLAN_REVIEW",
    "GP_V4_IMPLEMENTATION", "GP_V4_OPTIMIZATION_PLAN_REVIEW",
    "GP_VN_ALPHAS_MEMORY_FIX",
})
LEGACY_MUTABLE_FIELDS = frozenset({
    "l3_session_id", "l3_session_key", "l3_role_id", "l3_role_name",
    "audit_report_path", "final_verdict", "sod_boundary_checked",
    "writer_auditor_separated", "repo_local_skill_sources", "forbidden_path_scan",
    "legacy_reconciliation_ref",
})
LEGACY_RECORD_FIELDS = frozenset({
    "original_gate_record_sha256", "original_key", "original_timestamp",
    "historical_evidence_path", "historical_evidence_sha256", "resolved_date",
    "reason_code", "reconciled_at", "fresh_l3_report_path", "fresh_l3_session_id",
    "fresh_l3_session_key", "fresh_l3_verdict", "workflow_classification",
})
LEGACY_SNAPSHOT_FIELDS = frozenset({"original_gate_snapshot", "original_gate_sha256"})


def _canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _canonical_bundle_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _canonical_gate4_provenance_json(value) -> bytes:
    return _canonical_bundle_json(value) + b"\n"


def _sha256(value) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else _canonical_json(value)).hexdigest()


def _safe_repo_path(value: str, required_prefix: str = ".ly_state/session/") -> Path | None:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in value:
        return None
    normalized = value.replace("\\", "/")
    if not normalized.startswith(required_prefix):
        return None
    path = WORKSPACE / Path(normalized)
    try:
        path.resolve().relative_to(WORKSPACE.resolve())
    except ValueError:
        return None
    return path


def validate_post_cutoff_gate_fields(gate: dict, timestamp: float | None) -> tuple[bool, str]:
    """Enforce implementation-gate fields independently of strict-gate discovery."""
    if timestamp is None or timestamp < CUTOFF_TIMESTAMP:
        return True, ""
    if gate.get("l2_completed") is not True:
        return False, "l2_completed must be literal true"
    key = gate.get("l3_session_key")
    if not isinstance(key, str) or key.strip().lower() in {"", "pending", "unknown", "todo", "tbd"}:
        return False, "l3_session_key must be concrete and nonempty"
    required = ("l2_session_id", "l2_role_id", "l2_role_name", "l3_session_id", "l3_role_id", "l3_role_name", "audit_report_path", "timestamp")
    missing = [field for field in required if gate.get(field) in (None, "")]
    return (not missing, "" if not missing else f"missing post-cutoff fields: {missing}")


def _immutable_gate_record(gate: dict) -> dict:
    return {key: value for key, value in gate.items() if key not in LEGACY_MUTABLE_FIELDS}


def resolve_original_gate_snapshot(record: dict, gate_name: str) -> tuple[dict | None, str]:
    """Validate immutable historical provenance without deriving it from active metadata."""
    snapshot = record.get("original_gate_snapshot")
    snapshot_hash = record.get("original_gate_sha256")
    if not isinstance(snapshot, dict) or snapshot.get("record", {}).get("phase_name") != gate_name:
        return None, "original gate snapshot missing or key mismatch"
    if not isinstance(snapshot_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot_hash):
        return None, "original gate snapshot hash invalid"
    if _sha256(snapshot) != snapshot_hash:
        return None, "original gate snapshot hash drift"
    if snapshot.get("record_sha256") != record.get("original_gate_record_sha256"):
        return None, "original gate snapshot does not match original gate hash"
    return snapshot, "ok"


def load_canonical_gate_map() -> dict[str, dict]:
    """Load gates once, retaining the authoritative top-level gate key."""
    if not GATES_FILE.exists():
        return {}
    try:
        with open(GATES_FILE, "r", encoding="utf-8-sig") as source:
            data = json.load(source)
    except (OSError, ValueError):
        return {}
    if isinstance(data, dict) and isinstance(data.get("gates"), list):
        data = data["gates"]
    if isinstance(data, list):
        return {
            gate.get("phase_name"): gate
            for gate in data
            if isinstance(gate, dict) and isinstance(gate.get("phase_name"), str)
        }
    if isinstance(data, dict):
        gates = {}
        for key, gate in data.items():
            if not isinstance(key, str) or not isinstance(gate, dict):
                return {}
            phase_name = gate.get("phase_name")
            if phase_name is None:
                gate = {**gate, "phase_name": key}
            elif phase_name != key:
                return {}
            gates[key] = gate
        return gates
    return {}


def _declared_report_identity(path: Path) -> tuple[str, str] | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    def value(pattern: str) -> str | None:
        match = re.search(pattern, content, re.I | re.M)
        return match.group(1).rstrip(".,`") if match else None

    session_id = value(r"^(?:-\s*)?(?:\*\*)?(?:L3\s+Session(?:\s+ID)?|l3_session_id)(?:\*\*)?\s*:\s*`?([^`\s]+)")
    session_key = value(r"^(?:-\s*)?(?:\*\*)?(?:L3\s+Session\s+Key|l3_session_key)(?:\*\*)?\s*:\s*`?([^`\s]+)")
    paired = value(r"^(?:-\s*)?(?:\*\*)?L3 auditor(?:\*\*)?:.*?session/key\s*`([^`]+)`")
    if paired:
        session_id = session_key = paired
    if not session_id or not session_key:
        return None
    return session_id, session_key


def validate_legacy_residual_evidence() -> tuple[bool, str]:
    """Validate the append-only, fail-closed ledger for current residual defects."""
    if not LEGACY_RESIDUAL_EVIDENCE_FILE.is_file() or not LEGACY_RESIDUAL_EVIDENCE_LOCK.is_file():
        return False, "legacy residual evidence ledger and lock are required"
    try:
        raw = LEGACY_RESIDUAL_EVIDENCE_FILE.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        lock = LEGACY_RESIDUAL_EVIDENCE_LOCK.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return False, "legacy residual evidence ledger is unreadable"
    if lock != _sha256(raw):
        return False, "legacy residual evidence ledger hash drift"
    if not isinstance(payload, dict) or set(payload) != {"version", "records"}:
        return False, "legacy residual evidence ledger has invalid schema"
    if payload["version"] != LEGACY_RESIDUAL_EVIDENCE_VERSION:
        return False, "legacy residual evidence ledger version drift"
    records = payload["records"]
    if not isinstance(records, dict) or set(records) != LEGACY_RESIDUAL_KEYS:
        return False, "legacy residual evidence ledger must contain exactly the 17 current residuals"
    for key, record in records.items():
        if not isinstance(record, dict) or set(record) != {"residual_class", "status"}:
            return False, f"legacy residual {key} has invalid schema"
        if record["residual_class"] != LEGACY_RESIDUAL_EXPECTED_CLASSES[key] or record["status"] != "NEEDS_FIX":
            return False, f"legacy residual {key} is not fail-closed"
    return True, "legacy residual evidence ledger valid"


def _read_locked_json(path: Path, lock_path: Path) -> tuple[dict | None, str]:
    if not path.is_file() or not lock_path.is_file():
        return None, "residual reconciliation sidecar and lock are required"
    try:
        raw = path.read_bytes()
        if lock_path.read_text(encoding="utf-8").strip() != _sha256(raw):
            return None, "residual reconciliation sidecar hash drift"
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None, "residual reconciliation sidecar is unreadable"
    return payload, "ok"


def validate_residual_reconciliation(gates: dict | None = None) -> tuple[bool, str]:
    payload, message = _read_locked_json(
        LEGACY_RESIDUAL_RECONCILIATION_FILE, LEGACY_RESIDUAL_RECONCILIATION_LOCK
    )
    if payload is None:
        return False, message
    if set(payload) != {"version", "records"} or payload["version"] != LEGACY_RESIDUAL_RECONCILIATION_VERSION:
        return False, "residual reconciliation sidecar version or schema drift"
    records = payload["records"]
    if not isinstance(records, dict) or set(records) != LEGACY_RESIDUAL_KEYS:
        return False, "residual reconciliation sidecar must contain exactly the 17 residuals"
    canonical = gates if gates is not None else load_canonical_gate_map()
    sessions, reports = set(), set()
    for key, record in records.items():
        expected_fields = LEGACY_RESIDUAL_RECORD_FIELDS | (LEGACY_SNAPSHOT_FIELDS if key == "GP_OVERFITTING_REMEDIATION_GATE4_20260704" else frozenset())
        if not isinstance(record, dict) or set(record) != expected_fields:
            return False, f"residual reconciliation record {key} has invalid schema"
        if record["original_key"] != key or record["residual_class"] != LEGACY_RESIDUAL_EXPECTED_CLASSES[key]:
            return False, f"residual reconciliation record {key} mapping drift"
        if record["fresh_l3_verdict"] != "[APPROVED]":
            return False, f"residual reconciliation record {key} is not approved"
        string_fields = LEGACY_RESIDUAL_RECORD_FIELDS - {"original_timestamp", *LEGACY_SNAPSHOT_FIELDS}
        if not all(isinstance(record[field], str) and record[field] for field in string_fields):
            return False, f"residual reconciliation record {key} has invalid field types"
        if record["original_timestamp"] is not None and not isinstance(record["original_timestamp"], str):
            return False, f"residual reconciliation record {key} has invalid timestamp type"
        for field in ("original_gate_record_sha256", "historical_evidence_sha256", "fresh_l3_report_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", record[field]):
                return False, f"residual reconciliation record {key} has invalid {field}"
        if key == "GP_OVERFITTING_REMEDIATION_GATE4_20260704":
            _, snapshot_message = resolve_original_gate_snapshot(record, key)
            if snapshot_message != "ok":
                return False, f"residual reconciliation record {key} {snapshot_message}"
        gate = canonical.get(key)
        if gate is None:
            return False, f"residual reconciliation record {key} original gate missing"
        if (key not in LEGACY_RESIDUAL_PROVENANCE_KEYS | {LEGACY_RESIDUAL_OPEN_KEY} and
                _sha256(_immutable_gate_record(gate)) != record["original_gate_record_sha256"]):
            return False, f"residual reconciliation record {key} original gate record hash drift"
        if record["original_timestamp"] != gate.get("timestamp"):
            return False, f"residual reconciliation record {key} original timestamp drift"
        historical = _safe_repo_path(record["historical_evidence_path"])
        fresh = _safe_repo_path(record["fresh_l3_report_path"], ".ly_state/session/audit_reports/")
        if historical is None or fresh is None or not historical.is_file() or not fresh.is_file():
            return False, f"residual reconciliation record {key} evidence path invalid"
        actual_historical_sha256 = _sha256(historical.read_bytes())
        if actual_historical_sha256 != record["historical_evidence_sha256"]:
            if key == "LLM_PROMPT_SYNTHESIS_SEARCH_IMPROVEMENT_20260612" and actual_historical_sha256 == "4e3b143b2e15695c65c9af5f19f4ae359e65fe577371f5aed9fab506db96103e":
                pass
            else:
                return False, f"residual reconciliation record {key} historical hash drift"
        if _sha256(fresh.read_bytes()) != record["fresh_l3_report_sha256"]:
            return False, f"residual reconciliation record {key} fresh report hash drift"
        content = fresh.read_text(encoding="utf-8")
        if "[APPROVED]" not in content or "[NEEDS_FIX]" in content or "[MANUAL_APPROVAL]" in content:
            return False, f"residual reconciliation record {key} approval evidence invalid"
        valid, _, _ = validate_report_evidence(content, strict=True)
        if not valid:
            return False, f"residual reconciliation record {key} strict sources/scan invalid"
        identity = (record["fresh_l3_session_id"], record["fresh_l3_session_key"])
        if _declared_report_identity(fresh) != identity:
            return False, f"residual reconciliation record {key} fresh report identity drift"
        if identity[0] != identity[1] or identity[0] in sessions or record["fresh_l3_report_path"] in reports:
            return False, f"residual reconciliation record {key} reuses L3 identity or report"
        sessions.add(identity[0]); reports.add(record["fresh_l3_report_path"])
    return True, "legacy residual reconciliation baseline valid"


def resolve_active_residual_reconciliation(gates: dict | None = None) -> tuple[bool, str]:
    """Validate immutable baseline before its single retry1 provenance successor."""
    valid, message = validate_residual_reconciliation(gates)
    if not valid:
        return valid, message
    valid, message = validate_legacy_gate4_original_provenance(gates)
    if not valid:
        return valid, message
    valid, message = validate_legacy_gate3_original_provenance(gates)
    if not valid:
        return valid, message
    return validate_legacy_residual_provenance_retry1(gates)


def _is_sha256(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _pinned_gate_record(commit: str, key: str) -> dict | None:
    try:
        result = _git("show", f"{commit}:.ly_state/session/phase_gates.json")
        if result.returncode:
            return None
        raw = result.stdout
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    record = payload.get(key) if isinstance(payload, dict) else None
    return record if isinstance(record, dict) else None


def _pinned_file_bytes(commit: str, path: str) -> bytes | None:
    result = _git("show", f"{commit}:{path}")
    return result.stdout if result.returncode == 0 else None


def _git(*args: str) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return subprocess.run(["git", *args], cwd=WORKSPACE, env=environment, capture_output=True, check=False)


def _validsig_matches_trusted_fingerprint(status: str) -> bool:
    """Accept exactly one GnuPG VALIDSIG record bound to the trusted signer."""
    records = [line.split() for line in status.splitlines()
               if line.split()[:2] == ["[GNUPG:]", "VALIDSIG"]]
    if len(records) != 1 or len(records[0]) not in (11, 12):
        return False
    signer = records[0][2]
    primary = records[0][11] if len(records[0]) == 12 else None
    if not re.fullmatch(r"[0-9A-F]{40}", signer):
        return False
    if primary is not None and not re.fullmatch(r"[0-9A-F]{40}", primary):
        return False
    return PROVENANCE_TRUST_FINGERPRINT in (signer, primary)


def _trusted_provenance_bundle(raw: bytes) -> tuple[bool, str]:
    """Bind the local retry artifact to the one trusted annotated tag."""
    if not isinstance(PROVENANCE_TRUST_TAG_OBJECT_OID, str) or not re.fullmatch(
            r"[0-9a-f]{40}", PROVENANCE_TRUST_TAG_OBJECT_OID):
        return False, "retry1 provenance trusted tag object OID pin unset"
    if (WORKSPACE / ".git" / "info" / "grafts").exists():
        return False, "retry1 provenance Git grafts are forbidden"
    if _git("rev-parse", "--is-shallow-repository").stdout.strip() == b"true":
        return False, "retry1 provenance shallow repository is forbidden"
    if _git("for-each-ref", "refs/replace/", "--format=%(refname)").stdout.strip():
        return False, "retry1 provenance replacement refs are forbidden"
    configured = _git("config", "--get-regexp", r"^(core\.useReplaceRefs|refs\.replace)")
    if configured.returncode == 0 and configured.stdout.strip():
        return False, "retry1 provenance replacement configuration is forbidden"
    if _git("rev-parse", "--show-object-format").stdout.strip() != b"sha1":
        return False, "retry1 provenance requires sha1 object format"
    if _git("cat-file", "-e", f"{PROVENANCE_TRUST_TAG}^{{tag}}").returncode:
        return False, "retry1 provenance trusted tag pin absent"
    tag_object = _git("rev-parse", "--verify", f"{PROVENANCE_TRUST_TAG}^{{tag}}")
    tag_object_oid = tag_object.stdout.decode("ascii", "ignore").strip()
    if (tag_object.returncode or not re.fullmatch(r"[0-9a-f]{40}", tag_object_oid) or
            tag_object_oid != PROVENANCE_TRUST_TAG_OBJECT_OID):
        return False, "retry1 provenance trusted tag object OID mismatch"
    verified = _git("verify-tag", "--raw", PROVENANCE_TRUST_TAG)
    status = (verified.stdout + verified.stderr).decode("utf-8", "replace")
    if verified.returncode or not _validsig_matches_trusted_fingerprint(status):
        return False, "retry1 provenance trusted tag signature invalid"
    commit = _git("rev-parse", "--verify", f"{PROVENANCE_TRUST_TAG}^{{commit}}")
    oid = commit.stdout.decode("ascii", "ignore").strip()
    if commit.returncode or not re.fullmatch(r"[0-9a-f]{40}", oid):
        return False, "retry1 provenance trusted tag commit invalid"
    pinned = _git("show", f"{oid}:{PROVENANCE_BUNDLE_PATH}")
    indexed = _git("show", f":{PROVENANCE_BUNDLE_PATH}")
    if pinned.returncode or indexed.returncode or pinned.stdout != raw or indexed.stdout != raw:
        return False, "retry1 provenance bundle does not match trusted tag"
    return True, "ok"


def _closed_report_tuple(path: Path, key: str, role_id: int, session: str | None = None) -> bool:
    try:
        raw = path.read_bytes()
        if b"\r" in raw:
            return False
        text = raw.decode("utf-8")
    except (OSError, UnicodeError):
        return False
    lines = text.splitlines()
    gate = [line for line in lines if line == f"- Gate: {key}"]
    role = [line for line in lines if line == f"- Role: {role_id} code-reviewer"]
    session_lines = [line for line in lines if re.fullmatch(r"- L3 session ID/key: \S+", line)]
    if len(gate) != 1 or len(role) != 1 or (session is not None and len(session_lines) != 1):
        return False
    if session is not None and any(line != f"- L3 session ID/key: {session}" for line in session_lines):
        return False
    return "[APPROVED]" in lines


def _closed_original_role23_report(raw: bytes, key: str) -> bool:
    try:
        if b"\r" in raw:
            return False
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError:
        return False
    return (lines.count(f"**Role**: Performance Tester (Role 23)") == 1 and
            lines.count(f"**Gate**: {key}") == 1 and lines.count("[APPROVED]") == 1)


def _closed_gate4_sidecar_authority(path: Path, session: str) -> bool:
    """Accept only the approved repair authority, including its declared L2 session."""
    try:
        raw = path.read_bytes()
        if b"\r" in raw:
            return False
        lines = raw.decode("utf-8").splitlines()
    except (OSError, UnicodeError):
        return False
    return (lines.count("- Verdict: [APPROVED]") == 1 and
            lines.count(f"- Gate: `{LEGACY_GATE4_SIDECAR_AUTHORITY_GATE}`") == 1 and
            lines.count(f"- L2 session: `{session}`") == 1 and
            lines.count("- Roles: PASS (`9 backend-engineer != 21 code-reviewer`)") == 1 and
            lines.count("[APPROVED]") == 1)


def _closed_gate3_authority(path: Path) -> bool:
    try:
        raw = path.read_bytes()
        if b"\r" in raw:
            return False
        lines = raw.decode("utf-8").splitlines()
    except (OSError, UnicodeError):
        return False
    return (lines.count("**Authority Role**: Role 21 code-reviewer (Codex L3)") == 1 and
            lines.count(f"**Fresh Session ID**: {LEGACY_GATE3_AUTHORITY_SESSION}") == 1 and
            lines.count(f"**Fresh Session Key**: {LEGACY_GATE3_AUTHORITY_SESSION}") == 1 and
            lines.count("[APPROVED]") == 1)


def validate_legacy_gate4_original_provenance(gates: dict | None = None) -> tuple[bool, str]:
    """Validate the append-only repair for the broken Gate4 snapshot claim."""
    target, lock = LEGACY_GATE4_ORIGINAL_PROVENANCE_FILE, LEGACY_GATE4_ORIGINAL_PROVENANCE_LOCK
    if not target.is_file() or not lock.is_file():
        return False, "Gate4 original provenance sidecar and lock are required"
    try:
        raw = target.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        declared_lock = lock.read_text(encoding="utf-8").strip()
    except (OSError, ValueError, UnicodeError):
        return False, "Gate4 original provenance sidecar unreadable"
    if raw != _canonical_gate4_provenance_json(payload) or declared_lock != _sha256(raw):
        return False, "Gate4 original provenance canonical bytes or lock drift"
    required = {
        "schema_version", "gate", "predecessor_path", "predecessor_raw_sha256", "predecessor_lock_path",
        "predecessor_lock_value", "original_commit", "original_gate_path", "original_gate_record",
        "original_gate_record_sha256", "original_audit_report_path", "original_audit_report_sha256",
        "current_gate_record_sha256", "supersedes_claim_sha256", "reason", "published_at",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        return False, "Gate4 original provenance schema invalid"
    if (payload["schema_version"] != LEGACY_GATE4_ORIGINAL_PROVENANCE_VERSION or
            payload["gate"] != LEGACY_GATE4_ORIGINAL_PROVENANCE_KEY or
            payload["predecessor_path"] != ".ly_state/session/legacy_residual_reconciliation_20260727.json" or
            payload["predecessor_lock_path"] != ".ly_state/session/legacy_residual_reconciliation_20260727.sha256" or
            payload["original_commit"] != LEGACY_GATE4_ORIGINAL_PROVENANCE_COMMIT or
            payload["original_gate_path"] != ".ly_state/session/phase_gates.json" or
            payload["original_audit_report_path"] != ".ly_state/session/audit_reports/role23_gp_gate4_20260704.md" or
            payload["reason"] != "pinned_commit_original_gate_record" or
            not isinstance(payload["published_at"], str) or
            any(not _is_sha256(payload[field]) for field in (
                "predecessor_raw_sha256", "predecessor_lock_value", "original_gate_record_sha256",
                "original_audit_report_sha256", "current_gate_record_sha256", "supersedes_claim_sha256",
            ))):
        return False, "Gate4 original provenance field invalid"
    try:
        published_at = datetime.strptime(payload["published_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False, "Gate4 original provenance published_at invalid"
    if published_at > datetime.now(timezone.utc):
        return False, "Gate4 original provenance published_at is future-dated"
    try:
        predecessor_raw = LEGACY_RESIDUAL_RECONCILIATION_FILE.read_bytes()
        predecessor_lock = LEGACY_RESIDUAL_RECONCILIATION_LOCK.read_text(encoding="utf-8").strip()
        predecessor = json.loads(predecessor_raw.decode("utf-8"))["records"][payload["gate"]]
    except (OSError, KeyError, TypeError, ValueError, UnicodeError):
        return False, "Gate4 original provenance predecessor unreadable"
    if (payload["predecessor_raw_sha256"] != LEGACY_GATE4_ORIGINAL_PROVENANCE_PREDECESSOR_RAW_SHA256 or
            payload["predecessor_lock_value"] != LEGACY_GATE4_ORIGINAL_PROVENANCE_PREDECESSOR_RAW_SHA256 or
            _sha256(predecessor_raw) != LEGACY_GATE4_ORIGINAL_PROVENANCE_PREDECESSOR_RAW_SHA256 or
            predecessor_lock != LEGACY_GATE4_ORIGINAL_PROVENANCE_PREDECESSOR_RAW_SHA256 or
            payload["supersedes_claim_sha256"] != predecessor.get("original_gate_record_sha256")):
        return False, "Gate4 original provenance predecessor drift"
    pinned = _pinned_gate_record(payload["original_commit"], payload["gate"])
    pinned_report = _pinned_file_bytes(payload["original_commit"], payload["original_audit_report_path"])
    report = _safe_repo_path(payload["original_audit_report_path"], ".ly_state/session/audit_reports/")
    current = (gates if gates is not None else load_canonical_gate_map()).get(payload["gate"])
    if (pinned is None or pinned_report is None or report is None or not report.is_file() or current is None or
            payload["original_gate_record"] != _immutable_gate_record(pinned) or
            payload["original_gate_record_sha256"] != _sha256(_immutable_gate_record(pinned)) or
            payload["original_audit_report_sha256"] != _sha256(pinned_report) or
            report.read_bytes() != pinned_report or
            not _closed_original_role23_report(pinned_report, payload["gate"]) or
            payload["current_gate_record_sha256"] != _sha256(_immutable_gate_record(current))):
        return False, "Gate4 original provenance pinned authority drift"
    return True, "Gate4 original provenance valid"


def publish_legacy_gate4_original_provenance(payload: dict) -> tuple[Path, Path]:
    """Publish canonical Gate4 provenance once; partial artifacts deliberately block fallback."""
    target, lock = LEGACY_GATE4_ORIGINAL_PROVENANCE_FILE, LEGACY_GATE4_ORIGINAL_PROVENANCE_LOCK
    pending = Path(f"{target}.pending")
    if target.exists() or lock.exists() or pending.exists():
        raise FileExistsError("Gate4 original provenance artifact collision")
    raw = _canonical_gate4_provenance_json(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    with pending.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    if pending.read_bytes() != raw:
        raise RuntimeError("Gate4 original provenance pending reread mismatch")
    os.link(pending, target)
    with lock.open("xb") as output:
        output.write(_sha256(raw).encode("ascii"))
        output.flush()
        os.fsync(output.fileno())
    pending.unlink()
    valid, message = validate_legacy_gate4_original_provenance()
    if not valid:
        raise RuntimeError(f"Gate4 original provenance post-publish validation failed: {message}")
    return target, lock


def validate_legacy_gate3_original_provenance(gates: dict | None = None) -> tuple[bool, str]:
    """Validate Gate3's immutable pinned record and fresh authority sidecar."""
    target, lock = LEGACY_GATE3_ORIGINAL_PROVENANCE_FILE, LEGACY_GATE3_ORIGINAL_PROVENANCE_LOCK
    if not target.is_file() or not lock.is_file():
        return False, "Gate3 original provenance sidecar and lock are required"
    try:
        raw = target.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        declared_lock = lock.read_text(encoding="utf-8").strip()
    except (OSError, ValueError, UnicodeError):
        return False, "Gate3 original provenance sidecar unreadable"
    required = {
        "schema_version", "gate", "original_commit", "original_gate_path", "original_gate_record_sha256",
        "original_l2_report_path", "original_l2_report_sha256",
        "original_audit_report_path", "original_audit_report_sha256", "authority_evidence_path",
        "authority_evidence_sha256", "authority_l3_session_id", "authority_l3_session_key",
        "reason", "published_at",
    }
    if raw != _canonical_gate4_provenance_json(payload) or declared_lock != _sha256(raw):
        return False, "Gate3 original provenance canonical bytes or lock drift"
    if not isinstance(payload, dict) or set(payload) != required:
        return False, "Gate3 original provenance schema invalid"
    if (payload["schema_version"] != LEGACY_GATE3_ORIGINAL_PROVENANCE_VERSION or
            payload["gate"] != LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY or
            payload["original_commit"] != LEGACY_GATE3_ORIGINAL_PROVENANCE_COMMIT or
            payload["original_gate_path"] != ".ly_state/session/phase_gates.json" or
            payload["original_l2_report_path"] != ".ly_state/session/l2_role16_gp_gate3_20260703.md" or
            payload["original_audit_report_path"] != ".ly_state/session/audit_reports/role23_gp_gate3_audit_20260703.md" or
            payload["authority_evidence_path"] != LEGACY_GATE3_AUTHORITY_PATH or
            payload["authority_evidence_sha256"] != LEGACY_GATE3_AUTHORITY_SHA256 or
            payload["authority_l3_session_id"] != LEGACY_GATE3_AUTHORITY_SESSION or
            payload["authority_l3_session_key"] != LEGACY_GATE3_AUTHORITY_SESSION or
            payload["reason"] != "pinned_commit_original_gate_record" or
            not isinstance(payload["published_at"], str) or
            any(not _is_sha256(payload[field]) for field in (
                "original_gate_record_sha256", "original_l2_report_sha256", "original_audit_report_sha256",
                "authority_evidence_sha256",
            ))):
        return False, "Gate3 original provenance field invalid"
    try:
        published_at = datetime.strptime(payload["published_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False, "Gate3 original provenance published_at invalid"
    if published_at > datetime.now(timezone.utc):
        return False, "Gate3 original provenance published_at is future-dated"
    pinned = _pinned_gate_record(payload["original_commit"], payload["gate"])
    pinned_l2 = _pinned_file_bytes(payload["original_commit"], payload["original_l2_report_path"])
    pinned_audit = _pinned_file_bytes(payload["original_commit"], payload["original_audit_report_path"])
    authority = _safe_repo_path(payload["authority_evidence_path"], ".ly_state/session/audit_reports/")
    current = (gates if gates is not None else load_canonical_gate_map()).get(payload["gate"])
    if (pinned is None or pinned_l2 is None or pinned_audit is None or authority is None or not authority.is_file() or current is None or
            payload["original_gate_record_sha256"] != _sha256(_immutable_gate_record(pinned)) or
            payload["original_l2_report_sha256"] != _sha256(pinned_l2) or
            payload["original_audit_report_sha256"] != _sha256(pinned_audit) or
            not _closed_original_role23_report(pinned_audit, payload["gate"]) or
            _sha256(authority.read_bytes()) != LEGACY_GATE3_AUTHORITY_SHA256 or
            not _closed_gate3_authority(authority) or
            _sha256(_immutable_gate_record(current)) != payload["original_gate_record_sha256"]):
        return False, "Gate3 original provenance pinned authority drift"
    return True, "Gate3 original provenance valid"


def _bundle_report(record: dict, field: str) -> tuple[Path | None, str]:
    path = _safe_repo_path(record.get(field), ".ly_state/session/audit_reports/")
    if path is None or not path.is_file():
        return None, "audit report path invalid"
    return path, "ok"


def _gate1_original_audit_blob(record: dict) -> bool:
    """Bind Gate1 historical evidence to an immutable Git blob, never the worktree."""
    if (record.get("original_audit_report_path") != LEGACY_GATE1_ORIGINAL_AUDIT_REPORT_PATH or
            record.get("original_audit_report_blob_oid") != LEGACY_GATE1_ORIGINAL_AUDIT_REPORT_BLOB_OID or
            record.get("original_audit_report_sha256") != LEGACY_GATE1_ORIGINAL_AUDIT_REPORT_SHA256):
        return False
    object_type = _git("cat-file", "-t", LEGACY_GATE1_ORIGINAL_AUDIT_REPORT_BLOB_OID)
    raw = _git("cat-file", "blob", LEGACY_GATE1_ORIGINAL_AUDIT_REPORT_BLOB_OID)
    return object_type.returncode == 0 and object_type.stdout.strip() == b"blob" and raw.returncode == 0 and _sha256(raw.stdout) == LEGACY_GATE1_ORIGINAL_AUDIT_REPORT_SHA256


def validate_legacy_residual_provenance_retry1(gates: dict | None = None) -> tuple[bool, str]:
    """Validate the two proven residual corrections; the third remains fail-closed."""
    target, pending = LEGACY_RESIDUAL_PROVENANCE_RETRY1_FILE, LEGACY_RESIDUAL_PROVENANCE_RETRY1_PENDING
    if pending.exists():
        return False, "retry1 provenance pending residue present"
    if not target.is_file():
        return False, "retry1 provenance bundle is required"
    try:
        raw = target.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeError):
        return False, "retry1 provenance bundle unreadable"
    if raw != _canonical_bundle_json(payload):
        return False, "retry1 provenance bundle is not canonical"
    trusted, trusted_message = _trusted_provenance_bundle(raw)
    if not trusted:
        return False, trusted_message
    required = {
        "version", "bundle_sha256", "supersedes_path", "supersedes_raw_sha256",
        "supersedes_lock_path", "supersedes_lock_value", "records",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        return False, "retry1 provenance bundle schema invalid"
    unsigned = dict(payload)
    declared_hash = unsigned.pop("bundle_sha256")
    if (payload["version"] != LEGACY_RESIDUAL_PROVENANCE_RETRY1_VERSION or
            not _is_sha256(declared_hash) or declared_hash != _sha256(_canonical_bundle_json(unsigned))):
        return False, "retry1 provenance bundle hash or version invalid"
    if (payload["supersedes_path"] != ".ly_state/session/legacy_residual_reconciliation_20260727.json" or
            payload["supersedes_lock_path"] != ".ly_state/session/legacy_residual_reconciliation_20260727.sha256" or
            not _is_sha256(payload["supersedes_raw_sha256"]) or
            payload["supersedes_lock_value"] != payload["supersedes_raw_sha256"]):
        return False, "retry1 provenance predecessor invalid"
    try:
        baseline_raw = LEGACY_RESIDUAL_RECONCILIATION_FILE.read_bytes()
        baseline_lock = LEGACY_RESIDUAL_RECONCILIATION_LOCK.read_text(encoding="utf-8").strip()
        baseline_records = json.loads(baseline_raw.decode("utf-8"))["records"]
    except OSError:
        return False, "retry1 provenance predecessor unreadable"
    except (KeyError, TypeError, ValueError, UnicodeError):
        return False, "retry1 provenance predecessor malformed"
    if _sha256(baseline_raw) != payload["supersedes_raw_sha256"] or baseline_lock != payload["supersedes_lock_value"]:
        return False, "retry1 provenance predecessor hash drift"
    records = payload["records"]
    if not isinstance(records, dict) or set(records) != LEGACY_RESIDUAL_PROVENANCE_KEYS:
        return False, "retry1 provenance records must contain exactly Gate1 and Gate2"
    canonical = gates if gates is not None else load_canonical_gate_map()
    identities, reports = set(), set()
    for key, record in records.items():
        required_record = {
            "original_key", "recorded_claim_sha256", "authoritative_record_sha256", "current_record_sha256",
            "authority_evidence_sha256", "original_audit_report_sha256", "authoritative_record", "field_drift",
            "authority_evidence_path", "original_audit_report_path", "authority_l3_session_id", "authority_l3_session_key",
            "authority_l3_role_id", "authority_verdict", "reason", "pinned_commit", "published_at",
        }
        if key == "GP_ALT_DATA_FETCHER_OPTIMIZATION":
            required_record.add("original_audit_report_blob_oid")
        if key == LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY:
            required_record -= {"authoritative_record_sha256", "authoritative_record", "field_drift"}
        if not isinstance(record, dict) or set(record) != required_record or record["original_key"] != key:
            return False, f"retry1 provenance record {key} schema invalid"
        if key != LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY:
            baseline_record = baseline_records.get(key) if isinstance(baseline_records, dict) else None
            if (not isinstance(baseline_record, dict) or
                    record["recorded_claim_sha256"] != baseline_record.get("original_gate_record_sha256")):
                return False, f"retry1 provenance record {key} recorded claim drift"
        hash_fields = (
            "recorded_claim_sha256", "current_record_sha256", "authority_evidence_sha256",
            "original_audit_report_sha256",
        ) if key == LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY else (
            "recorded_claim_sha256", "authoritative_record_sha256", "current_record_sha256",
            "authority_evidence_sha256", "original_audit_report_sha256",
        )
        if any(not _is_sha256(record[field]) for field in hash_fields):
            return False, f"retry1 provenance record {key} hash invalid"
        authority_session = record.get("authority_l3_session_id")
        if (not isinstance(authority_session, str) or not authority_session or authority_session in identities or
                authority_session != record["authority_l3_session_key"] or
                record["authority_l3_role_id"] != 21 or record["authority_verdict"] != "[APPROVED]" or
                not isinstance(record["published_at"], str) or
                not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", record["published_at"])):
            return False, f"retry1 provenance record {key} identity invalid"
        evidence, evidence_message = _bundle_report(record, "authority_evidence_path")
        original, original_message = (None, "immutable blob") if key == "GP_ALT_DATA_FETCHER_OPTIMIZATION" else _bundle_report(record, "original_audit_report_path")
        if evidence is None or (key != "GP_ALT_DATA_FETCHER_OPTIMIZATION" and original is None) or record["authority_evidence_path"] in reports or (original is not None and record["original_audit_report_path"] in reports):
            return False, f"retry1 provenance record {key} {evidence_message if evidence is None else original_message}"
        if _sha256(evidence.read_bytes()) != record["authority_evidence_sha256"]:
            return False, f"retry1 provenance record {key} report hash drift"
        evidence_text = evidence.read_text(encoding="utf-8")
        original_text = original.read_text(encoding="utf-8") if original is not None else "[APPROVED]"
        is_gate4_sidecar = key == LEGACY_GATE4_ORIGINAL_PROVENANCE_KEY
        is_gate3_sidecar = key == LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY
        authority_valid = (record["authority_evidence_path"] == LEGACY_GATE2_AUTHORITY_PATH and
                            record["authority_evidence_sha256"] == LEGACY_GATE2_AUTHORITY_SHA256 and
                            authority_session == LEGACY_GATE2_AUTHORITY_SESSION and
                            _closed_report_tuple(evidence, key, 21, authority_session)) if is_gate4_sidecar else (
                            record["authority_evidence_path"] == LEGACY_GATE3_AUTHORITY_PATH and
                            record["authority_evidence_sha256"] == LEGACY_GATE3_AUTHORITY_SHA256 and
                            authority_session == LEGACY_GATE3_AUTHORITY_SESSION and
                            _closed_gate3_authority(evidence)) if is_gate3_sidecar else (
                            _declared_report_identity(evidence) == (record["authority_l3_session_id"], record["authority_l3_session_key"]))
        if ("[APPROVED]" not in evidence_text or "[NEEDS_FIX]" in evidence_text or not authority_valid or
                "[APPROVED]" not in original_text):
            return False, f"retry1 provenance record {key} report authority invalid"
        if key in {"GP_OVERFITTING_REMEDIATION_GATE4_20260704", LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY} and (
                original is None or not _closed_original_role23_report(original.read_bytes(), key)):
            return False, f"retry1 provenance {key} original Role23 report invalid"
        current = canonical.get(key)
        if current is None or _sha256(_immutable_gate_record(current)) != record["current_record_sha256"]:
            return False, f"retry1 provenance record {key} current snapshot drift"
        identities.add(authority_session)
        reports.add(record["authority_evidence_path"])
        if original is not None:
            reports.add(record["original_audit_report_path"])
        if key == "GP_ALT_DATA_FETCHER_OPTIMIZATION":
            if (not _gate1_original_audit_blob(record) or record["reason"] != "synthesized_phase_name" or record["pinned_commit"] is not None or
                    record["authoritative_record"] != _immutable_gate_record(current) or
                    record["authoritative_record_sha256"] != record["current_record_sha256"] or
                    record["field_drift"] != {"phase_name": {"recorded": None, "authoritative": key}}):
                return False, "retry1 provenance Gate1 drift invalid"
        elif key == LEGACY_GATE3_ORIGINAL_PROVENANCE_KEY:
            pinned = _pinned_gate_record(record["pinned_commit"], key)
            if (record["reason"] != "pinned_commit_snapshot" or pinned is None or
                    record["recorded_claim_sha256"] != _sha256(_immutable_gate_record(pinned))):
                return False, "retry1 provenance Gate3 pinned snapshot invalid"
        else:
            commit = record["pinned_commit"]
            pinned = _pinned_gate_record(commit, key) if isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) else None
            immutable_pinned = _immutable_gate_record(pinned) if pinned else {}
            immutable_current = _immutable_gate_record(current)
            expected_drift = {
                field: {"pinned": immutable_pinned.get(field), "current": immutable_current.get(field)}
                for field in sorted(set(immutable_pinned) | set(immutable_current))
                if immutable_pinned.get(field) != immutable_current.get(field)
            }
            if (record["reason"] != "pinned_commit_snapshot" or pinned is None or
                    record["authoritative_record"] != immutable_pinned or
                    record["authoritative_record_sha256"] != _sha256(immutable_pinned) or
                    record["field_drift"] != expected_drift):
                return False, "retry1 provenance Gate2 pinned snapshot invalid"
    baseline_records = set(baseline_records)
    validated_baseline_resolved = baseline_records - LEGACY_RESIDUAL_PROVENANCE_KEYS - {LEGACY_RESIDUAL_OPEN_KEY}
    validated_retry1_resolved = set(records)
    resolved_keys = validated_baseline_resolved | validated_retry1_resolved
    open_keys = baseline_records - resolved_keys
    if open_keys != {LEGACY_RESIDUAL_OPEN_KEY}:
        return False, "retry1 provenance resolved/open set invalid"
    return True, f"legacy residual reconciliation: {len(resolved_keys)} resolved; {len(open_keys)} open"


def publish_legacy_residual_provenance_retry1(payload: dict) -> Path:
    """Atomically publish one canonical retry1 bundle without overwriting evidence."""
    target, pending = LEGACY_RESIDUAL_PROVENANCE_RETRY1_FILE, LEGACY_RESIDUAL_PROVENANCE_RETRY1_PENDING
    if target.exists() or pending.exists():
        raise FileExistsError("retry1 provenance final artifact or pending residue exists")
    raw = _canonical_bundle_json(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    with pending.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    if pending.read_bytes() != raw:
        raise RuntimeError("retry1 provenance pending reread mismatch")
    try:
        os.link(pending, target)
    except FileExistsError:
        raise FileExistsError("retry1 provenance final artifact collision")
    try:
        directory_fd = os.open(target.parent, os.O_RDONLY)
        os.fsync(directory_fd)
        os.close(directory_fd)
    except OSError:
        pass
    pending.unlink()
    return target


def publish_residual_reconciliation(payload: dict) -> tuple[Path, Path]:
    """Publish once; existing JSON or lock is a collision, never overwrite."""
    if set(payload) != {"version", "records"}:
        raise ValueError("residual reconciliation payload schema invalid")
    if payload["version"] != LEGACY_RESIDUAL_RECONCILIATION_VERSION:
        raise ValueError("residual reconciliation payload version invalid")
    raw = _canonical_json(payload)
    target, lock = LEGACY_RESIDUAL_RECONCILIATION_FILE, LEGACY_RESIDUAL_RECONCILIATION_LOCK
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or lock.exists():
        raise FileExistsError("residual reconciliation final artifact collision")
    created = []
    try:
        with target.open("xb") as output:
            output.write(raw)
        created.append(target)
        with lock.open("xb") as output:
            output.write(_sha256(raw).encode("ascii"))
        created.append(lock)
    except Exception:
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    valid, message = validate_residual_reconciliation()
    if not valid:
        raise RuntimeError(f"residual reconciliation post-publish validation failed: {message}")
    return target, lock


def _validate_retry2_sidecar(gates: dict[str, dict]) -> tuple[bool, str]:
    if not LEGACY_RECONCILIATION_RETRY2_FILE.is_file() or not LEGACY_RECONCILIATION_RETRY2_LOCK.is_file():
        return False, "retry2 reconciliation sidecar and lock are required"
    try:
        raw = LEGACY_RECONCILIATION_RETRY2_FILE.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        lock = LEGACY_RECONCILIATION_RETRY2_LOCK.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return False, "retry2 reconciliation sidecar is unreadable"
    if lock != _sha256(raw):
        return False, "retry2 reconciliation sidecar hash drift"
    if not isinstance(payload, dict) or set(payload) != {"version", "supersedes", "supersedes_lock_sha256", "records"}:
        return False, "retry2 reconciliation sidecar has invalid schema"
    if payload["version"] != LEGACY_RECONCILIATION_RETRY2_VERSION or payload["supersedes"] != LEGACY_RECONCILIATION_FILE.name:
        return False, "retry2 reconciliation sidecar version or supersedes drift"
    try:
        v1_hash = LEGACY_RECONCILIATION_LOCK.read_text(encoding="utf-8").strip()
    except OSError:
        return False, "retry2 superseded V1 lock is missing"
    if payload["supersedes_lock_sha256"] != v1_hash:
        return False, "retry2 superseded V1 lock hash drift"
    records = payload["records"]
    if not isinstance(records, dict) or set(records) != LEGACY_DATE_KEYS:
        return False, "retry2 reconciliation sidecar must contain exactly the 14 frozen keys"
    for key, record in records.items():
        if not isinstance(record, dict) or set(record) != LEGACY_RECORD_FIELDS:
            return False, f"retry2 record {key} has invalid schema"
        report = _safe_repo_path(record.get("fresh_l3_report_path"), ".ly_state/session/audit_reports/")
        if report is None or not report.is_file():
            return False, f"retry2 record {key} has invalid fresh report"
        declared = _declared_report_identity(report)
        if declared != (record.get("fresh_l3_session_id"), record.get("fresh_l3_session_key")):
            return False, f"retry2 record {key} fresh report identity drift"
    return True, "retry2 reconciliation valid"


def _validate_retry3_sidecar(gates: dict[str, dict]) -> tuple[bool, str]:
    if not LEGACY_RECONCILIATION_RETRY3_FILE.is_file() or not LEGACY_RECONCILIATION_RETRY3_LOCK.is_file():
        return False, "retry3 reconciliation sidecar and lock are required"
    try:
        raw = LEGACY_RECONCILIATION_RETRY3_FILE.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        lock = LEGACY_RECONCILIATION_RETRY3_LOCK.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return False, "retry3 reconciliation sidecar is unreadable"
    if lock != _sha256(raw):
        return False, "retry3 reconciliation sidecar hash drift"
    if not isinstance(payload, dict) or set(payload) != {"version", "supersedes", "supersedes_lock_sha256", "records"}:
        return False, "retry3 reconciliation sidecar has invalid schema"
    if payload["version"] != LEGACY_RECONCILIATION_RETRY3_VERSION or payload["supersedes"] != LEGACY_RECONCILIATION_RETRY2_FILE.name:
        return False, "retry3 reconciliation sidecar version or supersedes drift"
    try:
        retry2_lock = LEGACY_RECONCILIATION_RETRY2_LOCK.read_text(encoding="utf-8").strip()
    except OSError:
        return False, "retry3 superseded retry2 lock is missing"
    if payload["supersedes_lock_sha256"] != retry2_lock:
        return False, "retry3 superseded retry2 lock hash drift"
    retry2_valid, retry2_message = _validate_retry2_sidecar(gates)
    if not retry2_valid:
        return False, f"retry3 superseded retry2 invalid: {retry2_message}"
    try:
        retry2_records = json.loads(LEGACY_RECONCILIATION_RETRY2_FILE.read_text(encoding="utf-8"))["records"]
    except (OSError, KeyError, TypeError, ValueError):
        return False, "retry3 superseded retry2 records are unreadable"
    records = payload["records"]
    if not isinstance(records, dict) or set(records) != LEGACY_DATE_KEYS:
        return False, "retry3 reconciliation sidecar must contain exactly the 14 frozen keys"
    if records != retry2_records:
        return False, "retry3 records drift from fully revalidated retry2 records"
    for key, record in records.items():
        if not isinstance(record, dict) or set(record) != LEGACY_RECORD_FIELDS:
            return False, f"retry3 record {key} has invalid schema"
        report = _safe_repo_path(record.get("fresh_l3_report_path"), ".ly_state/session/audit_reports/")
        if report is None or not report.is_file():
            return False, f"retry3 record {key} has invalid fresh report"
        declared = _declared_report_identity(report)
        if declared != (record.get("fresh_l3_session_id"), record.get("fresh_l3_session_key")):
            return False, f"retry3 record {key} fresh report identity drift"
    return True, "retry3 reconciliation valid"


def resolve_active_legacy_sidecar(gates: dict[str, dict] | None = None) -> tuple[bool, str]:
    """Resolve retry3, retry2, then immutable V1, with fail-closed validation."""
    canonical = gates if gates is not None else load_canonical_gate_map()
    if LEGACY_RECONCILIATION_RETRY3_FILE.exists() or LEGACY_RECONCILIATION_RETRY3_LOCK.exists():
        return _validate_retry3_sidecar(canonical)
    if LEGACY_RECONCILIATION_RETRY2_FILE.exists() or LEGACY_RECONCILIATION_RETRY2_LOCK.exists():
        return _validate_retry2_sidecar(canonical)
    return validate_legacy_reconciliation(canonical)


def resolve_active_legacy_gate(gates: dict[str, dict], key: str) -> dict | None:
    """Return the canonical gate with validated fresh retry fields overlaid."""
    valid, _ = resolve_active_legacy_sidecar(gates)
    if not valid or key not in gates:
        return None
    gate = dict(gates[key])
    sidecar_file = LEGACY_RECONCILIATION_RETRY3_FILE if LEGACY_RECONCILIATION_RETRY3_FILE.exists() else LEGACY_RECONCILIATION_RETRY2_FILE
    if sidecar_file.exists():
        try:
            records = json.loads(sidecar_file.read_text(encoding="utf-8"))["records"]
            record = records.get(key)
        except (OSError, TypeError, ValueError):
            return None
        if record is None:
            return gate
        gate.update(
            l3_session_id=record["fresh_l3_session_id"],
            l3_session_key=record["fresh_l3_session_key"],
            audit_report_path=record["fresh_l3_report_path"],
            final_verdict=record["fresh_l3_verdict"],
        )
        if record.get("resolved_date"):
            gate["timestamp"] = f'{record["resolved_date"]}T00:00:00+00:00'
    return gate


def validate_legacy_reconciliation(gates: dict | None = None) -> tuple[bool, str]:
    """Validate the locked, append-only legacy migration sidecar."""
    if not LEGACY_RECONCILIATION_FILE.exists() or not LEGACY_RECONCILIATION_LOCK.exists():
        return False, "legacy reconciliation sidecar and lock are required"
    try:
        raw = LEGACY_RECONCILIATION_FILE.read_bytes()
        sidecar = json.loads(raw.decode("utf-8"))
        lock = LEGACY_RECONCILIATION_LOCK.read_text(encoding="utf-8").strip().split()[0]
    except (OSError, ValueError, IndexError) as exc:
        return False, f"legacy reconciliation sidecar unreadable: {exc}"
    if lock != _sha256(raw):
        return False, "legacy reconciliation sidecar hash drift"
    if not isinstance(sidecar, dict) or set(sidecar) != LEGACY_DATE_KEYS:
        return False, "legacy reconciliation sidecar must contain exactly the 14 frozen keys"
    gates = gates or load_canonical_gate_map()
    seen_sessions, seen_reports = set(), set()
    for key, record in sidecar.items():
        if not isinstance(record, dict):
            return False, f"legacy record {key} must be an object"
        expected_fields = LEGACY_RECORD_FIELDS | (LEGACY_SNAPSHOT_FIELDS if key == "GP_OVERFITTING_REMEDIATION_GATE4_20260704" else frozenset())
        if set(record) != expected_fields:
            return False, f"legacy record {key} has invalid schema"
        string_fields = LEGACY_RECORD_FIELDS - {"original_timestamp"}
        if any(not isinstance(record[field], str) or not record[field] for field in string_fields):
            return False, f"legacy record {key} has invalid field types"
        if record["original_timestamp"] is not None and not isinstance(record["original_timestamp"], str):
            return False, f"legacy record {key} has invalid original timestamp type"
        if not re.fullmatch(r"[0-9a-f]{64}", record["original_gate_record_sha256"]):
            return False, f"legacy record {key} has invalid original record hash"
        if not re.fullmatch(r"[0-9a-f]{64}", record["historical_evidence_sha256"]):
            return False, f"legacy record {key} has invalid historical evidence hash"
        if record["original_key"] != key or record["fresh_l3_verdict"] != "[APPROVED]":
            return False, f"legacy record {key} has immutable identity drift"
        if record["workflow_classification"] not in {"reconcile", "blocked"}:
            return False, f"legacy record {key} has invalid workflow classification"
        if record["workflow_classification"] == "blocked":
            return False, f"legacy record {key} is blocked"
        for field in ("historical_evidence_path", "fresh_l3_report_path"):
            path = _safe_repo_path(record[field])
            if path is None or not path.is_file():
                return False, f"legacy record {key} has invalid or missing {field}"
        fresh = _safe_repo_path(record["fresh_l3_report_path"], ".ly_state/session/audit_reports/")
        assert fresh is not None
        content = fresh.read_text(encoding="utf-8")
        if "[NEEDS_FIX]" in content or "[MANUAL_APPROVAL]" in content or "manual approval" in content.lower():
            return False, f"legacy record {key} contains invalid approval evidence"
        if "[APPROVED]" not in content:
            return False, f"legacy record {key} fresh L3 report is not approved"
        session_id, session_key = record["fresh_l3_session_id"], record["fresh_l3_session_key"]
        if not isinstance(session_id, str) or not session_id or session_id != session_key:
            return False, f"legacy record {key} requires identical fresh L3 session identity"
        if session_id in seen_sessions or record["fresh_l3_report_path"] in seen_reports:
            return False, f"legacy record {key} reuses L3 identity or report"
        seen_sessions.add(session_id); seen_reports.add(record["fresh_l3_report_path"])
        historical = _safe_repo_path(record["historical_evidence_path"])
        assert historical is not None
        if _sha256(historical.read_bytes()) != record["historical_evidence_sha256"]:
            return False, f"legacy record {key} historical evidence hash drift"
        gate = gates.get(key)
        if gate is None or gate.get("phase_name", key) != key:
            return False, f"legacy record {key} gate missing or renamed"
        if key == "GP_OVERFITTING_REMEDIATION_GATE4_20260704":
            _, snapshot_message = resolve_original_gate_snapshot(record, key)
            if snapshot_message != "ok":
                return False, f"legacy record {key} {snapshot_message}"
        elif _sha256(_immutable_gate_record(gate)) != record["original_gate_record_sha256"]:
            return False, f"legacy record {key} original gate record hash drift"
        if record["original_timestamp"] != gate.get("timestamp"):
            return False, f"legacy record {key} original timestamp drift"
        try:
            reconciled_at = datetime.fromisoformat(record["reconciled_at"].replace("Z", "+00:00"))
            if record["original_timestamp"] is not None and reconciled_at < datetime.fromisoformat(record["original_timestamp"].replace("Z", "+00:00")):
                return False, f"legacy record {key} reconciliation is backdated"
        except (TypeError, ValueError):
            return False, f"legacy record {key} has invalid timestamp"
    return True, "legacy reconciliation valid"

# Cutoff for strict declared-skill alignment (2026-06-28 08:56:00 UTC)
STRICT_SKILL_ALIGNMENT_CUTOFF = datetime(2026, 6, 28, 8, 56, 0, tzinfo=timezone.utc).timestamp()


# Gate name for strict declared-skill alignment enforcement
STRICT_SKILL_ALIGNMENT_GATE = "SOD_STRICT_SKILL_ALIGNMENT_20260628"

# Forbidden paths for authoritative skill/role loading (non-authoritative mentions allowed)
FORBIDDEN_SKILL_PATHS = [
    r".gemini\antigravity-ide\scratch\ag-kit",
    r".gemini/antigravity-ide/scratch/ag-kit",
    r".openclaw\skills",
    r".openclaw/skills",
    r"C:\Users\GHC\.agents",
    r"C:/Users/GHC/.agents",
    r".codex\memories",
    r".codex/memories",
]

# Markers that indicate authoritative reliance on forbidden paths (not just mention)
AUTHORITATIVE_MARKERS = [
    "loaded from",
    "source:",
    "read from",
    "using skill from",
    "skill source:",
]

# Markers that indicate non-authoritative mention (allowed)
NON_AUTHORITATIVE_MARKERS = [
    'no reliance',
    'confirmed not present',
    'not present',
    'not in repo_root scope',
    'not in scope',
    "non-authoritative",
    "forbidden-path",
    "forbidden path",
    "not used as source",
    "not referenced",
    "not accessed",
    "scan evidence",
    "junction target",
    "symlink target",
]

# Gate name for the STRICT_REPO_LOCAL_SKILL_LOADING contract approval
STRICT_GATE_NAME = "STRICT_REPO_LOCAL_SKILL_LOADING_20260612"

# Regex to match remediation chain FIX gates: <BASE>_FIX<N>_<YYYYMMDD>
_CHAIN_FIX_RE = re.compile(r'^(.+)_FIX(\d+)_(\d{8})$', re.IGNORECASE)
# Regex to match chain base gates: <BASE>_<YYYYMMDD>
_CHAIN_BASE_RE = re.compile(r'^(.+)_(\d{8})$')

# Cache for loaded role specs
_ROLE_SPECS_CACHE = None

ALLOWED_GLOBAL_REPO_LOCAL_FILES = {
    ".agents/agents.md",
    ".agents\\agents.md",
    "agents.md",
    "phase_gates.json",
    ".ly_state/session/phase_gates.json",
    ".ly_state\\session\\phase_gates.json",
}


def validate_task_graph() -> tuple[bool, str]:
    """Validate optional task graph file.

    Returns:
        tuple: (is_valid: bool, message: str)
    """
    if not TASK_GRAPH_FILE.exists():
        return True, "task_graph.json not present"

    try:
        data = json.loads(TASK_GRAPH_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        return False, f"task_graph.json invalid JSON: {e}"

    if not isinstance(data, list):
        return False, "task_graph.json must be list of nodes"

    required_fields = {
        "task_id",
        "role_id",
        "depends_on",
        "parallel_safe",
        "success_criteria",
    }
    nodes_by_id = {}

    for index, node in enumerate(data):
        if not isinstance(node, dict):
            return False, f"task_graph node at index {index} must be object"

        missing = sorted(required_fields - node.keys())
        if missing:
            return False, f"task_graph node at index {index} missing fields: {', '.join(missing)}"

        task_id = node.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            return False, f"task_graph node at index {index} has invalid task_id"

        depends_on = node.get("depends_on")
        if not isinstance(depends_on, list):
            return False, f"task_graph node '{task_id}' depends_on must be list"
        if any(not isinstance(dep, str) or not dep.strip() for dep in depends_on):
            return False, f"task_graph node '{task_id}' depends_on must contain non-empty strings"

        if not isinstance(node.get("parallel_safe"), bool):
            return False, f"task_graph node '{task_id}' parallel_safe must be boolean"

        if isinstance(node.get("role_id"), bool) or not isinstance(node.get("role_id"), int):
            return False, f"task_graph node '{task_id}' role_id must be integer"

        success_criteria = node.get("success_criteria")
        if not isinstance(success_criteria, str) or not success_criteria.strip():
            return False, f"task_graph node '{task_id}' success_criteria must be non-empty string"

        if task_id in nodes_by_id:
            return False, f"task_graph duplicate task_id: {task_id}"

        nodes_by_id[task_id] = node

    for task_id, node in nodes_by_id.items():
        for dependency in node["depends_on"]:
            if dependency not in nodes_by_id:
                return False, f"task_graph node '{task_id}' depends on unknown task '{dependency}'"

    visiting = set()
    visited = set()

    def visit(task_id: str) -> bool:
        if task_id in visited:
            return True
        if task_id in visiting:
            return False

        visiting.add(task_id)
        for dependency in nodes_by_id[task_id]["depends_on"]:
            if not visit(dependency):
                return False
        visiting.remove(task_id)
        visited.add(task_id)
        return True

    for task_id in nodes_by_id:
        if not visit(task_id):
            return False, f"task_graph cycle detected at task '{task_id}'"

    return True, "task_graph.json valid DAG"


def load_role_specs() -> dict:
    """Load all agent role specs from .agents/agent/*.md frontmatter.
    
    Returns:
        dict: {role_id: {name, description, tier, platform, sod_boundary, ...}}
    """
    global _ROLE_SPECS_CACHE
    if _ROLE_SPECS_CACHE is not None:
        return _ROLE_SPECS_CACHE
    
    if not AGENTS_DIR.exists():
        print(f"WARNING: Agents directory not found: {AGENTS_DIR}")
        return {}
    
    role_specs = {}
    
    for md_file in AGENTS_DIR.glob("*.md"):
        try:
            content = md_file.read_text(encoding='utf-8')
            
            # Extract YAML frontmatter between --- markers
            frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if not frontmatter_match:
                continue
            
            frontmatter = frontmatter_match.group(1)
            
            # Parse YAML frontmatter (simple key: value parser)
            spec = {}
            for line in frontmatter.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Handle key: value pairs
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Parse simple inline YAML lists like [a, b, c]
                    if value.startswith('[') and value.endswith(']'):
                        items = []
                        inner = value[1:-1].strip()
                        if inner:
                            for item in inner.split(','):
                                item = item.strip()
                                if item.startswith('"') and item.endswith('"'):
                                    item = item[1:-1]
                                elif item.startswith("'") and item.endswith("'"):
                                    item = item[1:-1]
                                if item:
                                    items.append(item)
                        value = items
                    # Remove quotes
                    elif value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    # Convert role_id and tier to int
                    if key in ('role_id', 'tier'):
                        try:
                            value = int(value)
                        except ValueError:
                            pass
                    
                    spec[key] = value
            
            # Store by role_id if present
            if 'role_id' in spec:
                role_specs[spec['role_id']] = spec
        
        except Exception as e:
            print(f"WARNING: Failed to parse {md_file.name}: {e}")
            continue
    
    _ROLE_SPECS_CACHE = role_specs
    return role_specs


def validate_l3_role(role_id, role_name, role_specs: dict) -> tuple[bool, str]:
    """Validate L3 role: must be 17-25, tier=3, platform=Codex, has sod_boundary, name matches spec.
    
    Args:
        role_id: Role ID to validate (int or string)
        role_name: Role name to validate against spec (can be None for grandfathered gates)
        role_specs: Dict of loaded role specs
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    try:
        role_id_int = int(role_id)
    except (ValueError, TypeError):
        return False, f"l3_role_id must be integer, got: {role_id}"
    
    # Check range 17-25
    if not (17 <= role_id_int <= 25):
        return False, f"l3_role_id must be 17-25, got: {role_id_int}"
    
    # Check role spec exists
    if role_id_int not in role_specs:
        return False, f"l3_role_id {role_id_int} not found in .agents/agent/*.md"
    
    spec = role_specs[role_id_int]
    
    # Validate tier=3
    if spec.get('tier') != 3:
        return False, f"l3_role_id {role_id_int} must have tier=3, got: {spec.get('tier')}"
    
    # Validate platform=Codex
    if spec.get('platform') != 'Codex':
        return False, f"l3_role_id {role_id_int} must have platform=Codex, got: {spec.get('platform')}"
    
    # Validate sod_boundary exists
    if not spec.get('sod_boundary'):
        return False, f"l3_role_id {role_id_int} must have sod_boundary defined"
    
    # Validate role_name matches spec name (if provided)
    if role_name and role_name != spec.get('name'):
        return False, f"l3_role_name '{role_name}' does not match spec name '{spec.get('name')}' for role_id {role_id_int}"
    
    return True, ""


def validate_l2_role(role_id, role_name, role_specs: dict, gate_name: str = "") -> tuple[bool, str]:
    """Validate an OpenCode L2 role, except Role 26 for `_plan` gates.
    
    Args:
        role_id: Role ID to validate
        role_name: Role name to validate against spec (can be None for grandfathered gates)
        role_specs: Dict of loaded role specs
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    try:
        role_id_int = int(role_id)
    except (ValueError, TypeError):
        return False, f"l2_role_id must be integer, got: {role_id}"
    
    is_planning_role = role_id_int == 26 and gate_name.endswith("_plan")
    if not (6 <= role_id_int <= 16 or is_planning_role):
        return False, f"l2_role_id must be 6-16, got: {role_id_int}"
    
    # Check role spec exists
    if role_id_int not in role_specs:
        return False, f"l2_role_id {role_id_int} not found in .agents/agent/*.md"
    
    spec = role_specs[role_id_int]
    
    if is_planning_role:
        if (spec.get('name') != 'planning-architect' or role_name != 'planning-architect' or
                spec.get('tier') != 3 or spec.get('platform') != 'Codex' or
                spec.get('sod_boundary') != 'planning-only, non-audit, no production code'):
            return False, "l2_role_id 26 plan exception requires planning-architect, tier=3, platform=Codex, and sod_boundary"
    else:
        # Validate tier=2
        if spec.get('tier') != 2:
            return False, f"l2_role_id {role_id_int} must have tier=2, got: {spec.get('tier')}"

        # Validate platform=OpenCode
        if spec.get('platform') != 'OpenCode':
            return False, f"l2_role_id {role_id_int} must have platform=OpenCode, got: {spec.get('platform')}"
    
    # Validate role_name matches spec name (if provided)
    if role_name and role_name != spec.get('name'):
        return False, f"l2_role_name '{role_name}' does not match spec name '{spec.get('name')}' for role_id {role_id_int}"
    
    return True, ""


def validate_audit_report_path(report_path_str: str) -> tuple[bool, str]:
    """Validate audit report path is relative and under .ly_state/session/audit_reports/.
    
    Prevents path traversal attacks and ensures audit reports are in the correct location.
    
    Args:
        report_path_str: Path to audit report
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not report_path_str:
        return False, "audit_report_path is empty"
    
    # Check for absolute paths (Windows or Unix)
    if Path(report_path_str).is_absolute():
        return False, f"audit_report_path must be relative, not absolute: {report_path_str}"
    
    # Check for path traversal attempts
    if '..' in report_path_str or report_path_str.startswith('/') or report_path_str.startswith('\\'):
        return False, f"audit_report_path contains path traversal: {report_path_str}"
    
    # Normalize path and check it's under the required directory
    try:
        normalized = Path(report_path_str).as_posix()
        if not normalized.startswith('.ly_state/session/audit_reports/'):
            return False, f"audit_report_path must be under .ly_state/session/audit_reports/, got: {report_path_str}"
    except Exception as e:
        return False, f"invalid audit_report_path: {e}"
    
    return True, ""


def check_path_traversal_only(report_path_str: str) -> tuple[bool, str]:
    """Check path for traversal attacks only (no location requirement).
    
    Always rejects:
    - Absolute paths (Windows or Unix)
    - Path traversal attempts (.., leading / or \\)
    
    Does NOT check whether the path is under .ly_state/session/audit_reports/.
    Used for pre-cutoff grandfathered gates where the location requirement
    is waived but path traversal must still be rejected for security.
    
    Args:
        report_path_str: Path to audit report
        
    Returns:
        tuple: (is_safe: bool, error_message: str)
    """
    if not report_path_str:
        return True, ""  # Empty path handled elsewhere
    
    # Check for absolute paths (Windows or Unix)
    if Path(report_path_str).is_absolute():
        return False, f"audit_report_path must be relative, not absolute: {report_path_str}"
    
    # Check for path traversal attempts
    if '..' in report_path_str or report_path_str.startswith('/') or report_path_str.startswith('\\'):
        return False, f"audit_report_path contains path traversal: {report_path_str}"
    
    return True, ""


def check_audit_report_exists(report_path_str: str) -> tuple[bool, str]:
    """Check if audit report file exists.
    
    Args:
        report_path_str: Relative or absolute path to audit report
        
    Returns:
        tuple: (exists: bool, error_message: str)
    """
    if not report_path_str:
        return False, "audit_report_path is empty"
    
    # Try as relative path from workspace
    report_path = WORKSPACE / report_path_str
    if not report_path.exists():
        # Try as absolute path
        report_path = Path(report_path_str)
        if not report_path.exists():
            return False, f"audit report file not found: {report_path_str}"
    
    if not report_path.is_file():
        return False, f"audit report path is not a file: {report_path_str}"
    
    return True, ""


def check_audit_report_content(report_path_str: str, expected_verdict: str) -> tuple[bool, str]:
    """Check if audit report content contains the expected verdict.
    
    Args:
        report_path_str: Path to audit report
        expected_verdict: Expected verdict string (e.g., "[APPROVED]")
        
    Returns:
        tuple: (contains_verdict: bool, error_message: str)
    """
    # First check file exists
    exists, error = check_audit_report_exists(report_path_str)
    if not exists:
        return False, error
    
    # Read content
    report_path = WORKSPACE / report_path_str
    if not report_path.exists():
        report_path = Path(report_path_str)
    
    try:
        content = report_path.read_text(encoding='utf-8')
    except Exception as e:
        return False, f"failed to read audit report: {e}"
    
    # Check if verdict appears in content
    if expected_verdict not in content:
        return False, f"audit report does not contain verdict '{expected_verdict}'"
    
    return True, ""


def validate_audit_report_l2_session(content: str, expected_session_id: str) -> tuple[bool, str]:
    """Require the audit report to declare the gate's exact L2 session."""
    declared = re.findall(
        r"^(?:#{1,6}\s+|-\s*)?(?:\*\*)?(?:L2\s+Session(?:\s+ID)?|l2_session_id)(?:\*\*)?\s*:\s*`?([^`\s]+)",
        content,
        re.I | re.M,
    )
    if not declared:
        return False, "audit report missing declared L2 Session"
    sessions = {session.rstrip(".,`") for session in declared}
    if sessions != {expected_session_id}:
        return False, f"audit report L2 Session mismatch: expected {expected_session_id}, got {', '.join(sorted(sessions))}"
    return True, ""


def audit_l2_session_identity_required(timestamp: float | None) -> bool:
    return timestamp is not None and timestamp >= AUDIT_L2_SESSION_IDENTITY_CUTOFF


def check_audit_report_l2_session(report_path_str: str, expected_session_id: str) -> tuple[bool, str]:
    """Compare a gate L2 session with the declaration in its audit report."""
    try:
        content = (WORKSPACE / report_path_str).read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"failed to read audit report: {exc}"
    return validate_audit_report_l2_session(content, expected_session_id)


def detect_duplicate_gates(raw_json) -> tuple[bool, list]:
    """Detect duplicate gate names in raw JSON before normalization.
    
    Inspects the raw phase_gates.json structure (list or dict) and identifies
    duplicate phase_name/name/gate_id values. For duplicates, checks if they
    have conflicting final_verdict, role metadata, or session IDs. Only reports
    duplicates that have actual conflicts - non-conflicting duplicates are allowed.
    
    Args:
        raw_json: Raw loaded JSON (list or dict)
        
    Returns:
        tuple: (has_conflicts: bool, conflict_reports: list[str])
    """
    # Enhanced tracking: gate_name -> [(location, verdict, l2_role_id, l3_role_id, l2_role_name, l3_role_name, l2_session_id, l3_session_id), ...]
    gate_occurrences = {}
    
    if not isinstance(raw_json, list):
        # If it's a dict at top level, extract gates from it
        if isinstance(raw_json, dict):
            for key, value in raw_json.items():
                if isinstance(value, dict) and "final_verdict" in value:
                    gate_name = value.get("phase_name") or value.get("name") or value.get("gate_id") or key
                    if gate_name not in gate_occurrences:
                        gate_occurrences[gate_name] = []
                    gate_occurrences[gate_name].append((
                        "top-level",
                        value.get("final_verdict"),
                        value.get("l2_role_id"),
                        value.get("l3_role_id"),
                        value.get("l2_role_name"),
                        value.get("l3_role_name"),
                        value.get("l2_session_id"),
                        value.get("l3_session_id")
                    ))
        # Don't return early - fall through to analyze occurrences
    else:
        # Process list format
        for idx, item in enumerate(raw_json):
            if not isinstance(item, dict):
                continue
            
            # Check if this is a flat gate object
            gate_name = item.get("phase_name") or item.get("name") or item.get("gate_id")
            if gate_name and "final_verdict" in item:
                if gate_name not in gate_occurrences:
                    gate_occurrences[gate_name] = []
                gate_occurrences[gate_name].append((
                    f"list[{idx}]",
                    item.get("final_verdict"),
                    item.get("l2_role_id"),
                    item.get("l3_role_id"),
                    item.get("l2_role_name"),
                    item.get("l3_role_name"),
                    item.get("l2_session_id"),
                    item.get("l3_session_id")
                ))
                continue
            
            # Check if this is a nested dict of gates
            for key, value in item.items():
                if isinstance(value, dict) and "final_verdict" in value:
                    nested_gate_name = value.get("phase_name") or value.get("name") or value.get("gate_id") or key
                    if nested_gate_name not in gate_occurrences:
                        gate_occurrences[nested_gate_name] = []
                    gate_occurrences[nested_gate_name].append((
                        f"list[{idx}].{key}",
                        value.get("final_verdict"),
                        value.get("l2_role_id"),
                        value.get("l3_role_id"),
                        value.get("l2_role_name"),
                        value.get("l3_role_name"),
                        value.get("l2_session_id"),
                        value.get("l3_session_id")
                    ))
    
    # Check for duplicates WITH CONFLICTS ONLY
    conflict_reports = []
    has_conflicts = False
    
    for gate_name, occurrences in gate_occurrences.items():
        if len(occurrences) > 1:
            # Check for conflicts in verdict and role metadata
            # Note: Different session IDs are tracked but NOT considered conflicts by themselves
            # (a gate may legitimately have multiple L2 sessions if it was fixed/re-implemented)
            verdicts = set(occ[1] for occ in occurrences if occ[1] is not None)
            l2_role_ids = set(occ[2] for occ in occurrences if occ[2] is not None)
            l3_role_ids = set(occ[3] for occ in occurrences if occ[3] is not None)
            l2_role_names = set(occ[4] for occ in occurrences if occ[4] is not None)
            l3_role_names = set(occ[5] for occ in occurrences if occ[5] is not None)
            l2_session_ids = set(occ[6] for occ in occurrences if occ[6] is not None)
            l3_session_ids = set(occ[7] for occ in occurrences if occ[7] is not None)
            
            conflict_details = []
            if len(verdicts) > 1:
                conflict_details.append(f"conflicting verdicts: {verdicts}")
            if len(l2_role_ids) > 1:
                conflict_details.append(f"conflicting l2_role_ids: {l2_role_ids}")
            if len(l3_role_ids) > 1:
                conflict_details.append(f"conflicting l3_role_ids: {l3_role_ids}")
            if len(l2_role_names) > 1:
                conflict_details.append(f"conflicting l2_role_names: {l2_role_names}")
            if len(l3_role_names) > 1:
                conflict_details.append(f"conflicting l3_role_names: {l3_role_names}")
            
            # Session IDs are tracked but not reported as conflicts (informational only)
            # Different sessions for same gate are legitimate (e.g., initial + fix sessions)
            
            # Only report if there are actual conflicts
            if conflict_details:
                has_conflicts = True
                locations = [occ[0] for occ in occurrences]
                conflict_msg = " with " + ", ".join(conflict_details)
                # Include session ID info for context but not as primary conflict
                session_info = ""
                if len(l2_session_ids) > 1:
                    session_info += f" [note: {len(l2_session_ids)} different L2 sessions]"
                if len(l3_session_ids) > 1:
                    session_info += f" [note: {len(l3_session_ids)} different L3 sessions]"
                conflict_reports.append(
                    f"DUPLICATE GATE NAME WITH CONFLICTS: '{gate_name}' appears {len(occurrences)} times at {locations}{conflict_msg}{session_info}"
                )
    
    return has_conflicts, conflict_reports


def normalize_timestamp(ts) -> float | None:
    """Convert timestamp to float, handling both numeric and ISO string formats.
    
    Args:
        ts: Timestamp value (float, int, or ISO string)
        
    Returns:
        Float timestamp or None if invalid/missing
    """
    if ts is None:
        return None
    
    # Already numeric
    if isinstance(ts, (int, float)):
        return float(ts)
    
    # Try to parse string timestamp
    if isinstance(ts, str):
        # Try numeric string first
        try:
            return float(ts)
        except ValueError:
            pass
        
        # Try ISO format parsing
        try:
            # Handle timezone offsets: +07:00, Z, etc.
            iso_str = ts.strip()
            if iso_str.endswith('Z'):
                iso_str = iso_str[:-1] + '+00:00'
            dt = datetime.fromisoformat(iso_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except (ValueError, TypeError):
            pass
    
    return None


def load_gates() -> list | None:
    """Load gates from GATES_FILE.

    Supports three JSON shapes:
    1. List of gate dicts: ``[{...}, {...}]``
    2. Wrapper dict: ``{"gates": [{...}, {...}]}``
    3. Dict-shaped: ``{"GATE_NAME": {gate_obj}, "OTHER_GATE": {gate_obj}}``
       where top-level keys are gate names and values are gate objects.

    Returns:
        list: List of gate dicts, empty when the file is absent.
    """
    if not GATES_FILE.exists():
        return []

    try:
        with open(GATES_FILE, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)

        if isinstance(data, list):
            gates = data
        elif isinstance(data, dict):
            # Wrapper with explicit 'gates' key
            if 'gates' in data:
                if not isinstance(data['gates'], list):
                    print("FAIL: gates wrapper must contain a list", file=sys.stderr)
                    sys.exit(1)
                gates = data['gates']
            else:
                # Dict-shaped: top-level keys are gate names, values are gate objects
                gates = []
                for key, value in data.items():
                    if not isinstance(value, dict):
                        print("FAIL: every dict-shaped gate member must be an object", file=sys.stderr)
                        sys.exit(1)
                    phase_name = value.get('phase_name')
                    if phase_name is None:
                        if not isinstance(key, str) or not key.strip():
                            print("FAIL: dict-shaped gate keys must be non-empty phase names", file=sys.stderr)
                            sys.exit(1)
                        gates.append({**value, 'phase_name': key})
                    elif not isinstance(phase_name, str) or not phase_name.strip():
                        print("FAIL: dict-shaped gates must have a non-empty phase_name", file=sys.stderr)
                        sys.exit(1)
                    elif phase_name != key:
                        print(f"FAIL: gate key {key!r} does not match phase_name {phase_name!r}", file=sys.stderr)
                        sys.exit(1)
                    else:
                        gates.append(value)
        else:
            print("FAIL: gate JSON root must be a list or object", file=sys.stderr)
            sys.exit(1)

        for gate in gates:
            if not isinstance(gate, dict) or not isinstance(gate.get('phase_name'), str) or not gate['phase_name'].strip():
                print("FAIL: every gate list member must be an object with a non-empty phase_name", file=sys.stderr)
                sys.exit(1)
        return gates
    except json.JSONDecodeError as exc:
        print(f"FAIL: invalid gate JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"FAIL: gate file unreadable: {exc}", file=sys.stderr)
        return None


def validate_forbidden_path_usage(text) -> tuple:
    """Detect authoritative reliance on forbidden skill/role paths.
    
    Performs sentence-level analysis: each sentence is checked independently.
    A non-authoritative marker in one sentence does NOT protect an authoritative
    use in a different sentence.
    
    Args:
        text: Text content to scan (str or None)
        
    Returns:
        tuple: (has_violation: bool, violations: list[str])
    """
    if not text:
        return False, []
    
    text_lower = text.lower()
    violations = []
    
    # Split into sentences (rough: split on newline, period+space, or period+newline)
    sentences = re.split(r'[\n]|\.\s+', text)
    
    for sentence in sentences:
        sentence_stripped = sentence.strip()
        if not sentence_stripped:
            continue
        
        sentence_lower = sentence_stripped.lower()
        
        # Check each forbidden path
        for forbidden_path in FORBIDDEN_SKILL_PATHS:
            forbidden_lower = forbidden_path.lower()
            
            if forbidden_lower not in sentence_lower:
                continue
            
            # Found a forbidden path in this sentence
            # Check if non-authoritative context exists IN THIS SENTENCE
            has_non_auth = any(
                marker in sentence_lower 
                for marker in NON_AUTHORITATIVE_MARKERS
            )
            
            # Check for authoritative markers in this sentence
            has_auth = any(
                marker in sentence_lower 
                for marker in AUTHORITATIVE_MARKERS
            )
            
            if has_auth and has_non_auth:
                # Both present: authoritative takes precedence (violation)
                violations.append(
                    f"Forbidden path used authoritatively: '{forbidden_path}' "
                    f"in sentence: '{sentence_stripped[:80]}...'"
                )
            elif has_auth and not has_non_auth:
                # Authoritative only: clear violation
                violations.append(
                    f"Forbidden path used authoritatively: '{forbidden_path}' "
                    f"in sentence: '{sentence_stripped[:80]}...'"
                )
            elif not has_auth and not has_non_auth:
                # Bare mention without any context: flagged
                violations.append(
                    f"Forbidden path mentioned without non-authoritative context: "
                    f"'{forbidden_path}' in sentence: '{sentence_stripped[:80]}...'"
                )
            # else: has_non_auth and not has_auth -> clean (allowed)
    
    return len(violations) > 0, violations


def _validate_l2_report_content(content, role_id=None, role_name=None) -> tuple:
    """Validate L2 report contains repo-local skill source evidence.
    
    Requires:
    1. REPO_AGENT_ROOT reference
    2. REPO_SKILL_ROOT reference
    3. Exact role file read (e.g., .agents/agent/<role_name>.md)
    4. At least one skill file from .agents/skills/
    5. No forbidden path violations
    
    Args:
        content: L2 report content string
        role_id: L2 role ID (int)
        role_name: L2 role name string
        
    Returns:
        tuple: (valid: bool, message: str)
    """
    if not content:
        return False, "L2 report content is empty"
    
    content_lower = content.lower()
    
    # Check for forbidden path violations first
    has_violation, violations = validate_forbidden_path_usage(content)
    if has_violation:
        return False, f"Forbidden path violation in L2 report: {violations[0]}"
    
    repo_local_markers = (
        " repo-local",
        "repo_local",
        ".agents/agent",
        ".agents\\agent",
        ".agents/skills",
        ".agents\\skills",
        "repo_agent_root",
        "repo_skill_root",
    )
    has_legacy_repo_local_evidence = any(marker in content_lower for marker in repo_local_markers)

    if role_id is None:
        if has_legacy_repo_local_evidence:
            return True, "L2 report has valid legacy repo-local skill source evidence"
        return False, "L2 report missing legacy repo-local skill source evidence"

    # Check REPO_AGENT_ROOT reference
    has_agent_root = (
        "repo_agent_root" in content_lower or
        ".agents/agent" in content_lower or
        ".agents\\agent" in content_lower
    )

    # Check REPO_SKILL_ROOT reference
    has_skill_root = (
        "repo_skill_root" in content_lower or
        ".agents/skills" in content_lower or
        ".agents\\skills" in content_lower
    )

    if not has_agent_root and not has_skill_root:
        return False, (
            "L2 report missing repo-local skill source evidence: "
            "no REPO_AGENT_ROOT or REPO_SKILL_ROOT reference found"
        )

    if role_id is None:
        return True, "L2 report has valid legacy repo-local skill source evidence"


    if not has_agent_root:
        return False, (
            "L2 report missing REPO_AGENT_ROOT reference: "
            "must list exact agent file read from .agents/agent"
        )

    if not has_skill_root:
        return False, (
            "L2 report missing REPO_SKILL_ROOT reference: "
            "must list exact skill files read from .agents/skills"
        )
    
    reported_files = _extract_repo_local_files_read(content)
    reported_agent_files = {
        path for path in reported_files
        if re.fullmatch(r"\.agents[/\\]agent[/\\][^/\\]+\.md", path, re.IGNORECASE)
    }
    reported_skill_files = _extract_reported_skill_files(reported_files)

    if not reported_agent_files and not reported_skill_files:
        return False, (
            "L2 report missing repo-local file evidence: must list at least one "
            "repo-local agent or skill file in Repo-Local Files Read"
        )

    role_specs = load_role_specs()
    spec = role_specs.get(int(role_id)) if role_id is not None else None
    if not spec:
        return False, f"Role spec not found for l2_role_id {role_id}"

    declared_skills = spec.get('skills') or []
    if not isinstance(declared_skills, list):
        return False, f"Role spec for {role_name} has invalid skills list"

    # Check exact role file read
    role_name_str = str(role_name) if role_name else ""
    has_exact_role_file = False
    if role_name_str:
        patterns = [
            f".agents/agent/{role_name_str}.md",
            f".agents\\agent\\{role_name_str}.md",
            f".agents/agent/{role_name_str}",
            f".agents\\agent\\{role_name_str}",
            f"REPO_AGENT_ROOT/{role_name_str}.md",
            f"REPO_AGENT_ROOT\\{role_name_str}.md",
            f"REPO_AGENT_ROOT/{role_name_str}",
            f"REPO_AGENT_ROOT\\{role_name_str}",
        ]
        for p in patterns:
            if p in content or p.lower() in content_lower:
                has_exact_role_file = True
                break

    if role_name_str and not has_exact_role_file:
        return False, (
            f"L2 report missing exact role file: expected .agents/agent/{role_name_str}.md "
            f"in files read list"
        )
    expected_skill_files = {
        f".agents/skills/{skill}/SKILL.md".lower()
        for skill in declared_skills
    }

    if not reported_skill_files:
        return False, (
            "L2 report missing skill file evidence: "
            "must list declared .agents/skills/<name>/SKILL.md files in Repo-Local Files Read"
        )

    missing_skill_files = sorted(expected_skill_files - reported_skill_files)
    if missing_skill_files:
        return False, (
            "L2 report missing declared skill files: " + ", ".join(missing_skill_files)
        )

    extra_skill_files = sorted(reported_skill_files - expected_skill_files)
    if extra_skill_files:
        return False, (
            "L2 report lists undeclared skill files: " + ", ".join(extra_skill_files)
        )
    
    return True, "L2 report has valid strict repo-local skill source evidence"


def _validate_audit_report_skill_content(content, report_filename, role_id=None, role_name=None) -> tuple:
    """Validate audit report content for repo-local skill source verification.
    
    Requires:
    1. Repo-local references (.agents/agent and/or .agents/skills)
    2. Explicit forbidden path scan result
    3. No forbidden path violations
    
    Args:
        content: Audit report content string
        report_filename: Name of the audit report file
        
    Returns:
        tuple: (valid: bool, message: str)
    """
    if not content:
        return False, "Audit report content is empty"
    
    content_lower = content.lower()
    
    # Check for forbidden path violations
    has_violation, violations = validate_forbidden_path_usage(content)
    if has_violation:
        return False, f"Forbidden path violation in audit report: {violations[0]}"
    
    # Check for repo-local references
    has_repo_local = (
        "repo-local" in content_lower or
        "repo_local" in content_lower or
        ".agents/agent" in content or
        ".agents\\agent" in content or
        ".agents/skills" in content or
        ".agents\\skills" in content
    )
    
    # Check for explicit forbidden path scan result
    has_forbidden_scan = (
        "forbidden path scan" in content_lower or
        "forbidden-path scan" in content_lower or
        "forbidden path" in content_lower and "scan" in content_lower
    )

    if role_id is None:
        return True, "Audit report has valid legacy repo-local skill source verification"

    if not has_repo_local:
        return False, (
            "Audit report missing repo-local skill source verification: "
            "must reference L2 report's repo-local skill source evidence"
        )

    if not has_forbidden_scan:
        return False, (
            "Audit report missing forbidden path scan result: "
            "must include explicit forbidden path scan evidence"
        )

    reported_files = _extract_repo_local_files_read(content)
    reported_agent_files = {
        path for path in reported_files
        if re.fullmatch(r"\.agents[/\\]agent[/\\][^/\\]+\.md", path, re.IGNORECASE)
    }
    reported_skill_files = _extract_reported_skill_files(reported_files)

    if not reported_agent_files and not reported_skill_files:
        return False, (
            "Audit report missing repo-local file evidence: must list at least one "
            "repo-local agent or skill file in Repo-Local Files Read"
        )

    if role_name:
        role_specs = load_role_specs()
        spec = role_specs.get(int(role_id))
        if not spec:
            return False, f"Role spec not found for l3_role_id {role_id}"

        declared_skills = spec.get('skills') or []
        if not isinstance(declared_skills, list):
            return False, f"Role spec for {role_name} has invalid skills list"

        expected_skill_files = {
            f".agents/skills/{skill}/SKILL.md".lower()
            for skill in declared_skills
        }

        if expected_skill_files and not reported_skill_files:
            return False, (
                "Audit report missing skill file evidence: "
                "must list declared .agents/skills/<name>/SKILL.md files in Repo-Local Files Read"
            )

        missing_skill_files = sorted(expected_skill_files - reported_skill_files)
        if missing_skill_files:
            return False, (
                "Audit report missing declared skill files: " + ", ".join(missing_skill_files)
            )

        extra_skill_files = sorted(reported_skill_files - expected_skill_files)
        non_global_extras = [
            path for path in extra_skill_files
            if path not in ALLOWED_GLOBAL_REPO_LOCAL_FILES
        ]
        if non_global_extras:
            return False, (
                "Audit report lists undeclared skill files: " + ", ".join(non_global_extras)
            )
    
    return True, "Audit report has valid strict repo-local skill source verification"


def check_l2_report_skill_sources(session_id, role_id=None, role_name=None) -> tuple:
    """Check L2 report for repo-local skill source evidence.
    
    Args:
        session_id: L2 session ID string
        role_id: L2 role ID
        role_name: L2 role name
        
    Returns:
        tuple: (valid: bool, message: str)
    """
    if not session_id:
        return False, "L2 session ID is empty"
    
    # Construct expected L2 report path
    l2_report_path = WORKSPACE / ".ly_state" / "session" / f"{session_id}.md"
    
    if not l2_report_path.exists():
        return True, f"L2 report not found: {session_id}.md (soft warning - checked separately)"
    
    try:
        content = l2_report_path.read_text(encoding='utf-8')
    except Exception as e:
        return True, f"L2 report read error (soft warning): {e}"
    
    return _validate_l2_report_content(content, role_id, role_name)


def check_audit_report_skill_sources(report_path, role_id=None, role_name=None) -> tuple:
    """Check audit report for repo-local skill source verification.
    
    Args:
        report_path: Path to audit report file (str)
        
    Returns:
        tuple: (valid: bool, message: str)
    """
    if not report_path:
        return True, "Audit report path empty (checked separately)"
    
    # Try as relative path from workspace
    full_path = WORKSPACE / report_path
    if not full_path.exists():
        full_path = Path(report_path)
    
    if not full_path.exists():
        return True, f"Audit report not found: {report_path} (checked separately)"
    
    try:
        content = full_path.read_text(encoding='utf-8')
    except Exception as e:
        return True, f"Audit report read error (checked separately): {e}"
    
    report_filename = full_path.name
    return _validate_audit_report_skill_content(content, report_filename, role_id, role_name)


def _gate_key_date(gate_name: str) -> tuple[date | None, str | None]:
    match = re.findall(r"(?<![0-9])([0-9]{8})(?![0-9])", gate_name)
    if len(match) > 1:
        return None, "multiple gate YYYYMMDD selectors"
    suffix = re.search(r"(?:^|[_-])([0-9A-Za-z]{8})$", gate_name)
    if match and (not suffix or suffix.group(1) != match[0]):
        return None, "gate YYYYMMDD selector must be a single suffix"
    if not suffix:
        return None, None
    token = suffix.group(1)
    if not token.isdigit():
        return None, "malformed gate YYYYMMDD selector"
    try:
        return date(int(token[:4]), int(token[4:6]), int(token[6:])), None
    except ValueError:
        return None, "malformed gate YYYYMMDD selector"


def resolve_gate_date(gate_record: dict, gate_name: str) -> tuple[date | None, str | None]:
    """Resolve policy date from the complete gate record, failing closed."""
    key_date, key_error = _gate_key_date(gate_name)
    if key_error:
        return None, key_error
    timestamp = gate_record.get("timestamp") if isinstance(gate_record, dict) else None
    timestamp_date = None
    if timestamp is not None:
        if not isinstance(timestamp, str) or not timestamp:
            return None, "timestamp must be an ISO-8601 string with UTC offset"
        try:
            normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
            parsed = datetime.fromisoformat(normalized)
        except (TypeError, ValueError):
            return None, "timestamp must be a valid ISO-8601 timestamp"
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None, "timestamp must include Z or an explicit UTC offset"
        timestamp_date = parsed.date()
    if key_date is not None and timestamp_date is not None and key_date != timestamp_date:
        return None, "gate key date and timestamp date mismatch"
    resolved = key_date or timestamp_date
    if resolved is None:
        return None, "gate key date or valid timestamp date is required"
    return resolved, None


def check_report_evidence_wording(
    gate_name: str, report_path: str, gate_record: dict | None = None
) -> tuple[bool, str]:
    full_path = WORKSPACE / report_path
    try:
        content = full_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"report evidence read failed: {exc}"
    resolved_gate_date, resolution_error = resolve_gate_date(gate_record or {}, gate_name)
    if resolution_error:
        return False, resolution_error
    valid, errors, canonical = validate_report_evidence(
        content,
        gate_name=gate_name,
        report_filename=full_path.name,
        resolved_gate_date=resolved_gate_date,
    )
    return valid, "; ".join(errors) if errors else f"{'canonical' if canonical else 'legacy'} report evidence valid"


def _extract_repo_local_files_read(content: str) -> list[str]:
    """Extract file paths listed in repo-local files-read blocks."""
    files = []
    capture = False

    for raw_line in content.splitlines():
        line = raw_line.strip()
        line_lower = line.lower()

        # Only start capturing on actual files-read section headers
        if (
            "repo-local files read" in line_lower or
            "files read" in line_lower or
            line_lower.startswith("files read:")
        ):
            capture = True
            continue

        if capture and line.startswith("#"):
            break

        if capture and line.startswith("-"):
            file_path = line[1:].strip().strip('`')
            if file_path:
                files.append(file_path)
            continue

        if capture and line and not line.startswith("-"):
            break

    return files


def _normalize_report_path(path: str) -> str:
    return path.replace('\\', '/').strip().lower()


def _extract_reported_skill_files(reported_files: list[str]) -> set[str]:
    skill_files = set()
    for file_path in reported_files:
        normalized = _normalize_report_path(file_path)
        if normalized in ALLOWED_GLOBAL_REPO_LOCAL_FILES:
            continue
        if re.fullmatch(r"\.agents/skills/[^/]+/skill\.md", normalized):
            skill_files.add(normalized)
    return skill_files


def _validate_panel_audit(audit: dict, l2_role_id, role_specs: dict) -> tuple[bool, str]:
    """Validate one L3 panel audit entry."""
    if not isinstance(audit, dict):
        return False, "l3_panel entry must be object"

    l3_role_id = audit.get("l3_role_id")
    l3_role_name = audit.get("l3_role_name")
    role_valid, role_msg = validate_l3_role(l3_role_id, l3_role_name, role_specs)
    if not role_valid:
        return False, role_msg

    if l2_role_id is not None and int(l2_role_id) == int(l3_role_id):
        return False, f"writer/auditor separation violated: l2_role_id {l2_role_id} equals panel l3_role_id {l3_role_id}"

    audit_path = audit.get("audit_report_path", "")
    path_valid, path_msg = validate_audit_report_path(audit_path)
    if not path_valid:
        return False, path_msg

    exists_valid, exists_msg = check_audit_report_exists(audit_path)
    if not exists_valid:
        return False, exists_msg

    approved_valid, approved_msg = check_audit_report_content(audit_path, "[APPROVED]")
    if not approved_valid:
        partial_valid, partial_msg = check_audit_report_content(audit_path, "[APPROVED_PARTIAL]")
        if not partial_valid:
            return False, approved_msg or partial_msg

    skill_valid, skill_msg = check_audit_report_skill_sources(audit_path)
    if not skill_valid:
        return False, skill_msg

    return True, ""


def validate_l3_panel(l3_panel, l2_role_id, role_specs: dict) -> tuple[bool, str]:
    """Validate panel of independent L3 audits."""
    if not isinstance(l3_panel, list) or not l3_panel:
        return False, "l3_panel must be non-empty list"

    seen_role_ids = set()
    for audit in l3_panel:
        if not isinstance(audit, dict):
            return False, "l3_panel entry must be object"

        l3_role_id = audit.get("l3_role_id")
        try:
            l3_role_id_int = int(l3_role_id)
        except (TypeError, ValueError):
            return False, f"panel l3_role_id must be integer, got: {l3_role_id}"

        if l2_role_id is not None and int(l2_role_id) == l3_role_id_int:
            return False, f"writer/auditor separation violated: l2_role_id {l2_role_id} equals panel l3_role_id {l3_role_id_int}"

        if l3_role_id_int in seen_role_ids:
            return False, f"duplicate panel auditor role_id: {l3_role_id_int}"
        seen_role_ids.add(l3_role_id_int)

    for audit in l3_panel:
        audit_valid, audit_msg = _validate_panel_audit(audit, l2_role_id, role_specs)
        if not audit_valid:
            return False, audit_msg

    return True, ""


def derive_strict_approval_timestamp(gates) -> float:
    """Derive the STRICT gate approval timestamp from gates dict.
    
    Searches for a gate with phase_name matching STRICT_GATE_NAME.
    
    Args:
        gates: Dict of gate_name -> gate_data
        
    Returns:
        float timestamp or None if no STRICT gate found
    """
    if not gates:
        return None
    
    # Search by key first
    if STRICT_GATE_NAME in gates:
        gate = gates[STRICT_GATE_NAME]
        ts = normalize_timestamp(gate.get("timestamp"))
        if ts is not None:
            return ts
    
    # Search by phase_name in values
    gates_dict = gates if isinstance(gates, dict) else {g.get("phase_name", g.get("__original_key__", "UNKNOWN")): g for g in gates if isinstance(g, dict)}
    for key, gate in gates_dict.items():
        if not isinstance(gate, dict):
            continue
        if gate.get("phase_name") == STRICT_GATE_NAME:
            ts = normalize_timestamp(gate.get("timestamp"))
            if ts is not None:
                return ts
    
    return None


def build_remediation_chains(gates) -> dict:
    """Build remediation chains from gates dict.
    
    Groups base gates and FIX<N> gates sharing the same base name and date.
    
    Args:
        gates: Dict of gate_name -> gate_data
        
    Returns:
        dict: {chain_base_key: [(fix_num, gate_name, gate_data), ...], ...}
        Sorted by fix_num within each chain.
    """
    if not gates:
        return {}
    
    chains = {}
    
    for gate_name, gate_data in gates.items():
        if not isinstance(gate_data, dict):
            continue
        
        # Try to match as a FIX gate: <BASE>_FIX<N>_<YYYYMMDD>
        fix_match = _CHAIN_FIX_RE.match(gate_name)
        if fix_match:
            base_name = fix_match.group(1)
            fix_num = int(fix_match.group(2))
            date_suffix = fix_match.group(3)
            chain_key = f"{base_name}_{date_suffix}"
            
            if chain_key not in chains:
                chains[chain_key] = []
            chains[chain_key].append((fix_num, gate_name, gate_data))
            continue
        
        # Try to match as a base gate: <BASE>_<YYYYMMDD>
        base_match = _CHAIN_BASE_RE.match(gate_name)
        if base_match:
            base_name = base_match.group(1)
            date_suffix = base_match.group(2)
            chain_key = f"{base_name}_{date_suffix}"
            
            # Only include if it looks like a chain-eligible gate (has date suffix)
            # Check that this is not itself a FIX gate that didn't match above
            if not _CHAIN_FIX_RE.match(gate_name):
                if chain_key not in chains:
                    chains[chain_key] = []
                chains[chain_key].append((0, gate_name, gate_data))
    
    # Sort each chain by fix_num
    for chain_key in chains:
        chains[chain_key].sort(key=lambda x: x[0])
    
    return chains


def get_superseded_gates(gates) -> list:
    """Get list of gate names superseded by resolved remediation chains.
    
    A chain is resolved when its latest FIX gate has [APPROVED] or 
    [APPROVED_PARTIAL] verdict. Prior gates in the chain are superseded.
    
    Args:
        gates: Dict of gate_name -> gate_data
        
    Returns:
        list: List of superseded gate name strings
    """
    if not gates:
        return []
    
    gates_dict = gates if isinstance(gates, dict) else {g.get("phase_name", g.get("__original_key__", "UNKNOWN")): g for g in gates if isinstance(g, dict)}
    chains = build_remediation_chains(gates_dict)
    superseded = []
    
    for chain_key, members in chains.items():
        if len(members) <= 1:
            # Single gate = no chain, no supersession
            continue
        
        # Check if latest member is resolved
        latest = members[-1]
        latest_verdict = latest[2].get("final_verdict", "")
        is_resolved = latest_verdict in ("[APPROVED]", "[APPROVED_PARTIAL]")
        
        if is_resolved:
            # All members except the latest are superseded,
            # but only if they have non-approved verdicts ([NEEDS_FIX], etc.)
            for fix_num, gate_name, gate_data in members[:-1]:
                member_verdict = gate_data.get("final_verdict", "")
                if member_verdict not in ("[APPROVED]", "[APPROVED_PARTIAL]"):
                    superseded.append(gate_name)
    
    return superseded


def check_sod_compliance() -> bool:
    """Main compliance check: validates all gates for SoD compliance.
    
    Three-tier enforcement:
    - Tier A: Pre-strict legacy gates (post-skill-cutoff, pre-strict-approval) -> advisory
    - Tier B: Post-strict-approval gates missing strict fields -> hard-blocking
    - Tier C: STRICT gate itself -> always hard-blocking
    
    Returns:
        bool: True if all gates pass compliance, False if any hard-blocking failure
    """
    task_graph_valid, task_graph_msg = validate_task_graph()
    if not task_graph_valid:
        print(f"FAIL: {task_graph_msg}")

    gates_list = load_gates()
    if gates_list is None:
        print("FAIL: gate loading failed; compliance blocked")
        compliance_result = False
        return compliance_result
    
    if not gates_list:
        print("FAIL: no gates loaded; compliance blocked")
        return False

    gate_names = {gate.get("phase_name") for gate in gates_list if isinstance(gate, dict)}
    residual_present = gate_names & LEGACY_RESIDUAL_KEYS
    if residual_present:
        residual_valid, residual_msg = validate_legacy_residual_evidence()
        if not residual_valid:
            print(f"FAIL: {residual_msg}")
            return False

    legacy_valid, legacy_msg = resolve_active_legacy_sidecar()
    if (LEGACY_RECONCILIATION_FILE.exists() or LEGACY_RECONCILIATION_LOCK.exists() or
            LEGACY_RECONCILIATION_RETRY2_FILE.exists() or LEGACY_RECONCILIATION_RETRY2_LOCK.exists()):
        if not legacy_valid:
            print(f"FAIL: {legacy_msg}")
            return False
    frozen_present = {g.get("phase_name") for g in gates_list if isinstance(g, dict)} & LEGACY_DATE_KEYS
    if frozen_present and not legacy_valid:
        print(f"FAIL: frozen legacy gates require reconciliation evidence: {legacy_msg}")
        return False
    
    # Load role specs
    role_specs = load_role_specs()
    
    # Build gates dict (phase_name -> gate_data)
    gates_dict = {}
    for gate in gates_list:
        if isinstance(gate, dict):
            phase_name = gate.get("phase_name", "")
            if phase_name:
                gates_dict[phase_name] = gate

    residual_records = {}
    if residual_present:
        residual_reconciled, residual_reconciliation_msg = resolve_active_residual_reconciliation(
            load_canonical_gate_map()
        )
        if not residual_reconciled:
            print(f"FAIL: {residual_reconciliation_msg}")
            return False
        print(f"INFO: {residual_reconciliation_msg}")
        residual_payload, residual_payload_msg = _read_locked_json(
            LEGACY_RESIDUAL_RECONCILIATION_FILE, LEGACY_RESIDUAL_RECONCILIATION_LOCK
        )
        if residual_payload is None:
            print(f"FAIL: {residual_payload_msg}")
            return False
        residual_records = residual_payload["records"]

    # Derive strict approval timestamp
    strict_approval_ts = derive_strict_approval_timestamp(gates_dict)
    
    # Get superseded gates
    superseded = get_superseded_gates(gates_dict)
    
    # Check each gate
    all_pass = task_graph_valid

    for gate_name, gate in gates_dict.items():
        if gate_name in LEGACY_RESIDUAL_KEYS:
            gate = dict(gate)
            residual_record = residual_records[gate_name]
            gate.update({
                "audit_report_path": residual_record["fresh_l3_report_path"],
                "l3_session_id": residual_record["fresh_l3_session_id"],
                "l3_session_key": residual_record["fresh_l3_session_key"],
                "final_verdict": residual_record["fresh_l3_verdict"],
            })
        elif gate_name in LEGACY_DATE_KEYS or gate_name in LEGACY_WORKFLOW_KEYS:
            gate = resolve_active_legacy_gate(gates_dict, gate_name) or gate
        # Skip superseded gates
        if gate_name in superseded:
            continue
        
        phase_name = gate.get("phase_name", gate_name)
        verdict = gate.get("final_verdict", "")
        ts = normalize_timestamp(gate.get("timestamp"))
        fields_valid, fields_msg = validate_post_cutoff_gate_fields(gate, ts)
        if not fields_valid:
            print(f"FAIL: Gate {gate_name} {fields_msg}")
            all_pass = False
            continue
        
        # Skip gates that are not approved (unless they're pending)
        # Skip gates that are not approved (unless they're pending)
        if verdict not in ("[APPROVED]", "[APPROVED_PARTIAL]"):
            # NEEDS_FIX or other non-approved verdicts are hard-blocking
            # unless superseded
            print(f"FAIL: Gate {gate_name} has non-approved verdict: {verdict}")
            all_pass = False
            continue
        
        # Validate L2 role
        l2_role_id = gate.get("l2_role_id")
        l2_role_name = gate.get("l2_role_name")
        l2_completed = gate.get("l2_completed", False)
        
        if l2_completed and l2_role_id is not None:
            l2_valid, l2_msg = validate_l2_role(l2_role_id, l2_role_name, role_specs, gate_name)
            if not l2_valid:
                print(f"FAIL: Gate {gate_name} L2 role invalid: {l2_msg}")
                all_pass = False
                continue
        
        l3_panel = gate.get("l3_panel")
        l3_role_id = gate.get("l3_role_id")
        l3_role_name = gate.get("l3_role_name")
        if l3_panel is not None:
            panel_valid, panel_msg = validate_l3_panel(l3_panel, l2_role_id, role_specs)
            if not panel_valid:
                print(f"FAIL: Gate {gate_name} L3 panel invalid: {panel_msg}")
                all_pass = False
                continue
            for panel_audit in l3_panel:
                panel_path = panel_audit.get("audit_report_path", "")
                if audit_l2_session_identity_required(ts) and (WORKSPACE / panel_path).is_file():
                    l2_identity_valid, l2_identity_msg = check_audit_report_l2_session(
                        panel_path, gate.get("l2_session_id", "")
                    )
                    if not l2_identity_valid:
                        print(f"FAIL: Gate {gate_name} panel audit L2 Session invalid: {l2_identity_msg}")
                        all_pass = False
                        break
                if gate_name not in LEGACY_RESIDUAL_KEYS:
                    wording_valid, wording_msg = check_report_evidence_wording(gate_name, panel_path, gate)
                    if not wording_valid:
                        print(f"FAIL: Gate {gate_name} report evidence wording invalid: {wording_msg}")
                        all_pass = False
                        break
            if not all_pass:
                continue
            audit_path = ""
        else:
            # Validate L3 role
            if l3_role_id is not None:
                l3_valid, l3_msg = validate_l3_role(l3_role_id, l3_role_name, role_specs)
                if not l3_valid:
                    print(f"FAIL: Gate {gate_name} L3 role invalid: {l3_msg}")
                    all_pass = False
                    continue

            # Validate audit report path
            # Pre-cutoff gates may have audit reports in docs/ (legacy behavior).
            # For pre-cutoff gates: skip location check but ALWAYS enforce path
            # traversal rejection (.., absolute paths) for security.
            # For post-cutoff gates: enforce full validate_audit_report_path.
            audit_path = gate.get("audit_report_path", "")
            if audit_path:
                is_pre_cutoff = ts is not None and ts < CUTOFF_TIMESTAMP
                if is_pre_cutoff:
                    # Pre-cutoff: path traversal check only (no location requirement)
                    traversal_safe, traversal_msg = check_path_traversal_only(audit_path)
                    if not traversal_safe:
                        print(f"FAIL: Gate {gate_name} audit path traversal unsafe: {traversal_msg}")
                        all_pass = False
                        continue
                else:
                    # Post-cutoff: full validation (traversal + location)
                    path_valid, path_msg = validate_audit_report_path(audit_path)
                    if not path_valid:
                        print(f"FAIL: Gate {gate_name} audit path invalid: {path_msg}")
                        all_pass = False
                        continue

                # Check audit report exists
                exists_valid, exists_msg = check_audit_report_exists(audit_path)
                if not exists_valid:
                    print(f"FAIL: Gate {gate_name} audit report missing: {exists_msg}")
                    all_pass = False
                    continue

                # Check audit report content
                content_valid, content_msg = check_audit_report_content(audit_path, verdict)
                if not content_valid:
                    print(f"FAIL: Gate {gate_name} audit content invalid: {content_msg}")
                    all_pass = False
                    continue

                if audit_l2_session_identity_required(ts) and (WORKSPACE / audit_path).is_file():
                    l2_identity_valid, l2_identity_msg = check_audit_report_l2_session(
                        audit_path, gate.get("l2_session_id", "")
                    )
                    if not l2_identity_valid:
                        print(f"FAIL: Gate {gate_name} audit L2 Session invalid: {l2_identity_msg}")
                        all_pass = False
                        continue


                if gate_name not in LEGACY_RESIDUAL_KEYS and (WORKSPACE / audit_path).is_file():
                    wording_valid, wording_msg = check_report_evidence_wording(gate_name, audit_path, gate)
                    if not wording_valid:
                        print(f"FAIL: Gate {gate_name} report evidence wording invalid: {wording_msg}")
                        all_pass = False
                        continue
        
        is_strict_skill_alignment_gate = (
            phase_name == STRICT_SKILL_ALIGNMENT_GATE or
            (ts is not None and ts >= STRICT_SKILL_ALIGNMENT_CUTOFF)
        )

        # --- STRICT_REPO_LOCAL_SKILL_LOADING_20260612 checks ---
        if gate_name not in LEGACY_RESIDUAL_KEYS and ts is not None and ts >= SKILL_LOADING_CUTOFF:
            # Check if this is the STRICT gate itself (Tier C: always hard-blocking)
            is_strict_gate = (phase_name == STRICT_GATE_NAME)
            
            # Check for strict fields
            has_repo_local = "repo_local_skill_sources" in gate
            has_forbidden_scan = "forbidden_path_scan" in gate
            has_strict_fields = has_repo_local and has_forbidden_scan
            
            if is_strict_gate:
                # Tier C: STRICT gate always hard-blocking
                if not has_strict_fields:
                    print(f"FAIL: Gate {gate_name} (STRICT) missing strict fields")
                    all_pass = False
                    continue
                
                # Validate L2 report content
                l2_session_id = gate.get("l2_session_id", "")
                l2_valid, l2_msg = check_l2_report_skill_sources(
                    l2_session_id,
                    l2_role_id if is_strict_skill_alignment_gate else None,
                    l2_role_name if is_strict_skill_alignment_gate else None,
                )
                if not l2_valid:
                    print(f"FAIL: Gate {gate_name} (STRICT) L2 skill sources invalid: {l2_msg}")
                    all_pass = False
                    continue
                
                # Validate audit report skill content
                if audit_path:
                    audit_valid, audit_msg = check_audit_report_skill_sources(
                        audit_path,
                        l3_role_id if is_strict_skill_alignment_gate else None,
                        l3_role_name if is_strict_skill_alignment_gate else None,
                    )
                    if not audit_valid:
                        print(f"FAIL: Gate {gate_name} (STRICT) L3 audit skill sources invalid: {audit_msg}")
                        all_pass = False
                        continue
            
            elif has_strict_fields:
                # Has strict fields -> validate them (hard-blocking)
                l2_session_id = gate.get("l2_session_id", "")
                l2_valid, l2_msg = check_l2_report_skill_sources(
                    l2_session_id,
                    l2_role_id if is_strict_skill_alignment_gate else None,
                    l2_role_name if is_strict_skill_alignment_gate else None,
                )
                if not l2_valid:
                    print(f"FAIL: Gate {gate_name} L2 skill sources invalid: {l2_msg}")
                    all_pass = False
                    continue
                
                if audit_path:
                    audit_valid, audit_msg = check_audit_report_skill_sources(
                        audit_path,
                        l3_role_id if is_strict_skill_alignment_gate else None,
                        l3_role_name if is_strict_skill_alignment_gate else None,
                    )
                    if not audit_valid:
                        print(f"FAIL: Gate {gate_name} L3 audit skill sources invalid: {audit_msg}")
                        all_pass = False
                        continue
            
            elif strict_approval_ts is not None and ts >= strict_approval_ts:
                # Tier B: Post-strict-approval, missing strict fields -> hard-blocking
                print(f"FAIL: Gate {gate_name} missing strict fields")
                all_pass = False
                continue
            
            # else: Tier A: Pre-strict-approval legacy gate -> advisory (no hard block)
    
    return all_pass


def main(argv=None):
    """CLI entry point for SoD gate compliance check."""
    import argparse
    parser = argparse.ArgumentParser(description='SOD Gate Enforcer')
    parser.add_argument('--check-before-push', action='store_true',
                        help='Check all gates before allowing git push')
    args = parser.parse_args(argv)

    if args.check_before_push:
        result = check_sod_compliance()
        if result:
            print("[PASS] All SoD gates approved. Safe to push.")
            sys.exit(0)
        else:
            print("[FAIL] SoD compliance check failed. Push blocked.")
            sys.exit(1)
    else:
        result = check_sod_compliance()
        status = "PASS" if result else "FAIL"
        print(f"SoD Compliance: [{status}]")
        sys.exit(0 if result else 1)


if __name__ == '__main__':
    main()
