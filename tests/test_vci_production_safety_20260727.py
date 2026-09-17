import importlib.util
import json
import os
from pathlib import Path

import pandas as pd
import pytest
from unittest.mock import patch

from omega.data.official_watermark import OfficialWatermarkConfig, _OfficialSourceResponse, materialize_watermark


SCRIPT = Path(__file__).parents[1] / "scripts" / "update_market_data.py"
SPEC = importlib.util.spec_from_file_location("vci_safety_updater", SCRIPT)
updater = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(updater)


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"ticker": ["AAA"], "date": [pd.Timestamp("2026-07-24")], "close": [1.0]})


def _publish_manifest():
    return {"official_watermark_provenance": {"HSX": {"calendar_closures": ()}}}


def test_atomic_tmp_failure_cleans_temp(monkeypatch, tmp_path):
    target = tmp_path / "candidate.parquet"
    monkeypatch.setattr(pd.DataFrame, "to_parquet", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError, match="disk"):
        updater.atomic_write_with_backup(_frame(), target, backup=False)
    assert list(tmp_path.glob("*.parquet.tmp")) == []
    assert not target.exists()


def test_publication_lock_rejects_concurrent_writer(tmp_path):
    pointer = tmp_path / "current.json"
    lock = pointer.with_suffix(".json.lock")
    lock.write_bytes(b"held")
    with pytest.raises(RuntimeError, match="publication lock"):
        updater.publish_candidate(_frame(), tmp_path / "canonical.parquet", tmp_path / "releases", pointer, manifest=_publish_manifest())


@pytest.mark.skipif(os.name == "nt", reason="directory durability unsupported on Windows")
def test_publication_prune_failure_is_nonfatal(monkeypatch, tmp_path):
    releases = tmp_path / "releases"
    pointer = tmp_path / "current.json"
    monkeypatch.setattr(updater, "prune_releases", lambda *_args: (_ for _ in ()).throw(OSError("prune")))
    result = updater.publish_candidate(_frame(), tmp_path / "canonical.parquet", releases, pointer, manifest=_publish_manifest())
    assert result["run_id"]
    assert json.loads(pointer.read_text())["generation"] == 1


def test_receipt_coverage_is_exchange_partitioned_and_immutable(tmp_path, monkeypatch):
    def materialize_fixture(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    source = _OfficialSourceResponse("https://api.hsx.vn/m/api/v1.0/data-feed/files", "https://api.hsx.vn/m/api/v1.0/data-feed/files", 200, "application/json", b"raw", "2026-07-24T09:01:00+07:00")
    monkeypatch.setattr("omega.data.official_watermark._acquire_official_source", lambda *_: source)
    monkeypatch.setattr("omega.data.official_watermark._parse_official_payload", lambda *_: {
                "raw": source.raw,
                "rows": [{"market": "HSX", "date": "2026-07-24", "symbol": "AAA"}],
                "coverage": {"final_session": "2026-07-24", "symbols": ["wrong"]},
                "exceptions": [{"owner": "ops", "reason": "none", "expiry": "2026-12-31", "exchange": "HSX"}],
                "exceptions_version": "v1",
                "cutoff_at": "2026-07-24T09:02:00+07:00",
            })
    with patch("omega.data.official_watermark._exclusive_write", side_effect=materialize_fixture):
        result = materialize_watermark(OfficialWatermarkConfig(tmp_path), "HSX", "2026-07-24")
    receipt = json.loads(Path(result["paths"]["receipt"]).read_text())
    assert receipt["coverage"]["by_exchange"] == {"HSX": ["AAA"]}
    assert receipt["exceptions"] == [{"owner": "ops", "reason": "none", "expiry": "2026-12-31", "exchange": "HSX"}]


def test_post_pointer_failure_restores_state_and_quarantines_release(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "_fsync_directory", lambda *_: None)
    monkeypatch.setattr(updater, "_release_publication_lock", lambda path, lease: path.unlink(missing_ok=True))
    monkeypatch.setattr(updater, "prune_releases", lambda *_: (_ for _ in ()).throw(OSError("prune fault")))
    monkeypatch.setattr(updater, "_trusted_keyring", lambda: ("test", {"test": b"x" * 32}))
    pointer = tmp_path / "current.json"
    prior_pointer = b'{"generation":7,"candidate":"prior"}'
    pointer.write_bytes(prior_pointer)
    releases = tmp_path / "releases"
    authority = {"validation_outcome": "passed", "terminal_session": "2026-07-24", "cutoff_at": "2026-07-24T09:00:00+00:00"}
    with pytest.raises(OSError, match="prune fault"):
        updater.publish_candidate(_frame(), tmp_path / "canonical.parquet", releases, pointer, vci_authority=authority)
    run_dir = next(releases.iterdir())
    receipt = run_dir / "vci_authority_receipt.v2.json"
    assert pointer.read_bytes() == prior_pointer
    assert updater.verify_market_data_receipt(json.loads(receipt.read_text()))
    assert (run_dir / "quarantine.json").is_file()
    assert not pointer.with_suffix(".json.lock").exists()
    assert not (tmp_path / "canonical.parquet").exists()
    assert json.loads(pointer.read_text())["generation"] == 7
