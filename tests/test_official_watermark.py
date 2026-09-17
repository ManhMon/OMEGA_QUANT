import json
import os
from pathlib import Path

import pytest

from omega.data.official_watermark import (
    OfficialWatermarkConfig,
    _OfficialSourceResponse,
    STATUS_ARTIFACT_EXISTS,
    STATUS_CANDIDATE_DATE_MISMATCH,
    STATUS_MARKET_INVALID,
    STATUS_PATH_INVALID,
    STATUS_URL_NOT_ALLOWED,
    WatermarkContractError,
    canonical_json_bytes,
    materialize_watermark,
    _safe_path,
    select_candidate,
    sha256_hex,
    verify_artifact,
    _acquire_official_source,
)


URLS = {"HSX": "https://official.example/hsx", "HNX": "https://official.example/hnx"}


def config(tmp_path: Path) -> OfficialWatermarkConfig:
    return OfficialWatermarkConfig(tmp_path / "artifacts")


def evidence(raw=b"official-bytes", market="HSX"):
    url = {"HSX": "https://api.hsx.vn/m/api/v1.0/data-feed/files", "HNX": "https://hnx.vn/vi-vn/co-phieu-etfs/du-lieu-thi-truong-ny.html"}[market]
    return _OfficialSourceResponse(
        url, url, 200,
        "application/json", raw, "2026-07-24T08:59:00+07:00",
    )


def parsed(evidence_response, market="HSX"):
    return {"raw": evidence_response.raw, "rows": [{"market": market, "date": "2026-07-24", "symbol": "AAA", "value": 1}], "coverage": {"final_session": "2026-07-24", "symbols": ["AAA"]}, "cutoff_at": "2026-07-24T09:00:00+07:00", "exceptions": [], "calendar_closures": []}


@pytest.mark.parametrize("value", ["2026-07-24T09:00:00", "not-a-timestamp"])
def test_timestamp_requires_aware_iso8601(tmp_path, value, monkeypatch):
    source = evidence()
    payload = parsed(source)
    payload["cutoff_at"] = value
    monkeypatch.setattr("omega.data.official_watermark._acquire_official_source", lambda *_: source)
    monkeypatch.setattr("omega.data.official_watermark._parse_official_payload", lambda *_: payload)
    with pytest.raises(WatermarkContractError):
        materialize_watermark(config(tmp_path), "HSX", "2026-07-24")


def test_canonical_hash_and_immutable_receipt(tmp_path, monkeypatch):
    source = evidence()
    monkeypatch.setattr("omega.data.official_watermark._acquire_official_source", lambda *_: source)
    monkeypatch.setattr("omega.data.official_watermark._parse_official_payload", lambda *_: parsed(source))
    result = materialize_watermark(config(tmp_path), "HSX", "2026-07-24")
    assert result["status"] == "completed"
    assert canonical_json_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'
    assert result["manifest"]["canonical_sha256"] == sha256_hex(Path(result["paths"]["canonical"]).read_bytes())
    assert json.loads(Path(result["paths"]["receipt"]).read_text(encoding="utf-8"))["status"] == "completed"


@pytest.mark.parametrize("market,status", [("HOSE", STATUS_MARKET_INVALID), ("", STATUS_MARKET_INVALID)])
def test_market_exact(tmp_path, market, status, monkeypatch):
    source = evidence()
    monkeypatch.setattr("omega.data.official_watermark._acquire_official_source", lambda *_: source)
    monkeypatch.setattr("omega.data.official_watermark._parse_official_payload", lambda *_: parsed(source, market))
    with pytest.raises(WatermarkContractError) as exc:
        materialize_watermark(config(tmp_path), market, "2026-07-24")
    assert exc.value.status == status


def test_missing_evidence_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("omega.data.official_watermark._acquire_official_source", lambda *_: None)
    with pytest.raises(WatermarkContractError) as exc:
        materialize_watermark(config(tmp_path), "HSX", "2026-07-24")
    assert exc.value.status == "vci_receipt_invalid"
    assert not (tmp_path / "artifacts").exists()


def test_forged_rows_cannot_reach_receipt_writer(tmp_path):
    source = evidence(raw=b'{"rows": []}')
    forged_rows = [{"market": "HSX", "date": "2026-07-24", "symbol": "FORGED"}]
    with pytest.raises(TypeError):
        materialize_watermark(config(tmp_path), "HSX", "2026-07-24", source, forged_rows)
    assert not list((tmp_path / "artifacts").glob("*"))


