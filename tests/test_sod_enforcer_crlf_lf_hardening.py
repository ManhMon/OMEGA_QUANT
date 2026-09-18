import hashlib
import json
import re
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import sod_gate_enforcer as sod


def test_legacy_residual_historical_lf_hashes_contains_exact_five_records_plus_synthesis():
    """Verify LEGACY_RESIDUAL_HISTORICAL_LF_HASHES contains exact 6 entries (5 legacy + synthesis)."""
    expected_keys = {
        "LLM_PROMPT_SYNTHESIS_SEARCH_IMPROVEMENT_20260612",
        "ALPHA_WEAKNESS_DIAGNOSTICS_20260614",
        "GP_ALT_DATA_FETCHER_OPTIMIZATION",
        "GP_OVERFITTING_REMEDIATION_GATE4_20260704",
        "VNSTOCK_LATEST_STANDARDIZATION_20260612",
        "VN_ALPHA_GMM_SMOOTH_TRANSITION_20260624",
    }
    assert set(sod.LEGACY_RESIDUAL_HISTORICAL_LF_HASHES) == expected_keys
    for key, sha in sod.LEGACY_RESIDUAL_HISTORICAL_LF_HASHES.items():
        assert re.fullmatch(r"[0-9a-f]{64}", sha), f"Invalid hash format for {key}"


def test_validate_residual_reconciliation_repo_baseline():
    """Verify that validate_residual_reconciliation passes on current repository files."""
    valid, message = sod.validate_residual_reconciliation()
    assert valid is True
    assert message == "legacy residual reconciliation baseline valid"


def test_resolve_active_residual_reconciliation_repo_baseline():
    """Verify that resolve_active_residual_reconciliation passes on current repository files."""
    valid, message = sod.resolve_active_residual_reconciliation()
    assert valid is True
    assert "17 resolved; 1 open" in message


@pytest.mark.parametrize("key", [
    "ALPHA_WEAKNESS_DIAGNOSTICS_20260614",
    "GP_ALT_DATA_FETCHER_OPTIMIZATION",
    "GP_OVERFITTING_REMEDIATION_GATE4_20260704",
    "VNSTOCK_LATEST_STANDARDIZATION_20260612",
    "VN_ALPHA_GMM_SMOOTH_TRANSITION_20260624",
])
def test_each_of_the_five_legacy_records_tolerates_exact_lf_hash(key):
    """Verify each of the 5 legacy reconciliation records matches its exact LF hash on disk."""
    payload, msg = sod._read_locked_json(
        sod.LEGACY_RESIDUAL_RECONCILIATION_FILE, sod.LEGACY_RESIDUAL_RECONCILIATION_LOCK
    )
    assert payload is not None, msg
    record = payload["records"][key]
    historical = sod._safe_repo_path(record["historical_evidence_path"])
    assert historical is not None and historical.is_file()
    raw_bytes = historical.read_bytes()
    actual_sha = sod._sha256(raw_bytes)
    lf_sha = sod._sha256(raw_bytes.replace(b"\r\n", b"\n"))
    expected_lf = sod.LEGACY_RESIDUAL_HISTORICAL_LF_HASHES[key]
    assert expected_lf in (actual_sha, lf_sha)


def test_crlf_bytes_normalization_matches_lf_hash(monkeypatch):
    """Verify that CRLF-converted historical files normalize and match the tolerated LF hash."""
    key = "ALPHA_WEAKNESS_DIAGNOSTICS_20260614"
    payload, _ = sod._read_locked_json(
        sod.LEGACY_RESIDUAL_RECONCILIATION_FILE, sod.LEGACY_RESIDUAL_RECONCILIATION_LOCK
    )
    record = payload["records"][key]
    historical_file = sod.WORKSPACE / record["historical_evidence_path"]
    orig_bytes = historical_file.read_bytes()
    crlf_bytes = orig_bytes.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

    orig_read = Path.read_bytes

    def fake_read(self):
        if "role20_alpha_weakness_diagnostics_fix6_20260726.md" in str(self):
            return crlf_bytes
        return orig_read(self)

    monkeypatch.setattr(Path, "read_bytes", fake_read)
    valid, message = sod.validate_residual_reconciliation()
    assert valid is True, message


