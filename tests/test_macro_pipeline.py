import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
import requests

from filelock import Timeout

from omega.data.macro_pipeline import DEFAULT_URLS, SBV_RATE_URL, WORLD_BANK_URL, MacroDataPipeline, SCHEMA, next_tradable_session


def revision(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def store_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=SCHEMA)


def row(revision_id: str, value: float = 4.5, published: str = "2026-01-02", ingested: str = "2026-01-05") -> dict:
    return {"indicator": "sbv_rate", "value": value, "observation_date": "2026-01-01", "published_at": published, "available_at": "2026-01-04", "ingested_at": ingested, "revision_id": revision_id, "source": "sbv"}


class Response:
    def __init__(self, text: str, status_code: int = 200, content_type: str = "text/html"):
        self.text, self.status_code = text, status_code
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self):
        return None


def test_sbv_html_fallback_is_disabled():
    assert MacroDataPipeline._sbv_records() is None


def test_default_session_keeps_tls_verification_enabled():
    assert MacroDataPipeline(urls={}).session.verify is True


def test_empty_urls_disables_default_providers():
    assert MacroDataPipeline(urls={}).urls == {}


class FetchResponse(Response):
    def __init__(self, text: str = "", payload: object | None = None):
        super().__init__(text)
        self.payload = payload

    def json(self):
        return self.payload


class RecordingSession:
    def __init__(self):
        self.calls = []
        self.headers = {}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if "finance.yahoo.com" in url:
            return FetchResponse(payload={"chart": {"result": [{"timestamp": [1786147200], "indicators": {"quote": [{"close": [26000]}]}}]}})
        return FetchResponse(payload=[{}, [{"date": "2024", "value": 3.2}]])


class UnavailableExternalSession(RecordingSession):
    def __init__(self, unavailable_url):
        super().__init__()
        self.unavailable_url = unavailable_url

    def get(self, url, **kwargs):
        if url == self.unavailable_url:
            raise requests.Timeout(f"{url} timed out")
        return super().get(url, **kwargs)


def test_world_bank_uses_https_endpoint():
    assert WORLD_BANK_URL.startswith("https://")


def test_non_sbv_requests_use_default_tls_parameters_and_release_schedules():
    yahoo_url = "https://query1.finance.yahoo.com/v8/finance/chart/USDVND=X"
    world_bank_url = WORLD_BANK_URL.format("FP.CPI.TOTL.ZG")
    session = RecordingSession()
    records = MacroDataPipeline(session=session, urls={
        "usd_vnd": yahoo_url,
        "cpi": world_bank_url,
    }).fetch()
    calls = dict(session.calls)
    assert "verify" not in calls[yahoo_url]
    assert "params" not in calls[yahoo_url]
    assert "verify" not in calls[world_bank_url]
    assert calls[world_bank_url]["params"] == {"format": "json"}
    assert records.set_index("indicator")["published_at"].map(pd.Timestamp.isoformat).to_dict() == {
        "cpi": "2025-01-29T09:00:00+07:00",
        "usd_vnd": "2026-08-08T15:15:00+07:00",
    }


def test_session_uses_browser_user_agent_for_yahoo_requests():
    session = RecordingSession()
    MacroDataPipeline(session=session, urls={})
    assert session.headers["User-Agent"].startswith("Mozilla/5.0")


def test_fetch_maps_yahoo_close_to_same_day_schedule():
    records = MacroDataPipeline(session=RecordingSession(), urls={"usd_vnd": DEFAULT_URLS["usd_vnd"]}).fetch()
    assert records.iloc[0]["published_at"].isoformat() == "2026-08-08T15:15:00+07:00"


def test_fetch_deduplicates_intraday_revision_ids_before_validation():
    session = RecordingSession()
    payload = {"chart": {"result": [{"timestamp": [1786147200, 1786147260], "indicators": {"quote": [{"close": [26000, 26000]}]}}]}}
    with patch.object(session, "get", return_value=FetchResponse(payload=payload)):
        records = MacroDataPipeline(session=session, urls={"usd_vnd": DEFAULT_URLS["usd_vnd"]}).fetch()
    assert len(records) == 1
    assert records["revision_id"].nunique() == 1


def test_next_tradable_session_skips_weekend_and_holidays():
    pipeline = MacroDataPipeline(urls={})
    assert next_tradable_session("2024-04-27", pipeline.holidays).date().isoformat() == "2024-04-29"
    assert next_tradable_session("2024-04-30", pipeline.holidays).date().isoformat() == "2024-05-02"


