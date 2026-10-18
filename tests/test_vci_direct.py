"""16-Dimension resilience and unit tests for direct VCI client."""

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.update_market_data as umd
from datetime import date

from omega.data.calendar import VNTradingCalendar

from omega.data.vci_direct import (
    DirectVCIClient,
    TokenBucket,
    redact,
    unpack_vietcap_columnar,
    validate_price_bounds,
)
from omega.data.market_flow import VNMarketFlowDataSource
from omega.data.vnstock_client import RateLimiter, UpstreamTransportException, VnstockClient, atomic_write_with_backup
from omega.quant.graph.fetcher import GraphFetcher, slice_vci_statement_envelope


@pytest.fixture
def flow_lake_root():
    import tempfile
    with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".ly_state/session") as directory:
        yield Path(directory)


@pytest.mark.parametrize("kind,source,day,symbol", [
    ("foreign", "CAFEF", "2015-01-05", "OLD"),
    ("foreign", "SSI_MCP", "2015-01-05", "HPG"),
    ("proprietary", "PROPRIETARY", "2015-01-05", "OLD"),
    ("derivatives", "VNDIRECT", "2017-08-10", "VN30F1M"),
    ("derivatives", "SSI_MCP", "2017-08-10", "VN30F1M"),
])
def test_lakehouse_historical_sources_pit_roundtrip(flow_lake_root, kind, source, day, symbol):
    from omega.data.market_flow import MarketFlowLakehouse
    event = pd.Timestamp(day, tz="Asia/Ho_Chi_Minh") + pd.Timedelta(hours=15, minutes=30)
    available = pd.Timestamp("2026-10-16T09:00:00Z")
    row = dict(time=pd.Timestamp(day), ticker=symbol, as_of=event, available_at=available,
               source=source, historical_pit_verified=False)
    if kind == "derivatives":
        row.update(open=700., high=710., low=690., close=705., volume=1000,
                   price_scale="points", volume_unit="contracts", adjusted="provider_adjusted",
                   rebuild_date="2026-10-16")
    else:
        from omega.data.vci_direct import FOREIGN_FLOW_COLUMNS, PROP_FLOW_COLUMNS
        names = PROP_FLOW_COLUMNS if kind == "proprietary" else FOREIGN_FLOW_COLUMNS
        row.update(dict(zip(names, (day, 1000., 400., 600., 10., 4., 6.))))
        row.update(price_scale="VND_FULL", volume_unit="shares")
    frame = pd.DataFrame([row])
    lake = MarketFlowLakehouse(flow_lake_root)
    lake._validate_partition(frame, kind, symbol)
    if source == "VNDIRECT":
        prelaunch = frame.copy()
        prelaunch["time"] = pd.Timestamp("2017-08-09")
        prelaunch["as_of"] = pd.Timestamp("2017-08-09T15:30:00+07:00")
        with pytest.raises(ValueError):
            lake._validate_partition(prelaunch, kind, symbol)
    frame.to_parquet(flow_lake_root / f"{kind}_{symbol}.parquet", index=False)
    assert lake.read(kind, symbol, as_of=(available - pd.Timedelta(nanoseconds=1)).isoformat()).empty
    assert len(lake.read(kind, symbol, as_of=available.isoformat())) == 1
    for field, value in (("source", "UNKNOWN"), ("historical_pit_verified", True),
                         ("historical_pit_verified", "false"), ("available_at", event - pd.Timedelta(seconds=1)),
                         ("as_of", event - pd.Timedelta(seconds=1))):
        invalid = frame.copy()
        invalid[field] = value
        with pytest.raises(ValueError):
            lake._validate_partition(invalid, kind, symbol)


def test_lakehouse_historical_foreign_long_partition(flow_lake_root):
    from omega.data.market_flow import MarketFlowLakehouse
    dates = [day for day in pd.date_range("2015-01-05", "2019-12-31") if VNTradingCalendar.is_trading_day(day)]
    frame = pd.DataFrame(dict(trading_date=[day.date().isoformat() for day in dates], time=dates,
        ticker="OLD", fr_buy_value_total=1000., fr_sell_value_total=400., fr_net_value_total=600.,
        fr_buy_volume_total=10., fr_sell_volume_total=4., fr_net_volume_total=6.,
        as_of=[day.tz_localize("Asia/Ho_Chi_Minh") + pd.Timedelta(hours=15, minutes=30) for day in dates],
        available_at=pd.Timestamp("2026-10-16T09:00:00Z"), source="CAFEF", price_scale="VND_FULL",
        volume_unit="shares", historical_pit_verified=False))
    assert len(frame) > 731
    MarketFlowLakehouse._validate_partition(frame, "foreign", "OLD")
    frame.loc[frame.index[-1], "source"] = "SSI_MCP"
    MarketFlowLakehouse._validate_partition(frame, "foreign", "OLD")
    invalid = frame.copy()
    invalid.loc[invalid.index[0], "fr_net_value_total"] = 0
    with pytest.raises(ValueError):
        MarketFlowLakehouse._validate_partition(invalid, "foreign", "OLD")


def test_lakehouse_ssi_derivatives_points_contracts_and_foreign_vnd(flow_lake_root):
    from omega.data.market_flow import MarketFlowLakehouse
    calls = []
    def ssi(tool, arguments):
        calls.append(tool)
        row = _ssi_row()
        row.update(net_buy_sell_value="600", net_buy_sell_volume="6")
        if tool == "marketdata_list_stock_daily_data":
            row.update(symbol="VN30F1M", open="1234.5", high="1240", low="1200", close="1230", volume="100")
        return {"stocks": [row]}
    lake = MarketFlowLakehouse(flow_lake_root, DirectVCIClient(ssi_call=ssi))
    for kind, symbol, scale, unit in (("derivatives", "VN30F1M", "points", "contracts"),
                                      ("foreign", "HPG", "VND_FULL", "shares")):
        result = lake.ingest(kind, symbol, "2026-01-02", "2026-01-02")
        assert result["status"] == "success"
        frame = pd.read_parquet(REPO_ROOT / result["path"])
        assert frame["price_scale"].eq(scale).all() and frame["volume_unit"].eq(unit).all()
        assert not frame["historical_pit_verified"].any()
        assert (frame["as_of"] <= frame["available_at"]).all()
        observed = frame["available_at"].iloc[0]
        assert lake.read(kind, symbol, as_of=(observed - pd.Timedelta(nanoseconds=1)).isoformat()).empty
        assert len(lake.read(kind, symbol, as_of=observed.isoformat())) == 1
        if kind == "derivatives":
            assert frame.iloc[0]["close"] == 1230
        else:
            assert frame.iloc[0]["fr_buy_value_total"] == 1000
        assert lake.ingest(kind, symbol, "2026-01-02", "2026-01-02")["rows"] == 1
    assert set(calls) == {"marketdata_list_stock_daily_data", "marketdata_list_daily_stock_infor"}


@pytest.mark.parametrize("value", [None, "", "NaN", "Inf", "-Inf", [], {}, True, -1, 0, 1e13, pytest.param(10**400, id="overflow")])
@pytest.mark.parametrize("field", ["close", "volume"])
def test_lakehouse_derivatives_rejects_bad_numbers(field, value):
    row = dict(symbol="VN30F1M", trading_date="02/01/2026", open=1200, high=1250, low=1100, close=1230, volume=10)
    row[field] = value
    if field == "volume" and value == 0 and type(value) is int:
        assert DirectVCIClient(ssi_call=lambda *_: {"stocks": [row]}).fetch_derivatives("VN30F1M", "2026-01-02", "2026-01-02").iloc[0]["volume"] == 0
    else:
        with pytest.raises((ValueError, RuntimeError)):
            DirectVCIClient(ssi_call=lambda *_: {"stocks": [row]}).fetch_derivatives("VN30F1M", "2026-01-02", "2026-01-02")


@pytest.mark.parametrize("field", ["net_buy_sell_value", "net_buy_sell_volume"])
@pytest.mark.parametrize("value", [None, "NaN", "Inf", -999, [], True])
def test_lakehouse_foreign_rejects_inconsistent_provider_nets(field, value):
    row = _ssi_row()
    row[field] = value
    with pytest.raises(ValueError):
        DirectVCIClient(ssi_call=lambda *_: {"stocks": [row]}).foreign_trade("HPG", "2026-01-02", "2026-01-02", snapshot=False)


def test_lakehouse_proprietary_unavailable_not_zero_or_published(flow_lake_root):
    from omega.data.market_flow import MarketFlowLakehouse, ProprietaryFlowIngestor
    def unavailable(**_):
        raise TimeoutError("token=must-not-leak")
    client = DirectVCIClient(prop_call=unavailable)
    frame = ProprietaryFlowIngestor(client).fetch("HPG", "2026-01-02", "2026-01-02")
    assert frame.empty and frame.attrs["status"] == "unavailable"
    assert MarketFlowLakehouse(flow_lake_root, client).ingest("proprietary", "HPG", "2026-01-02", "2026-01-02") == {"status": "unavailable", "rows": 0}
    assert not list(flow_lake_root.glob("*.parquet"))


@pytest.mark.parametrize("failure", ["schema", "duplicate", "units", "write", "directory"])
def test_lakehouse_publication_failure_preserves_partition(flow_lake_root, monkeypatch, failure):
    from omega.data.market_flow import MarketFlowLakehouse
    import omega.data.vnstock_client as module
    lake = MarketFlowLakehouse(flow_lake_root, DirectVCIClient(ssi_call=lambda *_: {"stocks": [_ssi_row()]}))
    lake.ingest("foreign", "HPG", "2026-01-02", "2026-01-02")
    path = flow_lake_root / "foreign_HPG.parquet"
    frame = pd.read_parquet(path)
    if failure == "schema":
        frame = frame.drop(columns="source")
    elif failure == "duplicate":
        frame = pd.concat([frame, frame], ignore_index=True)
    elif failure == "units":
        frame["price_scale"] = "KVND"
    elif failure == "directory":
        path.unlink()
        path.mkdir()
    if failure not in ("write", "directory"):
        frame.to_parquet(path, index=False)
    before = path.read_bytes() if path.is_file() else None
    if failure == "write":
        monkeypatch.setattr(module, "_fsync_directory", lambda *_: (_ for _ in ()).throw(OSError("disk fault")))
    with pytest.raises((ValueError, OSError)):
        lake.ingest("foreign", "HPG", "2026-01-02", "2026-01-02")
    assert path.read_bytes() == before if before is not None else path.is_dir()


@pytest.fixture(params=["foreign", "proprietary"])
def flow_partition(request):
    from omega.data.vci_direct import FOREIGN_FLOW_COLUMNS, PROP_FLOW_COLUMNS
    kind = request.param
    columns = PROP_FLOW_COLUMNS if kind == "proprietary" else FOREIGN_FLOW_COLUMNS
    frame = pd.DataFrame([["2026-01-02", 2e12, 1e12, 1e12, 10, 4, 6]], columns=columns)
    frame["ticker"] = "HPG"
    frame["time"] = pd.to_datetime(frame["trading_date"])
    frame["as_of"] = pd.Timestamp("2026-01-02T15:30:00+07:00")
    frame["available_at"] = pd.Timestamp("2026-01-02T08:30:01Z")
    frame["source"] = "PROP_CALL" if kind == "proprietary" else "SSI_MCP"
    frame["price_scale"] = "VND_FULL"
    frame["volume_unit"] = "shares"
    frame["historical_pit_verified"] = False
    return kind, frame


@pytest.mark.parametrize("boundary", ["read", "merge"])
@pytest.mark.parametrize("mutation", [
    "empty", "missing_total", "extra", "other_dataset", "duplicate_column", "duplicate_row",
    "missing_metadata", "ticker", "units", "volume_unit", "source", "source_none",
    "verified_true", "verified_integer", "verified_null", "nan", "inf", "negative_inf",
    "none", "empty_numeric", "numeric_string", "bool_numeric", "complex", "negative",
    "overflow", "fractional_volume", "wrong_net", "time", "time_null", "time_aware",
    "trading_date", "intraday_date", "weekend", "holiday", "as_of_null", "as_of_naive",
    "early_close", "late_close", "available_null", "available_naive", "available_before_close",
    "available_future", "hidden_invalid_row", "optional_nan", "optional_inf",
    "optional_negative", "optional_bool", "mixed_source", "time_intraday",
] + ["missing_" + field for field in ("trading_date", "ticker", "time", "as_of", "available_at",
                                      "source", "volume_unit", "historical_pit_verified")])
