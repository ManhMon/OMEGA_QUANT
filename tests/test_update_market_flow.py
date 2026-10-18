import concurrent.futures
import json
from pathlib import Path
import sys
import urllib.error

import pandas as pd
import pytest
from filelock import FileLock, Timeout

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from scripts import update_market_flow as ingest
from omega.data.market_flow import MarketFlowLakehouse


@pytest.fixture
def clock(monkeypatch):
    now = pd.Timestamp("2026-10-16T09:00:00Z")
    monkeypatch.setattr(ingest, "_now", lambda: now)
    return now


@pytest.fixture
def storage():
    import tempfile
    with tempfile.TemporaryDirectory(prefix="market_flow_test_", dir=REPO_ROOT / ".ly_state/session") as folder:
        yield Path(folder)


def item(date="16/10/2026", symbol="HPG", proprietary=False):
    row = dict(Symbol=symbol, GtMua=8_371_555_000, GtBan=32_294_050_000)
    row.update({"Date" if proprietary else "Ngay": date})
    row.update({"KLcpMua": 402600, "KlcpBan": 1553100} if proprietary else
               {"KLMua": 402600, "KLBan": 1553100})
    return row


def page(items, proprietary=False, total=None):
    return {"Success": True, "Data": {"TotalCount": len(items) if total is None else total,
            "Data": {"ListDataTudoanh": items} if proprietary else items}}


def mock_flow(monkeypatch, rows=None, proprietary=False):
    rows = [item(proprietary=proprietary)] if rows is None else rows
    monkeypatch.setattr(ingest, "_request_json", lambda url: page(rows, proprietary))


def foreign(monkeypatch, clock, date="16/10/2026", symbol="HPG"):
    mock_flow(monkeypatch, [item(date, symbol)])
    return ingest.fetch_foreign_ticker(symbol, int(date[-4:]), int(date[-4:]))[1]


def dchart(day="2017-08-10"):
    timestamp = int(pd.Timestamp(day, tz="UTC").timestamp())
    return dict(s="ok", t=[timestamp], o=[700], h=[710], l=[690], c=[705], v=[1000])


def test_foreign_historical_provenance_units_and_pit(monkeypatch, clock):
    frame = foreign(monkeypatch, clock, "05/01/2015", "OLD")
    assert frame.source.eq("CAFEF").all()
    assert frame.fr_net_value_total.iloc[0] == 8_371_555_000 - 32_294_050_000
    assert frame.fr_buy_value_total.iloc[0] == 8_371_555_000
    assert frame.as_of.iloc[0] == pd.Timestamp("2015-01-05T15:30:00+07:00")
    assert frame.available_at.iloc[0] == clock
    assert not frame.historical_pit_verified.any()
    MarketFlowLakehouse._validate_partition(frame, "foreign", "OLD")


def test_foreign_pagination_resets_each_year(monkeypatch, clock):
    monkeypatch.setattr(ingest, "PAGE_SIZE", 1)
    urls = []
    def request(url):
        urls.append(url)
        year = 2015 if "2015" in url else 2016
        p = 1 if "PageIndex=1" in url else 2
        return page([item(f"0{p + 4}/01/{year}" if year == 2015 else f"0{p + 3}/01/{year}")], total=2)
    monkeypatch.setattr(ingest, "_request_json", request)
    frame = ingest.fetch_foreign_ticker("HPG", 2015, 2016)[1]
    assert len(frame) == 4
    assert sum("PageIndex=1" in url for url in urls) == 2


@pytest.mark.parametrize("bad", [None, [], "12", True, float("nan"), float("inf"), -float("inf"), -1, 1e300])
def test_numeric_boundary_fail_closed(monkeypatch, clock, bad):
    row = item()
    row["GtMua"] = bad
    mock_flow(monkeypatch, [row])
    with pytest.raises(ValueError):
        ingest.fetch_foreign_ticker("HPG", 2026, 2026)


@pytest.mark.parametrize("bad", [0.5, -1, 1e12 + 1, None])
def test_volume_bounds(monkeypatch, clock, bad):
    row = item()
    row["KLMua"] = bad
    mock_flow(monkeypatch, [row])
    with pytest.raises(ValueError):
        ingest.fetch_foreign_ticker("HPG", 2026, 2026)


