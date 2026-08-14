import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from scripts import update_market_data as updater


@pytest.fixture(autouse=True)
def lifecycle_keyring(monkeypatch, tmp_path):
    monkeypatch.setenv(updater.MARKET_DATA_RECEIPT_ACTIVE_KEY_ID, "lifecycle-test")
    monkeypatch.setenv(
        updater.MARKET_DATA_RECEIPT_KEYRING,
        json.dumps({"lifecycle-test": base64.b64encode(b"x" * 32).decode()}),
    )
    monkeypatch.setenv(
        updater.LIFECYCLE_RECEIPT_KEYRING,
        json.dumps({"lifecycle-authority": {"secret": base64.b64encode(b"y" * 32).decode(), "sources": ["VCI"]}}),
    )
    monkeypatch.setattr(updater, "LIFECYCLE_RECEIPT_LEDGER_DIR", tmp_path / "ledger")


def _lifecycle_evidence(ticker="BBB", status="halted", receipt_id="lifecycle-receipt-0001", expires_at="2026-08-06T00:00:00+00:00", source="VCI", effective_at="2026-08-04T00:00:00+00:00", as_of="2026-08-05T00:00:00+00:00", signed_at="2026-08-05T00:00:00+00:00"):
    payload = {"ticker": ticker, "status": status, "source": source, "reason": "exchange notice", "effective_at": effective_at, "as_of": as_of}
    evidence = {"schema_version": updater.LIFECYCLE_EVIDENCE_SCHEMA_VERSION, "payload": payload, "signed_at": signed_at, "expires_at": expires_at, "receipt_id": receipt_id, "integrity": {"algorithm": updater.LIFECYCLE_EVIDENCE_ALGORITHM, "key_id": "lifecycle-authority", "payload_sha256": updater.sha256_hex(updater._canonical_json(payload))}}
    evidence["integrity"]["signature"] = hmac.new(b"y" * 32, updater._canonical_json(evidence), hashlib.sha256).hexdigest()
    return evidence


def _rows(sessions=("2026-07-24", "2026-07-24")):
    dates = pd.to_datetime(sessions)
    return pd.DataFrame({
        "ticker": ["AAA", "BBB"], "date": dates, "exchange": ["HOSE", "HNX"],
        "open": [10000.0, 10000.0], "high": [10500.0, 10500.0],
        "low": [9500.0, 9500.0], "close": [10000.0, 10000.0], "volume": [100, 100],
        "as_of": ["2026-07-24", "2026-07-24"],
        "available_at": [pd.Timestamp("2026-07-25", tz=updater.VN_TZ)] * 2,
        "source": ["vnstock_vci"] * 2, "price_scale": ["VND"] * 2,
        "adjusted": ["backward_adjusted"] * 2, "rebuild_date": ["2026-07-24"] * 2,
    })


def test_common_vci_terminal_session_is_release_authority():
    ok, errors, report = updater.validate_release_gates(
        _rows(), {}, ["AAA", "BBB"], pd.Timestamp("2026-07-31"), None,
        datetime(2026, 7, 26, tzinfo=timezone.utc),
    )
    assert ok, errors
    assert report["terminal_session"] == "2026-07-24"
    assert report["vci_authority"]["provider"] == "VCI"


def test_stale_unjustified_terminal_blocks_release():
    ok, errors, _ = updater.validate_release_gates(
        _rows(("2026-07-31", "2026-06-15")), {}, ["AAA", "BBB"],
        pd.Timestamp("2026-07-31"), None,
        datetime(2026, 7, 26, tzinfo=timezone.utc),
    )
    assert not ok
    assert "terminal_session: BBB stale 34 sessions: missing independent lifecycle/provider evidence" in errors


def test_future_available_at_blocks_release():
    rows = _rows()
    rows["available_at"] = pd.Timestamp("2026-08-01", tz=updater.VN_TZ)
    ok, errors, _ = updater.validate_release_gates(
        rows, {}, ["AAA", "BBB"], pd.Timestamp("2026-07-31"), None,
        datetime(2026, 7, 26, tzinfo=timezone.utc),
    )
    assert not ok
    assert "provenance: available_at exceeds cutoff" in errors