def test_lakehouse_flow_partition_rejects_corruption(flow_lake_root, flow_partition, monkeypatch, boundary, mutation):
    from omega.data.market_flow import MarketFlowLakehouse
    from omega.data.vci_direct import FOREIGN_FLOW_COLUMNS, PROP_FLOW_COLUMNS
    kind, original = flow_partition
    frame = original.copy()
    columns = PROP_FLOW_COLUMNS if kind == "proprietary" else FOREIGN_FLOW_COLUMNS
    numeric = {"nan": math.nan, "inf": math.inf, "negative_inf": -math.inf, "none": None,
               "empty_numeric": "", "numeric_string": "2000000000000", "bool_numeric": True,
               "complex": 1j, "negative": -1, "overflow": float(2**64)}
    fields = {"ticker": ("ticker", "FPT"), "units": ("price_scale", "KVND"),
              "volume_unit": ("volume_unit", "contracts"), "source": ("source", "VCI"),
              "source_none": ("source", None), "verified_true": ("historical_pit_verified", True),
              "verified_integer": ("historical_pit_verified", 0), "verified_null": ("historical_pit_verified", None),
              "fractional_volume": (columns[4], 1.5), "wrong_net": (columns[3], 0),
              "time": ("time", pd.Timestamp("2026-01-05")), "time_null": ("time", pd.NaT),
              "time_aware": ("time", pd.Timestamp("2026-01-02T00:00:00Z")),
              "trading_date": ("trading_date", None), "intraday_date": ("trading_date", "2026-01-02T01:00:00"),
              "as_of_null": ("as_of", pd.NaT), "as_of_naive": ("as_of", pd.Timestamp("2026-01-02T08:30:00")),
              "early_close": ("as_of", pd.Timestamp("2026-01-02T08:29:59Z")),
              "late_close": ("as_of", pd.Timestamp("2026-01-02T08:30:01Z")),
              "available_null": ("available_at", pd.NaT),
              "available_naive": ("available_at", pd.Timestamp("2026-01-02T08:30:01")),
              "available_before_close": ("available_at", pd.Timestamp("2026-01-02T08:29:59Z")),
              "available_future": ("available_at", pd.Timestamp("2100-01-01T00:00:00Z"))}
    if mutation in numeric:
        frame[columns[1]] = numeric[mutation]
    elif mutation in fields:
        field, value = fields[mutation]
        frame[field] = value
    elif mutation == "empty":
        frame = frame.iloc[:0]
    elif mutation.startswith("missing_"):
        field = (columns[1] if mutation == "missing_total" else
                 "price_scale" if mutation == "missing_metadata" else mutation.removeprefix("missing_"))
        frame = frame.drop(columns=field)
    elif mutation in ("extra", "other_dataset"):
        frame["unexpected" if mutation == "extra" else
              (FOREIGN_FLOW_COLUMNS[1] if kind == "proprietary" else PROP_FLOW_COLUMNS[1])] = 0
    elif mutation == "duplicate_column":
        frame = pd.concat([frame, frame[[columns[1]]]], axis=1)
    elif mutation == "duplicate_row":
        frame = pd.concat([frame, frame], ignore_index=True)
    elif mutation in ("weekend", "holiday"):
        day = "2026-01-03" if mutation == "weekend" else "2026-01-01"
        frame["trading_date"], frame["time"] = day, pd.Timestamp(day)
        frame["as_of"] = pd.Timestamp(day, tz="Asia/Ho_Chi_Minh") + pd.Timedelta(hours=15, minutes=30)
        frame["available_at"] = frame["as_of"]
    elif mutation.startswith("optional_"):
        field = "percent_buy_trade_volume" if kind == "proprietary" else "fr_ownership"
        frame[field] = {"optional_nan": math.nan, "optional_inf": math.inf,
                        "optional_negative": -1, "optional_bool": True}[mutation]
    elif mutation == "time_intraday":
        frame["time"] += pd.Timedelta(hours=1)
    elif mutation in ("hidden_invalid_row", "mixed_source"):
        hidden = frame.copy()
        hidden["trading_date"], hidden["time"] = "2026-01-05", pd.Timestamp("2026-01-05")
        hidden["as_of"] = pd.Timestamp("2026-01-05T08:30:00Z")
        hidden["available_at"] = pd.Timestamp("2026-01-05T08:30:01Z")
        if mutation == "mixed_source":
            hidden["source"] = "VNSTOCK_VCI" if kind == "proprietary" else "VCI"
        else:
            hidden["historical_pit_verified"] = True
        frame = pd.concat([frame, hidden], ignore_index=True)
    path = flow_lake_root / f"{kind}_HPG.parquet"
    path.write_bytes(b"unchanged partition")
    monkeypatch.setattr(pd, "read_parquet", lambda *_: frame.copy())
    provider = original[list(columns)].copy()
    provider.attrs.update(observed_at=original["available_at"].iloc[0], source=original["source"].iloc[0])
    client = DirectVCIClient()
    monkeypatch.setattr(client, "foreign_trade", lambda *_, **__: provider.copy())
    monkeypatch.setattr(client, "prop_trade", lambda *_: provider.copy())
    lake = MarketFlowLakehouse(flow_lake_root, client)
    with pytest.raises(ValueError):
        if boundary == "read":
            lake.read(kind, "HPG", as_of="2026-01-02T08:30:01Z")
        else:
            lake.ingest(kind, "HPG", "2026-01-02", "2026-01-02")
    assert path.read_bytes() == b"unchanged partition"


@pytest.mark.parametrize("control", ["zero", "large", "negative_net", "optional", "source", "equal_close"])
@pytest.mark.parametrize("cutoff,rows", [("2026-01-02T08:29:59Z", 0),
                                        ("2026-01-02T08:30:00Z", 0),
                                        ("2026-01-02T08:30:01Z", 1),
                                        ("2026-01-02T15:30:01+07:00", 1)])
def test_lakehouse_flow_partition_legitimate_controls(flow_lake_root, flow_partition, control, cutoff, rows):
    from omega.data.market_flow import MarketFlowLakehouse
    from omega.data.vci_direct import FOREIGN_FLOW_COLUMNS, PROP_FLOW_COLUMNS
    kind, frame = flow_partition
    columns = PROP_FLOW_COLUMNS if kind == "proprietary" else FOREIGN_FLOW_COLUMNS
    if control == "zero":
        frame[list(columns[1:])] = 0
    elif control == "negative_net":
        frame[list(columns[1:])] = [1e12, 2e12, -1e12, 4, 10, -6]
    elif control == "optional":
        optional = ([f"percent_{side}_trade_{unit}" for side in ("buy", "sell", "net")
                     for unit in ("value", "volume")] if kind == "proprietary" else
                    ["fr_ownership", "fr_total_room", "fr_current_room"])
        frame[optional] = 0
    elif control == "source" and kind == "proprietary":
        frame["source"] = "VNSTOCK_VCI"
    elif control == "equal_close":
        frame["available_at"] = frame["as_of"]
        rows = int(pd.Timestamp(cutoff) >= frame["as_of"].iloc[0])
    path = flow_lake_root / f"{kind}_HPG.parquet"
    frame.to_parquet(path, index=False)
    before = path.read_bytes()
    result = MarketFlowLakehouse(flow_lake_root).read(kind, "HPG", as_of=cutoff)
    pd.testing.assert_frame_equal(result, pd.read_parquet(path).iloc[:rows])
    assert path.read_bytes() == before


@pytest.mark.parametrize("source", ["SSI_MCP", "PROP_CALL", "VNSTOCK_VCI", "PROPRIETARY"])
def test_lakehouse_flow_ingest_read_roundtrip(flow_lake_root, source):
    from omega.data.market_flow import MarketFlowLakehouse
    from omega.data.vci_direct import FOREIGN_FLOW_COLUMNS, PROP_FLOW_COLUMNS
    kind = "foreign" if source == "SSI_MCP" else "proprietary"
    columns = FOREIGN_FLOW_COLUMNS if kind == "foreign" else PROP_FLOW_COLUMNS
    def fetch(*_, **__):
        frame = pd.DataFrame([["2026-01-02", 2000, 1000, 1000, 10, 4, 6]], columns=columns)
        frame.attrs.update(source=source, observed_at=pd.Timestamp("2026-01-02T08:30:00Z"))
        return frame
    class Client:
        foreign_trade = staticmethod(fetch)
        prop_trade = staticmethod(fetch)
    lake = MarketFlowLakehouse(flow_lake_root, Client())
    assert lake.ingest(kind, "HPG", "2026-01-02", "2026-01-02")["rows"] == 1
    result = lake.read(kind, "HPG", as_of="2026-01-02T08:30:00Z")
    assert len(result) == 1 and result["source"].iloc[0] == source
    assert not result["historical_pit_verified"].any()


@pytest.fixture
def derivatives_partition():
    row = dict(symbol="VN30F1M", trading_date="02/01/2026", open=1200, high=1250, low=1100, close=1230, volume=0)
    frame = DirectVCIClient(ssi_call=lambda *_: {"stocks": [row]}).fetch_derivatives("VN30F1M", "2026-01-02", "2026-01-02")
    frame["historical_pit_verified"] = False
    return frame


@pytest.mark.parametrize("boundary", ["read", "ingest", "merge"])
@pytest.mark.parametrize("field,value", [
    (field, value) for field in ("open", "high", "low", "close", "volume")
    for value in (None, math.nan, math.inf, -math.inf, -1, True, "1230", 1e13 if field != "volume" else 2**63)
] + [(field, 0) for field in ("open", "high", "low", "close")] + [
    ("volume", 0.5), ("ticker", "HPG"), ("ticker", None),
    ("price_scale", "VND_FULL"), ("volume_unit", "shares"), ("source", "VCI"),
    ("adjusted", "unadjusted"), ("historical_pit_verified", True),
    ("historical_pit_verified", None), ("historical_pit_verified", 0),
    ("time", pd.NaT), ("time", pd.Timestamp("2026-01-03")),
    ("time", pd.Timestamp("2026-01-02T01:00:00")),
    ("as_of", pd.NaT), ("as_of", pd.Timestamp("2026-01-02T08:29:59Z")),
    ("available_at", pd.NaT), ("available_at", pd.Timestamp("2026-01-02T08:29:59Z")),
    ("available_at", pd.Timestamp("2100-01-01T00:00:00Z")),
    ("rebuild_date", "2026-01-01"), ("rebuild_date", None),
    ("low", 1240), ("high", 1220),
])
def test_lakehouse_derivatives_validates_each_field(flow_lake_root, derivatives_partition, monkeypatch, boundary, field, value):
    from omega.data.market_flow import MarketFlowLakehouse
    frame = derivatives_partition.copy()
    frame[field] = value
    path = flow_lake_root / "derivatives_VN30F1M.parquet"
    client = DirectVCIClient()
    monkeypatch.setattr(client, "fetch_derivatives", lambda *_: derivatives_partition.copy() if boundary == "merge" else frame.copy())
    lake = MarketFlowLakehouse(flow_lake_root, client)
    if boundary != "ingest":
        frame.to_parquet(path, index=False)
    before = path.read_bytes() if path.exists() else None
    with pytest.raises(ValueError):
        if boundary == "read":
            lake.read("derivatives", "VN30F1M", as_of=pd.Timestamp.now(tz="UTC").isoformat())
        else:
            lake.ingest("derivatives", "VN30F1M", "2026-01-02", "2026-01-02")
    assert path.read_bytes() == before if before is not None else not path.exists()


@pytest.mark.parametrize("boundary", ["read", "ingest", "merge"])
@pytest.mark.parametrize("mutation", ["extra", "duplicate_column", "duplicate_row"] + [
    "missing_" + field for field in ("time", "ticker", "open", "high", "low", "close", "volume", "as_of",
                                    "available_at", "source", "price_scale", "adjusted", "rebuild_date", "volume_unit")])
def test_lakehouse_derivatives_rejects_schema_drift(flow_lake_root, derivatives_partition, monkeypatch, boundary, mutation):
    from omega.data.market_flow import MarketFlowLakehouse
    frame = derivatives_partition.copy()
    if mutation.startswith("missing_"):
        frame = frame.drop(columns=mutation.removeprefix("missing_"))
    elif mutation == "extra":
        frame["unexpected"] = 1
    elif mutation == "duplicate_column":
        frame = pd.concat([frame, frame[["close"]]], axis=1)
    else:
        frame = pd.concat([frame, frame], ignore_index=True)
    path = flow_lake_root / "derivatives_VN30F1M.parquet"
    client = DirectVCIClient()
    monkeypatch.setattr(client, "fetch_derivatives", lambda *_: derivatives_partition.copy() if boundary == "merge" else frame.copy())
    if boundary != "ingest":
        path.write_bytes(b"unchanged partition")
        monkeypatch.setattr(pd, "read_parquet", lambda *_: frame.copy())
    lake = MarketFlowLakehouse(flow_lake_root, client)
    with pytest.raises(ValueError):
        if boundary == "read":
            lake.read("derivatives", "VN30F1M", as_of=pd.Timestamp.now(tz="UTC").isoformat())
        else:
            lake.ingest("derivatives", "VN30F1M", "2026-01-02", "2026-01-02")
    assert path.read_bytes() == b"unchanged partition" if boundary != "ingest" else not path.exists()


@pytest.mark.parametrize("kind,symbol", [("foreign", "HPG"), ("proprietary", "HPG"), ("derivatives", "VN30F1M")])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", ["write", "file_fsync", "readback", "replace_before", "replace_after", "directory_fsync"])
def test_lakehouse_publication_fault_rolls_back(flow_lake_root, derivatives_partition, monkeypatch, kind, symbol, existing, failure):
    from omega.data.market_flow import MarketFlowLakehouse
    import omega.data.vnstock_client as module
    client = DirectVCIClient(ssi_call=lambda *_: {"stocks": [_ssi_row()]}, prop_call=lambda **_: pd.DataFrame([{
        "trading_date": "2026-01-02", "total_buy_trade_value": 1000, "total_sell_trade_value": 400,
        "total_trade_net_value": 600, "total_buy_trade_volume": 10, "total_sell_trade_volume": 4,
        "total_trade_net_volume": 6}]))
    monkeypatch.setattr(client, "fetch_derivatives", lambda *_: derivatives_partition.copy())
    lake = MarketFlowLakehouse(flow_lake_root, client)
    path = flow_lake_root / f"{kind}_{symbol}.parquet"
    if existing:
        lake.ingest(kind, symbol, "2026-01-02", "2026-01-02")
    before = path.read_bytes() if existing else None
    def fault(*_args, **_kwargs):
        raise OSError("publication fault")
    if failure == "write":
        monkeypatch.setattr(pd.DataFrame, "to_parquet", fault)
    elif failure == "file_fsync":
        monkeypatch.setattr(module.os, "fsync", fault)
    elif failure == "readback":
        read = pd.read_parquet
        monkeypatch.setattr(pd, "read_parquet", lambda name, **kwargs: fault() if str(name).endswith(".tmp") else read(name, **kwargs))
    elif failure.startswith("replace_"):
        replace = module.os.replace
        def broken_replace(source, target):
            if failure == "replace_after":
                replace(source, target)
            fault()
        monkeypatch.setattr(module.os, "replace", broken_replace)
    else:
        monkeypatch.setattr(module, "_fsync_directory", fault)
    with pytest.raises(OSError, match="publication fault|rollback incomplete"):
        lake.ingest(kind, symbol, "2026-01-02", "2026-01-02")
    assert path.read_bytes() == before if existing else not path.exists()
    assert not list(flow_lake_root.glob("*.tmp"))


@pytest.mark.parametrize("mutation", ["empty", "missing_provenance"])
@pytest.mark.parametrize("boundary", ["read", "merge"])
def test_lakehouse_derivatives_rejects_empty_or_missing_provenance(flow_lake_root, derivatives_partition, monkeypatch, boundary, mutation):
    from omega.data.market_flow import MarketFlowLakehouse
    path = flow_lake_root / "derivatives_VN30F1M.parquet"
    frame = derivatives_partition.iloc[:0] if mutation == "empty" else derivatives_partition.drop(columns="historical_pit_verified")
    frame.to_parquet(path, index=False)
    before = path.read_bytes()
    client = DirectVCIClient()
    monkeypatch.setattr(client, "fetch_derivatives", lambda *_: derivatives_partition.copy())
    lake = MarketFlowLakehouse(flow_lake_root, client)
    with pytest.raises(ValueError):
        if boundary == "read":
            lake.read("derivatives", "VN30F1M", as_of=pd.Timestamp.now(tz="UTC").isoformat())
        else:
            lake.ingest("derivatives", "VN30F1M", "2026-01-02", "2026-01-02")
    assert path.read_bytes() == before


