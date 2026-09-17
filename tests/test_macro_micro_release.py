import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from omega.data.macro_micro_release import (
    GENESIS_POINTER_SHA256, PointerCASConflict, ProviderContractError,
    RevisionConflictError, accept_singleton_revision, activate_release_cas,
    canonical_consumer_json_v1, canonical_json_v1, classify_forecast_record,
    initialize_genesis_pointer, partition_vci_ratio_rows, recover_prepared_activation,
    seal_manifest, select_provider_revision_as_of, select_reconciled_revision_as_of,
)


FIXTURES = Path(__file__).parent / "fixtures" / "macro_micro" / "v8"


def test_canonical_json_normalizes_bytes_and_consumer_membership():
    row = {"release_id": "r2", "materialized_at": datetime(2026, 8, 10, 1, tzinfo=timezone.utc), "origin_ingested_at": datetime(2026, 8, 9, 1, tzinfo=timezone.utc), "value": Decimal("-0.00"), "label": "e\u0301"}
    changed = {**row, "release_id": "r3", "materialized_at": datetime(2026, 8, 11, 1, tzinfo=timezone.utc)}
    assert canonical_consumer_json_v1(row) == canonical_consumer_json_v1(changed)
    assert canonical_json_v1({"z": "e\u0301", "a": 1}) == b'{"a":1,"z":"\xc3\xa9"}'


def test_genesis_fixture_is_valid_canonical_json_with_declared_sha256():
    payload = (FIXTURES / "pointer" / "genesis_current.json").read_bytes()
    assert not payload.startswith(b"\xef\xbb\xbf") and not payload.endswith(b"\n")
    assert canonical_json_v1(json.loads(payload)) == payload
    assert hashlib.sha256(payload).hexdigest() == GENESIS_POINTER_SHA256


def test_partition_vci_ratios_rejects_unclassified_and_sorts():
    rows = [{"year": "2025", "yearReport": 2025, "quarter": 2, "ratioType": "RATIO_TTM", "organCode": "FPT", "ratioTTMId": 2, "ratioYearId": None}, {"year": "2025", "yearReport": 2025, "quarter": 5, "ratioType": "RATIO_YEAR", "organCode": "FPT", "ratioTTMId": 1, "ratioYearId": 4}]
    annual, quarterly = partition_vci_ratio_rows(rows, "FPT")
    assert annual[0]["ratioYearId"] == 4 and quarterly[0]["quarter"] == 2
    with pytest.raises(ProviderContractError, match="VCI_RATIO_PARTITION_VIOLATION"):
        partition_vci_ratio_rows([{**rows[0], "quarter": 5}], "FPT")


def test_forecast_classifier_is_explicit_only():
    cases = json.loads((FIXTURES / "forecast" / "classification_cases.json").read_text(encoding="utf-8"))
    assert [classify_forecast_record(case["record"], case["evidence"])["destination"] for case in cases] == [case["destination"] for case in cases]
    assert classify_forecast_record({"fiscal_period_end": "2099-12-31"}, {})["destination"] == "actual"


def test_singleton_and_provider_asof_fail_closed():
    row = {"revision_id": "r1", "record_evidence_sha256": "e1", "revision_order_kind": "singleton_immutable_evidence", "source_revision_at": None, "revision_seq": None, "record_type": "actual", "available_at": "2026-01-01T00:00:00Z", "origin_ingested_at": "2026-01-01T00:00:00Z"}
    assert accept_singleton_revision([], row)["status"] == "accepted"
    assert accept_singleton_revision([row], row)["status"] == "noop"
    assert accept_singleton_revision([row], {**row, "revision_id": "r2"})["reason"] == "REVISION_SINGLETON_CONFLICT"
    assert select_provider_revision_as_of([row], "2026-01-02T00:00:00Z")["revision_id"] == "r1"
    with pytest.raises(RevisionConflictError, match="REVISION_SINGLETON_CONFLICT"):
        select_provider_revision_as_of([row, {**row, "revision_id": "r2"}], "2026-01-02T00:00:00Z")