@pytest.mark.parametrize("change", ["missing", "duplicate", "holiday", "weekend", "identity", "date", "range"])
def test_invalid_cafef_observations(monkeypatch, clock, change):
    row = item()
    if change == "missing":
        del row["GtBan"]
    if change == "holiday":
        row["Ngay"] = "01/01/2026"
    if change == "weekend":
        row["Ngay"] = "17/10/2026"
    if change == "identity":
        row["Symbol"] = "VCB"
    if change == "date":
        row["Ngay"] = "31/02/2026"
    if change == "range":
        row["Ngay"] = "05/01/2015"
    mock_flow(monkeypatch, [row, row] if change == "duplicate" else [row])
    with pytest.raises(ValueError):
        ingest.fetch_foreign_ticker("HPG", 2026, 2026)


@pytest.mark.parametrize("payload", [{}, {"Success": False}, {"Success": True, "Data": {}},
    page([], total=1), page([item()], total=0), page([], total=True), page([], total=999999)])
def test_page_schema_and_incomplete_fail_closed(monkeypatch, clock, payload):
    monkeypatch.setattr(ingest, "_request_json", lambda url: payload)
    with pytest.raises(ValueError):
        ingest.fetch_foreign_ticker("HPG", 2026, 2026)


def test_repeated_pages_and_limit_exhaustion(monkeypatch, clock):
    monkeypatch.setattr(ingest, "PAGE_SIZE", 1)
    monkeypatch.setattr(ingest, "MAX_PAGES", 2)
    monkeypatch.setattr(ingest, "_request_json", lambda url: page([item()], total=2))
    with pytest.raises(ValueError, match="observation"):
        ingest.fetch_foreign_ticker("HPG", 2026, 2026)
    monkeypatch.setattr(ingest, "MAX_PAGES", 1)
    with pytest.raises(ValueError):
        ingest.fetch_foreign_ticker("HPG", 2026, 2026)


def test_changing_total_rejected(monkeypatch, clock):
    monkeypatch.setattr(ingest, "PAGE_SIZE", 1)
    pages = iter([page([item()], total=2), page([item("15/10/2026")], total=1)])
    monkeypatch.setattr(ingest, "_request_json", lambda url: next(pages))
    with pytest.raises(ValueError, match="pagination changed"):
        ingest.fetch_foreign_ticker("HPG", 2026, 2026)


def test_proprietary_rolling_year_non_vn30(monkeypatch, clock, storage):
    urls = []
    def request(url):
        urls.append(url)
        return page([item(symbol="OLD", proprietary=True)], proprietary=True)
    monkeypatch.setattr(ingest, "_request_json", request)
    monkeypatch.setattr(ingest, "DATA_DIR", storage)
    frames = ingest.ingest_proprietary(["OLD"])
    assert "StartDate=10%2F16%2F2025" in urls[0]
    assert frames[0].source.eq("PROPRIETARY").all()
    assert (storage / "proprietary_OLD.parquet").is_file()


def test_pit_close_inclusive_and_future_excluded(monkeypatch):
    monkeypatch.setattr(ingest, "_now", lambda: pd.Timestamp("2026-10-16T08:29:59Z"))
    mock_flow(monkeypatch, proprietary=True)
    with pytest.raises(ValueError, match="No completed"):
        ingest.fetch_prop_ticker("HPG")
    monkeypatch.setattr(ingest, "_now", lambda: pd.Timestamp("2026-10-16T08:30:00Z"))
    frame = ingest.fetch_prop_ticker("HPG")[1]
    assert frame.as_of.iloc[0] == frame.available_at.iloc[0]


def test_derivatives_historical_timezone_and_dry_run(monkeypatch, clock, storage):
    urls = []
    def request(url):
        urls.append(url)
        return dchart()
    monkeypatch.setattr(ingest, "_request_json", request)
    monkeypatch.setattr(ingest, "DATA_DIR", storage)
    frame = ingest.ingest_derivatives(["VN30F1M"], dry_run=True)[0]
    assert frame.source.eq("VNDIRECT").all()
    assert frame.time.iloc[0] == pd.Timestamp("2017-08-10")
    assert f"to={int(clock.timestamp())}" in urls[0]
    assert not list(storage.iterdir())


