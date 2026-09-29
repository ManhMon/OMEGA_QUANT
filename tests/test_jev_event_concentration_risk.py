import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest
import numpy as np

from omega.risk.contagion_risk_validator import ContagionRiskValidator, event_concentration_advisory
from omega.risk.risk_manager import RiskManager, RiskManagerConfig
from omega.quant.portfolio.sector_classifier import get_structure_metadata


CUTOFF = datetime(2024, 1, 2, tzinfo=timezone.utc)


def event():
    value = {"source_revision": "R1", "policy_version": "P1", "driver": "shared_driver",
             "event_versions": ["E1"], "entities": ["AAA", "BBB"],
             "available_at": CUTOFF - timedelta(days=1), "expires_at": CUTOFF + timedelta(days=1)}
    return sign_event(value)


def sign_event(value):
    canonical = {key: value[key] for key in ("source_revision", "policy_version", "driver", "event_versions", "entities")}
    canonical.update({"available_at": value["available_at"].astimezone(timezone.utc).isoformat(),
                      "expires_at": value["expires_at"].astimezone(timezone.utc).isoformat()})
    content = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return {**value, "source_content": content, "source_digest": hashlib.sha256(content.encode()).hexdigest(),
             "advisory_only": True, "applied": False, "lambda": 0,
             "gate_id": "GATE_JEV_DEEP_INTEGRATION_W4_20260929"}


def test_risk_manager_publishes_advisory_without_mutating_portfolio(tmp_path):
    if os.name == "nt":
        pytest.skip("durable advisory publication cannot be guaranteed on Windows")
    manager = RiskManager(RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                                            event_advisory_ledger_path=str(tmp_path / "ledger")))
    weights = {"AAA": 0.2, "BBB": -0.1, "CASH": 0.9}
    portfolio = SimpleNamespace(get_symbol_weights=lambda: weights)
    result = manager.evaluate_event_advisory(event(), portfolio, CUTOFF)
    assert result["signed_exposure"] == pytest.approx(0.1)
    assert result["gross_exposure"] == pytest.approx(0.3)
    assert result["advisory_only"] is True and result["applied"] is False and result["lambda"] == 0
    assert weights == {"AAA": 0.2, "BBB": -0.1, "CASH": 0.9}
    assert json.loads((tmp_path / "ledger" / (result["decision_id"] + ".json")).read_text())["advisory"] == result
    assert manager.evaluate_event_advisory(event(), portfolio, CUTOFF) == result


def test_distinct_portfolios_publish_same_event_concurrently(tmp_path):
    if os.name == "nt":
        pytest.skip("durable advisory publication cannot be guaranteed on Windows")
    config = RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                               event_advisory_ledger_path=str(tmp_path / "ledger"))
    manager = RiskManager(config)
    portfolios = [SimpleNamespace(get_symbol_weights=lambda weights=weights: weights)
                  for weights in ({"AAA": .2, "BBB": -.1}, {"AAA": .4, "BBB": -.1})]
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(lambda portfolio: manager.evaluate_event_advisory(event(), portfolio, CUTOFF),
                                 portfolios)
    assert first["group_id"] == second["group_id"]
    assert first["decision_id"] != second["decision_id"]
    assert first["gross_exposure"] != second["gross_exposure"]
    for advisory, portfolio in zip((first, second), portfolios):
        path = tmp_path / "ledger" / (advisory["decision_id"] + ".json")
        assert json.loads(path.read_text())["advisory"] == advisory
        assert RiskManager(config).evaluate_event_advisory(event(), portfolio, CUTOFF) == advisory
    assert len(list((tmp_path / "ledger").glob("*.json"))) == 2


def test_same_exposure_distinct_weights_have_distinct_publication_keys():
    first = event_concentration_advisory(event(), {"AAA": .2}, CUTOFF)
    second = event_concentration_advisory(event(), {"AAA": .2, "OTHER": .1}, CUTOFF)
    assert first["group_id"] == second["group_id"]
    assert first["signed_exposure"] == second["signed_exposure"]
    assert first["decision_id"] != second["decision_id"]


def test_equivalent_timezone_inputs_retry_same_decision(tmp_path):
    if os.name == "nt":
        pytest.skip("durable advisory publication cannot be guaranteed on Windows")
    config = RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                               event_advisory_ledger_path=str(tmp_path / "ledger"))
    manager = RiskManager(config)
    portfolio = SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2})
    original = event()
    translated = {**original,
                  "available_at": original["available_at"].astimezone(timezone(timedelta(hours=7))),
                  "expires_at": original["expires_at"].astimezone(timezone(timedelta(hours=7)))}
    first = manager.evaluate_event_advisory(original, portfolio, CUTOFF)
    assert manager.evaluate_event_advisory(translated, portfolio,
                                           CUTOFF.astimezone(timezone(timedelta(hours=7)))) == first
    assert len(list((tmp_path / "ledger").glob("*.json"))) == 1


def test_corrupt_portfolio_publication_does_not_block_other_portfolio(tmp_path):
    if os.name == "nt":
        pytest.skip("durable advisory publication cannot be guaranteed on Windows")
    config = RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                               event_advisory_ledger_path=str(tmp_path / "ledger"))
    manager = RiskManager(config)
    first = SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2})
    second = SimpleNamespace(get_symbol_weights=lambda: {"AAA": .4})
    published = manager.evaluate_event_advisory(event(), first, CUTOFF)
    path = tmp_path / "ledger" / (published["decision_id"] + ".json")
    path.write_bytes(b"corrupt")
    with pytest.raises(FileExistsError):
        manager.evaluate_event_advisory(event(), first, CUTOFF)
    other = manager.evaluate_event_advisory(event(), second, CUTOFF)
    assert other["group_id"] == published["group_id"]
    assert other["decision_id"] != published["decision_id"]
    assert json.loads((tmp_path / "ledger" / (other["decision_id"] + ".json")).read_text())["advisory"] == other
    assert path.read_bytes() == b"corrupt"