def test_reconciliation_requires_decision_knowledge_at_cutoff():
    row = {"revision_id": "r1", "available_at": "2026-01-01T00:00:00Z", "origin_ingested_at": "2026-01-01T00:00:00Z"}
    decision = {"decision_status": "selected", "selected_revision_id": "r1", "candidate_revision_ids": ["r1"], "candidate_available_at": ["2026-01-01T00:00:00Z"], "candidate_origin_ingested_at": ["2026-01-01T00:00:00Z"], "policy_effective_at": "2026-01-01T00:00:00Z", "policy_available_at": "2026-02-01T00:00:00Z", "policy_origin_ingested_at": "2026-02-01T00:00:00Z", "decision_created_at": "2026-02-01T00:00:00Z", "decision_recorded_at": "2026-02-01T00:00:00Z", "decision_origin_ingested_at": "2026-02-01T00:00:00Z"}
    assert select_reconciled_revision_as_of([row], [decision], "2026-01-02T00:00:00Z") is None
    assert select_reconciled_revision_as_of([row], [decision], "2026-02-02T00:00:00Z")["revision_id"] == "r1"


def test_pit_acceptance_trail_replay_is_byte_stable():
    trail = json.loads((FIXTURES / "pit" / "acceptance_trail.json").read_text(encoding="utf-8"))
    row = {"revision_id": trail["expected_revision_id"], "record_type": "actual", "available_at": "2026-01-01T00:00:00Z", "origin_ingested_at": "2026-01-01T00:00:00Z", "revision_order_kind": "singleton_immutable_evidence", "release_id": "r1", "materialized_at": "2026-01-01T00:00:00Z"}
    rematerialized = {**row, "release_id": "r2", "materialized_at": "2026-02-01T00:00:00Z"}
    first = select_provider_revision_as_of([row, rematerialized], trail["cutoff"])
    assert first["revision_id"] == trail["expected_revision_id"]
    assert canonical_consumer_json_v1(row) == canonical_consumer_json_v1(rematerialized)


def test_manifest_excludes_itself_and_pointer_wal_recovers(tmp_path):
    release = tmp_path / "release-1"
    release.mkdir()
    (release / "actual.json").write_bytes(b"[]")
    manifest = seal_manifest(release, release_id="release-1")
    assert [item["path"] for item in manifest["artifacts"]] == ["actual.json"]
    with pytest.raises(ValueError, match="sealed manifest already exists"):
        seal_manifest(release, release_id="release-1")
    pointer = tmp_path / "current.json"
    genesis = initialize_genesis_pointer(pointer)
    assert hashlib.sha256(pointer.read_bytes()).hexdigest() == GENESIS_POINTER_SHA256
    target = activate_release_cas(hashlib.sha256(canonical_json_v1(genesis)).hexdigest(), manifest, pointer, tmp_path / "attempts", activation_attempt_id="a1")
    assert target["pointer_generation"] == 1
    assert recover_prepared_activation(pointer, tmp_path / "attempts") == []
    with pytest.raises(PointerCASConflict):
        activate_release_cas(GENESIS_POINTER_SHA256, manifest, pointer, tmp_path / "attempts")


def test_recover_commits_crash_after_pointer_replacement(tmp_path):
    pointer = tmp_path / "current.json"
    genesis = initialize_genesis_pointer(pointer)
    target = {**genesis, "pointer_generation": 1, "activation_attempt_id": "a2"}
    attempt = tmp_path / "attempts" / "a2"
    attempt.mkdir(parents=True)
    prepared = {"schema_version": "activation_prepared/v1", "activation_attempt_id": "a2", "prior_pointer_bytes_base64": __import__("base64").b64encode(canonical_json_v1(genesis)).decode(), "prior_pointer_sha256": GENESIS_POINTER_SHA256, "target_pointer_bytes_base64": __import__("base64").b64encode(canonical_json_v1(target)).decode(), "target_pointer_sha256": hashlib.sha256(canonical_json_v1(target)).hexdigest()}
    prepared["prepared_record_sha256"] = hashlib.sha256(canonical_json_v1(prepared)).hexdigest()
    (attempt / "activation_prepared.json").write_bytes(canonical_json_v1(prepared))
    pointer.write_bytes(canonical_json_v1(target))
    assert recover_prepared_activation(pointer, tmp_path / "attempts") == ["a2"]
    assert (attempt / "activation_committed.json").exists()