@pytest.mark.parametrize("change", ["length", "missing", "empty", "status", "ohlc", "fraction", "duplicate", "holiday", "old", "future", "nan"])
def test_derivatives_malformed(monkeypatch, clock, change):
    data = dchart()
    if change == "length":
        data["v"] = []
    if change == "missing":
        del data["o"]
    if change == "empty":
        data = {k: [] for k in data}
    if change == "status":
        data["s"] = "no_data"
    if change == "ohlc":
        data["h"] = [1]
    if change == "fraction":
        data["v"] = [0.5]
    if change == "duplicate":
        data = {k: v * 2 if isinstance(v, list) else v for k, v in data.items()}
    if change == "holiday":
        data = dchart("2026-01-01")
    if change == "old":
        data = dchart("2015-01-05")
    if change == "future":
        data = dchart("2026-10-19")
    if change == "nan":
        data["c"] = [float("nan")]
    monkeypatch.setattr(ingest, "_request_json", lambda url: data)
    with pytest.raises(ValueError):
        ingest.ingest_derivatives(["VN30F1M"], True)


class Response:
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, limit):
        return self.body[:limit]


def test_request_retry_bound_and_redaction(monkeypatch):
    calls, sleeps = [], []
    class Opener:
        def open(self, request, timeout):
            calls.append(timeout)
            raise urllib.error.URLError("https://user:secret@example.com")
    monkeypatch.setattr(ingest.urllib.request, "build_opener", lambda *a: Opener())
    monkeypatch.setattr(ingest.time, "sleep", sleeps.append)
    with pytest.raises(RuntimeError, match="retries exhausted") as error:
        ingest._request_json(ingest.DCHART_ROOT)
    assert len(calls) == 3 and sleeps == [0.25, 0.5]
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("status,attempts", [(429, 3), (503, 3), (403, 1)])
def test_http_retry_classification(monkeypatch, status, attempts):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(1)
            raise urllib.error.HTTPError(request.full_url, status, "secret", {}, None)
    monkeypatch.setattr(ingest.urllib.request, "build_opener", lambda *a: Opener())
    monkeypatch.setattr(ingest.time, "sleep", lambda delay: None)
    with pytest.raises(RuntimeError):
        ingest._request_json(ingest.DCHART_ROOT)
    assert len(calls) == attempts