def test_incremental_terminal_session_wins_over_128_full_history_replacements():
    requested = [f"T{i:03d}" for i in range(703)]
    terminal_rows = pd.concat([_rows(("2026-07-24", "2026-07-24"))] * 352, ignore_index=True).iloc[:703].copy()
    terminal_rows["ticker"] = requested
    rows = terminal_rows.copy()
    rows.loc[:127, "date"] = pd.Timestamp("2026-07-25")
    rows.loc[:127, "as_of"] = "2026-07-25"
    rows.loc[:127, "rebuild_date"] = "2026-07-25"
    rows.loc[:127, "available_at"] = pd.Timestamp("2026-07-26", tz=updater.VN_TZ)
    full_symbols = requested[:128]
    full_stats = {
        "details": [{"symbol": symbol, "status": "success"} for symbol in full_symbols],
    }

    ok, errors, report = updater.validate_release_gates(
        rows, {"fetched": 703, "empty": 0, "errors": 0, "errors_list": []},
        requested, pd.Timestamp("2026-07-31"), None,
        datetime(2026, 7, 26, tzinfo=timezone.utc), full_stats, terminal_rows,
    )

    assert ok, errors
    assert report["terminal_session"] == "2026-07-24"


def test_sparse_575_128_terminal_shape_blocks_on_canonical_equality_alone():
    requested = [f"T{i:03d}" for i in range(703)]
    rows = pd.concat([_rows()] * 352, ignore_index=True).iloc[:703].copy()
    rows["ticker"] = requested
    rows["date"] = pd.Timestamp("2026-07-31")
    rows["available_at"] = pd.Timestamp("2026-08-01", tz=updater.VN_TZ)
    sparse = requested[:128]
    sparse_dates = pd.Series(pd.Timestamp("2025-02-21"), index=range(128))
    rows.loc[:127, "date"] = sparse_dates
    rows.loc[:127, "available_at"] = pd.Timestamp("2025-02-22", tz=updater.VN_TZ)
    canonical_terminals = {ticker: rows.loc[index, "date"] for index, ticker in enumerate(sparse)}

    ok, errors, report = updater.validate_release_gates(
        rows, {"fetched": 703, "empty": 0, "errors": 0, "errors_list": []}, requested,
        pd.Timestamp("2026-07-31"), None, datetime(2026, 8, 5, tzinfo=timezone.utc),
        canonical_terminals=canonical_terminals,
    )

    assert not ok
    assert report["terminal_session"] == "2026-07-31"
    assert all("missing independent lifecycle/provider evidence" in error for error in errors)


def test_sparse_terminal_accepts_current_halted_lifecycle_evidence():
    rows = pd.concat([_rows(), _rows().iloc[[0]]], ignore_index=True)
    rows["ticker"] = ["AAA", "BBB", "CCC"]
    rows["date"] = [pd.Timestamp("2026-07-31"), pd.Timestamp("2025-02-21"), pd.Timestamp("2026-07-31")]
    rows["available_at"] = [
        pd.Timestamp("2026-08-01", tz=updater.VN_TZ),
        pd.Timestamp("2025-02-22", tz=updater.VN_TZ),
        pd.Timestamp("2026-08-01", tz=updater.VN_TZ),
    ]
    evidence = {
        "BBB": _lifecycle_evidence(),
    }
    ok, errors, report = updater.validate_release_gates(
        rows, {}, ["AAA", "BBB", "CCC"], pd.Timestamp("2026-07-31"), None,
        datetime(2026, 8, 5, tzinfo=timezone.utc), sparse_terminal_evidence=evidence,
    )
    assert ok, errors
    assert report["vci_authority"]["sparse_terminal_exceptions"] == {
        "BBB": "independent_lifecycle_or_provider_evidence"
    }


def test_sparse_terminal_rejects_forged_old_or_missing_evidence():
    rows = _rows(("2026-07-31", "2025-02-21"))
    cases = (
        {"BBB": {"ticker": "BBB", "status": "halted", "source": "forged", "as_of": "2026-08-05T00:00:00+07:00", "reason": "notice"}},
        {"BBB": _lifecycle_evidence(expires_at="2026-08-04T00:00:00+00:00")},
        {},
    )
    for evidence in cases:
        ok, errors, _ = updater.validate_release_gates(
            rows, {}, ["AAA", "BBB"], pd.Timestamp("2026-07-31"), None,
            datetime(2026, 8, 5, tzinfo=timezone.utc), sparse_terminal_evidence=evidence,
        )
        assert not ok
        assert any(error.startswith("terminal_session: BBB stale") for error in errors)