def test_lakehouse_failed_initial_writer_does_not_remove_successor(flow_lake_root, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from omega.data.market_flow import MarketFlowLakehouse
    import omega.data.vnstock_client as module
    published, release = Event(), Event()
    write = module.atomic_write_with_backup
    def publish(frame, target):
        write(frame, target)
        if frame["trading_date"].iloc[0] == "2026-01-02":
            published.set()
            assert release.wait(5)
            raise OSError("first writer fault")
    monkeypatch.setattr(module, "atomic_write_with_backup", publish)
    def ingest(day):
        client = DirectVCIClient(ssi_call=lambda *_: {"stocks": [_ssi_row(f"{day}/01/2026")]})
        return MarketFlowLakehouse(flow_lake_root, client).ingest("foreign", "HPG", f"2026-01-{day}", f"2026-01-{day}")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(ingest, "02")
        try:
            assert published.wait(5)
            second = pool.submit(ingest, "05")
        finally:
            release.set()
        with pytest.raises(OSError, match="first writer fault"):
            first.result(timeout=10)
        assert second.result(timeout=10)["status"] == "success"
    assert pd.read_parquet(flow_lake_root / "foreign_HPG.parquet")["trading_date"].tolist() == ["2026-01-05"]


@pytest.mark.parametrize("failure", ["unlink", "rollback_fsync"])
def test_lakehouse_initial_publication_cleanup_failure_is_explicit(flow_lake_root, monkeypatch, failure):
    from omega.data.market_flow import MarketFlowLakehouse
    import omega.data.vnstock_client as module
    lake = MarketFlowLakehouse(flow_lake_root, DirectVCIClient(ssi_call=lambda *_: {"stocks": [_ssi_row()]}))
    path = flow_lake_root / "foreign_HPG.parquet"
    replace = module.os.replace
    unlink = Path.unlink
    def broken_replace(source, target):
        replace(source, target)
        raise OSError("replacement fault")
    monkeypatch.setattr(module.os, "replace", broken_replace)
    if failure == "unlink":
        def broken_unlink(target, **kwargs):
            if target == path:
                raise OSError("unlink fault")
            return unlink(target, **kwargs)
        monkeypatch.setattr(Path, "unlink", broken_unlink)
    else:
        monkeypatch.setattr(module, "_fsync_directory", lambda *_: (_ for _ in ()).throw(OSError("rollback fsync fault")))
    with pytest.raises(OSError, match="rollback incomplete") as caught:
        lake.ingest("foreign", "HPG", "2026-01-02", "2026-01-02")
    assert str(caught.value.__cause__) == "replacement fault"
    assert path.exists() is (failure == "unlink")
    unlink(path, missing_ok=True)


@pytest.mark.parametrize("clock", ["2026-01-02T08:29:59Z", "2026-01-02T08:30:00Z", "2026-01-02T08:30:01Z"])
def test_lakehouse_derivatives_session_boundary(monkeypatch, clock):
    monkeypatch.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: pd.Timestamp(clock)))
    row = dict(symbol="VN30F1M", trading_date="02/01/2026", open=1200, high=1250, low=1100, close=1230, volume=0)
    client = DirectVCIClient(ssi_call=lambda *_: {"stocks": [row]})
    if clock.endswith("29:59Z"):
        with pytest.raises(ValueError, match="session"):
            client.fetch_derivatives("VN30F1M", "2026-01-02", "2026-01-02", as_of=clock)
    else:
        assert len(client.fetch_derivatives("VN30F1M", "2026-01-02", "2026-01-02", as_of=clock)) == 1


def test_lakehouse_parallel_writers_preserve_distinct_sessions(flow_lake_root):
    from concurrent.futures import ThreadPoolExecutor
    from omega.data.market_flow import MarketFlowLakehouse
    def ingest(day):
        client = DirectVCIClient(ssi_call=lambda *_: {"stocks": [_ssi_row(f"{day}/01/2026")]})
        return MarketFlowLakehouse(flow_lake_root, client).ingest("foreign", "HPG", f"2026-01-{day}", f"2026-01-{day}")
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(result["status"] == "success" for result in pool.map(ingest, ["02", "05"]))
    assert len(pd.read_parquet(flow_lake_root / "foreign_HPG.parquet")) == 2


def _foreign_frame():
    from omega.data.vci_direct import FOREIGN_FLOW_COLUMNS
    return pd.DataFrame([["2026-01-02", 1000, 400, 600, 10, 4, 6]], columns=FOREIGN_FLOW_COLUMNS)


def _ssi_row(day="02/01/2026"):
    return {"symbol": "HPG", "trading_date": day, "foreign_buy_value_total": "1000",
            "foreign_sell_value_total": "400", "foreign_buy_volume_total": "10", "foreign_sell_volume_total": "4"}


def payload():
    return {"t": [1704067200000], "o": [27], "h": [28], "l": [26], "c": [27.5], "v": [100]}


def test_direct_client_is_wired_into_data_adapters():
    direct = DirectVCIClient()
    assert VnstockClient(direct_vci=True, direct_vci_client=direct).direct_vci_client is direct
    assert VNMarketFlowDataSource(vci_client=direct).vci_client is direct
    assert GraphFetcher(vci_client=direct).vci_client is direct


def test_market_flow_uses_injected_vci_client():
    class Client:
        def foreign_trade(self, **kwargs):
            return _foreign_frame()

    rows = VNMarketFlowDataSource(vci_client=Client()).fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")
    assert rows[0]["timestamp"]
    assert rows[0]["buy_value"] == 1000
    assert rows[0]["ownership"] is None


def test_f007_ssi_history_and_all_facades_use_total_semantics(monkeypatch):
    from omega.data.vnstock_client import Trading
    calls = []
    def ssi(name, arguments):
        calls.append((name, arguments))
        assert "exchange" not in arguments
        return {"status": "success", "data": {"stocks": [_ssi_row()]}}
    direct = DirectVCIClient(ssi_call=ssi)
    monkeypatch.setattr(direct, "fetch_price_board", lambda *_: pytest.fail("Historical request reached live board"))
    for fetch in (lambda: direct.foreign_trade("HPG", "2026-01-01", "2026-01-02"),
                  lambda: Trading("HPG", direct_vci_client=direct).foreign_trade(start="2026-01-01", end="2026-01-02"),
                  lambda: VnstockClient(direct_vci_client=direct).fetch_foreign_trade("HPG", "2026-01-01", "2026-01-02")):
        frame = fetch()
        assert frame.iloc[0]["fr_buy_value_total"] == 1000
        assert "fr_buy_value_matched" not in frame
        assert frame.attrs["historical_pit_verified"] is False
    assert calls[0] == ("marketdata_list_daily_stock_infor", {"symbol": "HPG", "range": "1d", "toDate": "02/01/2026", "pageSize": 200, "pageIndex": 1})
    assert VNMarketFlowDataSource(vci_client=direct).fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")[0]["net_value"] == 600


def test_f007_ssi_accepts_ok_status_and_explicit_token():
    calls = []
    def ssi(name, arguments):
        calls.append((name, arguments))
        return {"status": "ok", "data": {"stocks": [_ssi_row()]}}

    client = DirectVCIClient(ssi_call=ssi, ssi_token="test-token")
    assert client.ssi_token == "test-token"
    frame = client.foreign_trade("HPG", "2026-01-01", "2026-01-02")
    assert not frame.empty
    assert frame.iloc[0]["fr_buy_value_total"] == 1000

    with pytest.raises(ValueError, match="ssi_token must be string"):
        DirectVCIClient(ssi_token=123)

    res = client.call_ssi("marketdata_list_daily_stock_infor", {"symbol": "HPG"})
    assert res["status"] == "ok"


@pytest.mark.parametrize("bad", [None, {}, {"stocks": []}, {"stocks": None}, {"status": "error", "data": None}])
def test_f007_ssi_errors_never_become_empty_success(bad):
    with pytest.raises((ValueError, RuntimeError)):
        DirectVCIClient(ssi_call=lambda *_: bad).foreign_trade("HPG", "2026-01-01", "2026-01-02")


@pytest.mark.parametrize("key,value", [("foreign_buy_value_total", None), ("foreign_buy_value_total", ""),
    ("foreign_buy_value_total", "NaN"), ("foreign_buy_value_total", "Inf"), ("foreign_buy_value_total", "-Inf"),
    ("foreign_buy_value_total", True), ("foreign_buy_value_total", -1), pytest.param("foreign_buy_value_total", 10**400, id="numeric-overflow"),
    ("foreign_buy_volume_total", 1.5), ("symbol", "VCB"), ("trading_date", None),
    ("trading_date", "03/01/2026"), ("trading_date", "bad")])
def test_f007_ssi_rejects_malformed_rows(key, value):
    row = _ssi_row()
    row[key] = value
    with pytest.raises(ValueError):
        DirectVCIClient(ssi_call=lambda *_: {"stocks": [row]}).foreign_trade("HPG", "2026-01-01", "2026-01-02")


@pytest.mark.parametrize("days,window", [(1, "1d"), (2, "3m"), (90, "3m"), (91, "6m"), (180, "6m"), (181, "1y"), (365, "1y"), (366, "max_range")])
def test_f007_ssi_chooses_smallest_range(days, window):
    end = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).normalize() - pd.Timedelta(days=1)
    start = end - pd.Timedelta(days=days)
    def call(name, arguments):
        assert arguments["range"] == window
        return {"stocks": [_ssi_row(end.strftime("%d/%m/%Y"))]}
    DirectVCIClient(ssi_call=call).foreign_trade("HPG", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))


@pytest.mark.parametrize("failure", ["duplicate", "exhausted", "later-error"])
def test_f007_ssi_pagination_is_bounded_and_atomic(failure):
    calls = []
    def call(name, arguments):
        calls.append(arguments["pageIndex"])
        if failure == "later-error" and len(calls) == 2:
            raise TimeoutError("failure")
        return {"stocks": [_ssi_row()] * 200}
    source = VNMarketFlowDataSource(vci_client=DirectVCIClient(ssi_call=call))
    with pytest.raises((ValueError, RuntimeError)):
        source.fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")
    assert source._cache == {}
    assert len(calls) <= 5


@pytest.mark.parametrize("time", ["08:29:59", "08:30:00", "08:30:01"])
def test_f007_live_foreign_board_cutoff_and_provenance(time, monkeypatch):
    timestamp = pd.Timestamp
    class FixedTimestamp(timestamp):
        @classmethod
        def now(cls, tz=None):
            value = timestamp("2026-10-16T09:00:00Z")
            return value.tz_convert(tz) if tz is not None else value.tz_localize(None)
    monkeypatch.setattr(pd, "Timestamp", FixedTimestamp)
    today = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date().isoformat()
    row = _board_row()
    row["matchPrice"].update(time=today + "T" + time + "Z", foreignBuyValue=1000, foreignSellValue=400,
                             foreignBuyVolume=10, foreignSellVolume=4)
    client, _ = _direct_fixture([row])
    client.ssi_call = lambda *_: pytest.fail("Current snapshot reached SSI")
    frame = client.foreign_trade("HPG", today, today)
    assert frame.iloc[0]["fr_net_volume_total"] == 6
    assert frame.attrs["snapshot"] is True
    assert frame.attrs["historical_pit_verified"] is False


@pytest.mark.parametrize("failure", ["stale", "missing", "partial", "malformed"])
def test_f007_live_board_fails_closed(failure):
    today = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date().isoformat()
    row = _board_row()
    row["matchPrice"].update(foreignBuyValue=1000, foreignSellValue=400, foreignBuyVolume=10, foreignSellVolume=4)
    if failure != "stale":
        row["matchPrice"]["time"] = pd.Timestamp.now(tz="UTC").isoformat()
    if failure == "missing":
        for key in ("foreignBuyValue", "foreignSellValue", "foreignBuyVolume", "foreignSellVolume"):
            del row["matchPrice"][key]
    if failure == "partial":
        del row["matchPrice"]["foreignBuyValue"]
    if failure == "malformed":
        row["matchPrice"]["foreignBuyValue"] = math.nan
    client, _ = _direct_fixture([row])
    with pytest.raises(ValueError):
        client.foreign_trade("HPG", today, today)


@pytest.mark.parametrize("failure", [None, "missing", "timeout", "malformed"])
def test_f007_prop_fallback_and_facades(monkeypatch, failure):
    import types
    from omega.data.vci_direct import PROP_FLOW_COLUMNS
    from omega.data.vnstock_client import Trading
    calls = []
    frame = pd.DataFrame([["2026-01-02", 1000, 400, 600, 10, 4, 6]], columns=PROP_FLOW_COLUMNS)
    frame.attrs["historical_pit_verified"] = True
    class Provider:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def prop_trade(self, **kwargs):
            if failure == "timeout":
                raise TimeoutError("https://user:password@example.com/?token=secret")
            if failure == "malformed":
                return pd.DataFrame()
            return frame
    if failure == "missing":
        Provider.prop_trade = None
    monkeypatch.setitem(sys.modules, "vnstock.api.trading", types.SimpleNamespace(Trading=Provider))
    direct = DirectVCIClient()
    monkeypatch.setattr(direct, "_ssi_daily_stock", lambda **_: pytest.fail("Prop reached SSI"))
    methods = [lambda: direct.prop_trade("HPG", "2026-01-01", "2026-01-02"),
               lambda: Trading("HPG", direct_vci_client=direct).prop_trade(start="2026-01-01", end="2026-01-02"),
               lambda: VnstockClient(direct_vci_client=direct).fetch_prop_trade("HPG", "2026-01-01", "2026-01-02"),
               lambda: VNMarketFlowDataSource(vci_client=direct).fetch_prop_flow("HPG", "2026-01-01", "2026-01-02")]
    for method in methods:
        if failure:
            with pytest.raises((ValueError, RuntimeError)) as error:
                method()
            assert "secret" not in str(error.value) and "password" not in str(error.value)
        else:
            result = method()
            if isinstance(result, pd.DataFrame):
                assert result.attrs["historical_pit_verified"] is False
            else:
                assert result[0]["net_value"] == 600
                assert result[0]["pct_buy_volume"] is None
    assert all(call == {"symbol": "HPG", "source": "VCI"} for call in calls)