@pytest.mark.parametrize("body", [b"\xff", b"\xef\xbb\xbf{}", b"[]", b"{", b"{\"x\":NaN}"])
def test_response_encoding_and_schema(monkeypatch, body):
    class Opener:
        def open(self, request, timeout):
            return Response(body)
    monkeypatch.setattr(ingest.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(ValueError):
        ingest._request_json(ingest.DCHART_ROOT)


def test_deadlines_fail_closed_without_polling(monkeypatch, clock):
    ticks = iter([0, 61])
    monkeypatch.setattr(ingest.time, "monotonic", lambda: next(ticks))
    with pytest.raises(RuntimeError, match="retries exhausted"):
        ingest._request_json(ingest.DCHART_ROOT)
    ticks = iter([0, 1801])
    with pytest.raises(RuntimeError, match="deadline exhausted"):
        ingest.fetch_foreign_ticker("HPG", 2026, 2026)


def test_response_size_and_crlf(monkeypatch):
    class Opener:
        def open(self, request, timeout):
            return Response(b'{\r\n"s":"ok"\r\n}')
    monkeypatch.setattr(ingest.urllib.request, "build_opener", lambda *a: Opener())
    assert ingest._request_json(ingest.DCHART_ROOT) == {"s": "ok"}
    monkeypatch.setattr(ingest, "MAX_RESPONSE_BYTES", 3)
    with pytest.raises(ValueError):
        ingest._request_json(ingest.DCHART_ROOT)


@pytest.mark.parametrize("url", ["http://cafef.vn/", "https://user:secret@cafef.vn/", "https://127.0.0.1/", "https://cafef.vn/evil"])
def test_url_allowlist_and_userinfo(url):
    with pytest.raises(ValueError):
        ingest._request_json(url)


def test_redirect_denied():
    with pytest.raises(ValueError):
        ingest._NoRedirect().redirect_request(None, None, 302, "", {}, "https://127.0.0.1")


@pytest.mark.parametrize("symbols", [[], ["../HPG"], ["--kind"], ["HPG", "HPG"], [None], "HPG", ["HPG&x=1"]])
def test_symbol_validation(symbols):
    with pytest.raises(ValueError):
        ingest.ingest_foreign(symbols, dry_run=True)


@pytest.mark.parametrize("start,end", [(True, 2026), (2014, 2026), (2027, 2027), (2026, 2015), (None, 2026)])
def test_year_validation(clock, start, end):
    with pytest.raises(ValueError):
        ingest.fetch_foreign_ticker("HPG", start, end)


def test_atomic_merge_retains_history_symbols_and_availability(monkeypatch, clock, storage):
    target = storage / "foreign_flow_2015_now.parquet"
    old = foreign(monkeypatch, clock, "05/01/2015", "OLD")
    new = foreign(monkeypatch, clock)
    ingest.atomic_write(old, target, kind="foreign")
    before = target.read_bytes()
    ingest.atomic_write(new, target, kind="foreign")
    assert target.with_suffix(".parquet.bak").read_bytes() == before
    result = pd.read_parquet(target)
    assert set(result.ticker) == {"OLD", "HPG"}
    later = new.copy()
    later["available_at"] = clock + pd.Timedelta(minutes=1)
    ingest.atomic_write(later, target, kind="foreign")
    result = pd.read_parquet(target)
    assert result.loc[result.ticker.eq("HPG"), "available_at"].iloc[0] == clock
    later["fr_buy_value_total"] += 1
    later["fr_net_value_total"] += 1
    ingest.atomic_write(later, target, kind="foreign")
    assert pd.read_parquet(target).loc[lambda f: f.ticker.eq("HPG"), "available_at"].iloc[0] == later.available_at.iloc[0]


@pytest.mark.parametrize("failure", ["write", "sync", "copy", "backup_replace", "target_replace", "directory_sync", "final_sync"])
def test_atomic_faults_preserve_old_and_cleanup(monkeypatch, clock, storage, failure):
    frame = foreign(monkeypatch, clock)
    target = storage / "foreign_HPG.parquet"
    ingest.atomic_write(frame, target, kind="foreign")
    before = target.read_bytes()
    changed = frame.copy()
    changed["fr_buy_value_total"] += 1
    changed["fr_net_value_total"] += 1
    def fail(*args, **kwargs):
        raise OSError("injected")
    if failure == "write":
        monkeypatch.setattr(pd.DataFrame, "to_parquet", fail)
    elif failure == "sync":
        monkeypatch.setattr(ingest, "_sync_file", fail)
    elif failure == "copy":
        monkeypatch.setattr(ingest.shutil, "copyfile", fail)
    elif failure.endswith("replace"):
        replace = ingest.os.replace
        def replacing(src, dst):
            if (failure == "backup_replace" and Path(dst).suffix == ".bak"
                    or failure == "target_replace" and Path(dst) == target):
                fail()
            return replace(src, dst)
        monkeypatch.setattr(ingest.os, "replace", replacing)
    else:
        calls = []
        def syncing(path):
            calls.append(path)
            if failure == "directory_sync" or len(calls) == 2:
                fail()
        monkeypatch.setattr(ingest, "_sync_directory", syncing)
    with pytest.raises(OSError):
        ingest.atomic_write(changed, target, kind="foreign")
    assert target.read_bytes() == before
    assert not list(storage.glob("*.tmp"))
    assert not list(storage.glob("*.rollback.*"))


def test_atomic_invalid_paths_and_corrupt_prior(monkeypatch, clock, storage):
    frame = foreign(monkeypatch, clock)
    with pytest.raises(ValueError):
        ingest.atomic_write(frame, REPO_ROOT.parent / "outside.parquet")
    target = storage / "foreign_HPG.parquet"
    target.mkdir()
    with pytest.raises(ValueError):
        ingest.atomic_write(frame, target)
    target.rmdir()
    target.write_bytes(b"corrupt")
    with pytest.raises(Exception):
        ingest.atomic_write(frame, target, kind="foreign")
    assert target.read_bytes() == b"corrupt"
    target.unlink()
    target.with_suffix(".parquet.bak").mkdir()
    with pytest.raises(ValueError):
        ingest.atomic_write(frame, target)


def test_atomic_lock_timeout_and_concurrent_merge(monkeypatch, clock, storage):
    first = foreign(monkeypatch, clock, symbol="HPG")
    second = foreign(monkeypatch, clock, symbol="OLD")
    target = storage / "foreign_flow_2015_now.parquet"
    monkeypatch.setattr(ingest, "LOCK_TIMEOUT", 0)
    with FileLock(str(target) + ".ingest.lock"):
        with pytest.raises(Timeout):
            ingest.atomic_write(first, target, kind="foreign")
    monkeypatch.setattr(ingest, "LOCK_TIMEOUT", 10)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(ingest.atomic_write, f, target, kind="foreign") for f in (first, second)]
        for job in jobs:
            job.result()
    assert set(pd.read_parquet(target).ticker) == {"HPG", "OLD"}