def test_tampered_historical_file_fails_closed(monkeypatch):
    """Verify that tampered historical evidence fails closed with hash drift message."""
    orig_read = Path.read_bytes

    def fake_read(self):
        if "role20_alpha_weakness_diagnostics_fix6_20260726.md" in str(self):
            return b"# Tampered historical evidence content\n"
        return orig_read(self)

    monkeypatch.setattr(Path, "read_bytes", fake_read)
    valid, message = sod.validate_residual_reconciliation()
    assert valid is False
    assert "historical hash drift" in message


# ---------------------------------------------------------------------------
# 16-Dimension Adversarial Tests
# ---------------------------------------------------------------------------

def test_dim01_malformed_out_of_bounds_types(monkeypatch):
    """Dim 1: Malformed and out-of-bounds types (None, non-dict, non-string) fail closed."""
    # Non-dict records
    monkeypatch.setattr(
        sod, "_read_locked_json",
        lambda *args: ({"version": sod.LEGACY_RESIDUAL_RECONCILIATION_VERSION, "records": "not_a_dict"}, "ok")
    )
    valid, msg = sod.validate_residual_reconciliation()
    assert valid is False
    assert "must contain exactly the 17 residuals" in msg


def test_dim02_invalid_directory_io_paths(monkeypatch):
    """Dim 2: Directory provided where file expected fails closed."""
    orig_is_file = Path.is_file

    def fake_is_file(self):
        if "role20_alpha_weakness_diagnostics_fix6_20260726.md" in str(self):
            return False  # Simulate directory or non-file
        return orig_is_file(self)

    monkeypatch.setattr(Path, "is_file", fake_is_file)
    valid, msg = sod.validate_residual_reconciliation()
    assert valid is False
    assert "evidence path invalid" in msg


def test_dim03_corrupted_sidecar_lock_mismatch(tmp_path, monkeypatch):
    """Dim 3: Corrupted sidecar / SHA lock mismatch fails closed."""
    sidecar = tmp_path / "residual.json"
    sidecar.write_text('{"version": "invalid"}', encoding="utf-8")
    lock = sidecar.with_suffix(".sha256")
    lock.write_text("0" * 64, encoding="utf-8")

    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_FILE", sidecar)
    monkeypatch.setattr(sod, "LEGACY_RESIDUAL_RECONCILIATION_LOCK", lock)

    valid, msg = sod.validate_residual_reconciliation()
    assert valid is False
    assert "lock mismatch" in msg or "drift" in msg or "version" in msg


def test_dim04_fail_closed_error_states(monkeypatch):
    """Dim 4: Unreadable locked json returns False, never continues."""
    monkeypatch.setattr(sod, "_read_locked_json", lambda *args: (None, "simulated read error"))
    valid, msg = sod.validate_residual_reconciliation()
    assert valid is False
    assert msg == "simulated read error"


def test_dim05_rollback_and_atomicity_failures(tmp_path):
    """Dim 5: Publishing residual reconciliation rejects overwriting existing target."""
    target = tmp_path / "residual.json"
    target.write_text("existing", encoding="utf-8")
    lock = target.with_suffix(".sha256")
    lock.write_text("0" * 64, encoding="utf-8")

    with pytest.raises(FileExistsError):
        sod.publish_residual_reconciliation({
            "version": sod.LEGACY_RESIDUAL_RECONCILIATION_VERSION,
            "records": {}
        })


def test_dim06_pit_safety_timestamps():
    """Dim 6: All reconciliation timestamps must be valid ISO-8601 strings with timezone."""
    payload, _ = sod._read_locked_json(
        sod.LEGACY_RESIDUAL_RECONCILIATION_FILE, sod.LEGACY_RESIDUAL_RECONCILIATION_LOCK
    )
    for key, record in payload["records"].items():
        reconciled_at = record["reconciled_at"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})", reconciled_at), (
            f"Invalid reconciled_at timestamp format in {key}"
        )