def test_sparse_terminal_rejects_tampered_payload_and_unknown_key():
    rows = _rows(("2026-07-31", "2025-02-21"))
    tampered = _lifecycle_evidence()
    tampered["payload"]["status"] = "delisted"
    unknown_key = _lifecycle_evidence()
    unknown_key["integrity"]["key_id"] = "retired-key"
    for evidence in ({"BBB": tampered}, {"BBB": unknown_key}):
        ok, errors, _ = updater.validate_release_gates(
            rows, {}, ["AAA", "BBB"], pd.Timestamp("2026-07-31"), None,
            datetime(2026, 8, 5, tzinfo=timezone.utc), sparse_terminal_evidence=evidence,
        )
        assert not ok
        assert any("evidence signature invalid" in error for error in errors)


def test_lifecycle_loader_rejects_unsigned_repository_json(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text(json.dumps({"tickers": {"BBB": {"ticker": "BBB", "status": "halted"}}}), encoding="utf-8")
    assert updater._load_ticker_lifecycle(path) == {}


def test_sparse_terminal_rejects_future_signed_evidence():
    rows = _rows(("2026-07-31", "2025-02-21"))
    future = _lifecycle_evidence(receipt_id="lifecycle-receipt-future", expires_at="2026-08-07T00:00:00+00:00", effective_at="2026-08-06T00:00:00+00:00", as_of="2026-08-06T00:00:00+00:00")
    ok, errors, _ = updater.validate_release_gates(
        rows, {}, ["AAA", "BBB"], pd.Timestamp("2026-07-31"), None,
        datetime(2026, 8, 5, tzinfo=timezone.utc), sparse_terminal_evidence={"BBB": future},
    )
    assert not ok
    assert any("evidence timestamp ordering invalid" in error for error in errors)


def test_lifecycle_receipt_replay_persists_across_calls(tmp_path):
    evidence = _lifecycle_evidence()
    args = ("BBB", pd.Timestamp("2025-02-21"), pd.Timestamp("2026-07-31"), datetime(2026, 8, 5, tzinfo=timezone.utc), evidence)
    assert updater._sparse_terminal_evidence_error(*args, set(), tmp_path) is None
    assert updater._sparse_terminal_evidence_error(*args, set(), tmp_path) == "evidence receipt replayed"


def test_lifecycle_receipt_ledger_tamper_blocks_claim(tmp_path):
    evidence = _lifecycle_evidence()
    args = ("BBB", pd.Timestamp("2025-02-21"), pd.Timestamp("2026-07-31"), datetime(2026, 8, 5, tzinfo=timezone.utc), evidence)
    assert updater._sparse_terminal_evidence_error(*args, set(), tmp_path) is None
    (tmp_path / f"{evidence['receipt_id']}.json").write_text("{}", encoding="utf-8")
    assert updater._sparse_terminal_evidence_error(*args, set(), tmp_path) == "receipt ledger integrity invalid"


@pytest.mark.parametrize(("kwargs", "expected"), [({"signed_at": "2026-08-06T00:00:00+00:00"}, "evidence timestamp ordering invalid"), ({"expires_at": "2026-08-05T00:00:00+00:00"}, "evidence timestamp ordering invalid"), ({"effective_at": "2026-08-01T00:00:00+00:00", "as_of": "2026-08-02T00:00:00+00:00", "signed_at": "2026-08-03T00:00:00+00:00"}, "evidence signing age exceeds maximum")])
def test_lifecycle_receipt_rejects_invalid_timestamp_order(kwargs, expected, tmp_path):
    evidence = _lifecycle_evidence(receipt_id="lifecycle-order-violation-0001", **kwargs)
    assert updater._sparse_terminal_evidence_error("BBB", pd.Timestamp("2025-02-21"), pd.Timestamp("2026-07-31"), datetime(2026, 8, 5, tzinfo=timezone.utc), evidence, set(), tmp_path) == expected


def test_lifecycle_receipt_rejects_market_key_and_wrong_source(tmp_path):
    evidence = _lifecycle_evidence(receipt_id="lifecycle-wrong-source-0001", source="repository_ticker_lifecycle")
    assert updater._sparse_terminal_evidence_error("BBB", pd.Timestamp("2025-02-21"), pd.Timestamp("2026-07-31"), datetime(2026, 8, 5, tzinfo=timezone.utc), evidence, set(), tmp_path) == "evidence signature invalid"
    evidence = _lifecycle_evidence(receipt_id="lifecycle-market-key-use-0001")
    evidence["integrity"]["key_id"] = "lifecycle-test"
    assert updater._sparse_terminal_evidence_error("BBB", pd.Timestamp("2025-02-21"), pd.Timestamp("2026-07-31"), datetime(2026, 8, 5, tzinfo=timezone.utc), evidence, set(), tmp_path) == "evidence signature invalid"


@pytest.mark.parametrize("status", ["halted", "suspended", "delisted"])
def test_sparse_terminal_accepts_valid_signed_terminal_status(status):
    rows = pd.concat([_rows(), _rows().iloc[[0]]], ignore_index=True)
    rows["ticker"] = ["AAA", "BBB", "CCC"]
    rows["date"] = [pd.Timestamp("2026-07-31"), pd.Timestamp("2025-02-21"), pd.Timestamp("2026-07-31")]
    rows.loc[1, "available_at"] = pd.Timestamp("2025-02-22", tz=updater.VN_TZ)
    rows["date"] = [pd.Timestamp("2026-07-31"), pd.Timestamp("2025-02-21"), pd.Timestamp("2026-07-31")]
    rows["available_at"] = [pd.Timestamp("2026-08-01", tz=updater.VN_TZ), pd.Timestamp("2025-02-22", tz=updater.VN_TZ), pd.Timestamp("2026-08-01", tz=updater.VN_TZ)]
    ok, errors, _ = updater.validate_release_gates(
        rows, {}, ["AAA", "BBB", "CCC"], pd.Timestamp("2026-07-31"), None,
        datetime(2026, 8, 5, tzinfo=timezone.utc),
        sparse_terminal_evidence={"BBB": _lifecycle_evidence(status=status)},
    )
    assert ok, errors


def test_sparse_terminal_rejects_replayed_lifecycle_receipt():
    rows = pd.concat([_rows()] * 3, ignore_index=True).iloc[:5].copy()
    rows["ticker"] = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    rows["date"] = [pd.Timestamp("2026-07-31"), pd.Timestamp("2025-02-21"), pd.Timestamp("2025-02-21"), pd.Timestamp("2026-07-31"), pd.Timestamp("2026-07-31")]
    rows["available_at"] = [pd.Timestamp("2026-08-01", tz=updater.VN_TZ), pd.Timestamp("2025-02-22", tz=updater.VN_TZ), pd.Timestamp("2025-02-22", tz=updater.VN_TZ), pd.Timestamp("2026-08-01", tz=updater.VN_TZ), pd.Timestamp("2026-08-01", tz=updater.VN_TZ)]
    ok, errors, _ = updater.validate_release_gates(
        rows, {}, ["AAA", "BBB", "CCC", "DDD", "EEE"], pd.Timestamp("2026-07-31"), None,
        datetime(2026, 8, 5, tzinfo=timezone.utc),
        sparse_terminal_evidence={
            "BBB": _lifecycle_evidence(receipt_id="lifecycle-receipt-replay"),
            "CCC": _lifecycle_evidence(ticker="CCC", receipt_id="lifecycle-receipt-replay"),
        },
    )
    assert not ok
    assert any("CCC stale" in error and "evidence receipt replayed" in error for error in errors)


def test_release_gate_replay_uses_supplied_durable_ledger(tmp_path):
    rows = pd.concat([_rows(("2026-07-31", "2025-02-21")), _rows().iloc[[0]]], ignore_index=True)
    rows["ticker"] = ["AAA", "BBB", "CCC"]
    rows["date"] = pd.Timestamp("2026-07-31")
    rows.loc[1, "date"] = pd.Timestamp("2025-02-21")
    rows.loc[1, "available_at"] = pd.Timestamp("2025-02-22", tz=updater.VN_TZ)
    evidence = {"BBB": _lifecycle_evidence()}
    args = (rows, {}, ["AAA", "BBB", "CCC"], pd.Timestamp("2026-07-31"), None, datetime(2026, 8, 5, tzinfo=timezone.utc))
    ok, errors, _ = updater.validate_release_gates(*args, sparse_terminal_evidence=evidence, lifecycle_receipt_ledger_dir=tmp_path)
    assert ok, errors
    ok, errors, _ = updater.validate_release_gates(*args, sparse_terminal_evidence=evidence, lifecycle_receipt_ledger_dir=tmp_path)
    assert not ok
    assert any("evidence receipt replayed" in error for error in errors)


def test_downstream_release_failure_does_not_consume_lifecycle_receipt(tmp_path):
    rows = pd.concat([_rows(("2026-07-31", "2025-02-21")), _rows().iloc[[0]]], ignore_index=True)
    rows["ticker"] = ["AAA", "BBB", "CCC"]
    rows["date"] = pd.Timestamp("2026-07-31")
    rows.loc[1, "date"] = pd.Timestamp("2025-02-21")
    rows.loc[1, "available_at"] = pd.Timestamp("2025-02-22", tz=updater.VN_TZ)
    ok, errors, _ = updater.validate_release_gates(
        rows, {"errors": 1, "errors_list": [{"symbol": "AAA", "error": "VCI timeout"}]},
        ["AAA", "BBB", "CCC"], pd.Timestamp("2026-07-31"), None,
        datetime(2026, 8, 5, tzinfo=timezone.utc),
        sparse_terminal_evidence={"BBB": _lifecycle_evidence()},
        lifecycle_receipt_ledger_dir=tmp_path,
    )
    assert not ok
    assert errors[0].startswith("source errors:")
    assert not list(tmp_path.glob("*.json"))
    ok, errors, _ = updater.validate_release_gates(
        rows, {}, ["AAA", "BBB", "CCC"], pd.Timestamp("2026-07-31"), None,
        datetime(2026, 8, 5, tzinfo=timezone.utc),
        sparse_terminal_evidence={"BBB": _lifecycle_evidence()},
        lifecycle_receipt_ledger_dir=tmp_path,
    )
    assert ok, errors
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_dry_run_validation_does_not_consume_lifecycle_receipt(tmp_path):
    rows = pd.concat([_rows(("2026-07-31", "2025-02-21")), _rows().iloc[[0]]], ignore_index=True)
    rows["ticker"] = ["AAA", "BBB", "CCC"]
    rows["date"] = pd.Timestamp("2026-07-31")
    rows.loc[1, "date"] = pd.Timestamp("2025-02-21")
    rows.loc[1, "available_at"] = pd.Timestamp("2026-02-22", tz=updater.VN_TZ)
    args = (rows, {}, ["AAA", "BBB", "CCC"], pd.Timestamp("2026-07-31"), None, datetime(2026, 8, 5, tzinfo=timezone.utc))
    evidence = {"BBB": _lifecycle_evidence()}

    ok, errors, _ = updater.validate_release_gates(
        *args, sparse_terminal_evidence=evidence, lifecycle_receipt_ledger_dir=tmp_path,
        claim_receipts=False,
    )

    assert ok, errors
    assert not list(tmp_path.glob("*.json"))
    ok, errors, _ = updater.validate_release_gates(
        *args, sparse_terminal_evidence=evidence, lifecycle_receipt_ledger_dir=tmp_path,
    )
    assert ok, errors
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_terminal_regression_blocks_release():
    rows = _rows(("2026-07-31", "2026-07-24"))
    ok, errors, _ = updater.validate_release_gates(
        rows, {}, ["AAA", "BBB"], pd.Timestamp("2026-07-31"), None,
        datetime(2026, 8, 5, tzinfo=timezone.utc),
        canonical_terminals={"BBB": pd.Timestamp("2026-07-25")},
    )

    assert not ok
    assert "terminal_session: BBB regressed below canonical terminal" in errors


def test_updater_uses_incremental_terminal_for_703_with_128_full_history_replacements(tmp_path):
    requested = [f"T{i:03d}" for i in range(703)]
    incremental = pd.concat([_rows()] * 352, ignore_index=True).iloc[:703].copy()
    incremental["ticker"] = requested
    full_symbols = requested[:128]
    full_history = incremental.iloc[:128].copy()
    full_history["date"] = pd.Timestamp("2026-07-20")
    full_history["as_of"] = "2026-07-20"
    full_history["rebuild_date"] = "2026-07-20"
    full_history["available_at"] = pd.Timestamp("2026-07-21", tz=updater.VN_TZ)
    anomalies = [
        {
            "symbol": symbol,
            "exchange": "HOSE",
            "classification": "PRICE_JUMP",
            "date": "2026-07-24",
            "diff_pct": 1.0,
            "overlap_rows": 1,
            "mismatch_rows": 1,
        }
        for symbol in full_symbols
    ]
    full_stats = {"details": [{"symbol": symbol, "status": "success"} for symbol in full_symbols]}

    with patch.object(updater, "load_universe_from_json", return_value={"hsx": requested, "hnx": []}), \
         patch.object(updater, "_create_vnstock_client", return_value=MagicMock()), \
         patch.object(updater, "fetch_symbols", return_value=(incremental, {"fetched": 703, "empty": 0, "errors": 0, "rows": 703, "total_symbols": 703, "errors_list": [], "empty_tickers": []})), \
         patch.object(updater, "read_canonical", return_value=pd.DataFrame()), \
         patch.object(updater, "detect_price_anomalies", return_value=anomalies), \
         patch.object(updater, "run_full_history_refetch", return_value=(full_history, full_stats)), \
         patch.object(updater, "validate_dataframe", return_value=(True, [])), \
         patch.object(updater, "_run_reconciliation", return_value={"status": "ok"}), \
         patch.object(updater, "publish_candidate", return_value={"candidate_path": "candidate", "pointer_path": "pointer", "sha256": "sha", "vci_authority_receipt_path": "receipt"}):
        result = updater.run_updater(
            canonical_path=tmp_path / "canonical.parquet",
            output_path=tmp_path / "candidate.parquet",
            start_date="2026-07-20",
            end_date="2026-07-31",
        )

    assert result["status"] == "published"
    assert result["vci_authority"]["terminal_session"] == "2026-07-24"


def test_updater_passes_loaded_lifecycle_evidence_to_release_gates(tmp_path):
    rows = _rows()
    evidence = {"BBB": _lifecycle_evidence()}
    with patch.object(updater, "load_universe_from_json", return_value={"hsx": ["AAA"], "hnx": ["BBB"]}), \
         patch.object(updater, "_create_vnstock_client", return_value=MagicMock()), \
         patch.object(updater, "fetch_symbols", return_value=(rows, {"fetched": 2, "empty": 0, "errors": 0, "rows": 2, "total_symbols": 2, "errors_list": [], "empty_tickers": []})), \
         patch.object(updater, "validate_dataframe", return_value=(True, [])), \
         patch.object(updater, "_load_ticker_lifecycle", return_value=evidence), \
         patch.object(updater, "validate_release_gates", return_value=(False, ["blocked"], {"rejected_rows": 0})) as validate_gates:
        result = updater.run_updater(
            canonical_path=tmp_path / "canonical.parquet", output_path=tmp_path / "candidate.parquet",
            start_date="2026-07-20", end_date="2026-07-31", skip_refetch=True,
        )

    assert result["status"] == "gates_failed"
    assert validate_gates.call_args.kwargs["sparse_terminal_evidence"] == {}


@pytest.mark.parametrize(
    ("claim_error",),
    [("lifecycle receipt claim failed",), ("evidence receipt replayed",)],
    ids=["claim-failure", "replay"],
)
def test_updater_claim_failure_preserves_prior_pointer_and_quarantines_stage(tmp_path, claim_error):
    rows = _rows()
    pointer_path = tmp_path / "market_current.json"
    prior_pointer = b'{"run_id":"prior","candidate":"prior.parquet","sha256":"prior","generation":1}'
    pointer_path.write_bytes(prior_pointer)
    authority = {
        "validation_outcome": "passed",
        "terminal_session": "2026-07-24",
        "cutoff_at": "2026-08-05T00:00:00+00:00",
        "sparse_terminal_exceptions": {"BBB": "independent_lifecycle_or_provider_evidence"},
    }
    gate_report = {"rejected_rows": 0, "vci_authority": authority, "gates": {"terminal_coverage": True}}

    with patch.object(updater, "load_universe_from_json", return_value={"hsx": ["AAA"], "hnx": ["BBB"]}), \
         patch.object(updater, "_create_vnstock_client", return_value=MagicMock()), \
         patch.object(updater, "fetch_symbols", return_value=(rows, {"fetched": 2, "empty": 0, "errors": 0, "rows": 2, "total_symbols": 2, "errors_list": [], "empty_tickers": []})), \
         patch.object(updater, "validate_dataframe", return_value=(True, [])), \
         patch.object(updater, "validate_release_gates", return_value=(True, [], gate_report)), \
         patch.object(updater, "_run_reconciliation", return_value={"status": "ok"}), \
         patch.object(updater, "_claim_sparse_terminal_receipts", return_value=[claim_error]):
        with pytest.raises(RuntimeError, match=claim_error):
            updater.run_updater(
                canonical_path=tmp_path / "canonical.parquet",
                start_date="2026-07-20",
                end_date="2026-07-31",
                skip_refetch=True,
            )

    assert pointer_path.read_bytes() == prior_pointer
    quarantines = list((tmp_path / "market_releases").glob("*/quarantine.json"))
    assert len(quarantines) == 1


def test_publication_failure_rolls_back_lifecycle_receipt_claim(tmp_path, monkeypatch):
    pointer_path = tmp_path / "market_current.json"
    pointer_path.write_text('{"run_id":"prior","generation":1}', encoding="utf-8")
    evidence = _lifecycle_evidence()
    authority = {
        "validation_outcome": "passed",
        "terminal_session": "2026-07-24",
        "cutoff_at": "2026-08-05T00:00:00+00:00",
        "sparse_terminal_exceptions": {"BBB": "independent_lifecycle_or_provider_evidence"},
    }
    original_replace = Path.replace

    def fail_pointer_swap(path, target):
        if Path(target) == pointer_path:
            raise OSError("pointer swap failed")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_pointer_swap)
    with pytest.raises(OSError, match="pointer swap failed"):
        updater.publish_candidate(
            _rows(),
            tmp_path / "canonical.parquet",
            release_root=tmp_path / "market_releases",
            pointer_path=pointer_path,
            vci_authority=authority,
            sparse_terminal_evidence={"BBB": evidence},
            lifecycle_receipt_ledger_dir=tmp_path / "ledger",
        )

    assert not list((tmp_path / "ledger").glob("*.json"))


