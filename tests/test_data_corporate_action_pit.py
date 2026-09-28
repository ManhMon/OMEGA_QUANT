from datetime import UTC, datetime, timedelta, timezone

import pandas as pd
import pytest

from omega.data.corporate_action import CorporateAction, CorporateActionAdjuster, create_dividend_action
from omega.data.loader import DataLoader


def _base_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["VNM", "VNM"],
            "date": pd.to_datetime(["2026-05-30", "2026-06-01"]),
            "open": [100.0, 102.0],
            "high": [101.0, 103.0],
            "low": [99.0, 101.0],
            "close": [100.0, 102.0],
            "volume": [1000, 1100],
            "as_of": pd.to_datetime(["2026-06-01T10:00:00Z", "2026-06-01T10:00:00Z"], utc=True),
            "available_at": pd.to_datetime(["2026-05-30T15:00:00Z", "2026-06-01T15:00:00Z"], utc=True),
        }
    )


def test_corporate_action_enforces_available_at_invariant() -> None:
    with pytest.raises(ValueError, match="available_at must equal max"):
        CorporateAction(
            symbol="VNM",
            ex_date="2026-06-01",
            action_type="dividend",
            dividend_amount=10.0,
            announced_at=datetime(2026, 5, 31, 0, 0, tzinfo=UTC),
            ingested_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
            available_at=datetime(2026, 6, 1, 7, 59, tzinfo=UTC),
            source="exchange_notice",
        )


def test_create_dividend_action_without_recorded_provenance_is_quarantined() -> None:
    action = create_dividend_action("VNM", "2026-06-01", 10.0)
    assert action.is_quarantined
    assert action.available_at is None
    assert not action.is_available_at(datetime(2026, 6, 1, 10, tzinfo=UTC))


def test_apply_corporate_actions_filters_by_available_at() -> None:
    loader = DataLoader(validate_provenance=False, is_already_adjusted=False)
    action = create_dividend_action(
        "VNM",
        "2026-06-01",
        10.0,
        announced_at=datetime(2026, 5, 31, 0, 0, tzinfo=UTC),
        ingested_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        available_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        source="exchange_notice",
    )

    adjusted_df, adjustments = loader._apply_corporate_actions(
        df=_base_df(),
        ticker="VNM",
        corporate_actions=[action],
        as_of_time=datetime(2026, 6, 1, 7, 59, tzinfo=UTC),
    )

    pd.testing.assert_frame_equal(adjusted_df, _base_df())
    assert adjustments == []