def test_fetch_failure_before_publication(monkeypatch, clock, storage):
    frame = foreign(monkeypatch, clock)
    monkeypatch.setattr(ingest, "DATA_DIR", storage)
    def fetch(sym, *args):
        if sym == "OLD":
            raise RuntimeError("provider failed")
        return sym, frame
    monkeypatch.setattr(ingest, "fetch_foreign_ticker", fetch)
    with pytest.raises(RuntimeError):
        ingest.ingest_foreign(["HPG", "OLD"])
    assert not list(storage.iterdir())


@pytest.mark.parametrize("failure", ["copy", "sync", "replace_stage"])
def test_rollback_failure_keeps_recoverable_backup(monkeypatch, clock, storage, failure):
    frame = foreign(monkeypatch, clock)
    target = storage / "foreign_HPG.parquet"
    ingest.atomic_write(frame, target, kind="foreign")
    before = target.read_bytes()
    changed = frame.copy()
    changed["fr_buy_value_total"] += 1
    changed["fr_net_value_total"] += 1
    def directory_sync(path):
        if target.read_bytes() != before:
            raise OSError("injected final sync")
    monkeypatch.setattr(ingest, "_sync_directory", directory_sync)
    original_copy, original_sync, original_replace = ingest.shutil.copyfile, ingest._sync_file, ingest.os.replace
    def copy(src, dst):
        if failure == "copy" and ".rollback." in str(dst):
            raise OSError("rollback copy")
        return original_copy(src, dst)
    def sync(path):
        if failure == "sync" and ".rollback." in str(path):
            raise OSError("rollback sync")
        return original_sync(path)
    def replace(src, dst):
        if failure == "replace_stage" and ".rollback." in str(src):
            raise OSError("rollback replace")
        return original_replace(src, dst)
    monkeypatch.setattr(ingest.shutil, "copyfile", copy)
    monkeypatch.setattr(ingest, "_sync_file", sync)
    monkeypatch.setattr(ingest.os, "replace", replace)
    with pytest.raises(OSError, match="rollback incomplete"):
        ingest.atomic_write(changed, target, kind="foreign")
    assert target.with_suffix(".parquet.bak").read_bytes() == before
    assert not list(storage.glob("*.rollback.*"))


def test_first_publication_final_sync_removes_target(monkeypatch, clock, storage):
    frame = foreign(monkeypatch, clock)
    target = storage / "foreign_HPG.parquet"
    calls = []
    def sync(path):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("final sync")
    monkeypatch.setattr(ingest, "_sync_directory", sync)
    with pytest.raises(OSError):
        ingest.atomic_write(frame, target, kind="foreign")
    assert not target.exists()
    assert not list(storage.glob("*.tmp"))