def test_advisory_write_failure_leaves_no_publication(tmp_path, monkeypatch):
    manager = RiskManager(RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                                            event_advisory_ledger_path=str(tmp_path / "ledger")))
    item = event()
    def fail_dump(*args, **kwargs):
        raise OSError("injected write failure")
    monkeypatch.setattr("omega.risk.risk_manager.json.dumps", fail_dump)
    with pytest.raises(OSError, match="injected write failure"):
        manager.evaluate_event_advisory(item, SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2}), CUTOFF)
    assert not (tmp_path / "ledger").exists()


def test_advisory_fsync_failure_leaves_no_publication(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("durable advisory publication cannot be guaranteed on Windows")
    manager = RiskManager(RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                                            event_advisory_ledger_path=str(tmp_path / "ledger")))
    monkeypatch.setattr("omega.risk.risk_manager.os.fsync", lambda fd: (_ for _ in ()).throw(OSError("fsync failed")))
    with pytest.raises(OSError, match="fsync failed"):
        manager.evaluate_event_advisory(event(), SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2}), CUTOFF)
    assert list((tmp_path / "ledger").iterdir()) == []


def test_advisory_concurrent_publish_keeps_first_complete_payload(tmp_path):
    if os.name == "nt":
        pytest.skip("durable advisory publication cannot be guaranteed on Windows")
    manager = RiskManager(RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                                            event_advisory_ledger_path=str(tmp_path / "ledger")))
    portfolio = SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2})
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: _publish(manager, portfolio), range(8)))
    assert outcomes.count("published") == 8
    files = list((tmp_path / "ledger").iterdir())
    assert len(files) == 1 and files[0].suffix == ".json"
    assert json.loads(files[0].read_text())["advisory"]["decision_id"] == files[0].stem


def _publish(manager, portfolio):
    try:
        manager.evaluate_event_advisory(event(), portfolio, CUTOFF)
        return "published"
    except FileExistsError:
        return "duplicate"


@pytest.mark.parametrize("failure", ["directory_sync", "staging_unlink"])
def test_post_link_failure_recovers_after_restart(tmp_path, monkeypatch, failure):
    import omega.risk.risk_manager as module
    if os.name == "nt":
        pytest.skip("durable advisory publication cannot be guaranteed on Windows")
    config = RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                               event_advisory_ledger_path=str(tmp_path / "ledger"))
    portfolio = SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2})
    original_fsync, original_unlink = module.os.fsync, module.os.unlink
    if failure == "directory_sync":
        if os.name == "nt":
            pytest.skip("directory sync is POSIX-only")
        def fail_directory(fd):
            if os.path.isdir(f"/proc/self/fd/{fd}"):
                raise OSError("directory sync failed")
            return original_fsync(fd)
        monkeypatch.setattr(module.os, "fsync", fail_directory)
    else:
        def fail_unlink(path):
            if str(path).endswith(".tmp"):
                raise OSError("staging unlink failed")
            return original_unlink(path)
        monkeypatch.setattr(module.os, "unlink", fail_unlink)
    assert RiskManager(config).evaluate_event_advisory(event(), portfolio, CUTOFF)
    monkeypatch.undo()
    files = list((tmp_path / "ledger").glob("*.json"))
    assert len(files) == 1
    assert RiskManager(config).evaluate_event_advisory(event(), portfolio, CUTOFF) == json.loads(files[0].read_text())["advisory"]
    assert len(list((tmp_path / "ledger").glob("*.json"))) == 1


def test_existing_advisory_mismatch_fails_closed(tmp_path):
    if os.name == "nt":
        pytest.skip("durable advisory publication cannot be guaranteed on Windows")
    config = RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                               event_advisory_ledger_path=str(tmp_path / "ledger"))
    portfolio = SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2})
    result = RiskManager(config).evaluate_event_advisory(event(), portfolio, CUTOFF)
    path = tmp_path / "ledger" / (result["decision_id"] + ".json")
    path.write_text('{"corrupt":true}')
    with pytest.raises(FileExistsError):
        RiskManager(config).evaluate_event_advisory(event(), portfolio, CUTOFF)


@pytest.mark.parametrize("change", ["entities", "event_versions", "source_digest", "source_content", "policy_version"])
def test_tampered_provenance_rejected(change):
    item = event()
    item[change] = ["OTHER"] if isinstance(item[change], list) else "OTHER"
    with pytest.raises(ValueError):
        event_concentration_advisory(item, {"AAA": 0.2}, CUTOFF)


@pytest.mark.parametrize("field,delta", [("available_at", -timedelta(days=2)),
                                        ("expires_at", timedelta(days=2))])
def test_event_window_tamper_rejected_before_publication(tmp_path, field, delta):
    item = event()
    item[field] += delta
    ledger = tmp_path / "ledger"
    manager = RiskManager(RiskManagerConfig(event_advisory_ledger_path=str(ledger)))
    with pytest.raises(ValueError, match="source content does not match event"):
        manager.evaluate_event_advisory(item, SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2}), CUTOFF)
    assert not ledger.exists()


@pytest.mark.parametrize("field,delta", [("available_at", timedelta(hours=1)),
                                        ("expires_at", -timedelta(hours=1))])
def test_event_window_replay_changes_digest_and_identity(field, delta):
    original = event()
    changed = sign_event({**original, field: original[field] + delta})
    before = event_concentration_advisory(original, {"AAA": .2}, CUTOFF)
    after = event_concentration_advisory(changed, {"AAA": .2}, CUTOFF)
    assert original["source_digest"] != changed["source_digest"]
    assert before["group_id"] != after["group_id"]


