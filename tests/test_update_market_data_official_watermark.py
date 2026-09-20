import json
from datetime import datetime, timezone

import pandas as pd

from scripts import ingest_all_market_data as legacy_ingest
from scripts import update_market_data as updater


def _frame(symbols=("AAA", "BBB"), dates=("2026-07-24", "2026-07-24")):
    index = pd.to_datetime(dates)
    return pd.DataFrame({
        "ticker": symbols, "date": index, "exchange": ["HOSE", "HNX"],
        "open": [10000.0] * 2, "high": [10500.0] * 2, "low": [9500.0] * 2,
        "close": [10000.0] * 2, "volume": [100] * 2, "as_of": ["2026-07-24"] * 2,
        "available_at": [date + pd.Timedelta(days=1) for date in index.tz_localize(updater.VN_TZ)],
        "source": ["vnstock_vci"] * 2, "price_scale": ["VND"] * 2,
        "adjusted": ["backward_adjusted"] * 2, "rebuild_date": ["2026-07-24"] * 2,
    })


def test_legacy_ingest_delegates_exclusively_to_canonical_updater(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(legacy_ingest.update_market_data, "main", lambda argv: calls.append(argv) or 17)

    with __import__("pytest").warns(DeprecationWarning, match="deprecated"):
        result = legacy_ingest.main([
            "aaa", "2026-07-01", "2026-07-24", "--output", str(tmp_path / "AAA.parquet")
        ])

    assert result == 17
    assert calls == [[
        "--symbols", "AAA",
        "--start", "2026-07-01",
        "--end", "2026-07-24",
        "--output", str(tmp_path / "AAA.parquet"),
    ]]


def test_legacy_ingest_contains_no_independent_ingestion_api():
    assert not hasattr(legacy_ingest, "fetch_history")
    assert not hasattr(legacy_ingest, "ingest_symbol")
    assert not hasattr(legacy_ingest, "DirectVCIClient")


def test_exchange_mapping_preserves_canonical_labels():
    assert updater.build_symbol_exchange_map({"hsx": ["AAA"], "hnx": ["BBB"]}) == {"AAA": "HOSE", "BBB": "HNX"}


def test_hnx_only_vci_candidate_is_authoritative(tmp_path, monkeypatch):
    (tmp_path / "universe.json").write_text(json.dumps({"hsx": [], "hnx": ["BBB"]}), encoding="utf-8")
    monkeypatch.setattr(updater, "UNIVERSE_PATH", tmp_path / "universe.json")
    monkeypatch.setattr(updater, "_create_vnstock_client", lambda: object())
    data = _frame(("BBB", "BBB"), ("2026-07-23", "2026-07-24"))
    monkeypatch.setattr(updater, "fetch_symbols", lambda *args, **kwargs: (data, {"fetched": 1, "empty": 0, "errors": 0, "errors_list": [], "rows": 2}))
    monkeypatch.setattr(updater, "_run_reconciliation", lambda *args: {"status": "warning"})
    monkeypatch.setattr(updater, "_load_ticker_lifecycle", lambda: (_ for _ in ()).throw(AssertionError("mutable lifecycle state read")))
    monkeypatch.setattr(updater, "publish_candidate", lambda *args, **kwargs: {"candidate_path": "candidate.parquet", "pointer_path": "pointer.json", "sha256": "a" * 64, "run_id": "release", "vci_authority_receipt_path": "authority.json"})
    result = updater.run_updater(canonical_path=tmp_path / "canonical.parquet", end_date="2026-07-24", skip_refetch=True)
    assert result["status"] == "published"
    assert result["vci_authority"]["terminal_session"] == "2026-07-24"


def test_vci_terminal_rejects_beyond_requested_end():
    ok, errors, _ = updater._vci_terminal_evidence(_frame(), ["AAA", "BBB"], pd.Timestamp("2026-07-23"), None, datetime(2026, 7, 26, tzinfo=timezone.utc))
    assert not ok
    assert "terminal_session: beyond requested end" in errors
