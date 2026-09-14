"""16-Dimension resilience and unit tests for direct VCI client."""

import json
import math
from pathlib import Path
import sys

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.ingest_all_market_data as iam

from omega.data.vci_direct import (
    DirectVCIClient,
    TokenBucket,
    redact,
    unpack_vietcap_columnar,
    validate_price_bounds,
)


def payload():
    return {"t": [1704067200000], "o": [27], "h": [28], "l": [26], "c": [27.5], "v": [100]}


def test_unpack_normalizes_vnd_full_and_preserves_contract():
    frame = unpack_vietcap_columnar("HPG", payload())
    assert frame.raw_close.iloc[0] == 27500
    assert frame.close.iloc[0] == 27500.0
    assert frame.value.iloc[0] == 2_750_000


@pytest.mark.parametrize("bad", [None, {"t": [1]}, {"t": [1], "o": [1], "h": [1], "l": [1], "c": [1, 2], "v": [1]}, {"t": [1], "o": [math.nan], "h": [1], "l": [1], "c": [1], "v": [1]}])
def test_unpack_rejects_malformed_payloads(bad):
    with pytest.raises(ValueError):
        unpack_vietcap_columnar("HPG", bad)


def test_price_bounds_exchange_and_corporate_action():
    assert validate_price_bounds(10_700, 10_000, "HOSE")
    assert not validate_price_bounds(11_000, 10_000, "HOSE")
    assert validate_price_bounds(11_000, 10_000, "HOSE", is_corporate_action_date=True)


def test_client_rejects_credentialed_endpoint_and_invalid_timeout():
    with pytest.raises(ValueError):
        DirectVCIClient("https://user:secret@example.test")
    with pytest.raises(ValueError):
        DirectVCIClient(timeout=0)


def test_token_bucket_rejects_non_finite_rate():
    with pytest.raises(ValueError):
        TokenBucket(rate=math.inf)


def test_unpack_rejects_empty_mixed_scale_duplicate_and_overflow_payloads():
    empty = {key: [] for key in ("t", "o", "h", "l", "c", "v")}
    with pytest.raises(ValueError, match="no records"):
        unpack_vietcap_columnar("HPG", empty)
    mixed = {"t": [1, 2], "o": [27, 27000], "h": [28, 28000], "l": [26, 26000], "c": [27.5, 27500], "v": [100, 100]}
    with pytest.raises(ValueError, match="Mixed price scale"):
        unpack_vietcap_columnar("HPG", mixed)
    duplicate = payload()
    duplicate["t"] = [1, 1]
    for key in duplicate:
        duplicate[key] = duplicate[key] * 2 if key != "t" else duplicate[key]
    with pytest.raises(ValueError, match="Duplicate timestamps"):
        unpack_vietcap_columnar("HPG", duplicate)
    overflow = payload()
    overflow["v"] = [2**63]
    with pytest.raises(ValueError, match="overflows"):
        unpack_vietcap_columnar("HPG", overflow)


def test_redact_sanitizes_authorization_schemes():
    assert redact("Authorization: Basic dXNlcjpwYXNz") == "Authorization: Basic [REDACTED]"
    assert redact("Authorization: Bearer secret") == "Authorization: Bearer [REDACTED]"


def test_unpack_rejects_nested_timestamp_types():
    for bad_t in ([[1704067200000]], [{"time": 1704067200000}]):
        bad = {"t": bad_t, "o": [27], "h": [28], "l": [26], "c": [27.5], "v": [100]}
        with pytest.raises(ValueError):
            unpack_vietcap_columnar("HPG", bad)


def test_redact_sanitizes_url_userinfo():
    url = "https://user:secret@trading.vietcap.com.vn/api/chart"
    redacted = redact(url)
    assert "secret" not in redacted


def test_unpack_preserves_valid_vnd_full_under_1000():
    valid_penny = {"t": [1704067200000], "o": [500], "h": [500], "l": [500], "c": [500], "v": [100]}
    frame = unpack_vietcap_columnar("HPG", valid_penny)
    assert frame.raw_close.iloc[0] == 500
    assert frame.close.iloc[0] == 500.0


def test_unpack_rejects_adjusted_price_inf_overflow():
    with pytest.raises(ValueError):
        unpack_vietcap_columnar("HPG", payload(), adj_ratio=1e308)


def test_client_enforces_ict_1530_same_day_boundary(monkeypatch):
    trading_day = "2026-09-14"
    day_start_ms = 1789344000000
    body = json.dumps({"data": [{"t": [day_start_ms], "o": [27], "h": [28], "l": [26], "c": [27.5], "v": [100]}]}).encode()

    class _MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return body

    client = DirectVCIClient(opener=lambda req, timeout: _MockResponse())
    monkeypatch.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: pd.Timestamp("2026-09-14 02:20:00", tz="UTC")))
    with pytest.raises(ValueError, match="15:30|cutoff|trading-session|PIT"):
        client.fetch_history("HPG", trading_day, trading_day)