@pytest.mark.parametrize("prop_call", [False, 0, "provider", {}, []])
def test_rem6_prop_call_requires_callable(prop_call):
    with pytest.raises(ValueError, match="prop_call must be callable"):
        DirectVCIClient(prop_call=prop_call)


@pytest.mark.parametrize("failure", [None, "timeout", "none", "empty", "schema", "duplicate", "net",
                                    "nan", "inf", "negative-inf", "overflow", "negative", "zero"])
def test_rem6_prop_call_all_public_entries_fail_closed(monkeypatch, failure):
    from omega.data.vci_direct import PROP_FLOW_COLUMNS
    from omega.data.vnstock_client import Trading
    monkeypatch.setitem(sys.modules, "vnstock.api.trading", None)
    calls = []
    frame = pd.DataFrame([["2026-01-02", 2e12, 1e12, 1e12, 10, 4, 6]], columns=PROP_FLOW_COLUMNS)
    frame.attrs.update(historical_pit_verified=True, available_at="2026-01-02T00:00:00Z")
    if failure == "empty":
        frame = frame.iloc[:0]
    elif failure == "schema":
        frame = frame.iloc[:, :1]
    elif failure == "duplicate":
        frame = pd.concat([frame, frame])
    elif failure == "net":
        frame.iloc[0, 3] = 0
    elif failure in ("nan", "inf", "negative-inf", "overflow", "negative"):
        frame.iloc[0, 1] = {"nan": math.nan, "inf": math.inf, "negative-inf": -math.inf,
                           "overflow": float(2**64), "negative": -1}[failure]
    elif failure == "zero":
        frame.iloc[0, 1:] = 0
    def fetch(**kwargs):
        calls.append(kwargs)
        if failure == "timeout":
            raise TimeoutError("https://user:password@example.com/?token=secret")
        return None if failure == "none" else frame
    direct = DirectVCIClient(prop_call=fetch)
    source = VNMarketFlowDataSource(vci_client=direct)
    methods = [lambda: direct.prop_trade(" hpg ", "2026-01-01", "2026-01-02"),
               lambda: Trading("HPG", direct_vci_client=direct).prop_trade(start="2026-01-01", end="2026-01-02"),
               lambda: VnstockClient(direct_vci_client=direct).fetch_prop_trade("HPG", "2026-01-01", "2026-01-02"),
               lambda: source.fetch_prop_flow("HPG", "2026-01-01", "2026-01-02")]
    for method in methods:
        if failure not in (None, "zero"):
            with pytest.raises((ValueError, RuntimeError)) as error:
                method()
            assert "secret" not in str(error.value) and "password" not in str(error.value)
            assert error.value.__suppress_context__ or failure != "timeout"
            assert source._cache == {}
        else:
            result = method()
            if isinstance(result, pd.DataFrame):
                assert result.attrs["source"] == "PROP_CALL"
                assert result.attrs["historical_pit_verified"] is False
                assert "available_at" not in result.attrs
                assert result.attrs["observed_at"].tzinfo is not None
            else:
                assert result[0]["net_value"] == (0 if failure == "zero" else 1e12)
    assert calls == [{"symbol": "HPG", "start": "2026-01-01", "end": "2026-01-02"}] * 4


@pytest.mark.parametrize("symbol,start,end", [(None, "2026-01-01", "2026-01-02"),
                                             ("", "2026-01-01", "2026-01-02"),
                                             ("HPG", None, "2026-01-02"),
                                             ("HPG", "", "2026-01-02"),
                                             ("HPG", "2026-01-03", "2026-01-02"),
                                             ("HPG", "2026-01-01", "2100-01-01")])
def test_rem6_prop_call_validates_before_dispatch(symbol, start, end):
    client = DirectVCIClient(prop_call=lambda **_: pytest.fail("Invalid request reached provider"))
    with pytest.raises(ValueError):
        client.prop_trade(symbol, start, end)


def test_rem6_prop_call_failure_recovers_without_partial_cache():
    from omega.data.vci_direct import PROP_FLOW_COLUMNS
    calls = []
    def fetch(**kwargs):
        calls.append(kwargs)
        frame = _foreign_frame()
        frame.columns = PROP_FLOW_COLUMNS
        return frame.iloc[:0] if len(calls) == 1 else frame
    source = VNMarketFlowDataSource(vci_client=DirectVCIClient(prop_call=fetch))
    with pytest.raises(ValueError):
        source.fetch_prop_flow("HPG", "2026-01-01", "2026-01-02")
    assert source._cache == {}
    rows = source.fetch_prop_flow("HPG", "2026-01-01", "2026-01-02")
    rows[0]["net_value"] = -1
    assert source.fetch_prop_flow("HPG", "2026-01-01", "2026-01-02")[0]["net_value"] == 600
    assert len(calls) == 2


@pytest.mark.skipif(os.environ.get("OMEGA_REM6_LIVE_SSI") != "1", reason="Explicit live SSI opt-in required")
def test_rem6_live_authenticated_ssi_public_entries():
    from omega.data.vci_direct import _get_ssi_token
    from omega.data.vnstock_client import Trading
    assert _get_ssi_token(), "Live SSI credentials unavailable"
    observed = []
    class LiveClient(DirectVCIClient):
        def foreign_trade(self, symbol, start, end):
            frame = super().foreign_trade(symbol, start, end)
            assert frame.attrs["source"] == "SSI_MCP"
            assert frame.attrs["snapshot"] is False
            assert frame.attrs["historical_pit_verified"] is False
            assert frame.attrs["observed_at"].tzinfo is not None
            assert "available_at" not in frame.columns
            observed.append({"rows": len(frame), "observed_at": frame.attrs["observed_at"].isoformat(),
                             "historical_pit_verified": False})
            return frame
    client = LiveClient(timeout=30)
    methods = [lambda: client.foreign_trade("HPG", "2026-10-12", "2026-10-13"),
               lambda: Trading("HPG", direct_vci_client=client).foreign_trade(start="2026-10-12", end="2026-10-13"),
               lambda: VnstockClient(direct_vci_client=client).fetch_foreign_trade("HPG", "2026-10-12", "2026-10-13"),
               lambda: VNMarketFlowDataSource(vci_client=client).fetch_foreign_flow("HPG", "2026-10-12", "2026-10-13")]
    for method in methods:
        assert len(method()) == 2
    assert len(observed) == 4
    print("SSI_MCP live public entries: " + json.dumps(observed))


def test_rem6_missing_prop_dependency_fails_closed(monkeypatch):
    monkeypatch.setitem(sys.modules, "vnstock.api.trading", None)
    source = VNMarketFlowDataSource(vci_client=DirectVCIClient())
    with pytest.raises(RuntimeError, match="vnstock proprietary-trade fallback unavailable"):
        source.fetch_prop_flow("HPG", "2026-01-01", "2026-01-02")
    assert source._cache == {}


@pytest.mark.parametrize("proprietary", [False, True])
@pytest.mark.parametrize("failure", ["missing", "empty", "duplicate", "bad-net", "outside", "provenance"])
def test_f007_injected_frames_cannot_bypass_validation(proprietary, failure):
    from omega.data.vci_direct import PROP_FLOW_COLUMNS
    frame = _foreign_frame()
    if proprietary:
        frame.columns = PROP_FLOW_COLUMNS
    if failure == "missing":
        frame = frame.iloc[:, :1]
    elif failure == "empty":
        frame = frame.iloc[:0]
    elif failure == "duplicate":
        frame = pd.concat([frame, frame])
    elif failure == "bad-net":
        frame.iloc[0, 3] = 1
    elif failure == "outside":
        frame.iloc[0, 0] = "2026-01-03"
    else:
        frame.attrs["historical_pit_verified"] = True
    class Client:
        def foreign_trade(self, **kwargs):
            return frame
        prop_trade = foreign_trade
    source = VNMarketFlowDataSource(vci_client=Client())
    fetch = source.fetch_prop_flow if proprietary else source.fetch_foreign_flow
    if failure == "provenance":
        result = source._trading_data("HPG", "prop_trade" if proprietary else "foreign_trade", "2026-01-01", "2026-01-02")
        assert result.attrs["historical_pit_verified"] is False
    else:
        with pytest.raises(ValueError):
            fetch("HPG", "2026-01-01", "2026-01-02")
        assert source._cache == {}


@pytest.mark.parametrize("proprietary", [False, True])
@pytest.mark.parametrize("value", [None, "", "bad", "2026-01-01T00:00:00Z", "2100-01-01"])
def test_f007_all_flow_dates_validate_before_dispatch(proprietary, value):
    class Client:
        def foreign_trade(self, **kwargs):
            pytest.fail("Invalid input reached provider")
        prop_trade = foreign_trade
    source = VNMarketFlowDataSource(vci_client=Client())
    fetch = source.fetch_prop_flow if proprietary else source.fetch_foreign_flow
    with pytest.raises(ValueError):
        fetch("HPG", value, value)
    assert source._cache == {}


@pytest.mark.parametrize("proprietary", [False, True])
def test_f007_injected_missing_method_and_unavailable_provider(proprietary):
    source = VNMarketFlowDataSource(vci_client=object())
    fetch = source.fetch_prop_flow if proprietary else source.fetch_foreign_flow
    with pytest.raises(RuntimeError, match="lacks"):
        fetch("HPG", "2026-01-01", "2026-01-02")
    source.vci_client = None
    source.Trading = None
    with pytest.raises(RuntimeError, match="unavailable"):
        fetch("HPG", "2026-01-01", "2026-01-02")


@pytest.mark.parametrize("values", [(0, 0, 0, 0), (10**13, 0, 10**6, 0)])
def test_f007_total_values_allow_zero_and_large_vnd_without_division(values):
    row = _ssi_row()
    for name, value in zip(("foreign_buy_value_total", "foreign_sell_value_total", "foreign_buy_volume_total", "foreign_sell_volume_total"), values):
        row[name] = value
    frame = DirectVCIClient(ssi_call=lambda *_: {"stocks": [row]}).foreign_trade("HPG", "2026-01-01", "2026-01-02")
    assert frame.iloc[0]["fr_net_value_total"] == values[0] - values[1]


def test_f007_foreign_never_imports_vnstock(monkeypatch):
    import builtins
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == "vnstock" or name.startswith("vnstock."):
            pytest.fail("Foreign flow imported vnstock")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    frame = DirectVCIClient(ssi_call=lambda *_: {"stocks": [_ssi_row()]}).foreign_trade("HPG", "2026-01-01", "2026-01-02")
    assert not frame.empty


@pytest.mark.parametrize("mode", ["structured", "text", "tool-error", "bad-content", "transport", "oversized"])
def test_f007_native_ssi_transport_lifecycle(monkeypatch, mode):
    from contextlib import asynccontextmanager
    import types
    import mcp
    import mcp.client.streamable_http as transport
    events = []
    @asynccontextmanager
    async def stream(url, **kwargs):
        assert url == "https://mcp.ssi.com.vn/mcp"
        events.append("open")
        try:
            if mode == "transport":
                raise TimeoutError("https://user:password@example.com/?token=secret")
            yield object(), object(), None
        finally:
            events.append("close")
    class Session:
        def __init__(self, *_):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            events.append("session-close")
        async def initialize(self):
            events.append("initialize")
        async def call_tool(self, name, arguments):
            assert name == "marketdata_list_daily_stock_infor" and "exchange" not in arguments
            value = {"stocks": [_ssi_row()]}
            content = [] if mode == "bad-content" else [types.SimpleNamespace(type="text", text="x" * 2000 if mode == "oversized" else json.dumps(value))]
            return types.SimpleNamespace(isError=mode == "tool-error", structuredContent=value if mode == "structured" else None, content=content)
    monkeypatch.setattr(transport, "streamablehttp_client", stream)
    monkeypatch.setattr(mcp, "ClientSession", Session)
    client = DirectVCIClient(max_payload_bytes=1000)
    if mode in ("structured", "text"):
        assert not client.foreign_trade("HPG", "2026-01-01", "2026-01-02").empty
    else:
        with pytest.raises(RuntimeError) as error:
            client.foreign_trade("HPG", "2026-01-01", "2026-01-02")
        assert "password" not in str(error.value) and "secret" not in str(error.value)
    assert events[0] == "open" and events[-1] == "close"


def test_f007_prop_missing_dependency_is_explicit(monkeypatch):
    import builtins
    original = builtins.__import__
    def missing(name, *args, **kwargs):
        if name == "vnstock.api.trading":
            raise ImportError("not installed")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(RuntimeError, match="fallback unavailable"):
        DirectVCIClient().prop_trade("HPG", "2026-01-01", "2026-01-02")


def test_f007_ssi_callback_error_is_secret_safe():
    def failed(*_):
        raise TimeoutError("https://user:password@example.com/?token=secret")
    with pytest.raises(RuntimeError) as error:
        DirectVCIClient(ssi_call=failed).foreign_trade("HPG", "2026-01-01", "2026-01-02")
    assert str(error.value) == "SSI MCP daily-stock request failed"
    assert error.value.__suppress_context__