def test_publication_rollback_restores_pointer_when_receipt_release_fails(tmp_path, monkeypatch):
    pointer_path = tmp_path / "market_current.json"
    prior_pointer = b'{"run_id":"prior","generation":1}'
    pointer_path.write_bytes(prior_pointer)
    authority = {
        "validation_outcome": "passed",
        "terminal_session": "2026-07-24",
        "cutoff_at": "2026-08-05T00:00:00+00:00",
        "sparse_terminal_exceptions": {"BBB": "independent_lifecycle_or_provider_evidence"},
    }
    monkeypatch.setattr(updater, "_release_lifecycle_receipt_claims", lambda *args: (_ for _ in ()).throw(RuntimeError("receipt release failed")))
    monkeypatch.setattr(updater, "prune_releases", lambda *args: (_ for _ in ()).throw(OSError("post-publish failure")))

    with pytest.raises(ExceptionGroup) as exc_info:
        updater.publish_candidate(
            _rows(), tmp_path / "canonical.parquet", release_root=tmp_path / "market_releases",
            pointer_path=pointer_path, vci_authority=authority,
            sparse_terminal_evidence={"BBB": _lifecycle_evidence()}, lifecycle_receipt_ledger_dir=tmp_path / "ledger",
        )

    assert pointer_path.read_bytes() == prior_pointer
    assert {str(error) for error in exc_info.value.exceptions} == {"post-publish failure", "receipt release failed"}


