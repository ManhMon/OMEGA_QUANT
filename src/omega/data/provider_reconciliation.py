"""Warning-only VCI/KBS daily OHLCV reconciliation."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

PRICE_FIELDS = ("open", "high", "low", "close")
FIELDS = PRICE_FIELDS + ("volume",)
REQUIRED_COLUMNS = {"ticker", "date", "exchange", *FIELDS}


def _finding(ticker: str, exchange: str, date: str, field: str, reason: str, **values: Any) -> dict[str, Any]:
    return {"ticker": ticker, "exchange": exchange, "trading_date": date, "field": field,
            "vci_value": None, "kbs_value": None, "absolute_diff": None,
            "relative_diff": None, "tolerance": None, "severity": "warning",
            "consecutive_mismatch_sessions": 0, "reason": reason, **values}


def _state_key(ticker: str, field: str) -> str:
    return f"{ticker}:{field}"


def _valid_reference(frame: pd.DataFrame, as_of: pd.Timestamp) -> tuple[pd.DataFrame, str | None]:
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        return frame, f"schema_invalid: missing {sorted(missing)}"
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame[frame["date"] <= as_of].copy()
    if frame.duplicated(["ticker", "date"]).any():
        return frame, "duplicate_ticker_date"
    if frame.empty:
        return frame, "empty"
    return frame, None


def _failure_findings(session: pd.DataFrame, state: dict[str, dict[str, Any]], as_of: pd.Timestamp, reason: str) -> list[dict[str, Any]]:
    exchanges = session.drop_duplicates("ticker").set_index("ticker")["exchange"].to_dict()
    findings = [_finding(row.ticker, row.exchange, str(as_of.date()), "availability", reason)
                for row in session.sort_values(["ticker", "exchange"]).itertuples()]
    for key, previous in state.items():
        ticker, field = key.rsplit(":", 1)
        streak = int(previous.get("streak", 0))
        if streak >= 3:
            findings.append(_finding(ticker, exchanges.get(ticker, ""), str(as_of.date()), field,
                                     "retained_critical", severity="critical",
                                     consecutive_mismatch_sessions=streak))
    return findings


def _retained_critical(
    findings: list[dict[str, Any]], state: dict[str, dict[str, Any]], ticker: str, exchange: str, as_of: pd.Timestamp, field: str | None = None,
) -> None:
    for key, previous in state.items():
        state_ticker, state_field = key.rsplit(":", 1)
        if state_ticker == ticker and (field is None or state_field == field) and int(previous.get("streak", 0)) >= 3:
            findings.append(_finding(ticker, exchange, str(as_of.date()), state_field, "retained_critical", severity="critical",
                                     consecutive_mismatch_sessions=int(previous["streak"])))


def reconcile_ohlcv(
    vci: pd.DataFrame,
    kbs: pd.DataFrame | None,
    prior_state: dict[str, dict[str, Any]] | None,
    as_of_date: str | pd.Timestamp,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Compare only exact, non-future daily VND_FULL rows. No I/O."""
    as_of = pd.Timestamp(as_of_date).normalize()
    state = {key: dict(value) for key, value in (prior_state or {}).items()}
    primary = vci.copy()
    primary["date"] = pd.to_datetime(primary["date"]).dt.normalize()
    session = primary[primary["date"] == as_of].copy()
    findings: list[dict[str, Any]] = []
    reference = pd.DataFrame() if kbs is None else kbs.copy()
    if kbs is None:
        error = "fetch_failed"
    else:
        reference, error = _valid_reference(reference, as_of)
    if error:
        return _payload(as_of, _failure_findings(session, state, as_of, error)), state

    reference = reference[reference["date"] == as_of].set_index(["ticker", "date"])
    for row in session.sort_values(["ticker", "exchange"]).itertuples():
        key = (row.ticker, row.date)
        if key not in reference.index:
            findings.append(_finding(row.ticker, row.exchange, str(as_of.date()), "availability", "missing_ticker_date"))
            _retained_critical(findings, state, row.ticker, row.exchange, as_of)
            continue
        compare = reference.loc[key]
        history = primary[(primary["ticker"] == row.ticker) & (primary["date"] < as_of)]["date"]
        previous_date = history.max() if not history.empty else None
        for field in FIELDS:
            state_key = _state_key(row.ticker, field)
            previous = state.get(state_key, {})
            try:
                vci_value = float(getattr(row, field))
                kbs_value = float(compare[field])
            except (TypeError, ValueError):
                vci_value = kbs_value = float("nan")
            if not math.isfinite(vci_value) or not math.isfinite(kbs_value):
                findings.append(_finding(row.ticker, row.exchange, str(as_of.date()), field, "invalid_observation"))
                _retained_critical(findings, state, row.ticker, row.exchange, as_of, field)
                continue
            continuous = previous_date is not None and previous.get("trading_date") == str(previous_date.date())
            if field == "volume" and vci_value <= 0:
                findings.append(_finding(row.ticker, row.exchange, str(as_of.date()), field, "vci_volume_zero"))
                continue
            absolute_diff = abs(vci_value - kbs_value)
            relative_diff = absolute_diff / abs(vci_value) if vci_value else None
            tolerance = max(1.0, 0.001 * abs(vci_value)) if field in PRICE_FIELDS else 0.01
            mismatch = absolute_diff > tolerance if field in PRICE_FIELDS else relative_diff > tolerance
            streak = (int(previous.get("streak", 0)) + 1) if mismatch and continuous else int(mismatch)
            state[state_key] = {"trading_date": str(as_of.date()), "streak": streak}
            if mismatch:
                severity = "critical" if streak >= 3 else "warning"
                findings.append(_finding(row.ticker, row.exchange, str(as_of.date()), field, "mismatch",
                    vci_value=vci_value, kbs_value=kbs_value, absolute_diff=absolute_diff,
                    relative_diff=relative_diff, tolerance=tolerance, severity=severity,
                    consecutive_mismatch_sessions=streak))
            elif int(previous.get("streak", 0)) >= 3:
                findings.append(_finding(row.ticker, row.exchange, str(as_of.date()), field, "recovered",
                    vci_value=vci_value, kbs_value=kbs_value, absolute_diff=absolute_diff,
                    relative_diff=relative_diff, tolerance=tolerance, consecutive_mismatch_sessions=0))
    return _payload(as_of, findings), state


def _payload(as_of: pd.Timestamp, findings: list[dict[str, Any]]) -> dict[str, Any]:
    findings.sort(key=lambda item: (item["exchange"], item["ticker"], item["field"], item["reason"]))
    aggregate: dict[str, dict[str, int]] = {}
    for item in findings:
        bucket = aggregate.setdefault(item["exchange"], {"warning": 0, "critical": 0})
        bucket[item["severity"]] += 1
    status = "critical" if any(item["severity"] == "critical" for item in findings) else "warning" if findings else "ok"
    return {"schema_version": 1, "as_of_date": str(as_of.date()), "provider_primary": "vnstock_vci",
            "provider_reference": "vnstock_kbs", "status": status,
            "aggregate_by_exchange": aggregate, "findings": findings}