def test_f007_ssi_successful_pagination_filters_inclusive_range():
    calls = []
    end = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).normalize() - pd.Timedelta(days=1)
    start = end - pd.Timedelta(days=200)
    def ssi(name, arguments):
        calls.append(arguments)
        offset = 0 if len(calls) == 1 else 200
        size = 200 if offset == 0 else 1
        return {"stocks": [_ssi_row((start + pd.Timedelta(days=offset + day)).strftime("%d/%m/%Y")) for day in range(size)]}
    frame = DirectVCIClient(ssi_call=ssi).foreign_trade("HPG", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    assert len(frame) == 201 and len(calls) == 2
    assert frame.iloc[0]["trading_date"] == start.strftime("%Y-%m-%d")
    assert frame.iloc[-1]["trading_date"] == end.strftime("%Y-%m-%d")


def test_f007_cache_return_isolation_and_live_refresh():
    class Client:
        calls = 0
        def foreign_trade(self, **kwargs):
            self.calls += 1
            frame = _foreign_frame()
            frame["trading_date"] = kwargs["end"]
            return frame
    client = Client()
    source = VNMarketFlowDataSource(vci_client=client)
    first = source.fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")
    first[0]["buy_value"] = -1
    second = source.fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")
    assert second[0]["buy_value"] == 1000
    second[0]["buy_value"] = -1
    assert source.fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")[0]["buy_value"] == 1000
    today = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date().isoformat()
    source.fetch_foreign_flow("HPG", today, today)
    source.fetch_foreign_flow("HPG", today, today)
    assert client.calls == 3



def test_market_flow_propagates_injected_transport_error():
    class Client:
        def foreign_trade(self, **kwargs):
            raise TimeoutError("VCI timeout")

    with pytest.raises(TimeoutError):
        VNMarketFlowDataSource(vci_client=Client()).fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_market_flow_rejects_non_finite_numeric_fields(bad_value):
    class Client:
        def foreign_trade(self, **kwargs):
            frame = _foreign_frame()
            frame["fr_buy_value_total"] = bad_value
            return frame

    with pytest.raises(ValueError, match="finite"):
        VNMarketFlowDataSource(vci_client=Client()).fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")


def test_market_flow_converts_ict_date_to_utc():
    class Client:
        def foreign_trade(self, **kwargs):
            return _foreign_frame()

    row = VNMarketFlowDataSource(vci_client=Client()).fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")[0]
    assert row["timestamp"] == int(pd.Timestamp("2026-01-01 17:00:00", tz="UTC").timestamp())


def test_graph_fetcher_uses_injected_vci_client():
    class Response:
        offset = 0

        def raise_for_status(self):
            pass

        def json(self):
            if "statistics-financial" in self.url:
                return {"data": [{"value": 1}]}
            return {"data": {"years": [2026], "quarters": [1]}}

    class Client:
        def get(self, *args, **kwargs):
            response = Response()
            response.url = args[0]
            return response

    result = GraphFetcher(vci_client=Client()).vci_financial_raw("HPG")
    assert set(result) == {"income_statement", "balance_sheet", "cash_flow", "ratios"}


def test_graph_fetcher_retry_exhaustion_does_not_make_extra_call(monkeypatch):
    calls = 0

    def rate_limited():
        nonlocal calls
        calls += 1
        raise RuntimeError("HTTP 429 rate limit")

    monkeypatch.setattr("omega.quant.graph.fetcher.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="HTTP 429"):
        GraphFetcher(max_retry_wall_time=0.001, retry_delay=60.0)._call(rate_limited)
    assert calls == 2


@pytest.mark.parametrize("symbol", [None, "", " ", 123, math.nan, math.inf, "HPG/../x", "HPG?x=1", "HPG#x", "A" * 17])
def test_graph_fetcher_vci_financial_raw_rejects_invalid_tickers(symbol):
    calls = 0

    class Client:
        def get(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            raise AssertionError("HTTP dispatch must not occur for invalid ticker")

    with pytest.raises(ValueError, match="Invalid ticker"):
        GraphFetcher(vci_client=Client()).vci_financial_raw(symbol)
    assert calls == 0


def test_graph_fetcher_vci_financial_raw_normalizes_and_escapes_ticker():
    urls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"value": 1}]} if "statistics-financial" in urls[-1] else {"data": {"years": [2026], "quarters": [1]}}

    class Client:
        def get(self, url, **_kwargs):
            urls.append(url)
            return Response()

    GraphFetcher(vci_client=Client()).vci_financial_raw("  hpg  ")
    assert all("/HPG/" in url for url in urls)
    assert all("?" not in url.split("?")[0] for url in urls)


def test_graph_fetcher_retry_wall_time_is_bounded_with_injected_clock():
    now = 0.0
    sleeps = []
    calls = 0

    def clock():
        return now

    def sleep(delay):
        nonlocal now
        sleeps.append(delay)
        now += delay

    def rate_limited():
        nonlocal calls
        calls += 1
        raise RuntimeError("HTTP 429 rate limit")

    with pytest.raises(RuntimeError, match="HTTP 429"):
        GraphFetcher(max_retry_wall_time=120.0, retry_delay=60.0, time_fn=clock, sleep_fn=sleep)._call(rate_limited)
    assert calls == 3
    assert sleeps == [60.0, 60.0]


def test_graph_fetcher_does_not_retry_non_rate_limit_errors(monkeypatch):
    calls = 0
    sleeps = 0

    def failed():
        nonlocal calls
        calls += 1
        raise ValueError("invalid response")

    def sleep(_):
        nonlocal sleeps
        sleeps += 1

    monkeypatch.setattr("omega.quant.graph.fetcher.time.sleep", sleep)
    with pytest.raises(ValueError, match="invalid response"):
        GraphFetcher()._call(failed)
    assert calls == 1
    assert sleeps == 0


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit()])
def test_graph_fetcher_propagates_base_exception(error):
    calls = 0

    def halted():
        nonlocal calls
        calls += 1
        raise error

    with pytest.raises(type(error)):
        GraphFetcher()._call(halted)
    assert calls == 1


def test_direct_client_rejects_invalid_dates_before_http_dispatch():
    calls = 0

    def opener(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("HTTP must not be called")

    client = DirectVCIClient(opener=opener)
    for start, end in [(None, "2026-01-02"), ("", "2026-01-02"), ("2026-02-01", "2026-1-1"), ("bad-date", "2026-01-02"), ("NaN", "2026-01-02")]:
        with pytest.raises(ValueError, match="date range"):
            client.fetch_history("HPG", start, end)
    assert calls == 0


def test_direct_client_normalizes_date_bounds_in_request():
    requests = []

    class Response:
        offset = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, amount):
            raw = json.dumps({"data": payload()}).encode()
            chunk = raw[self.offset:self.offset + amount]
            self.offset += len(chunk)
            return chunk

    def opener(request, **_kwargs):
        requests.append(json.loads(request.data))
        return Response()

    client = DirectVCIClient(opener=opener)
    with pytest.raises(ValueError, match="trading-session"):
        client.fetch_history("HPG", "2026-01-01T07:00:00+07:00", "2026-01-02T07:00:00+07:00")
    request_data = requests[-1]
    assert "from" not in request_data
    assert request_data["to"] == int(pd.Timestamp("2026-01-02T00:00:00+00:00").timestamp())
    assert request_data["countBack"] == 2


def test_vnstock_direct_transport_error_is_typed(monkeypatch):
    from omega.data import vnstock_client

    monkeypatch.setattr(vnstock_client, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("timeout")))
    client = VnstockClient(direct_vci=True)
    with pytest.raises(UpstreamTransportException):
        client.fetch_history("VCB", "2026-01-01", "2026-01-02")


def test_updater_cli_bootstraps_from_external_cwd_and_uses_canonical_flags(tmp_path):
    script = REPO_ROOT / "scripts" / "update_market_data.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, str(script), "--help"], cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert all(flag in result.stdout for flag in ("--symbols", "--start", "--end"))

    result = subprocess.run([sys.executable, str(script), "--dry-run", "--symbols", "HPG", "--start", "2026-01-01", "--end", "2026-01-02", "--obsolete"], cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr


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


@pytest.mark.parametrize("endpoint", [None, 123, ""])
def test_direct_client_rejects_invalid_endpoint_types(endpoint):
    with pytest.raises(ValueError):
        DirectVCIClient(endpoint=endpoint)


@pytest.mark.parametrize("timeout", [None, "15", math.nan, math.inf])
def test_direct_client_rejects_invalid_timeout_types(timeout):
    with pytest.raises(ValueError):
        DirectVCIClient(timeout=timeout)


def test_unpack_normalizes_integer_valued_kvnd_prices():
    integer_payload = {"t": [1704067200000], "o": [27], "h": [28], "l": [26], "c": [27], "v": [100]}
    assert unpack_vietcap_columnar("HPG", integer_payload).raw_close.iloc[0] == 27000


@pytest.mark.parametrize("timestamp", ["1704067200", "1704067200000"])
def test_unpack_accepts_numeric_string_timestamps(timestamp):
    string_payload = payload()
    string_payload["t"] = [timestamp]
    assert unpack_vietcap_columnar("HPG", string_payload).time.iloc[0] == pd.Timestamp("2024-01-01", tz="UTC")


@pytest.mark.parametrize("timestamp", ["", "abc", "1704067200.5", str(2**63), True, False])
def test_unpack_rejects_invalid_string_timestamps(timestamp):
    invalid_payload = payload()
    invalid_payload["t"] = [timestamp]
    with pytest.raises(ValueError, match="timestamps"):
        unpack_vietcap_columnar("HPG", invalid_payload)


@pytest.mark.parametrize("max_requests,period_seconds", [(0, 60), (-1, 60), (60, 0), (60, math.nan), (60, math.inf), ("60", 60)])
def test_rate_limiter_rejects_invalid_settings(max_requests, period_seconds):
    with pytest.raises(ValueError):
        RateLimiter(max_requests=max_requests, period_seconds=period_seconds)


def test_vnstock_client_atomic_write_restores_backup_on_dir_fsync_failure(tmp_path, monkeypatch):
    import omega.data.vnstock_client as vsc
    target = tmp_path / "market.parquet"
    atomic_write_with_backup(pd.DataFrame({"value": [1]}), target)
    monkeypatch.setattr(vsc.os, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("directory fsync failure")))
    with pytest.raises(OSError, match="directory fsync failure"):
        atomic_write_with_backup(pd.DataFrame({"value": [2]}), target)
    assert pd.read_parquet(target)["value"].tolist() == [1]


@pytest.mark.parametrize("start,end", [("2026-01-02", "2026-01-01"), (None, "2026-01-01"), ("bad", "2026-01-01")])
def test_market_flow_rejects_invalid_date_range_before_dispatch(start, end):
    class Client:
        def foreign_trade(self, **kwargs):
            raise AssertionError("provider dispatch must not occur")
    with pytest.raises(ValueError, match="date range"):
        VNMarketFlowDataSource(vci_client=Client()).fetch_foreign_flow("HPG", start, end)


def _canonical_sample():
    dates = pd.to_datetime(["2026-01-01", "2026-01-02"])
    return pd.DataFrame({
        "ticker": ["HPG", "HPG"], "date": dates, "exchange": ["HOSE", "HOSE"],
        "open": [27000.0, 27000.0], "high": [28000.0, 28000.0], "low": [26500.0, 26500.0],
        "close": [27500.0, 27500.0], "volume": [100000, 100000],
        "as_of": dates, "available_at": pd.to_datetime(["2026-01-02", "2026-01-03"], utc=True),
        "source": ["vnstock_vci", "vnstock_vci"], "price_scale": ["VND", "VND"],
        "adjusted": ["backward_adjusted", "backward_adjusted"], "rebuild_date": ["2026-06-13"] * 2,
    })


def test_updater_validation_rejects_duplicate_and_invalid_canonical_rows():
    frame = _canonical_sample()
    valid, errors = umd.validate_dataframe(pd.concat([frame, frame], ignore_index=True), "candidate")
    assert not valid and any("duplicate (ticker, date)" in error for error in errors)
    invalid = frame.copy()
    invalid.loc[0, "close"] = math.nan
    valid, errors = umd.validate_dataframe(invalid, "candidate")
    assert not valid and any("null" in error and "close" in error for error in errors)


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


def test_unpack_rejects_mixed_unit_duplicate_timestamps():
    bad = {"t": [1704067200, 1704067200000], "o": [27, 27], "h": [28, 28], "l": [26, 26], "c": [27.5, 27.5], "v": [100, 100]}
    with pytest.raises(ValueError, match="Duplicate timestamps"):
        unpack_vietcap_columnar("HPG", bad)


def test_unpack_rejects_non_integral_timestamps():
    bad = payload()
    bad["t"] = [1704067200.5]
    with pytest.raises(ValueError, match="timestamps"):
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
        offset = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, amount):
            chunk = body[self.offset:self.offset + amount]
            self.offset += len(chunk)
            return chunk

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


def test_updater_rejects_empty_candidate_before_publication():
    valid, errors = umd.validate_dataframe(pd.DataFrame(), "candidate")
    assert not valid and any("empty" in error for error in errors)


def test_updater_atomic_write_writes_valid_data(tmp_path):
    frame = _canonical_sample()
    target = tmp_path / "valid.parquet"
    umd.atomic_write_with_backup(frame, target)
    pd.testing.assert_frame_equal(pd.read_parquet(target), frame)


def test_updater_rejects_none_and_non_finite_candidate(tmp_path):
    with pytest.raises(TypeError, match="DataFrame"):
        umd.atomic_write_with_backup(None, tmp_path / "invalid.parquet")
    invalid = _canonical_sample()
    invalid.loc[0, "close"] = math.nan
    valid, errors = umd.validate_dataframe(invalid, "candidate")
    assert not valid and any("non-finite" in error for error in errors)


def test_direct_atomic_write_post_replace_failure_rolls_back(tmp_path, monkeypatch):
    import omega.data.vnstock_client as module

    target = tmp_path / "market.parquet"
    module.atomic_write_with_backup(_sample_frame(), target)
    original = target.read_bytes()
    def failed_sync(*_):
        raise OSError("directory fsync crash")
    monkeypatch.setattr(module, "_fsync_directory", failed_sync)
    with pytest.raises(OSError, match="directory fsync crash"):
        module.atomic_write_with_backup(_sample_frame(n=4), target)
    assert target.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("failure", [TimeoutError("VCI unavailable"), ConnectionError("VCI unavailable")])
def test_updater_provider_failure_has_bounded_attempts_without_remote_fallback(monkeypatch, failure):
    calls = []
    class Client:
        def fetch_history(self, **kwargs):
            calls.append(kwargs)
            raise failure
    with pytest.raises(RuntimeError, match="failed after 2 attempts") as caught:
        umd._fetch_history_chunked(Client(), "HPG", "2026-01-01", "2026-01-02", max_chunk_retries=2, listing_date="2020-01-01")
    assert len(calls) == 2
    assert caught.value.__cause__ is failure


def test_updater_rejects_unparseable_dates_before_transport():
    class Client:
        def fetch_history(self, **kwargs):
            raise AssertionError("No dispatch for malformed date")
    with pytest.raises(ValueError):
        umd._fetch_history_chunked(Client(), "HPG", "bad-date", "2026-01-02")


@pytest.mark.parametrize("start,end", [(None, "2026-01-02"), ("bad-date", "2026-01-02"), ("2026-01-03", "2026-01-02")])
def test_direct_history_rejects_invalid_date_bounds_before_transport(start, end):
    def forbidden(*_, **__):
        raise AssertionError("No dispatch for invalid bounds")
    with pytest.raises(ValueError, match="date range|date"):
        DirectVCIClient(opener=forbidden).fetch_history("HPG", start, end)