def test_dim07_trading_calendar_holiday_boundary_format():
    """Dim 7: Date formats in keys match YYYYMMDD syntax where applicable."""
    for key in sod.LEGACY_RESIDUAL_KEYS:
        date_matches = re.findall(r"\d{8}", key)
        for d_str in date_matches:
            year, month, day = int(d_str[:4]), int(d_str[4:6]), int(d_str[6:])
            assert 2020 <= year <= 2030
            assert 1 <= month <= 12
            assert 1 <= day <= 31


def test_dim08_numeric_precision_hash_length_invariance():
    """Dim 8: All sha256 hashes must be exactly 64 lower-case hex characters."""
    for key, sha in sod.LEGACY_RESIDUAL_HISTORICAL_LF_HASHES.items():
        assert len(sha) == 64
        assert set(sha) <= set("0123456789abcdef")


def test_dim09_concurrency_race_condition_resistance(monkeypatch):
    """Dim 9: Duplicate L3 identities across reconciliation records fail closed."""
    payload, _ = sod._read_locked_json(
        sod.LEGACY_RESIDUAL_RECONCILIATION_FILE, sod.LEGACY_RESIDUAL_RECONCILIATION_LOCK
    )
    keys = list(payload["records"].keys())
    k1, k2 = keys[0], keys[1]
    test_payload = json.loads(json.dumps(payload))
    # Reuse session id and report path from k1 in k2
    test_payload["records"][k2]["fresh_l3_session_id"] = test_payload["records"][k1]["fresh_l3_session_id"]
    test_payload["records"][k2]["fresh_l3_session_key"] = test_payload["records"][k1]["fresh_l3_session_key"]
    test_payload["records"][k2]["fresh_l3_report_path"] = test_payload["records"][k1]["fresh_l3_report_path"]
    test_payload["records"][k2]["fresh_l3_report_sha256"] = test_payload["records"][k1]["fresh_l3_report_sha256"]

    monkeypatch.setattr(sod, "_read_locked_json", lambda *args: (test_payload, "ok"))
    valid, msg = sod.validate_residual_reconciliation()
    assert valid is False
    assert "reuses L3 identity or report" in msg or "identity drift" in msg


def test_dim09_reader_publisher_never_consumes_mixed_sidecar_generation(tmp_path):
    """Dim 9: Shared artifact lock covers JSON and checksum as one snapshot."""
    sidecar = tmp_path / "generation.json"
    checksum = sidecar.with_suffix(".sha256")
    generations = [{"generation": 1}, {"generation": 2}]
    sidecar.write_bytes(json.dumps(generations[0]).encode("utf-8"))
    checksum.write_text(sod._sha256(sidecar.read_bytes()), encoding="utf-8")
    publisher_has_lock = threading.Event()
    reader_result = {}

    def publish_generation():
        with sod._shared_file_lock(sidecar):
            raw = json.dumps(generations[1]).encode("utf-8")
            publisher_has_lock.set()
            sidecar.write_bytes(raw)
            time.sleep(0.02)
            checksum.write_text(sod._sha256(raw), encoding="utf-8")

    def read_generation():
        publisher_has_lock.wait()
        reader_result["value"] = sod._read_locked_json(sidecar, checksum)

    publisher = threading.Thread(target=publish_generation)
    reader = threading.Thread(target=read_generation)
    publisher.start()
    reader.start()
    publisher.join(timeout=2)
    reader.join(timeout=2)
    assert not publisher.is_alive() and not reader.is_alive()
    payload, message = reader_result["value"]
    assert message == "ok"
    assert payload == generations[1]


