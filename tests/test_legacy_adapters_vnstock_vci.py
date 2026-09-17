import ast
import os
from pathlib import Path

import pandas as pd
import pytest

from omega.data.vnstock_vci import VnstockVCIDataSource


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "archive/legacy_adapters/vnstock_vci.py"


def test_archive_is_complete_and_compiles():
    source = ARCHIVE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))}
    assert {"RateLimiter", "VnstockVCIDataSource", "_price_worker", "_stop_price_process"} <= names
    compile(source, str(ARCHIVE), "exec")


def test_active_adapter_has_no_vnstock_import():
    source = (ROOT / "src/omega/data/vnstock_vci.py").read_text(encoding="utf-8")
    assert "from vnstock" not in source


@pytest.mark.parametrize("method", ["fetch_price_data", "fetch_price_data_with_reconciliation", "get_ohlcv"])
def test_active_adapter_fails_closed(method):
    with pytest.raises(ImportError, match="has been archived"):
        getattr(VnstockVCIDataSource(), method)("VCB", "2026-01-01", "2026-01-02")


@pytest.mark.parametrize("value, expected", [(50, 50000), (50000, 50000), (None, 0), (float("nan"), 0), ("bad", 0)])
def test_pure_price_normalization_is_safe(value, expected):
    assert VnstockVCIDataSource()._normalize_price_vnd(value) == expected


def test_loader_uses_direct_vci(monkeypatch, tmp_path):
    from omega.data.loader import DataLoader

    frame = pd.DataFrame({"ticker": ["VCB"], "time": [pd.Timestamp("2026-01-02", tz="UTC")], "open": [50000], "high": [51000], "low": [49000], "close": [50500], "volume": [100]})
    loader = DataLoader(cache_dir=tmp_path)
    monkeypatch.setattr(loader.vci_client, "fetch_history", lambda *args, **kwargs: frame.copy())
    result = loader._fetch_from_source("VCB", "2026-01-01", "2026-01-02", pd.Timestamp("2026-01-03", tz="UTC"), source="vci")
    assert list(result.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]