def test_ledger_claim_verification_failure_preserves_pointer_quarantines_stage_and_allows_retry(tmp_path, monkeypatch):
    pointer_path = tmp_path / "market_current.json"
    prior_pointer = b'{"run_id":"prior","generation":1}'
    pointer_path.write_bytes(prior_pointer)
    ledger_dir = tmp_path / "ledger"
    evidence = _lifecycle_evidence()
    authority = {
        "validation_outcome": "passed",
        "terminal_session": "2026-07-24",
        "cutoff_at": "2026-08-05T00:00:00+00:00",
        "sparse_terminal_exceptions": {"BBB": "independent_lifecycle_or_provider_evidence"},
    }
    original_fsync_directory = updater._fsync_directory
    failed = False

    def fail_first_ledger_sync(path):
        nonlocal failed
        if path == ledger_dir and not failed:
            failed = True
            raise OSError("ledger sync failed")
        original_fsync_directory(path)

    monkeypatch.setattr(updater, "_fsync_directory", fail_first_ledger_sync)
    with pytest.raises(RuntimeError, match="lifecycle receipt claim failed"):
        updater.publish_candidate(
            _rows(), tmp_path / "canonical.parquet", release_root=tmp_path / "market_releases",
            pointer_path=pointer_path, vci_authority=authority,
            sparse_terminal_evidence={"BBB": evidence}, lifecycle_receipt_ledger_dir=ledger_dir,
        )

    assert pointer_path.read_bytes() == prior_pointer
    assert len(list((tmp_path / "market_releases").glob("*/quarantine.json"))) == 1
    assert not (ledger_dir / f"{evidence['receipt_id']}.json").exists()
    assert updater._claim_lifecycle_receipt(evidence, evidence["payload"], ledger_dir) is None