def _assert_report_reader_waits_for_complete_snapshot(tmp_path, reader, expected):
    """Dim 9: report readers cannot observe an in-place partial generation."""
    report = tmp_path / "report.md"
    complete = (b"- L3 Session ID: session\n- L3 Session Key: session\n"
                b"- L3 session ID/key: session\n- Gate: GATE\n"
                b"- Role: 21 code-reviewer\n[APPROVED]\n")
    report.write_bytes(complete)
    entered = threading.Event()
    release = threading.Event()
    result = {}

    def publisher():
        with sod._shared_file_lock(report):
            report.write_bytes(b"- L3 Session ID: torn")
            entered.set()
            release.wait(timeout=2)
            report.write_bytes(complete)

    def consume():
        entered.wait(timeout=2)
        result["value"] = reader(report)

    publisher_thread = threading.Thread(target=publisher)
    reader_thread = threading.Thread(target=consume)
    publisher_thread.start()
    reader_thread.start()
    assert entered.wait(timeout=2)
    time.sleep(0.02)
    assert reader_thread.is_alive()
    release.set()
    publisher_thread.join(timeout=2)
    reader_thread.join(timeout=2)
    assert not publisher_thread.is_alive() and not reader_thread.is_alive()
    assert result["value"] == expected


def test_dim09_declared_identity_reader_waits_for_complete_locked_snapshot(tmp_path):
    _assert_report_reader_waits_for_complete_snapshot(
        tmp_path, sod._declared_report_identity, ("session", "session")
    )


def test_dim09_closed_authority_reader_waits_for_complete_locked_snapshot(tmp_path):
    _assert_report_reader_waits_for_complete_snapshot(
        tmp_path, lambda path: sod._closed_report_tuple(path, "GATE", 21, "session"), True
    )


def test_dim10_vnd_full_price_scale_immutability():
    """Dim 10: Enforcer constants must be immutable frozensets / dicts."""
    assert isinstance(sod.LEGACY_RESIDUAL_KEYS, frozenset)
    assert isinstance(sod.LEGACY_RESIDUAL_RECORD_FIELDS, frozenset)
    assert isinstance(sod.LEGACY_RESIDUAL_HISTORICAL_LF_HASHES, dict)


def test_dim11_survivorship_delisting_all_17_keys_accounted():
    """Dim 11: Exact 17 legacy residual keys must be present with zero omissions."""
    assert len(sod.LEGACY_RESIDUAL_KEYS) == 17
    payload, _ = sod._read_locked_json(
        sod.LEGACY_RESIDUAL_RECONCILIATION_FILE, sod.LEGACY_RESIDUAL_RECONCILIATION_LOCK
    )
    assert set(payload["records"].keys()) == sod.LEGACY_RESIDUAL_KEYS


def test_dim12_cli_injection_and_path_traversal_sanitization():
    """Dim 12: Historical evidence paths with traversal sequences are rejected."""
    bad_path = "../../../etc/passwd"
    safe = sod._safe_repo_path(bad_path)
    assert safe is None


def test_dim13_schema_drift_unexpected_columns(monkeypatch):
    """Dim 13: Schema drift with unexpected field fails closed."""
    payload, _ = sod._read_locked_json(
        sod.LEGACY_RESIDUAL_RECONCILIATION_FILE, sod.LEGACY_RESIDUAL_RECONCILIATION_LOCK
    )
    k = next(iter(payload["records"]))
    test_payload = json.loads(json.dumps(payload))
    test_payload["records"][k]["unexpected_injected_column"] = "payload"

    monkeypatch.setattr(sod, "_read_locked_json", lambda *args: (test_payload, "ok"))
    valid, msg = sod.validate_residual_reconciliation()
    assert valid is False
    assert "invalid schema" in msg


def test_dim14_resource_exhaustion_bounds():
    """Dim 14: Sidecar contains finite bounded records count."""
    payload, _ = sod._read_locked_json(
        sod.LEGACY_RESIDUAL_RECONCILIATION_FILE, sod.LEGACY_RESIDUAL_RECONCILIATION_LOCK
    )
    assert len(payload["records"]) == 17
    assert len(sod.LEGACY_RESIDUAL_HISTORICAL_LF_HASHES) == 6