def test_existing_store_corruption_preserves_destination(tmp_path: Path):
    path = tmp_path / "macro.parquet"
    store_frame([row(revision("corrupt"), value=float("nan"))]).to_parquet(path, index=False)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    pipeline = MacroDataPipeline(urls={})
    pipeline.fetch = lambda: store_frame([])  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="finite"):
        pipeline.run(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_concurrent_writers_safety(tmp_path: Path):
    path = tmp_path / "macro.parquet"
    def write(value: float):
        pipeline = MacroDataPipeline(urls={})
        pipeline.fetch = lambda: store_frame([row(revision(str(value)), value=value)])  # type: ignore[method-assign]
        return pipeline.run(path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(write, [4.5, 4.6]))
    result = pd.read_parquet(path)
    assert sorted(result["value"].tolist()) == [4.5, 4.6]


def test_run_fetches_only_after_acquiring_file_lock(tmp_path: Path):
    entered = False

    class RecordingFileLock:
        def __init__(self, _: str, timeout: int):
            pass

        def __enter__(self):
            nonlocal entered
            entered = True
            return self

        def __exit__(self, *_):
            return False

    pipeline = MacroDataPipeline(urls={})

    def fetch():
        assert entered
        return store_frame([row(revision("locked"))])

    pipeline.fetch = fetch  # type: ignore[method-assign]
    with patch("omega.data.macro_pipeline.FileLock", RecordingFileLock):
        pipeline.run(tmp_path / "macro.parquet")


def test_run_reports_lock_contention_timeout(tmp_path: Path):
    class ContendedFileLock:
        def __init__(self, _: str, timeout: int):
            assert timeout == 120

        def __enter__(self):
            raise Timeout("macro lock")

        def __exit__(self, *_):
            return False

    peer_temporary_path = tmp_path / "macro.tmp.parquet"
    peer_temporary_path.write_text("peer output")
    with patch("omega.data.macro_pipeline.FileLock", ContendedFileLock):
        with pytest.raises(RuntimeError, match="Macro data concurrent lock acquisition timeout"):
            MacroDataPipeline(urls={}).run(tmp_path / "macro.parquet")
    assert peer_temporary_path.read_text() == "peer output"


def test_query_as_of_latest_vintage_deterministic(tmp_path: Path):
    path = tmp_path / "macro.parquet"
    store_frame([
        row(revision("early"), 4.5, "2026-01-02", "2026-01-05"),
        row(revision("late-a"), 4.6, "2026-01-03", "2026-01-06"),
        row(revision("late-b"), 4.7, "2026-01-03", "2026-01-06"),
    ]).to_parquet(path, index=False)
    result = MacroDataPipeline.query_as_of(path, "2026-01-07 12:00:00+07:00")
    assert result["revision_id"].tolist() == [max(revision("late-a"), revision("late-b"))]


def test_query_as_of_keeps_latest_row_atomic(tmp_path: Path):
    path = tmp_path / "macro.parquet"
    latest = row(revision("latest"), 4.7, "2026-01-03", "2026-01-06")
    latest["source"] = "latest-source"
    store_frame([row(revision("early"), 4.5, "2026-01-02", "2026-01-05"), latest]).to_parquet(path, index=False)
    result = MacroDataPipeline.query_as_of(path, "2026-01-07 12:00:00+07:00")
    assert result.iloc[0][["value", "source", "revision_id"]].to_dict() == {
        "value": 4.7, "source": "latest-source", "revision_id": revision("latest"),
    }


def test_query_as_of_orders_mixed_timestamp_offsets_by_instant(tmp_path: Path):
    path = tmp_path / "macro.parquet"
    earlier = row(revision("earlier"), 4.5, "2026-01-02 19:00:00+00:00", "2026-01-05 00:00:00+00:00")
    later = row(revision("later"), 4.6, "2026-01-03 03:00:00+07:00", "2026-01-05 00:00:00+00:00")
    earlier["available_at"] = later["available_at"] = "2026-01-06 00:00:00+00:00"
    store_frame([earlier, later]).to_parquet(path, index=False)
    result = MacroDataPipeline.query_as_of(path, "2026-01-07 12:00:00+07:00")
    assert result["revision_id"].tolist() == [revision("later")]


def test_query_as_of_breaks_equivalent_timestamp_instants_by_revision_id(tmp_path: Path):
    path = tmp_path / "macro.parquet"
    first = row(revision("first"), 4.5, "2026-01-03 00:00:00+07:00", "2026-01-05 00:00:00+00:00")
    second = row(revision("second"), 4.6, "2026-01-02 17:00:00+00:00", "2026-01-05 00:00:00+00:00")
    first["available_at"] = second["available_at"] = "2026-01-06 00:00:00+00:00"
    store_frame([first, second]).to_parquet(path, index=False)
    result = MacroDataPipeline.query_as_of(path, "2026-01-07 12:00:00+07:00")
    assert result["revision_id"].tolist() == [max(revision("first"), revision("second"))]


def test_query_as_of_deduplicates_equivalent_observation_timestamp_offsets(tmp_path: Path):
    path = tmp_path / "macro.parquet"
    first = row(revision("first"), 4.5, "2026-01-03 00:00:00+07:00", "2026-01-03")
    second = row(revision("second"), 4.6, "2026-01-02 17:00:00+00:00", "2026-01-04")
    first["available_at"] = second["available_at"] = "2026-01-06 00:00:00+00:00"
    store_frame([first, second]).to_parquet(path, index=False)
    result = MacroDataPipeline.query_as_of(path, "2026-01-07 12:00:00+07:00")
    assert result["revision_id"].tolist() == [revision("second")]


def test_query_as_of_rejects_null_latest_timestamp(tmp_path: Path):
    path = tmp_path / "macro.parquet"
    valid = row(revision("valid"), 4.5, "2026-01-02", "2026-01-05")
    null_published = row(revision("null"), 4.6, None, "2026-01-05")
    store_frame([valid, null_published]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="PIT violation"):
        MacroDataPipeline.query_as_of(path, "2026-01-07 12:00:00+07:00")


def test_query_as_of_rejects_null_ingested_at(tmp_path: Path):
    path = tmp_path / "macro.parquet"
    invalid = row(revision("null-ingested"), ingested=None)
    store_frame([invalid]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="ingested_at must be non-null"):
        MacroDataPipeline.query_as_of(path, "2026-01-07 12:00:00+07:00")


def test_query_as_of_excludes_unavailable_vintage(tmp_path: Path):
    path = tmp_path / "macro.parquet"
    store_frame([row(revision("future"), 4.5, "2026-01-02", "2026-01-05")]).assign(available_at="2026-01-06").to_parquet(path, index=False)
    assert MacroDataPipeline.query_as_of(path, "2026-01-05 12:00:00+07:00").empty


def test_world_bank_year_only_observation_uses_following_year_release_schedule():
    pipeline = MacroDataPipeline(urls={})
    records = pipeline._records("cpi", [{"date": "2024", "value": 3.2}], "world-bank", pipeline.holidays, pd.Timestamp("2026-01-01", tz="Asia/Ho_Chi_Minh"))
    assert records[0]["observation_date"].isoformat() == "2024-01-01T00:00:00+07:00"
    assert records[0]["published_at"].isoformat() == "2025-01-29T09:00:00+07:00"


def test_world_bank_records_before_calendar_range_are_ignored():
    pipeline = MacroDataPipeline(urls={})
    records = pipeline._records(
        "cpi", [{"date": "2014", "value": 4.1}, {"date": "2015", "value": 0.6}],
        "world-bank", pipeline.holidays, pd.Timestamp("2026-01-01", tz="Asia/Ho_Chi_Minh"),
    )
    assert len(records) == 1
    assert records[0]["observation_date"].year == 2015


def test_yahoo_rejects_mismatched_timestamp_and_close_arrays():
    pipeline = MacroDataPipeline(urls={})
    with pytest.raises(ValueError, match="equal lengths"):
        pipeline._records(
            "usd_vnd", {"chart": {"result": [{"timestamp": [1, 2], "indicators": {"quote": [{"close": [26000]}]}}]}},
            "yahoo", pipeline.holidays, pd.Timestamp("2026-01-01", tz="Asia/Ho_Chi_Minh"),
        )


def test_yahoo_chart_timestamp_uses_same_day_close_schedule():
    pipeline = MacroDataPipeline(urls={})
    records = pipeline._records(
        "usd_vnd", {"chart": {"result": [{"timestamp": [1704067200], "indicators": {"quote": [{"close": [26000]}]}}]}},
        "yahoo", pipeline.holidays, pd.Timestamp("2026-01-01", tz="Asia/Ho_Chi_Minh"),
    )
    assert records[0]["observation_date"].isoformat() == "2024-01-01T00:00:00+07:00"
    assert records[0]["published_at"].isoformat() == "2024-01-01T15:15:00+07:00"


def test_sbv_records_use_next_day_afternoon_schedule():
    pipeline = MacroDataPipeline(urls={})
    records = pipeline._records(
        "interbank_rate", [{"date": "2024-01-02", "rate": 4.5}], "sbv", pipeline.holidays,
        pd.Timestamp("2026-01-01", tz="Asia/Ho_Chi_Minh"),
    )
    assert records[0]["published_at"].isoformat() == "2024-01-03T16:00:00+07:00"