def _sample_frame(ticker="HPG", n=3):
    return pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC"),
        "ticker": ticker,
        "open": [27000.0] * n,
        "high": [28000.0] * n,
        "low": [26500.0] * n,
        "close": [27500.0] * n,
        "volume": [100000] * n,
    })


def test_production_atomic_write_frame_rejects_empty_frame(tmp_path):
    with pytest.raises(ValueError, match="empty market data"):
        iam.atomic_write_frame(pd.DataFrame(), tmp_path / "empty.parquet")


def test_production_atomic_write_frame_writes_valid_data(tmp_path):
    frame = _sample_frame()
    target = tmp_path / "valid.parquet"
    iam.atomic_write_frame(frame, target)
    assert target.exists()
    assert len(pd.read_parquet(target)) == len(frame)


def test_production_atomic_write_frame_rejects_none_and_non_finite(tmp_path):
    target = tmp_path / "invalid.parquet"
    with pytest.raises(TypeError, match="cannot be None"):
        iam.atomic_write_frame(None, target)
    invalid = _sample_frame()
    invalid.loc[0, "close"] = math.nan
    with pytest.raises(ValueError, match="NaN or Inf"):
        iam.atomic_write_frame(invalid, target)


def test_production_atomic_write_post_replace_failure_reports_rollback(tmp_path):
    target = tmp_path / "market.parquet"
    iam.atomic_write_frame(_sample_frame(), target)
    original = target.read_bytes()
    with pytest.raises(iam.AtomicWriteError) as exc_info:
        iam.atomic_write_frame(
            _sample_frame(n=4),
            target,
            post_replace_hook=lambda: (_ for _ in ()).throw(OSError("directory fsync crash")),
        )
    assert exc_info.value.rolled_back is True
    assert target.read_bytes() == original


def test_production_fetch_history_http_error_falls_back_to_tcbs(monkeypatch):
    class FailedVCI:
        def __init__(self, **kwargs):
            pass

        def fetch_history(self, *args):
            raise OSError("VCI unavailable")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({"data": [{"time": 1, "open": 27, "high": 28, "low": 26, "close": 27, "volume": 100}]}).encode()

    monkeypatch.setattr(iam, "DirectVCIClient", FailedVCI)
    monkeypatch.setattr(iam, "urlopen", lambda request, timeout: Response())
    frame = iam.fetch_history("hpg", "2026-01-01", "2026-01-02")
    assert frame.loc[0, "ticker"] == "HPG"


def test_production_ingest_empty_remote_preserves_cache(tmp_path, monkeypatch):
    target = tmp_path / "FLC.parquet"
    iam.atomic_write_frame(_sample_frame("FLC"), target)
    original = target.read_bytes()
    registry = tmp_path / "symbols_delisted.json"
    registry.write_text(json.dumps(["FLC"]), encoding="utf-8")
    class EmptyVCI:
        def __init__(self, **kwargs):
            pass

        def fetch_history(self, *args):
            return pd.DataFrame()

    class EmptyResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"data": []}'

    monkeypatch.setattr(iam, "DirectVCIClient", EmptyVCI)
    monkeypatch.setattr(iam, "urlopen", lambda request, timeout: EmptyResponse())
    with pytest.raises(ValueError, match="delisted=True"):
        iam.ingest_symbol("FLC", "2026-01-01", "2026-01-02", target, registry=registry, archive_dir=tmp_path / "archive")
    assert target.read_bytes() == original


def test_production_ingest_uses_delisted_archive_when_provider_empty(tmp_path, monkeypatch):
    archive_dir = tmp_path / "delisted_archive"
    archive_dir.mkdir()
    archive = archive_dir / "FLC.parquet"
    archived = _sample_frame("FLC", n=2)
    archived.to_parquet(archive, index=False)
    target = tmp_path / "FLC.output.parquet"
    class EmptyVCI:
        def __init__(self, **kwargs):
            pass

        def fetch_history(self, *args):
            return pd.DataFrame()

    class EmptyResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"data": []}'

    monkeypatch.setattr(iam, "DirectVCIClient", EmptyVCI)
    monkeypatch.setattr(iam, "urlopen", lambda request, timeout: EmptyResponse())
    iam.ingest_symbol("flc", "2026-01-01", "2026-01-02", target, archive_dir=archive_dir)
    assert target.exists()
    pd.testing.assert_frame_equal(pd.read_parquet(target), archived)


def test_production_main_routes_through_ingest_symbol(monkeypatch, tmp_path):
    archive_dir = tmp_path / "delisted_archive"
    archive_dir.mkdir()
    archived = _sample_frame("HPG", n=2)
    archived.to_parquet(archive_dir / "HPG.parquet", index=False)
    target = tmp_path / "HPG.parquet"
    registry = tmp_path / "symbols_delisted.json"
    registry.write_text(json.dumps(["HPG"]), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "ingest_all_market_data.py", "HPG", "2026-01-01", "2026-01-02",
        "--output", str(target), "--registry", str(registry), "--archive-dir", str(archive_dir),
    ])
    assert iam.main() == 0
    pd.testing.assert_frame_equal(pd.read_parquet(target), archived)