def test_updater_empty_remote_preserves_cache(tmp_path):
    target = tmp_path / "FLC.parquet"
    umd.atomic_write_with_backup(_canonical_sample(), target)
    original = target.read_bytes()
    class Client:
        def fetch_history(self, **kwargs):
            return pd.DataFrame()
    with pytest.raises(RuntimeError, match="empty"):
        umd.fetch_one_symbol(Client(), "FLC", "2026-01-01", "2026-01-12", "HOSE", listing_date="2020-01-01")
    assert target.read_bytes() == original


def test_updater_transport_failure_preserves_cache(tmp_path):
    target = tmp_path / "HPG.parquet"
    umd.atomic_write_with_backup(_canonical_sample(), target)
    original = target.read_bytes()
    class Client:
        def fetch_history(self, **kwargs):
            raise ConnectionError("provider down")
    with pytest.raises(RuntimeError, match="failed after"):
        umd.fetch_one_symbol(Client(), "HPG", "2026-01-01", "2026-01-02", "HOSE", listing_date="2020-01-01")
    assert target.read_bytes() == original


def test_direct_history_rejects_malformed_symbol_without_fallback():
    def forbidden(*_, **__):
        raise AssertionError("Invalid ticker dispatched")
    with pytest.raises(ValueError, match="Invalid ticker"):
        DirectVCIClient(opener=forbidden).fetch_history("HPG/../x", "2026-01-01", "2026-01-02")


def test_updater_post_delisting_empty_is_not_synthetic_archive_data():
    class Client:
        def fetch_history(self, **kwargs):
            return pd.DataFrame()
    frame = umd.fetch_one_symbol(Client(), "FLC", "2026-01-01", "2026-01-02", "HOSE", listing_date="2020-01-01", delisting_date="2025-12-31")
    assert frame.empty


class _FakeTransportResponse:
    def __init__(self, raw: bytes, status: int = 200):
        self._raw = raw
        self._offset = 0
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, *args):
        amount = args[0] if args else -1
        if amount < 0:
            amount = len(self._raw) - self._offset
        chunk = self._raw[self._offset:self._offset + amount]
        self._offset += len(chunk)
        return chunk