def _load_archived_vci():
    import importlib.util

    spec = importlib.util.spec_from_file_location("archived_vnstock_vci", ARCHIVE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── F-001: DirectVCI Routing (No retired vnstock.Market bypass) ───────────────


def test_f001_direct_vci_routing(monkeypatch, tmp_path):
    """F-001: load_market_data must route through DirectVCIClient and never invoke retired vnstock.Market."""
    import sys
    from omega.data.loader import DataLoader

    called = {"vci": 0}
    sample_df = pd.DataFrame({
        "ticker": ["VCB"],
        "date": [pd.Timestamp("2026-01-02", tz="UTC")],
        "open": [50000.0],
        "high": [51000.0],
        "low": [49000.0],
        "close": [50500.0],
        "volume": [100.0],
        "as_of": [pd.Timestamp("2026-01-02", tz="UTC")],
        "available_at": [pd.Timestamp("2026-01-05 02:00:00", tz="UTC")],
    })

    loader = DataLoader(cache_dir=tmp_path)
    monkeypatch.setattr(
        loader.vci_client,
        "fetch_history",
        lambda *a, **k: (called.__setitem__("vci", called["vci"] + 1) or sample_df.copy()),
    )

    if "vnstock" in sys.modules:
        m = sys.modules["vnstock"]
        if hasattr(m, "Market"):
            monkeypatch.setattr(
                m,
                "Market",
                lambda *a, **k: (_ for _ in ()).throw(AssertionError("Retired vnstock.Market bypass invoked")),
            )

    result = loader.load_market_data(
        start_date=pd.Timestamp("2026-01-01", tz="UTC"),
        end_date=pd.Timestamp("2026-01-02", tz="UTC"),
        as_of_time=pd.Timestamp("2026-01-06", tz="UTC"),
        tickers=["VCB"],
    )
    assert called["vci"] == 1
    assert not result.empty


# ── F-002: Fail-Closed Fetch / PIT / Calendar Errors ─────────────────────────


def test_f002_fail_closed_fetch_pit_calendar(monkeypatch, tmp_path):
    """F-002: load_market_data must raise and fail closed on upstream fetch, PIT, or calendar errors."""
    from omega.data.loader import DataLoader

    loader = DataLoader(cache_dir=tmp_path)

    def fail_fetch(*args, **kwargs):
        raise RuntimeError("DirectVCI upstream failure")

    monkeypatch.setattr(loader.vci_client, "fetch_history", fail_fetch)

    with pytest.raises(RuntimeError, match="DirectVCI upstream failure"):
        loader.load_market_data(
            start_date=pd.Timestamp("2026-01-01", tz="UTC"),
            end_date=pd.Timestamp("2026-01-02", tz="UTC"),
            as_of_time=pd.Timestamp("2026-01-04", tz="UTC"),
            tickers=["VCB"],
        )


# ── F-003: Ticker Path Traversal Validation ──────────────────────────────────


@pytest.mark.parametrize(
    "bad_ticker",
    [
        "../../etc/passwd",
        "..\\..\\windows\\system32",
        "../secret",
        "VCB/../../sub",
        "",
        "   ",
    ],
)
def test_f003_ticker_traversal_rejected(tmp_path, bad_ticker):
    """F-003: Ticker path traversal or blank ticker must fail closed with ValueError."""
    from omega.data.loader import DataLoader

    loader = DataLoader(cache_dir=tmp_path)
    with pytest.raises(ValueError):
        loader.load_market_data(
            start_date=pd.Timestamp("2026-01-01", tz="UTC"),
            end_date=pd.Timestamp("2026-01-02", tz="UTC"),
            as_of_time=pd.Timestamp("2026-01-04", tz="UTC"),
            tickers=[bad_ticker],
        )

    with pytest.raises(ValueError):
        loader.clear_cache(ticker=bad_ticker)


# ── F-004: Selective Cache + Sidecars Clear ──────────────────────────────────


def test_f004_selective_cache_and_sidecars(tmp_path):
    """F-004: clear_cache(ticker) must selectively delete only the target ticker's parquet and sidecars."""
    from omega.data.loader import DataLoader

    loader = DataLoader(cache_dir=tmp_path)
    vcb_p = tmp_path / "VCB.parquet"
    vcb_m = tmp_path / "VCB.metadata.json"
    tcb_p = tmp_path / "TCB.parquet"
    tcb_m = tmp_path / "TCB.metadata.json"

    for p in (vcb_p, vcb_m, tcb_p, tcb_m):
        p.write_text("test", encoding="utf-8")

    deleted = loader.clear_cache(ticker="VCB")
    assert not vcb_p.exists(), "Target ticker parquet was not deleted"
    assert not vcb_m.exists(), "Target ticker metadata sidecar was not deleted"
    assert tcb_p.exists(), "Unrelated ticker parquet was destructively deleted"
    assert tcb_m.exists(), "Unrelated ticker metadata sidecar was destructively deleted"

    loader.clear_cache(ticker=None)
    assert not tcb_p.exists()
    assert not tcb_m.exists()


# ── F-005: Atomic Metadata Sidecar Write ─────────────────────────────────────


def test_f005_atomic_metadata(monkeypatch, tmp_path):
    """F-005: _save_metadata_sidecar must write atomically via temporary file and replace."""
    import json
    from datetime import datetime, timezone
    from omega.data.loader import DataLoader

    loader = DataLoader(cache_dir=tmp_path)
    parquet_path = tmp_path / "VCB.parquet"
    parquet_path.write_bytes(b"dummy")
    metadata_path = tmp_path / "VCB.metadata.json"
    initial_data = {"status": "unmodified"}
    metadata_path.write_text(json.dumps(initial_data), encoding="utf-8")

    df = pd.DataFrame({"date": [pd.Timestamp("2026-01-02", tz="UTC")], "close": [50000.0]})

    def fail_dump(*args, **kwargs):
        raise OSError("Simulated write interruption")

    monkeypatch.setattr(json, "dump", fail_dump)

    with pytest.raises(OSError, match="Simulated write interruption"):
        loader._save_metadata_sidecar(
            cache_path=parquet_path,
            df=df,
            quality_score=1.0,
            adjustments_applied=[],
            as_of_time=datetime(2026, 1, 2, 0, 0, tzinfo=timezone.utc),
        )

    assert json.loads(metadata_path.read_text(encoding="utf-8")) == initial_data


# ── F-006: Archive Malformed List/Array Input ────────────────────────────────


@pytest.mark.parametrize(
    "malformed_price",
    [
        [50000],
        [50000, 51000],
        [],
        {"price": 50000},
    ],
)
def test_f006_archive_list_input(malformed_price):
    """F-006: Archived _normalize_price_vnd must fail-close to 0.0 on list/dict/array inputs without crashing."""
    mod = _load_archived_vci()
    instance = mod.VnstockVCIDataSource()
    assert instance._normalize_price_vnd(malformed_price) == 0.0


# ── F-007: Deterministic Timezone Ingestion ──────────────────────────────────


def test_f007_deterministic_timezone():
    """F-007: Timestamp conversion in _rows_from_frame must be deterministic and timezone-anchored."""
    mod = _load_archived_vci()
    instance = mod.VnstockVCIDataSource()

    df = pd.DataFrame({
        "time": ["2026-01-02 00:00:00"],
        "open": [50.0],
        "high": [51.0],
        "low": [49.0],
        "close": [50.5],
        "volume": [1000],
    })
    rows = instance._rows_from_frame(df, "VCB", "VCI")
    assert len(rows) == 1
    assert rows[0]["timestamp"] == 1767286800


# ── F-008: Monkeypatch Restoration ───────────────────────────────────────────


def test_f008_monkeypatch_restoration(monkeypatch):
    """F-008: Monkeypatch on vci_quote.send_request must be safely restored and not leak."""
    import vnstock.explorer.vci.quote as vci_quote
    from vnstock.api.quote import Quote

    orig_send = getattr(vci_quote, "send_request", None)
    assert orig_send is not None

    mod = _load_archived_vci()
    instance = mod.VnstockVCIDataSource()

    monkeypatch.setattr(Quote, "history", lambda *a, **k: pd.DataFrame({"time": ["2026-01-02"], "close": [50.0]}))

    try:
        instance._fetch_provider("VCI", "VCB", "2026-01-01", "2026-01-02")
    except Exception:
        pass

    assert vci_quote.send_request is orig_send, "send_request monkeypatch leaked globally"


def test_rem2_loader_anchors_eod_at_1500_ict(tmp_path):
    from omega.data.loader import DataLoader

    loader = DataLoader(cache_dir=tmp_path)
    frame = pd.DataFrame({
        "date": [pd.Timestamp("2026-01-02", tz="UTC")],
        "open": [50000.0], "high": [51000.0], "low": [49000.0],
        "close": [50500.0], "volume": [100.0],
    })
    result = loader._add_pit_timestamps(frame)
    assert result.loc[0, "as_of"] == pd.Timestamp("2026-01-02 15:00", tz="Asia/Ho_Chi_Minh")
    assert result.loc[0, "available_at"] == pd.Timestamp("2026-01-05 09:00", tz="Asia/Ho_Chi_Minh")


def test_rem2_archive_naive_timestamp_anchors_to_ict():
    instance = _load_archived_vci().VnstockVCIDataSource()
    rows = instance._rows_from_frame(pd.DataFrame({"time": ["2026-01-02"], "close": [50.0]}), "VCB", "VCI")
    assert rows[0]["timestamp"] == 1767286800


def test_rem2_archive_does_not_mutate_api_key_environment(monkeypatch):
    monkeypatch.delenv("VNSTOCK_API_KEY", raising=False)
    instance = _load_archived_vci().VnstockVCIDataSource()
    assert instance.api_key == "dummy_key"
    assert "VNSTOCK_API_KEY" not in os.environ


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
def test_rem2_schema_rejects_negative_ohlcv(tmp_path, column):
    from omega.data.loader import DataLoader

    values = {"ticker": ["VCB"], "date": ["2026-01-02"], "open": [1.0], "high": [2.0],
              "low": [1.0], "close": [1.5], "volume": [1.0],
              "as_of": ["2026-01-02 15:00+07:00"], "available_at": ["2026-01-05 09:00+07:00"]}
    values[column] = [-1.0]
    with pytest.raises(ValueError, match="Negative prices or volume"):
        DataLoader(cache_dir=tmp_path)._validate_schema(pd.DataFrame(values))


def test_rem2_provider_exhaustion_fails_closed(monkeypatch):
    instance = _load_archived_vci().VnstockVCIDataSource(providers=["VCI", "KBS"])
    monkeypatch.setattr(instance, "_fetch_provider_isolated", lambda *args: [])
    with pytest.raises(RuntimeError, match="Provider exhaustion"):
        instance.fetch_price_data("VCB", "2026-01-01", "2026-01-02")