@pytest.mark.parametrize("field,delta", [("available_at", timedelta(days=1, seconds=1)),
                                        ("expires_at", -timedelta(days=1))])
def test_resigned_ineligible_event_fails_closed(field, delta):
    item = event()
    item[field] += delta
    item = sign_event(item)
    with pytest.raises(ValueError, match="unavailable or expired"):
        event_concentration_advisory(item, {"AAA": .2}, CUTOFF)


@pytest.mark.parametrize("cutoff", [None, datetime(2024, 1, 2)])
def test_historical_cutoff_required_even_when_disabled(cutoff):
    from omega.risk.contagion_risk_validator import ContagionRiskConfig
    with pytest.raises(ValueError):
        ContagionRiskValidator(ContagionRiskConfig(enabled=False)).validate(None, [], as_of_time=cutoff)


@pytest.mark.parametrize("date", [None, "bad", "2024-2-01", "2024-02-30", "2024-01-01junk"])
def test_malformed_sector_date_never_reaches_network(monkeypatch, date):
    import omega.quant.portfolio.sector_classifier as sector
    monkeypatch.setattr(sector, "Vnstock", lambda: pytest.fail("network contacted"))
    with pytest.raises(ValueError):
        get_structure_metadata(["AAA"], date, use_cache=False)


def test_historical_sector_cache_miss_is_unknown(monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    monkeypatch.setattr(sector, "Vnstock", lambda: pytest.fail("network contacted"))
    assert get_structure_metadata(["AAA"], "2020-01-01", use_cache=False)["AAA"]["sector_code"] == "UNKNOWN"


def test_matching_advisory_retry_restores_directory_durability(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("directory fsync unavailable")
    import omega.risk.risk_manager as module
    config = RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                               event_advisory_ledger_path=str(tmp_path / "ledger"))
    manager = RiskManager(config)
    portfolio = SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2})
    original = module.os.fsync
    failed = False
    def fail_first_directory_sync(fd):
        nonlocal failed
        if os.path.isdir(f"/proc/self/fd/{fd}") and not failed:
            failed = True
            raise OSError("directory sync failed")
        return original(fd)
    monkeypatch.setattr(module.os, "fsync", fail_first_directory_sync)
    assert manager.evaluate_event_advisory(event(), portfolio, CUTOFF)
    assert manager.evaluate_event_advisory(event(), portfolio, CUTOFF)


@pytest.mark.parametrize("kind", ["directory", "symlink", "fifo", "corrupt"])
def test_advisory_existing_non_regular_or_corrupt_path_fails_closed(tmp_path, kind):
    if os.name == "nt":
        pytest.skip("durable advisory publication cannot be guaranteed on Windows")
    config = RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                               event_advisory_ledger_path=str(tmp_path / "ledger"))
    manager = RiskManager(config)
    portfolio = SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2})
    advisory = manager.evaluate_event_advisory(event(), portfolio, CUTOFF)
    target = tmp_path / "ledger" / (advisory["decision_id"] + ".json")
    target.unlink()
    if kind == "directory":
        target.mkdir()
    elif kind == "symlink":
        target.symlink_to(tmp_path / "missing")
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFO unsupported")
        os.mkfifo(target)
    else:
        target.write_bytes(b"bad")
    with pytest.raises((OSError, FileExistsError)):
        manager.evaluate_event_advisory(event(), portfolio, CUTOFF)


def test_windows_advisory_durability_fails_closed(tmp_path, monkeypatch):
    import omega.risk.risk_manager as module
    monkeypatch.setattr(module.os, "name", "nt")
    config = RiskManagerConfig(event_advisory_ledger_path=str(tmp_path / "ledger"))
    with pytest.raises(OSError, match="unsupported on Windows"):
        RiskManager(config).evaluate_event_advisory(event(), SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2}), CUTOFF)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_contagion_invalid_returns_fail_closed(bad):
    import numpy as np
    from omega.quant.portfolio.contagion_overlay import compute_correlation_spike_exposure
    matrix = np.ones((130, 10), dtype=float)
    matrix[0, 0] = 0.0
    matrix[1, 0] = bad
    with pytest.raises(ValueError, match="finite"):
        compute_correlation_spike_exposure(matrix)


@pytest.mark.parametrize("kwargs", [
    {"spike_exposure": np.nan}, {"spike_exposure": 1.1},
    {"normal_exposure": np.inf}, {"normal_exposure": -0.1},
    {"spike_threshold_std": np.inf}, {"lookback": 0},
])
def test_contagion_invalid_settings_fail_closed(kwargs):
    import numpy as np
    from omega.quant.portfolio.contagion_overlay import compute_correlation_spike_exposure
    matrix = np.random.default_rng(1).normal(size=(130, 10))
    with pytest.raises(ValueError):
        compute_correlation_spike_exposure(matrix, **kwargs)


@pytest.mark.parametrize("matrix", [[[1.0]], [["1"]], [[1.0, 2.0], [3.0]]])
def test_contagion_invalid_shapes_or_types_fail_closed(matrix):
    from omega.quant.portfolio.contagion_overlay import compute_correlation_spike_exposure
    with pytest.raises(ValueError):
        compute_correlation_spike_exposure(matrix)


def test_same_day_sector_metadata_requires_aware_cutoff_and_available_at(monkeypatch):
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
    with pytest.raises(ValueError):
        get_structure_metadata(["AAA"], today, use_cache=False)


def test_same_day_sector_metadata_enforces_utc_cutoff(monkeypatch):
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    as_of = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    available = as_of + timedelta(minutes=1)
    with pytest.raises(ValueError, match="later than"):
        get_structure_metadata(["AAA"], as_of, use_cache=False, available_at=available)