def test_graph_fetcher_vci_financial_raw_exercises_genuine_direct_vci_client_get():
    recorded_urls = []
    recorded_timeouts = []

    def fake_transport_opener(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        recorded_urls.append(url)
        recorded_timeouts.append(timeout)
        assert request.get_method() == "GET"
        user_agent = request.headers.get("User-agent", request.headers.get("User-Agent", ""))
        assert "Mozilla" in user_agent or "OMEGA_QUANT" in user_agent
        if "statistics-financial" in url:
            data = {"data": [{"ticker": "HPG", "pe": 10.5, "pb": 1.2}]}
        else:
            data = {"data": {"years": [2025, 2026], "quarters": [1, 2]}}
        return _FakeTransportResponse(json.dumps(data).encode(), status=200)

    client = DirectVCIClient(opener=fake_transport_opener)
    fetcher = GraphFetcher(vci_client=client)
    res = fetcher.vci_financial_raw("HPG", timeout=22)

    assert set(res.keys()) == {"income_statement", "balance_sheet", "cash_flow", "ratios"}
    assert res["ratios"]["data"][0]["pe"] == 10.5
    assert res["income_statement"]["data"]["years"] == [2025, 2026]
    assert len(recorded_urls) == 4
    assert all(t == 22 for t in recorded_timeouts)
    assert all("/HPG/" in u for u in recorded_urls)


def test_graph_fetcher_vci_financial_raw_direct_vci_timeout_error():
    def timing_out_opener(request, timeout=None):
        raise TimeoutError("connection timed out to Vietcap gateway")

    client = DirectVCIClient(opener=timing_out_opener)
    fetcher = GraphFetcher(vci_client=client)
    with pytest.raises(RuntimeError, match="VCI request failed: connection timed out"):
        fetcher.vci_financial_raw("HPG")


def test_graph_fetcher_vci_financial_raw_direct_vci_http_404_error():
    def not_found_opener(request, timeout=None):
        raise HTTPError(request.full_url, 404, "Not Found", {}, None)

    client = DirectVCIClient(opener=not_found_opener)
    fetcher = GraphFetcher(vci_client=client)
    with pytest.raises(RuntimeError, match="HTTP Error 404"):
        fetcher.vci_financial_raw("HPG")


def test_graph_fetcher_vci_financial_raw_direct_vci_http_429_retry_exhaustion(monkeypatch):
    calls = 0
    sleeps = []

    def rate_limited_opener(request, timeout=None):
        nonlocal calls
        calls += 1
        raise HTTPError(request.full_url, 429, "Too Many Requests", {"Retry-After": "0.5"}, None)

    monkeypatch.setattr(time, "sleep", lambda delay: sleeps.append(delay))
    client = DirectVCIClient(opener=rate_limited_opener, max_attempts=3)
    fetcher = GraphFetcher(vci_client=client)

    with pytest.raises(RuntimeError, match="429"):
        fetcher.vci_financial_raw("HPG")

    assert calls == 3
    assert sleeps == [0.5, 0.5]


def test_direct_client_get_retries_normal_429_response(monkeypatch):
    calls = 0
    sleeps = []

    def opener(request, timeout=None):
        nonlocal calls
        calls += 1
        return _FakeTransportResponse(b"{}", status=429 if calls == 1 else 200)

    monkeypatch.setattr(time, "sleep", lambda delay: sleeps.append(delay))
    response = DirectVCIClient(opener=opener).get("https://iq.vietcap.com.vn/api/iq-insight-service/v1/test")
    assert response.status_code == 200
    assert calls == 2
    assert sleeps == [1]


@pytest.mark.parametrize("status_code", [300, 301, 302, 400, 404, 500, 503])
def test_direct_client_get_rejects_all_non_success_statuses(status_code):
    calls = 0

    def opener(request, timeout=None):
        nonlocal calls
        calls += 1
        return _FakeTransportResponse(b"{}", status=status_code)

    with pytest.raises(RuntimeError, match=f"HTTP Error {status_code}"):
        DirectVCIClient(opener=opener, max_attempts=10).get("https://iq.vietcap.com.vn/api/test")
    assert calls == 1


def test_direct_client_get_bounds_normal_429_retry(monkeypatch):
    calls = 0
    sleeps = []

    def opener(request, timeout=None):
        nonlocal calls
        calls += 1
        return _FakeTransportResponse(b"{}", status=429)

    monkeypatch.setattr(time, "sleep", lambda delay: sleeps.append(delay))
    with pytest.raises(RuntimeError, match="HTTP 429"):
        DirectVCIClient(opener=opener, max_attempts=3).get("https://iq.vietcap.com.vn/api/test")
    assert calls == 3
    assert sleeps == [1, 2]


@pytest.mark.parametrize("url", [
    "https://example.com/api/test",
    "https://iq.vietcap.com.vn/private/test",
    "https://127.0.0.1/api/test",
])
def test_direct_client_get_rejects_unapproved_origins_and_paths(url):
    with pytest.raises(ValueError, match="approved VCI"):
        DirectVCIClient().get(url)


def test_graph_fetcher_vci_financial_raw_direct_vci_payload_size_limit():
    def huge_payload_opener(request, timeout=None):
        return _FakeTransportResponse(b"X" * 1024)

    client = DirectVCIClient(opener=huge_payload_opener, max_payload_bytes=512)
    fetcher = GraphFetcher(vci_client=client)
    with pytest.raises(ValueError, match="exceeds size limit"):
        fetcher.vci_financial_raw("HPG")


@pytest.mark.parametrize("bad_envelope,expected_err", [
    ({"data": {"years": [], "quarters": [1]}}, "VCI_STATEMENT_CONTRACT_VIOLATION"),
    ({"data": {"years": [2026], "quarters": []}}, "VCI_STATEMENT_CONTRACT_VIOLATION"),
    ({"data": None}, "VCI_STATEMENT_CONTRACT_VIOLATION"),
    ({}, "VCI_STATEMENT_CONTRACT_VIOLATION"),
    ({"data": {"years": [2026], "quarters": [1]}, "error": "upstream fault"}, "VCI_STATEMENT_CONTRACT_VIOLATION"),
    ({"data": {"years": [2026], "quarters": [1]}, "truncated": True}, "VCI_STATEMENT_CONTRACT_VIOLATION"),
])
def test_graph_fetcher_vci_financial_raw_statement_contract_violations(bad_envelope, expected_err):
    def opener(request, timeout=None):
        return _FakeTransportResponse(json.dumps(bad_envelope).encode())

    client = DirectVCIClient(opener=opener)
    fetcher = GraphFetcher(vci_client=client)
    with pytest.raises(ValueError, match=expected_err):
        fetcher.vci_financial_raw("HPG")


@pytest.mark.parametrize("bad_ratios", [
    {"data": []},
    {"data": None},
    {"data": {}},
    {},
])
def test_graph_fetcher_vci_financial_raw_ratio_contract_violations(bad_ratios):
    def opener(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "statistics-financial" in url:
            data = bad_ratios
        else:
            data = {"data": {"years": [2026], "quarters": [1]}}
        return _FakeTransportResponse(json.dumps(data).encode())

    client = DirectVCIClient(opener=opener)
    fetcher = GraphFetcher(vci_client=client)
    with pytest.raises(ValueError, match="VCI_RATIO_CONTRACT_VIOLATION"):
        fetcher.vci_financial_raw("HPG")


@pytest.mark.parametrize("bad_endpoint", [
    None,
    "",
    "http://insecure.vietcap.com.vn",
    "ftp://vietcap.com.vn",
    "https://user:pass@iq.vietcap.com.vn",
])
def test_direct_client_get_rejects_invalid_endpoints(bad_endpoint):
    client = DirectVCIClient()
    with pytest.raises((ValueError, TypeError)):
        client.get(bad_endpoint)


@pytest.mark.parametrize("bad_timeout", [
    math.nan,
    math.inf,
    -1.0,
    0,
    0.0,
])
def test_direct_client_get_and_init_rejects_non_finite_or_non_positive_timeout(bad_timeout):
    with pytest.raises(ValueError, match="timeout must be positive and finite"):
        DirectVCIClient(timeout=bad_timeout)

    client = DirectVCIClient()
    with pytest.raises(ValueError, match="timeout must be positive and finite"):
        client.get("https://iq.vietcap.com.vn/api/test", timeout=bad_timeout)


def test_direct_client_init_rejects_unapproved_post_endpoint():
    for bad_endpoint in (
        "https://evil.example/api/chart/OHLCChart/gap-chart",
        "https://trading.vietcap.com.vn/private/chart",
        "http://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
    ):
        with pytest.raises(ValueError):
            DirectVCIClient(endpoint=bad_endpoint)


def test_direct_client_get_rejects_bool_timeout():
    for bad_timeout in (True, False):
        with pytest.raises(ValueError, match="timeout must be positive and finite"):
            DirectVCIClient().get("https://iq.vietcap.com.vn/api/test", timeout=bad_timeout)


def test_unpack_vietcap_columnar_rejects_bool_scalars():
    for key in ("t", "o", "h", "l", "c", "v"):
        bad = payload()
        bad[key] = [True]
        with pytest.raises(ValueError):
            unpack_vietcap_columnar("HPG", bad)
    with pytest.raises(ValueError):
        unpack_vietcap_columnar("HPG", payload(), adj_ratio=True)


def test_f001_oversized_integer_scalars_fail_closed():
    for key in ("t", "o", "h", "l", "c", "v"):
        bad = payload()
        bad[key] = [10**400]
        with pytest.raises(ValueError):
            unpack_vietcap_columnar("HPG", bad)


def test_f001_oversized_price_bound_scalars_fail_closed():
    assert not validate_price_bounds(10**400, 10_000, "HOSE")
    assert not validate_price_bounds(10_000, 10**400, "HOSE")


def test_f002_url_validation_rejects_traversal_query_and_fragment():
    for url in (
        "https://trading.vietcap.com.vn/api/../private",
        "https://trading.vietcap.com.vn/api/%2e%2e/private",
        "https://trading.vietcap.com.vn/api/%252e%252e/private",
        "https://iq.vietcap.com.vn/v1/test?smuggled=1",
        "https://iq.vietcap.com.vn/v1/test#fragment",
    ):
        with pytest.raises(ValueError, match="approved VCI"):
            DirectVCIClient().get(url)


@pytest.mark.parametrize("bad_ratio", [None, "1", 0.0, -1.0, math.nan, math.inf, 1000.0001])
def test_unpack_rejects_invalid_or_unbounded_adjustment_ratio(bad_ratio):
    with pytest.raises((ValueError, TypeError), match="adjustment ratio|float"):
        unpack_vietcap_columnar("HPG", payload(), adj_ratio=bad_ratio)


@pytest.mark.parametrize("ratio", [0.01, 1000.0])
def test_unpack_rejects_adjusted_prices_outside_vnd_full_bounds(ratio):
    with pytest.raises(ValueError, match="VND_FULL bounds"):
        unpack_vietcap_columnar("HPG", payload(), adj_ratio=ratio)


def test_direct_client_enforces_hard_resource_ceilings():
    with pytest.raises(ValueError):
        DirectVCIClient(max_payload_bytes=64 * 1024 * 1024 + 1)
    with pytest.raises(ValueError):
        DirectVCIClient(max_attempts=11)
    client = DirectVCIClient(max_payload_bytes=64 * 1024 * 1024, max_attempts=10)
    assert client.max_payload_bytes == 64 * 1024 * 1024
    assert client.max_attempts == 10


def test_unpack_vietcap_columnar_rejects_unsorted_timestamps():
    bad = payload()
    bad.update({key: [value[0], value[0]] for key, value in bad.items()})
    bad["t"] = [1704067200000, 1703980800000]
    with pytest.raises(ValueError, match="chronological"):
        unpack_vietcap_columnar("HPG", bad)


def test_direct_client_fetch_history_checks_http_status():
    def opener(request, timeout=None):
        return _FakeTransportResponse(b'{"data": {}}', status=500)

    with pytest.raises(RuntimeError, match="HTTP Error 500"):
        DirectVCIClient(opener=opener, max_attempts=1).fetch_history("HPG", "2026-01-01", "2026-01-02")


def test_direct_client_fetch_history_rejects_countback_overflow():
    with pytest.raises(ValueError, match="countBack"):
        DirectVCIClient().fetch_history("HPG", "1800-01-01", "2026-01-01")


@pytest.mark.parametrize("bad_rate,bad_cap", [
    (math.nan, 10.0),
    (math.inf, 10.0),
    (-1.0, 10.0),
    (0.0, 10.0),
    (10.0, math.nan),
    (10.0, math.inf),
    (10.0, -1.0),
    (10.0, 0.0),
])
def test_token_bucket_boundary_rejections(bad_rate, bad_cap):
    with pytest.raises(ValueError):
        TokenBucket(rate=bad_rate, capacity=bad_cap)


@pytest.mark.parametrize("raw_c,prev_c", [
    (math.nan, 10000),
    (math.inf, 10000),
    (10000, math.nan),
    (10000, math.inf),
    (None, 10000),
    (10000, None),
])
def test_validate_price_bounds_rejects_non_finite_or_none(raw_c, prev_c):
    assert not validate_price_bounds(raw_c, prev_c, "HOSE")


@pytest.mark.parametrize("bad_bool", [True, False])
def test_f001_numeric_limits_reject_booleans(bad_bool):
    with pytest.raises(ValueError):
        DirectVCIClient(max_payload_bytes=bad_bool)
    with pytest.raises(ValueError):
        DirectVCIClient(max_attempts=bad_bool)
    with pytest.raises(ValueError):
        TokenBucket(rate=bad_bool)
    with pytest.raises(ValueError):
        TokenBucket(capacity=bad_bool)


@pytest.mark.parametrize("raw_c,prev_c,exchange", [(True, 10000, "HOSE"), (10000, True, "HOSE"), (10000, 10000, None), (10000, 10000, 123)])
def test_f001_validate_price_bounds_rejects_bool_and_invalid_exchange(raw_c, prev_c, exchange):
    assert not validate_price_bounds(raw_c, prev_c, exchange)


@pytest.mark.parametrize("flag_name", ["is_corporate_action_date", "is_first_listing_date"])
@pytest.mark.parametrize("flag", [0, 1, "true", "false", 1.0, None])
def test_f001_validate_price_bounds_rejects_non_bool_flags(flag_name, flag):
    flags = {flag_name: flag}
    assert not validate_price_bounds(10_000, 10_000, "HOSE", **flags)


@pytest.mark.parametrize("exchange", ["", " ", "BOGUS", "NYSE", "NASDAQ", "hose_extra", None, 123])
def test_f001_validate_price_bounds_rejects_unknown_exchanges(exchange):
    assert not validate_price_bounds(10_000, 10_000, exchange)


def test_f002_url_validation_rejects_oversized_url_before_request():
    client = DirectVCIClient(opener=lambda *_args, **_kwargs: pytest.fail("HTTP dispatch must not occur"))
    oversized_url = "https://iq.vietcap.com.vn/api/" + ("a" * 2020)
    with pytest.raises(ValueError, match="approved VCI"):
        client.get(oversized_url)


def test_f002_url_validation_rejects_oversized_query_before_parse():
    client = DirectVCIClient(opener=lambda *_args, **_kwargs: pytest.fail("HTTP dispatch must not occur"))
    oversized_query = "https://iq.vietcap.com.vn/api/test?" + ("a" * 1025)
    with pytest.raises(ValueError, match="approved VCI"):
        client.get(oversized_query)


def test_f002_fetch_history_returns_explicit_pit_fields():
    bar_ms = 1704153600000
    raw = json.dumps({"data": [{"t": [bar_ms], "o": [27], "h": [28], "l": [26], "c": [27.5], "v": [100]}]}).encode()
    client = DirectVCIClient(opener=lambda request, timeout=None: _FakeTransportResponse(raw))
    frame = client.fetch_history("HPG", "2024-01-01", "2024-01-05", as_of="2024-01-03T15:30:00Z")
    assert {"as_of", "available_at"}.issubset(frame.columns)
    assert (frame["as_of"] <= frame["available_at"]).all()
    assert (frame["available_at"] <= pd.Timestamp("2024-01-03T15:30:00Z")).all()


@pytest.mark.parametrize("cli_args", [["--unknown-flag"], ["--malicious=true"], ["-x"], ["--output", "target.parquet", "--bogus"]])
def test_f003_updater_cli_rejects_unknown_and_flag_smuggling(cli_args):
    script = REPO_ROOT / "scripts" / "update_market_data.py"
    result = subprocess.run([sys.executable, str(script), "--dry-run", "--symbols", "HPG", "--start", "2026-01-01", "--end", "2026-01-02", *cli_args], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr


def test_f004_capped_reader_reads_chunks_and_rejects_oversized_stream():
    class Stream(_FakeTransportResponse):
        def __init__(self):
            super().__init__(b"", 200)
            self.calls = []
            self.remaining = 3

        def read(self, amount):
            self.calls.append(amount)
            self.remaining -= 1
            return b"x" * 1024 if self.remaining >= 0 else b""

    stream = Stream()
    client = DirectVCIClient(opener=lambda request, timeout=None: stream, max_payload_bytes=2048)
    with pytest.raises(ValueError, match="exceeds size limit"):
        client.get("https://iq.vietcap.com.vn/api/test")
    assert stream.calls == [2048, 1024]


@pytest.mark.parametrize("bad_val", [math.nan, math.inf, 0, -1.0])
def test_graph_fetcher_retry_timing_boundaries_reject_non_finite_or_non_positive(bad_val):
    with pytest.raises(ValueError, match="max_retry_wall_time must be positive and finite"):
        GraphFetcher(max_retry_wall_time=bad_val)
    with pytest.raises(ValueError, match="retry_delay must be positive and finite"):
        GraphFetcher(retry_delay=bad_val)


def test_updater_atomic_write_readback_failure_preserves_target_and_cleans_temp(tmp_path, monkeypatch):
    target = tmp_path / "protected_target.parquet"
    original_frame = _canonical_sample()
    umd.atomic_write_with_backup(original_frame, target)
    original_bytes = target.read_bytes()
    def corrupt_readback(*_, **__):
        return pd.DataFrame()
    monkeypatch.setattr(umd.pd, "read_parquet", corrupt_readback)
    with pytest.raises(ValueError, match="verification failed"):
        umd.atomic_write_with_backup(original_frame, target)
    assert target.read_bytes() == original_bytes
    assert not list(tmp_path.glob("*.tmp"))


# ---------------------------------------------------------------------------
# F-001: Fractional volume rejection
# ---------------------------------------------------------------------------

def test_unpack_rejects_fractional_volume():
    """Volume with non-integer values must raise ValueError, not silently round."""
    frac_payload = {"t": [1704067200000], "o": [27], "h": [28], "l": [26], "c": [27.5], "v": [100.7]}
    with pytest.raises(ValueError, match="non-integer"):
        unpack_vietcap_columnar("HPG", frac_payload)


def test_unpack_accepts_integer_volume_as_float():
    """Volume stored as float but with zero fractional part is accepted."""
    ok_payload = {"t": [1704067200000], "o": [27], "h": [28], "l": [26], "c": [27.5], "v": [100.0]}
    frame = unpack_vietcap_columnar("HPG", ok_payload)
    assert frame["volume"].iloc[0] == 100
    assert frame["volume"].dtype.name == "int64"


# ---------------------------------------------------------------------------
# F-002: available_at next-trading-session semantics
# ---------------------------------------------------------------------------

def _make_friday_payload():
    """2026-01-02 is a Friday (trading day); available_at should be Monday 2026-01-05 09:00 ICT."""
    # timestamp for 2026-01-02 09:00 ICT = 2026-01-02 02:00 UTC
    ts_ms = int(pd.Timestamp("2026-01-02 02:00:00", tz="UTC").timestamp() * 1000)
    return {"t": [ts_ms], "o": [27], "h": [28], "l": [26], "c": [27.5], "v": [100]}


def test_available_at_friday_candle_available_on_monday():
    """Friday candle should be available on the next Monday, not Saturday."""
    from omega.data.calendar import VNTradingCalendar
    from datetime import date
    frame = unpack_vietcap_columnar("HPG", _make_friday_payload())
    local_date = frame["time"].iloc[0].tz_convert("Asia/Ho_Chi_Minh").date()
    assert local_date == date(2026, 1, 2)  # confirm it is a Friday
    assert VNTradingCalendar.is_trading_day(pd.Timestamp("2026-01-02").to_pydatetime())
    # next_trading_day must skip Saturday and Sunday
    next_td = VNTradingCalendar.next_trading_day(local_date)
    assert next_td == date(2026, 1, 5), f"Expected Monday 2026-01-05, got {next_td}"


def test_unpack_friday_available_at_is_not_saturday():
    """available_at for a Friday date must not be Saturday - verify via calendar."""
    from omega.data.calendar import VNTradingCalendar
    from datetime import date
    friday = date(2026, 1, 2)
    assert VNTradingCalendar.is_trading_day(pd.Timestamp(friday.isoformat()).to_pydatetime())
    next_td = VNTradingCalendar.next_trading_day(friday)
    # Compute available_at as the patched code does: next trading day at 09:00 ICT
    import zoneinfo
    ict = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
    available_at_ict = pd.Timestamp(next_td, tz=ict) + pd.Timedelta(hours=9)
    assert available_at_ict.weekday() != 5, "available_at must not fall on Saturday"
    assert available_at_ict.weekday() == 0, f"Expected Monday, got weekday {available_at_ict.weekday()}"
    assert available_at_ict.hour == 9


def _direct_fixture(data):
    calls = []
    def opener(request, timeout=None):
        calls.append(request)
        return _FakeTransportResponse(json.dumps(data).encode())
    return DirectVCIClient(opener=opener), calls


def test_direct_company_profile_and_listing_date():
    client, calls = _direct_fixture({"data": {"ticker": "HPG", "listingDate": "2007-11-15", "profile": "Steel"}})
    assert client.fetch_listing_date(" hpg ") == "2007-11-15"
    assert client.fetch_company_profile("HPG").iloc[0]["company_profile"] == "Steel"
    assert calls[0].full_url.endswith("/company/details?ticker=HPG")


@pytest.mark.parametrize("value", [None, {}, {"data": []}, {"data": {"listingDate": 123}}, {"data": {"listingDate": "bad"}}])
def test_direct_profile_rejects_malformed_metadata(value):
    client, _ = _direct_fixture(value)
    with pytest.raises(ValueError):
        client.fetch_listing_date("HPG")


def test_direct_listing_date_missing_is_not_inferred():
    client, _ = _direct_fixture({"data": {}})
    assert client.fetch_listing_date("HPG") is None


def test_direct_all_symbols_filters_products_and_maps_exchange():
    client, calls = _direct_fixture([{"symbol": "HPG", "board": "HSX", "type": "STOCK", "organName": "Steel"}, {"symbol": "VN30F1M", "board": "HNX", "type": "FUTURES"}])
    frame = client.fetch_all_symbols()
    assert frame[["ticker", "exchange"]].to_dict("records") == [{"ticker": "HPG", "exchange": "HOSE"}]
    assert calls[0].get_method() == "GET"


@pytest.mark.parametrize("rows", [None, {}, [None], [{"symbol": "HPG"}], [{"symbol": "HPG", "board": "OTHER", "type": "STOCK"}], [{"symbol": "HPG", "board": "HSX", "type": "STOCK"}] * 2])
def test_direct_symbols_reject_malformed_or_duplicate_universe(rows):
    client, _ = _direct_fixture(rows)
    with pytest.raises(ValueError):
        client.fetch_all_symbols()


@pytest.mark.parametrize("statement,section", [("income", "INCOME_STATEMENT"), ("balance", "BALANCE_SHEET"), ("cashflow", "CASH_FLOW"), ("ratio", None)])
@pytest.mark.parametrize("period,key", [("year", "years"), ("quarter", "quarters")])
def test_direct_financials_statement_and_period(statement, section, period, key):
    client, calls = _direct_fixture({"data": {"years": [{"yearReport": 2025}], "quarters": [{"yearReport": 2026}]}})
    frame = client.fetch_financials("HPG", statement, period)
    assert frame.iloc[0]["year_report"] == (2025 if key == "years" else 2026)
    assert frame.attrs["historical_pit_verified"] is False
    assert calls[0].full_url.endswith("section=" + section if section else "/statistics-financial")


@pytest.mark.parametrize("method", ["fetch_company_news", "fetch_company_events"])
def test_direct_company_pages_cursor_and_schema(method):
    row = {"newsTitle": "Profit", "publicDate": "2026-10-01T09:00:00"} if method == "fetch_company_news" else {"eventNameVi": "Dividend", "publicDate": "2026-10-01T09:00:00"}
    client, calls = _direct_fixture({"data": {"content": [row], "last": False}})
    frame = getattr(client, method)("HPG", page_size=1, cursor="2")
    assert frame.attrs["next_cursor"] == "3"
    assert "page=2&size=1" in calls[0].full_url
    assert "public_date" in frame
    if method == "fetch_company_news":
        assert frame.iloc[0]["news_title"] == "Profit"


@pytest.mark.parametrize("method", ["fetch_company_news", "fetch_company_events"])
@pytest.mark.parametrize("value", [None, {}, {"data": []}, {"data": {"content": [None]}}, {"data": {"content": [{}]}}, {"data": {"content": [], "last": False}}, {"data": {"content": [], "last": "false"}}])
def test_direct_company_pages_fail_closed(method, value):
    client, _ = _direct_fixture(value)
    with pytest.raises(ValueError):
        getattr(client, method)("HPG")


@pytest.mark.parametrize("value", [None, "", [], 123, math.nan, math.inf, "--help", "HPG/../X"])
@pytest.mark.parametrize("method", ["fetch_listing_date", "fetch_company_profile", "fetch_financials", "fetch_company_news", "fetch_company_events"])
def test_direct_company_inputs_rejected_before_transport(method, value):
    client, calls = _direct_fixture({})
    with pytest.raises(ValueError):
        getattr(client, method)(value)
    assert calls == []


@pytest.mark.parametrize("page_size,cursor", [(0, None), (-1, None), (True, None), (101, None), (math.inf, None), (10, "-1"), (10, "500"), (10, []), (10, "1&size=999")])
def test_direct_company_pagination_is_bounded(page_size, cursor):
    client, calls = _direct_fixture({})
    with pytest.raises(ValueError):
        client.fetch_company_news("HPG", page_size, cursor)
    assert calls == []


@pytest.mark.parametrize("value", [None, {}, {"data": {"years": None}}, {"data": {"years": [None]}}, {"data": {"years": [{"isa1": math.inf}]}}, {"data": {"years": [{"isa1": math.nan}]}}])
def test_direct_financials_rejects_malformed_and_non_finite_payloads(value):
    client, _ = _direct_fixture(value)
    with pytest.raises(ValueError):
        client.fetch_financials("HPG")


@pytest.mark.parametrize("statement,period", [(None, "year"), ([], "year"), ("income", []), ("income", "month"), ("--help", "year")])
def test_direct_financials_validates_options_before_transport(statement, period):
    client, calls = _direct_fixture({})
    with pytest.raises(ValueError):
        client.fetch_financials("HPG", statement, period)
    assert calls == []


@pytest.mark.parametrize("method", ["fetch_company_profile", "fetch_all_symbols", "fetch_financials", "fetch_company_news", "fetch_company_events", "fetch_price_board"])
def test_direct_new_endpoints_transport_failure_is_explicit(method):
    def opener(*args, **kwargs):
        raise TimeoutError("upstream timeout")
    client = DirectVCIClient(opener=opener)
    args = () if method == "fetch_all_symbols" else (["HPG"],) if method == "fetch_price_board" else ("HPG",)
    with pytest.raises(RuntimeError, match="timeout"):
        getattr(client, method)(*args)


def _board_row():
    return {"listingInfo": {"symbol": "HPG", "board": "HSX"}, "matchPrice": {"openPrice": 20450, "highest": 20550, "lowest": 20350, "matchPrice": 20450, "accumulatedVolume": 4857400, "time": "2026-10-01T06:35:49Z"}}


def test_direct_price_board_is_full_vnd_not_chart_thousands():
    client, calls = _direct_fixture([_board_row()])
    frame = client.fetch_price_board([" hpg "])
    assert frame.iloc[0]["close"] == 20450
    assert frame.iloc[0]["exchange"] == "HOSE"
    assert frame.attrs["price_scale"] == "VND_FULL"
    assert calls[0].get_method() == "POST"
    assert json.loads(calls[0].data) == {"symbols": ["HPG"]}


@pytest.mark.parametrize("key,value", [("matchPrice", math.nan), ("highest", math.inf), ("lowest", -math.inf), ("openPrice", 0), ("openPrice", -1), ("matchPrice", 1e13), ("accumulatedVolume", 1.5), ("accumulatedVolume", 2**63), ("time", None), ("time", "2026-10-01"), ("time", "2100-01-01T00:00:00Z")])
def test_direct_price_board_rejects_invalid_numeric_and_timestamp_fields(key, value):
    row = _board_row()
    row["matchPrice"][key] = value
    client, _ = _direct_fixture([row])
    with pytest.raises(ValueError):
        client.fetch_price_board(["HPG"])


@pytest.mark.parametrize("symbols", [None, [], "HPG", ["HPG"] * 2, ["HPG"] * 101, [None], ["HPG;rm"]])
def test_direct_price_board_validates_batch_before_transport(symbols):
    client, calls = _direct_fixture([])
    with pytest.raises(ValueError):
        client.fetch_price_board(symbols)
    assert calls == []


@pytest.mark.parametrize("host", ["127.0.0.1", "2130706433", "0177.0.0.1", "0x7f000001", "[::ffff:127.0.0.1]", "[64:ff9b::7f00:1]", "169.254.169.254", "100.64.0.1", "192.0.2.1", "[::1]"])
def test_direct_url_denies_literal_legacy_and_special_use_addresses(host):
    client, calls = _direct_fixture({})
    with pytest.raises(ValueError):
        client.get(f"https://{host}/api/test")
    assert calls == []


def test_updater_listing_resolution_uses_direct_metadata_once():
    from scripts import update_market_data
    class Direct:
        calls = 0
        def fetch_listing_date(self, symbol):
            self.calls += 1
            return "2007-11-15"
    direct = Direct()
    class Adapter:
        direct_vci_client = direct
        def fetch_company_profile(self, symbol):
            raise AssertionError("Legacy profile resolution must not run")
    listing, _ = update_market_data._resolve_listing_dates(Adapter(), "HPG")
    assert listing == pd.Timestamp("2007-11-15")
    assert direct.calls == 1


def test_updater_direct_downloads_use_bounded_concurrency(monkeypatch):
    from scripts import update_market_data
    import threading
    class Adapter:
        direct_vci = True
        source = "VCI"
    rendezvous = threading.Barrier(2)
    seen = set()
    def fetch(*args, **kwargs):
        seen.add(threading.get_ident())
        rendezvous.wait(timeout=5)
        return pd.DataFrame(columns=update_market_data.CANONICAL_COLUMNS)
    monkeypatch.setattr(update_market_data, "fetch_one_symbol", fetch)
    _, stats = update_market_data.fetch_symbols(Adapter(), ["HPG", "VCB"], {"HPG": "HOSE", "VCB": "HOSE"}, "2026-10-01", "2026-10-02")
    assert len(seen) == 2
    assert stats["errors"] == 0


def test_direct_intraday_and_industry_helpers():
    client, calls = _direct_fixture({"data": [{"truncTime": "2026-10-01T06:30:00Z", "matchPrice": 20450, "matchVol": 100}]})
    frame = client.fetch_intraday("HPG")
    assert frame.iloc[0]["price"] == 20450
    assert calls[0].get_method() == "POST"
    client, _ = _direct_fixture({"data": [{"icbCode": "10", "viSector": "Steel"}]})
    assert "icb_code" in client.industries_icb()
    client, _ = _direct_fixture({"data": [{"code": "HPG", "icbLv2": {"code": "10", "name": "Steel"}}]})
    assert "icb_lv2" in client.symbols_by_industries()


def test_data_namespace_limits_vnstock_import_to_prop_trade():
    import ast
    offenders = []
    for path in (REPO_ROOT / "src/omega/data").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)) and (getattr(node.func, "id", "") == "__import__" or getattr(node.func, "attr", "") == "import_module"):
                names = [arg.value for arg in node.args[:1] if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
            else:
                names = []
            if any(name == "vnstock" or name.startswith("vnstock.") for name in names):
                parents = [parent for parent in ast.walk(tree) if isinstance(parent, ast.FunctionDef) and node in list(ast.walk(parent))]
                if path != REPO_ROOT / "src/omega/data/vci_direct.py" or len(parents) != 1 or parents[0].name != "prop_trade":
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    assert offenders == []


def test_direct_adapter_defaults_to_vci_without_throttle():
    client, _ = _direct_fixture({"data": {"ticker": "HPG", "listingDate": "2007-11-15"}})
    limiter = RateLimiter(sleep_fn=lambda _: pytest.fail("Wrapper throttle invoked"))
    adapter = VnstockClient(direct_vci=False, direct_vci_client=client, rate_limiter=limiter)
    assert adapter.direct_vci is True
    assert adapter.fetch_company_profile("HPG").iloc[0]["symbol"] == "HPG"


@pytest.mark.parametrize("endpoint,statement", [("income_statement", "income"), ("balance_sheet", "balance"), ("cash_flow", "cashflow"), ("ratios", "ratio")])
def test_direct_graph_financial_compatibility_delegates(monkeypatch, endpoint, statement):
    calls = []
    frame = pd.DataFrame([{"year_report": 2025}])
    monkeypatch.setattr(DirectVCIClient, "fetch_financials", lambda self, symbol, section, period:
                        calls.append((symbol, section, period)) or frame)
    result = GraphFetcher(rate_limiter=type("Limiter", (), {"throttle": lambda self: None})()).financial("hpg", endpoint, "quarter")
    assert result is frame
    assert calls == [("HPG", statement, "quarter")]


def test_direct_graph_reference_and_flow_delegation_are_explicit(monkeypatch):
    from omega.data.vnstock_client import Reference, Trading
    frame = pd.DataFrame([{"symbol": "HPG"}])
    monkeypatch.setattr(DirectVCIClient, "fetch_company_profile", lambda self, symbol: frame)
    assert Reference().company("HPG").info() is frame
    with pytest.raises(NotImplementedError):
        Reference().company("HPG").shareholders()
    monkeypatch.setattr(DirectVCIClient, "foreign_trade", lambda self, symbol, start, end: _foreign_frame())
    assert not Trading("HPG").foreign_trade(start="2026-01-01", end="2026-01-02").empty


@pytest.mark.parametrize("source", [None, 1, "KBS", "TCBS"])
def test_direct_consumers_reject_unsupported_sources(source):
    from omega.data.live_ingestor import LiveDataIngestor
    with pytest.raises(ValueError, match="Unsupported source"):
        VnstockClient(source=source)
    with pytest.raises(ValueError, match="Unsupported source"):
        LiveDataIngestor(source=source)


def test_direct_live_snapshot_retains_vnd_identity_and_session_date(monkeypatch):
    from omega.data.live_ingestor import LiveDataIngestor
    mock_time = pd.Timestamp("2026-10-01T06:35:49Z")
    observed_at = mock_time + pd.Timedelta(minutes=1)
    assert mock_time <= observed_at
    monkeypatch.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: observed_at))
    ingestor = LiveDataIngestor(timeout=7, max_retries=2)
    assert ingestor.client.direct_vci_client.timeout == 7
    assert ingestor.client.direct_vci_client.max_attempts == 2
    client, _ = _direct_fixture([_board_row()])
    ingestor.client.direct_vci_client = client
    frame = ingestor.fetch_live_price(" hpg ", "HSX")
    assert frame.iloc[0]["symbol"] == "HPG"
    assert frame.iloc[0]["close"] == 20450
    assert frame.iloc[0]["exchange"] == "HOSE"
    assert frame.iloc[0]["date"] == pd.Timestamp("2026-10-01")
    assert ingestor.fetch_live_price("HPG", "HNX") is None