def test_apply_corporate_actions_quarantines_unverified_actions(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")
    loader = DataLoader(validate_provenance=False, is_already_adjusted=False)
    action = CorporateAction(symbol="VNM", ex_date="2026-06-01", action_type="dividend", dividend_amount=10.0)

    adjusted_df, adjustments = loader._apply_corporate_actions(
        df=_base_df(),
        ticker="VNM",
        corporate_actions=[action],
        as_of_time=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
    )

    pd.testing.assert_frame_equal(adjusted_df, _base_df())
    assert adjustments == []
    assert "Quarantined unverified corporate action" in caplog.text


def test_apply_corporate_actions_applies_verified_available_action() -> None:
    loader = DataLoader(validate_provenance=False, is_already_adjusted=False)
    action = create_dividend_action(
        "VNM",
        "2026-06-01",
        10.0,
        announced_at=datetime(2026, 5, 31, 0, 0, tzinfo=UTC),
        ingested_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        available_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        source="exchange_notice",
    )

    adjusted_df, adjustments = loader._apply_corporate_actions(
        df=_base_df(),
        ticker="VNM",
        corporate_actions=[action],
        as_of_time=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
    )

    assert adjustments == ["dividend:2026-06-01:10.0"]
    assert adjusted_df.loc[0, "close"] == 90.0
    assert adjusted_df.loc[1, "close"] == 102.0


def test_adjuster_excludes_late_ingested_earlier_ex_date() -> None:
    data = {"type": "CleanDataFrame", "price_basis": "raw", "data": {"VNM": {
        "2026-05-29": {"close": 100.0}, "2026-06-01": {"close": 102.0},
    }}}
    action = create_dividend_action(
        "VNM", "2026-06-01", 10.0,
        announced_at=datetime(2026, 5, 28, tzinfo=UTC),
        ingested_at=datetime(2026, 6, 2, tzinfo=UTC),
        available_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="exchange_notice",
    )
    adjuster = CorporateActionAdjuster()
    adjuster.add_action(action)
    before = datetime(2026, 6, 1, 12, tzinfo=UTC)
    assert adjuster.apply_adjustments(data, as_of_time=before)["data"]["VNM"]["2026-05-29"]["close"] == 100.0
    assert adjuster.apply_adjustments(data, as_of_time=action.available_at)["data"]["VNM"]["2026-05-29"]["close"] == 90.0
    with pytest.raises(ValueError, match="timezone-aware"):
        adjuster.apply_adjustments(data, as_of_time=datetime(2026, 6, 1))


def test_adjuster_rejects_missing_time_and_unknown_basis() -> None:
    adjuster = CorporateActionAdjuster()
    with pytest.raises(TypeError, match="as_of_time"):
        adjuster.apply_adjustments({"price_basis": "raw"})
    for basis in (None, "vendor_adjusted", "RAW"):
        with pytest.raises(ValueError, match="price_basis"):
            adjuster.apply_adjustments({"price_basis": basis}, as_of_time=datetime.now(UTC))


@pytest.mark.parametrize("module", ["omega.data.pipeline.production_pipeline", "omega.data.production_data_pipeline"])
def test_pipeline_adjusted_prices_and_atomic_failure(module, tmp_path, monkeypatch) -> None:
    import importlib
    import json

    pipeline_module = importlib.import_module(module)
    pipeline = pipeline_module.ProductionDataPipeline(
        str(tmp_path / "input.parquet"), str(tmp_path / "output.parquet"),
        cache_dir=str(tmp_path / "cache"), as_of_time=datetime(2026, 6, 2, tzinfo=UTC),
    )
    df = pd.DataFrame({"symbol": ["VNM", "VNM"], "timestamp": pd.to_datetime(["2026-05-29", "2026-06-01"]),
                       "open": [90., 102.], "high": [90., 102.], "low": [90., 102.],
                       "close": [90., 102.], "volume": [1000, 1100], "price_basis": ["adjusted", "adjusted"]})
    pipeline.corp_action_adjuster.add_action(create_dividend_action(
        "VNM", "2026-06-01", 10., announced_at=datetime(2026, 5, 28, tzinfo=UTC),
        ingested_at=datetime(2026, 5, 28, tzinfo=UTC), available_at=datetime(2026, 5, 28, tzinfo=UTC),
        source="exchange_notice"))
    pd.testing.assert_frame_equal(pipeline._apply_corporate_actions(df), df)
    for basis in ("unknown", None):
        with pytest.raises(ValueError, match="price_basis"):
            pipeline._apply_corporate_actions(df.assign(price_basis=basis))
    path = pipeline.output_path
    report_path = path.with_name(f"{path.stem}_quality_report.json")
    pipeline._l8_save_output(df, {"version": 1})
    original_parquet, original_report = path.read_bytes(), report_path.read_bytes()
    assert pd.read_parquet(path).loc[0, "close"] == 90.
    assert json.loads(original_report)["version"] == 1

    def fail_fsync(_):
        raise OSError("disk failure")

    monkeypatch.setattr(pipeline_module.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="disk failure"):
        pipeline._l8_save_output(df.assign(close=1.), {"version": 2})
    assert path.read_bytes() == original_parquet
    assert report_path.read_bytes() == original_report
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("module", ["omega.data.pipeline.production_pipeline", "omega.data.production_data_pipeline"])
@pytest.mark.parametrize("existing", [True, False])
def test_pipeline_second_replace_failure_restores_pair(module, existing, tmp_path, monkeypatch) -> None:
    import importlib

    pipeline_module = importlib.import_module(module)
    pipeline = pipeline_module.ProductionDataPipeline(
        str(tmp_path / "input.parquet"), str(tmp_path / "output.parquet"),
        cache_dir=str(tmp_path / "cache"), as_of_time=datetime(2026, 6, 2, tzinfo=UTC),
    )
    path = pipeline.output_path
    report_path = path.with_name(f"{path.stem}_quality_report.json")
    df = pd.DataFrame({"close": [100.]})
    if existing:
        pipeline._l8_save_output(df, {"version": 1})
    before = {p: p.read_bytes() if p.exists() else None for p in (path, report_path)}
    publisher = importlib.import_module("omega.data.pipeline.production_pipeline")
    replace = publisher.os.replace
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("second replacement failed")
        return replace(source, target)

    monkeypatch.setattr(publisher.os, "replace", fail_second)
    with pytest.raises(OSError, match="second replacement failed"):
        pipeline._l8_save_output(df.assign(close=200.), {"version": 2})
    assert {p: p.read_bytes() if p.exists() else None for p in (path, report_path)} == before
    assert not list(tmp_path.glob("*.tmp"))


def test_adjuster_rejects_overflowing_split_and_adjusted_prices() -> None:
    adjuster = CorporateActionAdjuster()
    provenance = dict(announced_at=datetime(2026, 5, 28, tzinfo=UTC),
                      ingested_at=datetime(2026, 5, 28, tzinfo=UTC),
                      available_at=datetime(2026, 5, 28, tzinfo=UTC), source="exchange_notice")
    data = {"type": "CleanDataFrame", "price_basis": "raw", "data": {"VNM": {
        "2026-05-29": {"open": 100., "high": 100., "low": 100., "close": 100.},
        "2026-06-01": {"close": 102.},
    }}}
    action = CorporateAction("VNM", "2026-06-01", "split", split_ratio=1e-320, **provenance)
    adjuster.add_action(action)
    with pytest.raises(ValueError, match="Invalid split ratio"):
        adjuster.apply_adjustments(data, as_of_time=datetime(2026, 6, 2, tzinfo=UTC))
    adjuster.clear_actions()
    adjuster.add_action(CorporateAction("VNM", "2026-06-01", "split", split_ratio=0.5, **provenance))
    for field in ("open", "high", "low", "close"):
        overflowing = {**data, "data": {"VNM": {**data["data"]["VNM"],
            "2026-05-29": {**data["data"]["VNM"]["2026-05-29"], field: 1e308}}}}
        with pytest.raises(ValueError, match="Non-finite adjusted price"):
            adjuster.apply_adjustments(overflowing, as_of_time=datetime(2026, 6, 2, tzinfo=UTC))


def test_split_volume_overflow_rejected() -> None:
    action = CorporateAction("VNM", "2026-06-01", "split", split_ratio=2.0,
                             announced_at=datetime(2026, 5, 28, tzinfo=UTC),
                             ingested_at=datetime(2026, 5, 28, tzinfo=UTC),
                             available_at=datetime(2026, 5, 28, tzinfo=UTC), source="exchange")
    adjuster = CorporateActionAdjuster()
    adjuster.add_action(action)
    data = {"price_basis": "raw", "data": {"VNM": {
        "2026-05-29": {"close": 100., "volume": 1e308}, "2026-06-01": {"close": 50.}}}}
    with pytest.raises(ValueError, match="Non-finite adjusted volume"):
        adjuster.apply_adjustments(data, as_of_time=datetime(2026, 6, 2, tzinfo=UTC))


@pytest.mark.parametrize("module", ["omega.data.pipeline.production_pipeline", "omega.data.production_data_pipeline"])
def test_pipeline_rejects_non_utc(module, tmp_path) -> None:
    import importlib
    pipeline = importlib.import_module(module).ProductionDataPipeline
    with pytest.raises(ValueError, match="UTC"):
        pipeline(str(tmp_path / "in"), str(tmp_path / "out"),
                 cache_dir=str(tmp_path / "cache"),
                  as_of_time=datetime(2026, 6, 2, tzinfo=timezone(timedelta(hours=7))))


@pytest.mark.parametrize("module", ["omega.data.pipeline.production_pipeline", "omega.data.production_data_pipeline"])
@pytest.mark.parametrize("hour,applies", [(16, False), (17, True), (18, True)])
def test_pipeline_ex_date_uses_ict_midnight(module, hour, applies, tmp_path, monkeypatch):
    import importlib
    pipeline_module = importlib.import_module(module)
    monkeypatch.setattr(pipeline_module, "DEFAULT_EVENT_HISTORY_PATH", tmp_path / "history.sqlite")
    as_of = datetime(2026, 6, 1, hour, tzinfo=UTC)
    pipeline = pipeline_module.ProductionDataPipeline(
        str(tmp_path / "input.parquet"), str(tmp_path / "out.parquet"),
        cache_dir=str(tmp_path / "cache"), as_of_time=as_of,
    )
    action = create_dividend_action(
        "VNM", "2026-06-02", 10., announced_at=datetime(2026, 5, 29, tzinfo=UTC),
        ingested_at=datetime(2026, 5, 29, tzinfo=UTC),
        available_at=datetime(2026, 5, 29, tzinfo=UTC), source="exchange_notice",
    )
    pipeline.corp_action_adjuster.add_action(action)
    df = pd.DataFrame({"symbol": ["VNM", "VNM"], "timestamp": pd.to_datetime(["2026-06-01", "2026-06-02"]),
                       "open": [100., 100.], "high": [100., 100.], "low": [100., 100.],
                       "close": [100., 100.], "volume": [1000, 1000], "price_basis": ["raw", "raw"]})
    result = pipeline._apply_corporate_actions(df)
    assert result.loc[result["timestamp"] == pd.Timestamp("2026-06-01"), "close"].iloc[0] == (90. if applies else 100.)


def test_adjuster_rejects_non_utc_even_without_actions() -> None:
    with pytest.raises(ValueError, match="UTC"):
        CorporateActionAdjuster().apply_adjustments({"price_basis": "raw"},
            as_of_time=datetime(2026, 6, 2, tzinfo=timezone(timedelta(hours=7))))


def test_pipeline_restore_failure_preserves_backups(tmp_path, monkeypatch) -> None:
    import omega.data.pipeline.production_pipeline as publisher
    output = tmp_path / "output.parquet"
    report = tmp_path / "output_quality_report.json"
    publisher._publish_output_pair(output, pd.DataFrame({"close": [1.]}), {"version": 1})
    before = (output.read_bytes(), report.read_bytes())
    replace = publisher.os.replace
    calls = 0

    def fail(source, target):
        nonlocal calls
        calls += 1
        if calls in (2, 4):
            raise OSError(f"replace {calls} failed")
        return replace(source, target)

    monkeypatch.setattr(publisher.os, "replace", fail)
    with pytest.raises(OSError, match="replace 2 failed"):
        publisher._publish_output_pair(output, pd.DataFrame({"close": [2.]}), {"version": 2})
    assert report.read_bytes() == before[1]
    assert before[0] in [p.read_bytes() for p in tmp_path.glob("output.parquet.*.tmp")]


@pytest.mark.parametrize("module", ["omega.data.pipeline.production_pipeline", "omega.data.production_data_pipeline"])
def test_pipeline_filters_future_availability_before_fit(module, tmp_path, monkeypatch):
    import importlib
    pipeline = importlib.import_module(module).ProductionDataPipeline(
        str(tmp_path / "input.parquet"), str(tmp_path / "out.parquet"),
        cache_dir=str(tmp_path / "cache"), as_of_time=datetime(2026, 6, 2, tzinfo=UTC))
    frame = pd.DataFrame({"symbol": ["VNM", "VNM"], "timestamp": pd.to_datetime(["2026-06-01", "2026-06-02"]),
        "available_at": ["2026-06-02T00:00:00Z", "2026-06-03T00:00:00Z"],
        "price_basis": ["adjusted", "adjusted"], "close": [100., 999.]})
    frame.to_parquet(pipeline.input_path)
    def observe_fit(rows, **kwargs):
        assert rows["close"].tolist() == [100.]
        raise RuntimeError("fit observed")
    monkeypatch.setattr(pipeline.sanitizer, "fit", observe_fit)
    with pytest.raises(RuntimeError, match="fit observed"):
        pipeline.run()
    frame["available_at"] = ["2026-06-03T00:00:00Z"] * 2
    frame.to_parquet(pipeline.input_path)
    with pytest.raises(ValueError, match="no rows available"):
        pipeline.run()


def test_output_pair_manifest_commits_only_after_both_generations(tmp_path, monkeypatch):
    import omega.data.pipeline.production_pipeline as publisher
    output = tmp_path / "out.parquet"
    publisher._publish_output_pair(output, pd.DataFrame({"close": [1.]}), {"version": 1})
    replace = publisher.os.replace
    def fail_manifest(source, target):
        if str(target).endswith(".manifest.json"):
            raise OSError("manifest commit failed")
        return replace(source, target)
    monkeypatch.setattr(publisher.os, "replace", fail_manifest)
    with pytest.raises(OSError, match="manifest commit failed"):
        publisher._publish_output_pair(output, pd.DataFrame({"close": [2.]}), {"version": 2})
    data, report = publisher.read_output_pair(output)
    assert data["close"].tolist() == [1.]
    assert report == {"version": 1}


def test_output_pair_sync_failure_restores_pointer_and_legacy(tmp_path, monkeypatch):
    import omega.data.pipeline.production_pipeline as publisher
    output = tmp_path / "out.parquet"
    publisher._publish_output_pair(output, pd.DataFrame({"close": [1.]}), {"version": 1})
    manifest = tmp_path / "out.parquet.manifest.json"
    before = manifest.read_bytes()
    sync = publisher._sync_parent
    failed = False

    def fail_after_replace(path):
        nonlocal failed
        if path == manifest and not failed:
            failed = True
            raise OSError("manifest sync failed")
        sync(path)

    monkeypatch.setattr(publisher, "_sync_parent", fail_after_replace)
    with pytest.raises(OSError, match="manifest sync failed"):
        publisher._publish_output_pair(output, pd.DataFrame({"close": [2.]}), {"version": 2})
    assert manifest.read_bytes() == before
    for reader in (publisher.read_output_pair, publisher.read_legacy_output_pair):
        data, report = reader(output)
        assert data["close"].tolist() == [1.]
        assert report == {"version": 1}


def test_output_pair_first_publish_sync_failure_removes_pointer(tmp_path, monkeypatch):
    import omega.data.pipeline.production_pipeline as publisher
    output = tmp_path / "out.parquet"
    manifest = tmp_path / "out.parquet.manifest.json"
    sync = publisher._sync_parent
    failed = False

    def fail_after_replace(path):
        nonlocal failed
        if path == manifest and not failed:
            failed = True
            raise OSError("manifest sync failed")
        sync(path)

    monkeypatch.setattr(publisher, "_sync_parent", fail_after_replace)
    with pytest.raises(OSError, match="manifest sync failed"):
        publisher._publish_output_pair(output, pd.DataFrame({"close": [2.]}), {"version": 2})
    assert not manifest.exists() and not output.exists()


def test_legacy_pair_reader_uses_committed_generation_during_partial_replacement(tmp_path, monkeypatch):
    import omega.data.pipeline.production_pipeline as publisher
    output = tmp_path / "out.parquet"
    publisher._publish_output_pair(output, pd.DataFrame({"close": [1.]}), {"version": 1})
    replace = publisher.os.replace
    observed = []

    def observe_replace(source, target):
        replace(source, target)
        if target == output:
            data, report = publisher.read_legacy_output_pair(output)
            observed.append((data["close"].tolist(), report))

    monkeypatch.setattr(publisher.os, "replace", observe_replace)
    publisher._publish_locked(output, tmp_path / "out_quality_report.json",
                              pd.DataFrame({"close": [2.]}), {"version": 2})
    assert observed == [([1.], {"version": 1})]
    assert publisher.read_legacy_output_pair(output)[1] == {"version": 2}


def test_legacy_pair_reader_fails_closed_without_manifest(tmp_path):
    import omega.data.pipeline.production_pipeline as publisher
    output = tmp_path / "out.parquet"
    pd.DataFrame({"close": [1.]}).to_parquet(output)
    (tmp_path / "out_quality_report.json").write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        publisher.read_legacy_output_pair(output)


@pytest.mark.parametrize("artifact", ["data", "report"])
def test_output_pair_tampered_artifact_fails_closed(tmp_path, artifact):
    import json
    import omega.data.pipeline.production_pipeline as publisher
    output = tmp_path / "out.parquet"
    publisher._publish_output_pair(output, pd.DataFrame({"close": [1.]}), {"version": 1})
    manifest = json.loads((tmp_path / "out.parquet.manifest.json").read_text(encoding="utf-8"))
    target = tmp_path / manifest[artifact]
    target.write_bytes(target.read_bytes() + b"tampered")
    for reader in (publisher.read_output_pair, publisher.read_legacy_output_pair):
        with pytest.raises(ValueError, match="digest mismatch"):
            reader(output)


@pytest.mark.parametrize("artifact", ["data", "report"])
def test_output_pair_missing_digest_fails_closed(tmp_path, artifact):
    import json
    import omega.data.pipeline.production_pipeline as publisher
    output = tmp_path / "out.parquet"
    publisher._publish_output_pair(output, pd.DataFrame({"close": [1.]}), {"version": 1})
    manifest_path = tmp_path / "out.parquet.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest[f"{artifact}_sha256"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        publisher.read_output_pair(output)


@pytest.mark.parametrize("existing", [False, True])
def test_output_pair_digest_failure_pre_replacement(tmp_path, monkeypatch, existing):
    import omega.data.pipeline.production_pipeline as publisher
    output = tmp_path / "out.parquet"
    report = tmp_path / "out_quality_report.json"
    manifest = tmp_path / "out.parquet.manifest.json"
    if existing:
        publisher._publish_output_pair(output, pd.DataFrame({"close": [1.]}), {"version": 1})
    before = {p: p.read_bytes() if p.exists() else None for p in (output, report, manifest)}

    def fail_digest(_):
        raise MemoryError("digest allocation")

    monkeypatch.setattr(publisher, "_digest_file", fail_digest)
    with pytest.raises(MemoryError, match="digest allocation"):
        publisher._publish_output_pair(output, pd.DataFrame({"close": [2.]}), {"version": 2})
    assert {p: p.read_bytes() if p.exists() else None for p in before} == before
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("error", [MemoryError, RuntimeError])
@pytest.mark.parametrize("existing", [False, True])
def test_output_pair_post_replacement_failure_rolls_back(tmp_path, monkeypatch, error, existing):
    import omega.data.pipeline.production_pipeline as publisher
    output = tmp_path / "out.parquet"
    report = tmp_path / "out_quality_report.json"
    manifest = tmp_path / "out.parquet.manifest.json"
    if existing:
        publisher._publish_output_pair(output, pd.DataFrame({"close": [1.]}), {"version": 1})
    before = {p: p.read_bytes() if p.exists() else None for p in (output, report, manifest)}
    replace = publisher.os.replace
    calls = 0

    def fail_after_legacy(source, target):
        nonlocal calls
        calls += 1
        if target == manifest and calls == 3:
            raise error("manifest replacement fault")
        return replace(source, target)

    monkeypatch.setattr(publisher.os, "replace", fail_after_legacy)
    with pytest.raises(error, match="manifest replacement fault"):
        publisher._publish_output_pair(output, pd.DataFrame({"close": [2.]}), {"version": 2})
    assert {p: p.read_bytes() if p.exists() else None for p in before} == before
    assert not list(tmp_path.glob("*.tmp"))


def test_output_pair_digest_reads_bounded_chunks(tmp_path, monkeypatch):
    import omega.data.pipeline.production_pipeline as publisher
    path = tmp_path / "large.bin"
    path.write_bytes(b"x" * 150000)
    original_open = type(path).open
    reads = []

    class TrackedStream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def read(self, size):
            reads.append(size)
            return self.stream.read(size)

    def tracked_open(self, *args, **kwargs):
        stream = original_open(self, *args, **kwargs)
        return TrackedStream(stream) if self == path and args == ("rb",) else stream

    monkeypatch.setattr(type(path), "open", tracked_open)
    assert publisher._digest_file(path) == __import__("hashlib").sha256(b"x" * 150000).hexdigest()
    assert len(reads) >= 3 and all(0 < size <= 65536 for size in reads)