def test_missing_full_history_ticker_blocks_release():
    requested = ["AAA", "BBB"]
    full_stats = {"details": [{"symbol": "BBB", "status": "failed", "reason": "empty"}]}

    ok, errors, _ = updater.validate_release_gates(
        _rows(), {"fetched": 2, "empty": 0, "errors": 0, "errors_list": []},
        requested, pd.Timestamp("2026-07-31"), None,
        datetime(2026, 7, 26, tzinfo=timezone.utc), full_stats,
    )

    assert not ok
    assert "coverage: full-history refetch ticker missing or failed" in errors


def test_equivalent_overlap_keeps_normalized_canonical_row():
    existing = _rows().iloc[[0]].copy()
    existing["as_of"] = "legacy"
    existing["rebuild_date"] = "legacy"
    existing["available_at"] = pd.Timestamp("2026-07-25")
    new_data = _rows().iloc[[0]].copy()
    merged, errors = updater.merge_canonical_and_new(existing, new_data)
    assert not errors
    assert len(merged) == 1
    assert merged.loc[0, "as_of"] == "legacy"
    assert merged.loc[0, "available_at"] == pd.Timestamp("2026-07-25", tz=updater.VN_TZ)


def test_conflicting_overlap_blocks_merge_before_publication():
    existing = _rows().iloc[[0]].copy()
    new_data = _rows().iloc[[0]].copy()
    new_data["close"] = 10001.0
    merged, errors = updater.merge_canonical_and_new(existing, new_data)
    assert len(merged) == 2
    assert errors == ["overlap conflict: AAA 2026-07-24"]


def test_runtime_scale_equivalent_overlaps_normalize_both_inputs_without_duplicates():
    count = 13_039
    dates = pd.date_range("2026-01-01", periods=count, freq="D")
    existing = pd.concat([_rows().iloc[[0]]] * count, ignore_index=True)
    existing["date"] = dates
    existing["available_at"] = dates + pd.Timedelta(days=1)
    new_data = existing.copy()
    new_data["available_at"] = (dates + pd.Timedelta(days=1)).tz_localize(updater.VN_TZ)

    merged, errors = updater.merge_canonical_and_new(existing, new_data)

    assert not errors
    assert len(merged) == count
    assert isinstance(merged["available_at"].dtype, pd.DatetimeTZDtype)
    valid, validation_errors = updater.validate_dataframe(merged, "runtime_scale")
    assert valid, validation_errors