def test_proprietary_retains_prior_year_and_lakehouse_read(monkeypatch, clock, storage):
    old = foreign(monkeypatch, clock, "05/01/2015")
    rename = {"fr_buy_value_total": "total_buy_trade_value", "fr_sell_value_total": "total_sell_trade_value",
              "fr_net_value_total": "total_trade_net_value", "fr_buy_volume_total": "total_buy_trade_volume",
              "fr_sell_volume_total": "total_sell_trade_volume", "fr_net_volume_total": "total_trade_net_volume"}
    old = old.rename(columns=rename)
    old["source"] = "PROPRIETARY"
    target = storage / "proprietary_HPG.parquet"
    ingest.atomic_write(old, target, kind="proprietary")
    mock_flow(monkeypatch, proprietary=True)
    monkeypatch.setattr(ingest, "DATA_DIR", storage)
    ingest.ingest_proprietary(["HPG"])
    lake = MarketFlowLakehouse(storage)
    assert len(lake.read("proprietary", "HPG", as_of=clock.isoformat())) == 2


def test_bounded_input_files_and_duplicate_shards(monkeypatch, clock, storage):
    frame = foreign(monkeypatch, clock)
    target = storage / "foreign_HPG.parquet"
    ingest.atomic_write(frame, target, kind="foreign")
    before = target.read_bytes()
    pd.concat([frame, frame]).to_parquet(target, index=False)
    with pytest.raises(ValueError):
        ingest.atomic_write(frame, target, kind="foreign")
    target.write_bytes(before)
    monkeypatch.setattr(ingest, "MAX_FILE_BYTES", 1)
    with pytest.raises(ValueError):
        ingest.atomic_write(frame, target, kind="foreign")
    assert target.read_bytes() == before


def test_cli_fail_closed_and_derivative_symbols(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise RuntimeError("https://user:secret@example.com")
    monkeypatch.setattr(ingest, "ingest_foreign", fail)
    assert ingest.main(["--kind", "foreign", "--symbols", "HPG"]) == 1
    assert "secret" not in capsys.readouterr().err
    called = []
    monkeypatch.setattr(ingest, "ingest_derivatives", lambda *args: called.append(args))
    assert ingest.main(["--kind", "derivatives", "--symbols", "VN30F2M", "--dry-run"]) == 0
    assert called == [(["VN30F2M"], True)]


@pytest.mark.parametrize("kind", ["foreign", "proprietary", "derivatives"])
def test_rem1_cli_provider_failure_is_nonzero_and_secret_safe(monkeypatch, capsys, storage, kind):
    monkeypatch.setattr(ingest, "DATA_DIR", storage)
    def fail(*args, **kwargs):
        raise TimeoutError("https://user:secret@example.com/?token=private")
    monkeypatch.setattr(ingest, f"ingest_{kind}", fail)
    symbol = "VN30F1M" if kind == "derivatives" else "HPG"
    assert ingest.main(["--kind", kind, "--symbols", symbol]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "Market flow ingestion failed (TimeoutError)\n"
    assert not list(storage.iterdir())


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("phase", ["candidate_sync", "target_replace", "final_sync"])
def test_rem1_interrupted_publication_preserves_state(monkeypatch, clock, storage, existing, phase):
    frame = foreign(monkeypatch, clock)
    target = storage / "foreign_HPG.parquet"
    if existing:
        ingest.atomic_write(frame, target, kind="foreign")
    before = target.read_bytes() if existing else None
    changed = frame.copy()
    changed["fr_buy_value_total"] += 1
    changed["fr_net_value_total"] += 1
    if phase == "candidate_sync":
        def interrupted_file_sync(path):
            raise KeyboardInterrupt
        monkeypatch.setattr(ingest, "_sync_file", interrupted_file_sync)
    elif phase == "target_replace":
        replace = ingest.os.replace
        def interrupted_replace(src, dst):
            if Path(dst) == target:
                raise KeyboardInterrupt
            return replace(src, dst)
        monkeypatch.setattr(ingest.os, "replace", interrupted_replace)
    else:
        calls = []
        def interrupted_sync(path):
            calls.append(path)
            if len(calls) == 2:
                raise KeyboardInterrupt
        monkeypatch.setattr(ingest, "_sync_directory", interrupted_sync)
    with pytest.raises(KeyboardInterrupt):
        ingest.atomic_write(changed, target, kind="foreign")
    if existing:
        assert target.read_bytes() == before
    else:
        assert not target.exists()
    assert not list(storage.glob("*.tmp"))
    assert not list(storage.glob("*.rollback.*"))