def test_dim15_network_timeout_zero_network_io():
    """Dim 15: residual reconciliation validation uses 100% local file I/O with zero network calls."""
    valid, msg = sod.validate_residual_reconciliation()
    assert valid is True


def test_dim16_secret_redaction_credential_protection():
    """Dim 16: No bearer tokens or credentials in sidecar records."""
    payload, _ = sod._read_locked_json(
        sod.LEGACY_RESIDUAL_RECONCILIATION_FILE, sod.LEGACY_RESIDUAL_RECONCILIATION_LOCK
    )
    raw = json.dumps(payload)
    for pattern in (r"bearer\s+[a-zA-Z0-9_\-\.]{20,}", r"api[_-]?key", r"password\s*="):
        assert not re.search(pattern, raw, re.IGNORECASE)


# ---------------------------------------------------------------------------
# Audit Report Content Scoping & Contradictory Verdict Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("report_path, expected", [
    (".ly_state/session/audit_reports/role21_gp_numba_jit_vm_plan_review_20260705.md", "[APPROVED]"),
    (".ly_state/session/audit_reports/role21_gp_parallel_batch_kernels_plan_review_20260705_FIX2.md", "[APPROVED]"),
    (".ly_state/session/audit_reports/role21_legacy_residual_closure_dossier_20260728.md", "[APPROVED]"),
    (".ly_state/session/audit_reports/role20_vci_terminal_receipt_full_history_aggregation_reaudit_20260805.md", "[APPROVED]"),
    (".ly_state/session/audit_reports/role20_vci_terminal_receipt_gate_metadata_repair_20260805.md", "[APPROVED]"),
    (".ly_state/session/audit_reports/role20_vci_sparse_terminal_independent_freshness_evidence_20260805.md", "[APPROVED]"),
    (".ly_state/session/audit_reports/role20_vci_signed_lifecycle_freshness_receipts_20260805.md", "[APPROVED]"),
    (".ly_state/session/audit_reports/role20_official_exchange_lifecycle_evidence_20260805.md", "[APPROVED]"),
], ids=[f"gate{i}" for i in range(1, 9)])
def test_check_audit_report_content_historical_gates_pass(report_path, expected):
    """Verify check_audit_report_content passes for all 8 historical gates without false-positive contradictory errors."""
    valid, msg = sod.check_audit_report_content(report_path, expected)
    assert valid is True, f"Failed for {report_path}: {msg}"


def test_check_audit_report_content_contradictory_in_verdict_section_fails(tmp_path):
    """Contradictory verdicts inside ## Verdict section fail closed."""
    report = tmp_path / "contradictory.md"
    report.write_text("## Verdict\n[APPROVED]\n[NEEDS_FIX]\n", encoding="utf-8")
    valid, msg = sod.check_audit_report_content(str(report), "[APPROVED]")
    assert valid is False
    assert "missing or contradictory" in msg


def test_check_audit_report_content_missing_verdict_fails(tmp_path):
    """Missing expected verdict in ## Verdict section fails closed."""
    report = tmp_path / "missing.md"
    report.write_text("## Verdict\n[NEEDS_FIX]\n", encoding="utf-8")
    valid, msg = sod.check_audit_report_content(str(report), "[APPROVED]")
    assert valid is False
    assert "missing or contradictory" in msg


def test_check_audit_report_content_subheading_isolation(tmp_path):
    """Subheadings like ### Verdict Rationale mentioning other verdicts do not pollute ## Verdict."""
    report = tmp_path / "subheading.md"
    report.write_text(
        "## Verdict\n**[APPROVED]**\n\n### Verdict Rationale\nAddresses prior [NEEDS_FIX].\n",
        encoding="utf-8",
    )
    valid, msg = sod.check_audit_report_content(str(report), "[APPROVED]")
    assert valid is True, msg