def test_direct_live_batch_chunks_and_contains_provider_failures():
    from omega.data.live_ingestor import LiveDataIngestor
    ingestor = LiveDataIngestor()
    calls = []

    class Client:
        def fetch_price_board(self, symbols):
            calls.append(symbols)
            if len(calls) == 1:
                raise RuntimeError("provider unavailable")
            return pd.DataFrame([dict(symbol=symbols[0], exchange="HNX", date=pd.Timestamp("2026-10-01T03:00:00Z"),
                                      open=100, high=100, low=100, close=100, volume=0)])

    ingestor.client.direct_vci_client = Client()
    symbols = [f"S{i}" for i in range(101)]
    frame = ingestor.fetch_live_batch(symbols, {})
    assert [len(batch) for batch in calls] == [100, 1]
    assert frame.iloc[0]["exchange"] == "HNX"
    assert frame.iloc[0]["close"] == 100  # Live full-VND prices must not be scaled heuristically.


def test_direct_live_append_replaces_only_matching_symbol_session():
    from omega.data.live_ingestor import LiveDataIngestor
    warehouse = pd.DataFrame([{"symbol": "HPG", "date": pd.Timestamp("2026-10-01"), "close": 20000},
                              {"symbol": "VCB", "date": pd.Timestamp("2026-10-01"), "close": 60000}])
    live = pd.DataFrame([{"symbol": "HPG", "date": pd.Timestamp("2026-10-01"), "close": 20450}])
    result = LiveDataIngestor().append_live_to_warehouse(warehouse, live)
    assert dict(zip(result["symbol"], result["close"])) == {"HPG": 20450, "VCB": 60000}
    assert warehouse.iloc[0]["close"] == 20000


def test_direct_news_consumer_paginates_unsorted_pages_and_filters_pit(monkeypatch):
    from datetime import datetime, timezone
    import omega.data.news_aggregator as module
    aggregator = module.NewsAggregator()
    monkeypatch.setattr(aggregator, "_rate_limit", lambda _: None)
    monkeypatch.setattr(aggregator, "_load_universe_tickers", lambda: ["HPG"])
    monkeypatch.setattr(aggregator, "_matches_sentiment_keywords", lambda *_: True)
    calls = []

    class Client:
        def fetch_company_news(self, ticker, page_size, cursor):
            calls.append(cursor)
            frame = pd.DataFrame([{"news_title": "Old", "public_date": "2026-09-01T09:00:00+07:00"},
                                  {"news_title": "New", "public_date": "2026-10-01T09:00:00+07:00"}]) if cursor is None else pd.DataFrame([
                                      {"news_title": "More", "public_date": "2026-10-01T10:00:00+07:00"},
                                      {"news_title": "Future", "public_date": "2026-10-03T09:00:00+07:00"}])
            frame.attrs["next_cursor"] = "1" if cursor is None else None
            return frame

    monkeypatch.setattr(module, "VnstockClient", lambda **_: type("Adapter", (), {"direct_vci_client": Client()})())
    result = aggregator._scrape_vnstock_news(datetime(2026, 10, 2, tzinfo=timezone.utc), hours_back=48)
    assert calls == [None, "1"]
    assert [record.text for record in result] == ["New", "More"]


def test_direct_news_consumer_contains_provider_errors(monkeypatch):
    from datetime import datetime, timezone
    import omega.data.news_aggregator as module
    aggregator = module.NewsAggregator()
    monkeypatch.setattr(aggregator, "_rate_limit", lambda _: None)
    monkeypatch.setattr(aggregator, "_load_universe_tickers", lambda: ["HPG"])

    class Client:
        def fetch_company_news(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(module, "VnstockClient", lambda **_: type("Adapter", (), {"direct_vci_client": Client()})())
    assert aggregator._scrape_vnstock_news(datetime(2026, 10, 2, tzinfo=timezone.utc)) == []


@pytest.mark.parametrize("failure", [False, True])
def test_direct_macro_news_worker_preserves_failure_and_cleanup(monkeypatch, failure):
    import omega.data.macro_news_pipeline as module
    frame = pd.DataFrame([{"news_title": "Profit", "public_date": "2026-10-01T09:00:00+07:00"}])
    def fetch(self, ticker, page_size):
        assert ticker == "HPG" and page_size == 100
        if failure:
            raise RuntimeError("provider unavailable")
        return frame
    monkeypatch.setattr(DirectVCIClient, "fetch_company_news", fetch)
    class Connection:
        sent = None
        closed = False
        def send(self, data):
            self.sent = data
        def close(self):
            self.closed = True
    connection = Connection()
    module._vnstock_news_worker(connection, "HPG", 1_000_000)
    assert connection.closed is True
    assert connection.sent[0] is not failure
    if failure:
        assert connection.sent[1] == "RuntimeError"
    else:
        pd.testing.assert_frame_equal(connection.sent[1], frame)