def test_candidate_date_rejected(tmp_path):
    with pytest.raises(WatermarkContractError) as exc:
        select_candidate([{"market": "HSX", "date": "2026-07-23"}], "HSX", "2026-07-24")
    assert exc.value.status == STATUS_CANDIDATE_DATE_MISMATCH


def test_path_traversal_and_no_overwrite(tmp_path):
    with pytest.raises(WatermarkContractError) as exc:
        _safe_path(tmp_path / "artifacts", "../escape")
    assert exc.value.status == STATUS_PATH_INVALID
    monkeypatch = pytest.MonkeyPatch()
    source = evidence()
    monkeypatch.setattr("omega.data.official_watermark._acquire_official_source", lambda *_: source)
    monkeypatch.setattr("omega.data.official_watermark._parse_official_payload", lambda *_: parsed(source))
    materialize_watermark(config(tmp_path), "HSX", "2026-07-24")
    with pytest.raises(WatermarkContractError) as exc:
        materialize_watermark(config(tmp_path), "HSX", "2026-07-24")
    monkeypatch.undo()
    assert exc.value.status == STATUS_ARTIFACT_EXISTS


def test_symlink_path_rejected(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    target = tmp_path / "outside"
    target.mkdir()
    link = root / "nested"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(WatermarkContractError) as exc:
        _safe_path(root, "nested/file.json")
    assert exc.value.status == STATUS_PATH_INVALID


def test_tamper_status(tmp_path, monkeypatch):
    source = evidence()
    source = evidence(market="HNX")
    monkeypatch.setattr("omega.data.official_watermark._acquire_official_source", lambda *_: source)
    monkeypatch.setattr("omega.data.official_watermark._parse_official_payload", lambda *_: parsed(source, "HNX"))
    result = materialize_watermark(config(tmp_path), "HNX", "2026-07-24")
    path = Path(result["paths"]["canonical"])
    path.write_bytes(b"tampered")
    with pytest.raises(WatermarkContractError) as exc:
        verify_artifact(path, result["manifest"]["canonical_sha256"])
    assert exc.value.status == "artifact_tampered"


def test_partial_receipt_bundle_is_removed_on_write_failure(tmp_path, monkeypatch):
    calls = {"count": 0}
    from omega.data import official_watermark

    original = official_watermark._exclusive_write
    def fail_after_first(path, content):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated receipt bundle failure")
        return original(path, content)
    monkeypatch.setattr(official_watermark, "_exclusive_write", fail_after_first)
    with pytest.raises(OSError):
        source = evidence()
        monkeypatch.setattr("omega.data.official_watermark._acquire_official_source", lambda *_: source)
        monkeypatch.setattr("omega.data.official_watermark._parse_official_payload", lambda *_: parsed(source))
        materialize_watermark(config(tmp_path), "HSX", "2026-07-24")
    assert not list((tmp_path / "artifacts").glob("*"))


def test_windows_directory_durability_is_supported(tmp_path, monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows capability contract")
    source = evidence()
    monkeypatch.setattr("omega.data.official_watermark._acquire_official_source", lambda *_: source)
    monkeypatch.setattr("omega.data.official_watermark._parse_official_payload", lambda *_: parsed(source))
    result = materialize_watermark(config(tmp_path), "HSX", "2026-07-24")
    assert result["status"] == "completed"


class _Headers(dict):
    def get_content_type(self):
        return self["Content-Type"].split(";", 1)[0]


class _Response:
    headers = _Headers({"Content-Type": "text/html; charset=utf-8"})

    def getcode(self):
        return 200

    def geturl(self):
        return URLS["HNX"]

    def read(self):
        return b'<input id="txtSymbol_Date" value="28/07/2026"><title>HNX</title>'

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_hnx_official_html_date_marker_is_rejected(monkeypatch):
    monkeypatch.setenv("VCI_API_TOKEN", "test-token")
    monkeypatch.setattr("omega.data.official_watermark.urlopen", lambda *args, **kwargs: _Response())
    with pytest.raises(WatermarkContractError):
        _acquire_official_source("HNX", "2026-07-28")


def test_public_fetch_and_evidence_construction_are_unavailable():
    import omega.data.official_watermark as module
    assert not hasattr(module, "fetch_official_source")
    assert not hasattr(module, "OfficialSourceResponse")


def test_materialize_has_no_external_evidence_or_rows_parameters():
    import inspect
    from omega.data.official_watermark import materialize_watermark
    assert list(inspect.signature(materialize_watermark).parameters) == ["config", "market", "expected_date"]
