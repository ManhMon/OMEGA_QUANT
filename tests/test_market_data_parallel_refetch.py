"""Focused tests for direct VCI full-history refetch behavior."""

import threading
import time
from unittest.mock import patch

import pandas as pd

from scripts import update_market_data as umd


def _history(symbol: str) -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": [symbol], "date": [pd.Timestamp("2015-01-02")],
        "open": [100.0], "high": [110.0], "low": [90.0],
        "close": [105.0], "volume": [100],
    })


def test_direct_vci_full_refetch_is_parallel_and_has_no_pacing_sleep():
    active = peak = 0
    lock = threading.Lock()
    barrier = threading.Barrier(4)

    class Client:
        source = "VCI"
        direct_vci = True

    def fetch(*_args, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait()
        with lock:
            active -= 1
        return _history(kwargs.get("symbol", _args[1]))

    symbols = [{"symbol": f"S{i}", "exchange": "HOSE"} for i in range(4)]
    with patch.object(umd, "fetch_one_symbol", side_effect=fetch), patch.object(
        umd.time, "sleep", side_effect=AssertionError("direct VCI must not sleep")
    ):
        frame, stats = umd.run_full_history_refetch(Client(), symbols, {}, "2026-01-01")

    assert stats["success"] == 4
    assert len(frame) == 4
    assert peak > 1


def test_pre_listing_full_refetch_fails_fast_without_provider_retry():
    calls = []

    class Client:
        source = "VCI"
        direct_vci = True

        def fetch_company_profile(self, _symbol):
            return pd.DataFrame({"listing_date": ["2020-01-01"]})

    def fetch(*args, **kwargs):
        calls.append((args, kwargs))
        return pd.DataFrame()

    with patch.object(umd, "fetch_one_symbol", side_effect=fetch):
        frame, stats = umd.run_full_history_refetch(
            Client(), [{"symbol": "NEW", "exchange": "HOSE"}], {}, "2019-12-31"
        )

    assert frame.empty
    assert calls == []
    assert stats["failed"] == 1
    assert stats["details"] == [{
        "symbol": "NEW", "status": "pre_listing", "reason": "end_date before listing_date",
    }]


def test_direct_vci_full_refetch_applies_backoff_after_retry():
    class Client:
        source = "VCI"
        direct_vci = True

    attempts = iter([RuntimeError("429"), _history("RETRY")])

    def fetch(*_args, **_kwargs):
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    with patch.object(umd, "fetch_one_symbol", side_effect=fetch):
        with patch.object(umd.time, "sleep") as sleep:
            frame, stats = umd.run_full_history_refetch(
                Client(), [{"symbol": "RETRY", "exchange": "HOSE"}], {}, "2026-01-01"
            )

    assert stats["success"] == 1
    assert not frame.empty
    sleep.assert_called_once_with(2)


def test_direct_vci_full_refetch_orders_tickers_deterministically():
    class Client:
        source = "VCI"
        direct_vci = True

    entries = [
        {"symbol": "ZZZ", "exchange": "HOSE"},
        {"symbol": "AAA", "exchange": "HOSE"},
    ]
    with patch.object(umd, "fetch_one_symbol", side_effect=lambda *_args, **kwargs: _history(kwargs.get("symbol", _args[1]))):
        _frame, stats = umd.run_full_history_refetch(Client(), entries, {}, "2026-01-01")

    assert [detail["symbol"] for detail in stats["details"]] == ["AAA", "ZZZ"]
