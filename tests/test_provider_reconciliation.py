import pandas as pd

from omega.data.provider_reconciliation import reconcile_ohlcv


def _frame(date="2026-08-02", close=1000.0, volume=100, ticker="VCB"):
    return pd.DataFrame({"ticker": [ticker], "date": [date], "exchange": ["HOSE"],
                         "open": [close], "high": [close], "low": [close], "close": [close],
                         "volume": [volume]})


def test_price_and_volume_exact_boundaries_match():
    vci = _frame()
    kbs = _frame(close=1001.0, volume=101)
    payload, state = reconcile_ohlcv(vci, kbs, {}, "2026-08-02")
    assert payload["status"] == "ok"
    assert state["VCB:close"]["streak"] == 0
    assert state["VCB:volume"]["streak"] == 0


def test_three_sessions_escalate_then_exact_match_recovers():
    state = {}
    canonical = pd.DataFrame()
    for date in ("2026-07-30", "2026-07-31", "2026-08-02"):
        canonical = pd.concat([canonical, _frame(date)], ignore_index=True)
        payload, state = reconcile_ohlcv(canonical, _frame(date, close=1002), state, date)
    assert next(item for item in payload["findings"] if item["field"] == "close")["severity"] == "critical"
    canonical = pd.concat([canonical, _frame("2026-08-03")], ignore_index=True)
    payload, state = reconcile_ohlcv(canonical, _frame("2026-08-03"), state, "2026-08-03")
    assert next(item for item in payload["findings"] if item["field"] == "close")["reason"] == "recovered"
    assert state["VCB:close"]["streak"] == 0


def test_failure_projects_persisted_critical_state():
    state = {"VCB:close": {"trading_date": "2026-08-01", "streak": 3}}
    vci = pd.concat([_frame("2026-08-01"), _frame("2026-08-02")], ignore_index=True)
    payload, after_failure = reconcile_ohlcv(vci, None, state, "2026-08-02")
    retained = next(item for item in payload["findings"] if item["reason"] == "retained_critical")
    assert payload["status"] == "critical"
    assert retained["field"] == "close"
    assert retained["consecutive_mismatch_sessions"] == 3
    assert after_failure == state


def test_missing_ticker_date_retains_matching_critical_state():
    state = {"VCB:close": {"trading_date": "2026-08-01", "streak": 3}}
    vci = pd.concat([_frame("2026-08-01"), _frame("2026-08-02")], ignore_index=True)
    payload, next_state = reconcile_ohlcv(vci, _frame("2026-08-02", ticker="VNM"), state, "2026-08-02")
    retained = next(item for item in payload["findings"] if item["reason"] == "retained_critical")
    assert payload["status"] == "critical"
    assert retained["ticker"] == "VCB"
    assert retained["field"] == "close"
    assert next_state == state


def test_invalid_current_observation_retains_critical_state():
    state = {"VCB:close": {"trading_date": "2026-08-01", "streak": 3}}
    vci = pd.concat([_frame("2026-08-01"), _frame("2026-08-02")], ignore_index=True)
    payload, next_state = reconcile_ohlcv(vci, _frame("2026-08-02", close="not-a-number"), state, "2026-08-02")
    retained = next(item for item in payload["findings"] if item["reason"] == "retained_critical")
    assert payload["status"] == "critical"
    assert retained["field"] == "close"
    assert next_state["VCB:close"] == state["VCB:close"]


def test_future_kbs_duplicates_do_not_affect_current_reconciliation():
    vci = pd.concat([_frame("2026-08-01"), _frame("2026-08-02")], ignore_index=True)
    historical = _frame("2026-08-02", close=1002)
    future_conflicts = pd.concat([historical, _frame("2026-08-03", close=900), _frame("2026-08-03", close=800)], ignore_index=True)
    expected_payload, expected_state = reconcile_ohlcv(vci, historical, {}, "2026-08-02")
    payload, state = reconcile_ohlcv(vci, future_conflicts, {}, "2026-08-02")
    assert payload == expected_payload
    assert state == expected_state


def test_malformed_future_kbs_row_does_not_affect_current_reconciliation():
    vci = pd.concat([_frame("2026-08-01"), _frame("2026-08-02")], ignore_index=True)
    historical = _frame("2026-08-02", close=1002)
    malformed_future = _frame("2026-08-03", close="not-a-number")
    reference = pd.concat([historical, malformed_future], ignore_index=True)
    expected_payload, expected_state = reconcile_ohlcv(vci, historical, {}, "2026-08-02")
    payload, state = reconcile_ohlcv(vci, reference, {}, "2026-08-02")
    assert payload == expected_payload
    assert state == expected_state


def test_future_kbs_is_ignored_when_current_reference_is_missing():
    state = {"VCB:close": {"trading_date": "2026-08-01", "streak": 3}}
    vci = pd.concat([_frame("2026-08-01"), _frame("2026-08-02")], ignore_index=True)
    future = _frame("2026-08-03", close=900)
    payload, next_state = reconcile_ohlcv(vci, future, state, "2026-08-02")
    assert any(item["reason"] == "empty" for item in payload["findings"])
    assert payload["status"] == "critical"
    assert next_state == state


def test_duplicate_reference_and_vci_gap_reset_streak():
    duplicate = pd.concat([_frame(), _frame()])
    payload, state = reconcile_ohlcv(_frame(), duplicate, {}, "2026-08-02")
    assert payload["findings"][0]["reason"] == "duplicate_ticker_date"
    gap_vci = _frame("2026-08-04")
    prior = {"VCB:close": {"trading_date": "2026-08-01", "streak": 2}}
    _, state = reconcile_ohlcv(gap_vci, _frame("2026-08-04", close=1002), prior, "2026-08-04")
    assert state["VCB:close"]["streak"] == 1