def test_historical_sector_cache_without_source_availability_is_unknown(monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    monkeypatch.setattr(sector, "_load_metadata_cache", lambda: {
        "AAA": {"2020-01-01": {"sector_code": "LATER", "exchange_code": "HOSE"}}
    })
    monkeypatch.setattr(sector, "Vnstock", lambda: pytest.fail("network contacted"))
    assert get_structure_metadata(["AAA"], "2020-01-01")["AAA"]["sector_code"] == "UNKNOWN"


def test_historical_sector_cache_requires_availability_before_date_cutoff(monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    monkeypatch.setattr(sector, "_load_metadata_cache", lambda: {
        "AAA": {"2020-01-01": {"sector_code": "KNOWN", "exchange_code": "HOSE",
                                "available_at": "2020-01-02T00:00:00+00:00",
                                "availability_source": "provider"}}
    })
    assert get_structure_metadata(["AAA"], "2020-01-01")["AAA"]["sector_code"] == "UNKNOWN"


def test_live_sector_profile_uses_observed_time_and_rejects_intraday_replay(monkeypatch):
    import pandas as pd
    import omega.quant.portfolio.sector_classifier as sector
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    as_of = datetime.combine(today, datetime.min.time(), tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    profile = pd.DataFrame([{"industryName": "TECH", "exchange": "HOSE"}])
    monkeypatch.setattr(sector, "Vnstock", lambda: SimpleNamespace(
        stock=lambda **kwargs: SimpleNamespace(company=SimpleNamespace(profile=lambda: profile))))
    with pytest.raises(ValueError, match="intraday replay unsupported"):
        get_structure_metadata(["AAA"], as_of, use_cache=False, available_at=as_of)


@pytest.mark.parametrize("date_only", [True, False])
@pytest.mark.parametrize("provenance,lag,expected", [
    (None, -1, "UNKNOWN"), ("provider", -1, "UNKNOWN"),
    ("observed", 1, "UNKNOWN"), ("observed", -1, "UNKNOWN"),
    ("historical_snapshot", -1, "TECH"),
])
def test_historical_sector_cache_requires_observed_provenance_before_cutoff(monkeypatch, date_only, provenance, lag, expected):
    import omega.quant.portfolio.sector_classifier as sector
    cutoff = datetime(2020, 1, 1, 12, tzinfo=timezone.utc)
    key = "2020-01-01" if date_only else cutoff.isoformat()
    row = {"sector_code": "TECH", "exchange_code": "HOSE",
           "available_at": (cutoff + timedelta(days=lag)).isoformat()}
    if provenance is not None:
        row["availability_source"] = provenance
    monkeypatch.setattr(sector, "_load_metadata_cache", lambda: {"AAA": {key: row}})
    monkeypatch.setattr(sector, "Vnstock", lambda: pytest.fail("network contacted"))
    assert get_structure_metadata(["AAA"], key if date_only else cutoff)["AAA"]["sector_code"] == expected


def test_historical_date_string_cache_uses_vietnam_day_end_cutoff(monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    from zoneinfo import ZoneInfo
    day_end = datetime(2020, 1, 1, 23, 59, 59, 999999, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    cache = {symbol: {"2020-01-01": {"sector_code": "TECH", "exchange_code": "HOSE",
                                     "availability_source": "historical_snapshot", "available_at": available}}
             for symbol, available in (("BEFORE", day_end.isoformat()),
                                       ("AFTER", (day_end + timedelta(microseconds=1)).isoformat()),
                                       ("NAIVE", "2020-01-01T10:00:00"))}
    monkeypatch.setattr(sector, "_load_metadata_cache", lambda: cache)
    monkeypatch.setattr(sector, "Vnstock", lambda: pytest.fail("network contacted"))
    result = get_structure_metadata(["BEFORE", "AFTER", "NAIVE"], "2020-01-01")
    assert result["BEFORE"] == {"sector_code": "TECH", "exchange_code": "HOSE"}
    assert result["AFTER"]["sector_code"] == result["NAIVE"]["sector_code"] == "UNKNOWN"


def test_historical_cache_naive_availability_rejected(monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    monkeypatch.setattr(sector, "_load_metadata_cache", lambda: {"AAA": {"2020-01-01": {
        "sector_code": "TECH", "availability_source": "observed", "available_at": "2020-01-01T09:00:00"}}})
    assert get_structure_metadata(["AAA"], "2020-01-01")["AAA"]["sector_code"] == "UNKNOWN"


def test_datetime_cache_key_roundtrip_and_atomic_replace(tmp_path, monkeypatch):
    import json
    import omega.quant.portfolio.sector_classifier as sector
    target = tmp_path / "cache.json"
    original = b'{"metadata":{"OLD":{}}}'
    target.write_bytes(original)
    monkeypatch.setattr(sector, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sector, "METADATA_CACHE_FILE", target)
    key = datetime(2026, 9, 29, 9, tzinfo=timezone.utc)
    sector._save_metadata_cache({"AAA": {key: {"sector_code": "TECH"}}})
    assert json.loads(target.read_text())["metadata"]["AAA"][key.isoformat()]


def test_same_day_cache_roundtrip_preserves_existing_rows(tmp_path, monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    from zoneinfo import ZoneInfo
    target = tmp_path / "cache.json"
    target.write_text(json.dumps({"metadata": {"OLD": {"2020-01-01": {"sector_code": "OLD"}}}}))
    monkeypatch.setattr(sector, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sector, "METADATA_CACHE_FILE", target)
    profile = __import__("pandas").DataFrame([{"industryName": "TECH", "exchange": "HOSE"}])
    monkeypatch.setattr(sector, "Vnstock", lambda: SimpleNamespace(
        stock=lambda **kw: SimpleNamespace(company=SimpleNamespace(profile=lambda: profile))))
    tomorrow = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date() + timedelta(days=1)
    cutoff = datetime.combine(tomorrow, datetime.max.time(), tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    result = get_structure_metadata(["AAA"], cutoff, available_at=cutoff)
    assert result["AAA"]["sector_code"] == "TECH"
    assert "OLD" not in sector._load_metadata_cache()
    assert sector._load_metadata_cache()["AAA"][cutoff.isoformat()]["availability_source"] == "observed"


def test_live_observed_cache_repeat_hit_without_network(tmp_path, monkeypatch):
    import pandas as pd
    import omega.quant.portfolio.sector_classifier as sector
    from zoneinfo import ZoneInfo
    monkeypatch.setattr(sector, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sector, "METADATA_CACHE_FILE", tmp_path / "cache.json")
    calls = []
    def profile():
        calls.append(True)
        return pd.DataFrame([{"industryName": "TECH", "exchange": "HOSE"}])
    monkeypatch.setattr(sector, "Vnstock", lambda: SimpleNamespace(
        stock=lambda **kw: SimpleNamespace(company=SimpleNamespace(profile=profile))))
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    cutoff = datetime.combine(today, datetime.max.time(), tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    first = get_structure_metadata(["AAA"], cutoff, available_at=cutoff)
    monkeypatch.setattr(sector, "Vnstock", lambda: pytest.fail("network contacted on cache hit"))
    second = get_structure_metadata(["AAA"], cutoff, available_at=cutoff)
    assert first["AAA"]["sector_code"] == second["AAA"]["sector_code"] == "TECH"
    assert len(calls) == 1


@pytest.mark.parametrize("source,lag", [("observed", 1), ("provider", -1)])
def test_live_cache_invalid_provenance_or_future_availability_fails_closed(monkeypatch, source, lag):
    import omega.quant.portfolio.sector_classifier as sector
    from zoneinfo import ZoneInfo
    cutoff = datetime.combine(datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date() + timedelta(days=1),
                              datetime.max.time(), tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    cached = {"sector_code": "TECH", "exchange_code": "HOSE", "availability_source": source,
              "available_at": (cutoff + timedelta(days=lag)).isoformat()}
    monkeypatch.setattr(sector, "_load_metadata_cache", lambda: {"AAA": {cutoff.isoformat(): cached}})
    monkeypatch.setattr(sector, "Vnstock", lambda: pytest.fail("network contacted"))
    assert get_structure_metadata(["AAA"], cutoff, available_at=cutoff)["AAA"]["sector_code"] == "UNKNOWN"


@pytest.mark.parametrize("failure", ["serialize", "write", "fsync", "replace"])
def test_cache_save_failure_preserves_existing_file(tmp_path, monkeypatch, failure):
    import omega.quant.portfolio.sector_classifier as sector
    target = tmp_path / "cache.json"
    original = b'{"metadata":{"OLD":{}}}'
    target.write_bytes(original)
    monkeypatch.setattr(sector, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sector, "METADATA_CACHE_FILE", target)
    if failure == "serialize":
        monkeypatch.setattr(sector.json, "dumps", lambda *a, **k: (_ for _ in ()).throw(TypeError("serialize failed")))
    elif failure == "write":
        original_fdopen = sector.os.fdopen
        def fail_write(fd, *args, **kwargs):
            stream = original_fdopen(fd, *args, **kwargs)
            class BrokenStream:
                def __enter__(self): return self
                def __exit__(self, *exc): stream.close()
                def write(self, payload):
                    stream.write(payload[:8])
                    raise OSError("write failed")
            return BrokenStream()
        monkeypatch.setattr(sector.os, "fdopen", fail_write)
    elif failure == "fsync":
        monkeypatch.setattr(sector.os, "fsync", lambda *a: (_ for _ in ()).throw(OSError("fsync failed")))
    else:
        monkeypatch.setattr(sector.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises((TypeError, OSError)):
        sector._save_metadata_cache({"AAA": {"2026-09-29": {"sector_code": "TECH"}}})
    assert target.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []


def test_cache_load_corruption_surfaces_without_overwrite(tmp_path, monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    target = tmp_path / "cache.json"
    target.write_text("{broken")
    monkeypatch.setattr(sector, "METADATA_CACHE_FILE", target)
    with pytest.raises(ValueError, match="Failed to load metadata cache"):
        get_structure_metadata(["AAA"], "2020-01-01")
    assert target.read_text() == "{broken"


def test_metadata_cache_prunes_expired_but_keeps_active(tmp_path, monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    monkeypatch.setattr(sector, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sector, "METADATA_CACHE_FILE", tmp_path / "cache.json")
    now = datetime.now(timezone.utc)
    active = now.isoformat()
    expired = (now - timedelta(days=sector.CACHE_EXPIRY_DAYS + 1)).isoformat()
    sector._save_metadata_cache({"AAA": {active: {"sector_code": "TECH"},
                                           expired: {"sector_code": "OLD"}}})
    assert sector._load_metadata_cache() == {"AAA": {active: {"sector_code": "TECH"}}}


def test_metadata_cache_limits_entries_and_roundtrips_large_cache(tmp_path, monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    monkeypatch.setattr(sector, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sector, "METADATA_CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(sector, "MAX_METADATA_CACHE_ENTRIES", 80)
    now = datetime.now(timezone.utc)
    metadata = {f"S{i:05d}": {now.isoformat(): {"sector_code": "X" * 1000}}
                for i in range(12000)}
    sector._save_metadata_cache(metadata)
    loaded = sector._load_metadata_cache()
    assert len(loaded) == 80
    assert (tmp_path / "cache.json").stat().st_size < sector.MAX_METADATA_CACHE_BYTES // 2
    assert loaded["S00000"][now.isoformat()] == metadata["S00000"][now.isoformat()]


def test_metadata_cache_size_limit_crossing_retains_recent_entries(tmp_path, monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    monkeypatch.setattr(sector, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sector, "METADATA_CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(sector, "MAX_METADATA_CACHE_WRITE_BYTES", 1024)
    now = datetime.now(timezone.utc)
    recent = now.isoformat()
    older = (now - timedelta(hours=1)).isoformat()
    sector._save_metadata_cache({"AAA": {recent: {"sector_code": "A" * 500},
                                           older: {"sector_code": "B" * 500}}})
    assert sector._load_metadata_cache() == {"AAA": {recent: {"sector_code": "A" * 500}}}
    assert (tmp_path / "cache.json").stat().st_size <= 1024


def test_metadata_cache_oversize_entry_fails_before_publication(tmp_path, monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    target = tmp_path / "cache.json"
    target.write_bytes(b'{"metadata":{"OLD":{}}}')
    original = target.read_bytes()
    monkeypatch.setattr(sector, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sector, "METADATA_CACHE_FILE", target)
    monkeypatch.setattr(sector, "MAX_METADATA_CACHE_WRITE_BYTES", 1024)
    with pytest.raises(ValueError, match="write limit"):
        sector._save_metadata_cache({"AAA": {datetime.now(timezone.utc).isoformat():
                                              {"sector_code": "X" * 2000}}})
    assert target.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []


def test_contagion_extreme_finite_returns_zero_exposure():
    from omega.quant.portfolio.contagion_overlay import compute_correlation_spike_exposure
    matrix = np.random.default_rng(4).normal(size=(130, 10)) * 1e200
    assert np.isfinite(matrix).all()
    assert np.array_equal(compute_correlation_spike_exposure(matrix), np.zeros(130))


def test_contagion_local_constant_window_zeroes_exposure_and_weights():
    import pandas as pd
    from omega.quant.portfolio.contagion_overlay import apply_contagion_overlay
    matrix = np.random.default_rng(4).normal(size=(130, 5))
    matrix[:60, 0] = 1.0
    assert np.ptp(matrix[:, 0]) > 0
    adjusted = apply_contagion_overlay(pd.DataFrame(np.ones_like(matrix)), matrix)
    assert (adjusted.to_numpy() == 0).all()


def test_f001_historical_metadata_future_available_at_is_unknown(monkeypatch):
    """F-001: cached metadata with available_at beyond as_of_date returns UNKNOWN."""
    import omega.quant.portfolio.sector_classifier as sector
    cutoff = datetime(2020, 1, 1, 12, tzinfo=timezone.utc)
    future_available = (cutoff + timedelta(days=2)).isoformat()
    monkeypatch.setattr(sector, "_load_metadata_cache", lambda: {
        "AAA": {cutoff.isoformat(): {
            "sector_code": "TECH", "exchange_code": "HOSE",
            "available_at": future_available, "availability_source": "observed"
        }}
    })
    monkeypatch.setattr(sector, "Vnstock", lambda: pytest.fail("network contacted"))
    result = get_structure_metadata(["AAA"], cutoff)
    assert result["AAA"]["sector_code"] == "UNKNOWN"
    assert result["AAA"]["exchange_code"] == "UNKNOWN"


def test_f001_sector_mapping_pit_date_boundary_isolation():
    """F-001: historical sector mapping isolates dates and rejects lookahead changes."""
    from omega.quant.portfolio.sector_classifier import SectorClassifier
    import pandas as pd
    classifier = SectorClassifier()
    history = pd.DataFrame([
        {"ticker": "AAA", "sector_code": "OLD_SECTOR", "effective_date": "2020-01-01"},
        {"ticker": "AAA", "sector_code": "NEW_SECTOR", "effective_date": "2024-01-01"},
    ])
    early = classifier.get_sector_mapping_pit("2023-12-31", sector_history=history)
    assert early["AAA"] == "OLD_SECTOR"
    late = classifier.get_sector_mapping_pit("2024-01-01", sector_history=history)
    assert late["AAA"] == "NEW_SECTOR"
    pre_history = classifier.get_sector_mapping_pit("2019-12-31", sector_history=history)
    assert "AAA" not in pre_history


def test_f001_structure_features_never_backfill_current_profile():
    import pandas as pd
    from omega.quant.portfolio.sector_classifier import SectorClassifier
    panel = pd.DataFrame({'date': pd.to_datetime(['2020-01-01', '2020-01-03']),
                          'ticker': ['AAA', 'AAA'], 'close': [20000, 21000]})
    current = {'AAA': {'sector_code': 'FUTURE', 'exchange_code': 'HOSE'}}
    result = SectorClassifier().compute_structure_features(panel, current)
    assert result['sector_code'].tolist() == ['UNKNOWN', 'UNKNOWN']
    snapshots = {'AAA': {'2020-01-02': {'sector_code': 'KNOWN', 'exchange_code': 'HOSE',
                                         'availability_source': 'historical_snapshot',
                                         'available_at': '2020-01-02T00:00:00+00:00'}}}
    result = SectorClassifier().compute_structure_features(panel, snapshots)
    assert result['sector_code'].tolist() == ['UNKNOWN', 'KNOWN']
    with pytest.raises(ValueError, match='feature date exceeds'):
        SectorClassifier().compute_structure_features(panel, {}, as_of_date='2020-01-02')


@pytest.mark.parametrize('effective,available,expected', [
    ('2020-01-04', '2020-01-01T00:00:00+00:00', ['UNKNOWN', 'KNOWN']),
    ('2020-01-01', '2020-01-04T00:00:00+00:00', ['UNKNOWN', 'KNOWN']),
])
def test_f001_snapshot_requires_both_effective_and_available_date(effective, available, expected):
    import pandas as pd
    from omega.quant.portfolio.sector_classifier import SectorClassifier
    panel = pd.DataFrame({'date': ['2020-01-03', '2020-01-05'],
                          'ticker': ['AAA', 'AAA'], 'close': [20000, 21000]})
    snapshots = {'AAA': {effective: {'sector_code': 'KNOWN', 'exchange_code': 'HOSE',
                                    'availability_source': 'historical_snapshot', 'available_at': available}}}
    assert SectorClassifier().compute_structure_features(panel, snapshots)['sector_code'].tolist() == expected


def test_f002_scoped_validator_rejects_future_event_before_publication(tmp_path):
    item = event()
    item['available_at'] = CUTOFF + timedelta(seconds=1)
    item = sign_event(item)
    ledger = tmp_path / 'ledger'
    manager = RiskManager(RiskManagerConfig(risk_log_path=str(tmp_path / 'risk.jsonl'),
                                            event_advisory_ledger_path=str(ledger)))
    with pytest.raises(ValueError, match='unavailable'):
        manager.evaluate_event_advisory(item, SimpleNamespace(get_symbol_weights=lambda: {'AAA': .2}), CUTOFF)
    assert not ledger.exists()


def test_f001_live_observed_cache_cannot_be_replayed_historically(monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    cutoff = datetime(2020, 1, 1, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(sector, '_load_metadata_cache', lambda: {'AAA': {cutoff.isoformat(): {
        'sector_code': 'FUTURE', 'exchange_code': 'HOSE', 'availability_source': 'observed',
        'available_at': '2019-12-31T00:00:00+00:00'}}})
    assert sector.get_structure_metadata(['AAA'], cutoff)['AAA']['sector_code'] == 'UNKNOWN'


@pytest.mark.parametrize('kind', ['invalid_utf8', 'bom', 'oversize'])
def test_f004_cache_rejects_non_utf8_and_oversize(tmp_path, monkeypatch, kind):
    import omega.quant.portfolio.sector_classifier as sector
    target = tmp_path / 'cache.json'
    content = {'invalid_utf8': b'\xff', 'bom': b'\xef\xbb\xbf{}'}
    target.write_bytes(content.get(kind, b' ' * (8 * 1024 * 1024 + 1)))
    monkeypatch.setattr(sector, 'METADATA_CACHE_FILE', target)
    with pytest.raises(ValueError, match='Failed to load metadata cache'):
        sector._load_metadata_cache()


def test_f004_cache_rejects_directory(tmp_path, monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    monkeypatch.setattr(sector, 'METADATA_CACHE_FILE', tmp_path)
    with pytest.raises(ValueError, match='Failed to load metadata cache'):
        sector._load_metadata_cache()


def test_f004_cache_directory_sync_failure_surfaces_committed_file(tmp_path, monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    target = tmp_path / 'cache.json'
    target.write_text('{"metadata":{}}', encoding='utf-8')
    monkeypatch.setattr(sector, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(sector, 'METADATA_CACHE_FILE', target)
    key = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(sector, '_sync_cache_directory', lambda: (_ for _ in ()).throw(OSError('directory sync failed')))
    with pytest.raises(OSError, match='directory sync failed'):
        sector._save_metadata_cache({'AAA': {key: {'sector_code': 'KNOWN'}}})
    assert sector._load_metadata_cache()['AAA'][key]['sector_code'] == 'KNOWN'
    assert not list(tmp_path.glob('*.tmp'))


def test_f004_cache_directory_sync_transient_failure_recovers(tmp_path, monkeypatch):
    import omega.quant.portfolio.sector_classifier as sector
    target = tmp_path / 'cache.json'
    monkeypatch.setattr(sector, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(sector, 'METADATA_CACHE_FILE', target)
    key = datetime.now(timezone.utc).isoformat()
    calls = []
    def sync_once():
        calls.append(True)
        if len(calls) == 1:
            raise OSError('transient directory sync failure')
    monkeypatch.setattr(sector, '_sync_cache_directory', sync_once)
    sector._save_metadata_cache({'AAA': {key: {'sector_code': 'KNOWN'}}})
    assert len(calls) == 2
    assert sector._load_metadata_cache()['AAA'][key]['sector_code'] == 'KNOWN'


def test_f004_risk_log_failure_never_approves_portfolio(tmp_path):
    from omega.risk.models import RiskViolation
    config = RiskManagerConfig(risk_log_path=str(tmp_path / 'risk_dir'))
    (tmp_path / 'risk_dir').mkdir()
    manager = RiskManager(config)
    portfolio = SimpleNamespace(get_symbol_weights=lambda: {})
    assert isinstance(manager.evaluate(portfolio), RiskViolation)


def test_f003_windows_advisory_rejection_leaves_no_side_effects(tmp_path, monkeypatch):
    """F-003: Windows publication rejection fails closed before creating ledger dir."""
    import omega.risk.risk_manager as module
    monkeypatch.setattr(module.os, "name", "nt")
    ledger = tmp_path / "never_created_ledger"
    config = RiskManagerConfig(event_advisory_ledger_path=str(ledger))
    with pytest.raises(OSError, match="durable advisory publication is unsupported on Windows"):
        RiskManager(config).evaluate_event_advisory(event(), SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2}), CUTOFF)
    assert not ledger.exists()
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob("*.json"))


def test_f003_windows_supported_platform_contract(tmp_path, monkeypatch):
    """F-003: existing ledger directory left unmodified upon Windows rejection."""
    import omega.risk.risk_manager as module
    monkeypatch.setattr(module.os, "name", "nt")
    ledger = tmp_path / "existing_ledger"
    ledger.mkdir()
    sentinel = ledger / "sentinel.txt"
    sentinel.write_text("untouched")
    config = RiskManagerConfig(event_advisory_ledger_path=str(ledger))
    with pytest.raises(OSError, match="durable advisory publication is unsupported on Windows"):
        RiskManager(config).evaluate_event_advisory(event(), SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2}), CUTOFF)
    assert sentinel.read_text() == "untouched"
    assert list(ledger.glob("*.tmp")) == []
    assert list(ledger.glob("*.json")) == []


def test_f004_post_link_directory_sync_failure_cleans_temp_and_recovers(tmp_path, monkeypatch):
    """F-004: post-link directory fsync failure cleans up staging tmp and recovers on retry."""
    import omega.risk.risk_manager as module
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    config = RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                               event_advisory_ledger_path=str(ledger))
    manager = RiskManager(config)
    portfolio = SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2})

    orig_open = module.os.open
    orig_fsync = module.os.fsync
    orig_close = module.os.close

    def mock_open(path, flags, *args):
        if str(path) == str(ledger):
            return 8888
        return orig_open(path, flags, *args)

    def mock_close(fd):
        if fd == 8888:
            return
        return orig_close(fd)

    failed = False
    def mock_fsync_fail_first_dir(fd):
        nonlocal failed
        if fd == 8888:
            if not failed:
                failed = True
                raise OSError("directory sync failed")
            return
        return orig_fsync(fd)

    monkeypatch.setattr(module.os, "name", "posix")
    monkeypatch.setattr(module.os, "open", mock_open)
    monkeypatch.setattr(module.os, "close", mock_close)
    monkeypatch.setattr(module.os, "fsync", mock_fsync_fail_first_dir)

    assert manager.evaluate_event_advisory(event(), portfolio, CUTOFF)

    assert list(ledger.glob("*.tmp")) == []
    json_files = list(ledger.glob("*.json"))
    assert len(json_files) == 1

    retried = manager.evaluate_event_advisory(event(), portfolio, CUTOFF)
    assert retried["decision_id"] == json_files[0].stem


def test_f004_staging_unlink_failure_leaves_orphan_tmp_but_acknowledges_existing(tmp_path, monkeypatch):
    """F-004: staging unlink failure after commit leaves tmp but retry acknowledges existing."""
    import omega.risk.risk_manager as module
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    config = RiskManagerConfig(risk_log_path=str(tmp_path / "risk.jsonl"),
                               event_advisory_ledger_path=str(ledger))
    manager = RiskManager(config)
    portfolio = SimpleNamespace(get_symbol_weights=lambda: {"AAA": .2})

    orig_open = module.os.open
    orig_close = module.os.close
    orig_fsync = module.os.fsync
    orig_unlink = module.os.unlink

    def mock_open(path, flags, *args):
        if str(path) == str(ledger):
            return 8888
        return orig_open(path, flags, *args)

    def mock_close(fd):
        if fd == 8888:
            return
        return orig_close(fd)

    def mock_fsync(fd):
        if fd == 8888:
            return
        return orig_fsync(fd)

    def mock_unlink_fail(path):
        if str(path).endswith(".tmp"):
            raise OSError("staging unlink failed")
        return orig_unlink(path)

    monkeypatch.setattr(module.os, "name", "posix")
    monkeypatch.setattr(module.os, "open", mock_open)
    monkeypatch.setattr(module.os, "close", mock_close)
    monkeypatch.setattr(module.os, "fsync", mock_fsync)
    monkeypatch.setattr(module.os, "unlink", mock_unlink_fail)

    assert manager.evaluate_event_advisory(event(), portfolio, CUTOFF)

    assert len(list(ledger.glob("*.tmp"))) == 1
    assert len(list(ledger.glob("*.json"))) == 1

    retried = manager.evaluate_event_advisory(event(), portfolio, CUTOFF)
    assert retried["decision_id"] == list(ledger.glob("*.json"))[0].stem


def test_f004_sector_cache_save_temp_cleanup_on_replace_failure(tmp_path, monkeypatch):
    """F-004: cache save temp file cleaned up when atomic replace fails."""
    import omega.quant.portfolio.sector_classifier as sector
    target = tmp_path / "cache.json"
    target.write_bytes(b'{"metadata":{}}')
    monkeypatch.setattr(sector, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sector, "METADATA_CACHE_FILE", target)
    monkeypatch.setattr(sector.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("replace disk full")))
    with pytest.raises(OSError, match="replace disk full"):
        sector._save_metadata_cache({"AAA": {"2026-09-29": {"sector_code": "TECH"}}})
    assert list(tmp_path.glob("*.tmp")) == []


def test_f005_partial_sector_cache_fetches_missing_symbols(monkeypatch):
    """F-005: subsequent symbol lookups fetch missing entries, never return unrelated cache."""
    from omega.quant.portfolio.sector_classifier import SectorClassifier
    import pandas as pd
    import vnstock
    monkeypatch.setattr(vnstock, 'Listing', lambda **kw: SimpleNamespace(
        symbols_by_industries=lambda: pd.DataFrame([{'symbol': 'BBB', 'industry_code_group': 'STEEL'}])))
    classifier = SectorClassifier()
    classifier._sector_cache = {"AAA": "TECH"}
    result = classifier.fetch_sector_mapping(["BBB"])
    assert result == {"BBB": "STEEL"}
    assert classifier.fetch_sector_mapping(["AAA", "BBB"]) == {"AAA": "TECH", "BBB": "STEEL"}


def test_f005_get_sector_mapping_pit_omits_unmapped_symbols():
    """F-005: PIT mapping for partial history omits symbols without records."""
    from omega.quant.portfolio.sector_classifier import SectorClassifier
    import pandas as pd
    classifier = SectorClassifier()
    history = pd.DataFrame([
        {"ticker": "AAA", "sector_code": "TECH", "effective_date": "2020-01-01"},
    ])
    mapping = classifier.get_sector_mapping_pit("2024-01-01", sector_history=history)
    assert "AAA" in mapping
    assert "BBB" not in mapping
