"""Point-in-time post-earnings announcement drift features."""
from __future__ import annotations

import math
import re
from collections import deque
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from numbers import Real
from typing import Any, Iterable, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

from omega.data.calendar import VNTradingCalendar
from omega.data.earnings_ledger import EarningsAnnouncement, EarningsLedger

_ICT = ZoneInfo("Asia/Ho_Chi_Minh")
_MAX_EVENTS, _MAX_ROWS, _MAX_SESSIONS = 10_000, 1_000_000, 10_000
_HISTORY, _MIN_HISTORY = 20, 8


@dataclass(frozen=True)
class SurpriseResult:
    value: Optional[float]
    raw: Optional[float]
    sigma: Optional[float]
    reason: Optional[str]
    history_ids: Tuple[str, ...] = ()


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a finite number")
    if isinstance(value, int) and abs(value) > 10**12:
        raise ValueError(f"{name} magnitude exceeds 1e12")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if abs(number) > 1e12:
        raise ValueError(f"{name} magnitude exceeds 1e12")
    return number


def _finite_error(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a finite number")
    if isinstance(value, int) and abs(value) > 2 * 10**12:
        raise ValueError(f"{name} magnitude exceeds 2e12")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(number) or abs(number) > 2e12:
        raise ValueError(f"{name} must be finite and within ±2e12")
    return number


def _standardize(numerator: float, errors: Iterable[float], min_history: int = _MIN_HISTORY) -> SurpriseResult:
    if not math.isfinite(numerator):
        return SurpriseResult(None, None, None, "non_finite")
    values = list(errors)[-_HISTORY:]
    if any(not math.isfinite(error) for error in values):
        return SurpriseResult(None, None, None, "non_finite")
    if len(values) < min_history:
        return SurpriseResult(None, None, None, "insufficient_history")
    try:
        mean = math.fsum(values) / len(values)
        sigma = math.sqrt(math.fsum((error - mean) ** 2 for error in values) / (len(values) - 1))
    except (OverflowError, ValueError):
        return SurpriseResult(None, None, None, "non_finite")
    if not math.isfinite(sigma):
        return SurpriseResult(None, None, None, "non_finite")
    scale = max(map(abs, values), default=0.0)
    if sigma <= max(1e-12, scale * 1e-12):
        return SurpriseResult(None, None, sigma, "near_zero_sigma")
    ratio = numerator / sigma
    if not math.isfinite(ratio):
        return SurpriseResult(None, None, sigma, "non_finite")
    return SurpriseResult(max(-5.0, min(5.0, ratio)), ratio, sigma, None)


def standardized_surprise(
    actual: float, expected: float, prior_errors: Iterable[float], min_history: int = _MIN_HISTORY,
) -> SurpriseResult:
    """Standardize by the sample deviation of at most 20 prior forecast errors."""
    actual, expected = _finite_number(actual, "actual"), _finite_number(expected, "expected")
    if isinstance(min_history, bool) or not isinstance(min_history, int) or not _MIN_HISTORY <= min_history <= _HISTORY:
        raise ValueError("min_history must be an integer in [8, 20]")
    if isinstance(prior_errors, (str, bytes)):
        raise TypeError("prior_errors must be an iterable of finite numbers")
    errors: deque[float] = deque(maxlen=_HISTORY)
    count = 0
    for value in prior_errors:
        count += 1
        if count > _MAX_EVENTS:
            raise ValueError("prior_errors exceeds 10000 values")
        errors.append(_finite_error(value, "prior error"))
    return _standardize(actual - expected, errors, min_history)


def drift_decay(
    surprise: float, age_sessions: int, half_life_sessions: float = 20, max_age_sessions: int = 60,
) -> float:
    """Return clipped surprise with exponential half-life decay."""
    surprise = _finite_number(surprise, "surprise")
    if isinstance(age_sessions, bool) or not isinstance(age_sessions, int) or age_sessions < 0:
        raise ValueError("age_sessions must be a nonnegative integer")
    half_life_sessions = _finite_number(half_life_sessions, "half_life_sessions")
    if not 0 < half_life_sessions <= 10_000:
        raise ValueError("half_life_sessions must be in (0, 10000]")
    if isinstance(max_age_sessions, bool) or not isinstance(max_age_sessions, int) or not 1 <= max_age_sessions <= 10_000:
        raise ValueError("max_age_sessions must be an integer in [1, 10000]")
    if age_sessions >= max_age_sessions:
        return 0.0
    return max(-5.0, min(5.0, surprise)) * math.exp2(-age_sessions / half_life_sessions)


def _aware_ict(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(_ICT)


def _date_label(value: Any) -> date:
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            raise ValueError("panel date cannot be NaT")
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is None and value.time() != time.min:
            raise ValueError("naive panel timestamps must be daily date labels")
        return value.astimezone(_ICT).date() if value.tzinfo is not None else value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("panel date cannot be empty")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                return date.fromisoformat(text)
            except ValueError as exc:
                raise ValueError("invalid panel date label") from exc
        if parsed.tzinfo is None and parsed.time() != time.min:
            raise ValueError("naive panel timestamps must be daily date labels")
        return parsed.astimezone(_ICT).date() if parsed.tzinfo is not None else parsed.date()
    raise TypeError("panel date labels must be strings, dates, or timestamps")


def _basis_supported(basis: Any) -> bool:
    return (
        basis.metric in {"EPS", "NET_INCOME", "REVENUE"}
        and basis.unit == "VND_FULL" and basis.currency == "VND"
        and basis.scope in {"consolidated", "parent"}
        and basis.period_basis in {"standalone", "cumulative"}
        and isinstance(basis.share_basis, str)
        and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", basis.share_basis) is not None
        and type(basis.audited) is bool
    )


def _period(event: EarningsAnnouncement) -> int:
    return event.fiscal_year * 4 + event.fiscal_quarter


def _event_key(event: EarningsAnnouncement) -> tuple:
    return event.ready_at, event.announced_at, _period(event), event.revision, event.event_id


def _known_event(event: EarningsAnnouncement, cutoff: datetime) -> bool:
    return event.announced_at is not None and event.ready_at <= cutoff


def _latest_period(
    events: Sequence[EarningsAnnouncement], issuer: str, year: int, quarter: int, cutoff: datetime,
    basis: Any = None,
) -> Optional[EarningsAnnouncement]:
    matching = [event for event in events if event.issuer == issuer and event.fiscal_year == year
                and event.fiscal_quarter == quarter and _known_event(event, cutoff)
                and (basis is None or event.basis == basis)]
    return max(matching, key=_event_key) if matching else None


def _period_index(
    events: Sequence[EarningsAnnouncement], issuer: str,
) -> dict[tuple[int, int, Any], list[EarningsAnnouncement]]:
    index: dict[tuple[int, int, Any], list[EarningsAnnouncement]] = {}
    for event in events:
        if event.issuer == issuer and event.announced_at is not None:
            index.setdefault((event.fiscal_year, event.fiscal_quarter, event.basis), []).append(event)
    for revisions in index.values():
        revisions.sort(key=_event_key)
    return index


def _latest_from_index(
    index: dict[tuple[int, int, Any], list[EarningsAnnouncement]],
    year: int, quarter: int, basis: Any, cutoff: datetime,
) -> Optional[EarningsAnnouncement]:
    revisions = index.get((year, quarter, basis), ())
    position = bisect_right(revisions, cutoff, key=lambda event: event.ready_at) - 1
    return revisions[position] if position >= 0 else None


def _normalized_actual(
    event: EarningsAnnouncement, events: Sequence[EarningsAnnouncement], cutoff: datetime,
    index: Optional[dict[tuple[int, int, Any], list[EarningsAnnouncement]]] = None,
) -> tuple[Optional[float], Optional[str], Tuple[str, ...]]:
    basis = event.basis
    if not 1900 <= event.fiscal_year <= 2100:
        return None, "unsupported_fiscal_year", ()
    if not _basis_supported(basis):
        return None, "unsupported_basis", ()
    try:
        actual = _finite_number(event.actual, "actual")
    except (TypeError, ValueError):
        return None, "invalid_actual", ()
    if basis.metric == "EPS" and basis.period_basis == "cumulative" and event.fiscal_quarter > 1:
        return None, "unsupported_basis", ()
    if basis.period_basis == "standalone" or event.fiscal_quarter == 1:
        return actual, None, ()
    # ponytail: v1 handles calendar fiscal years; add alternate calendars only with explicit event fields.
    if basis.metric == "EPS":
        return None, "unsupported_basis", ()
    previous = (_latest_from_index(index, event.fiscal_year, event.fiscal_quarter - 1, basis, cutoff)
                if index is not None else _latest_period(events, event.issuer, event.fiscal_year,
                                                        event.fiscal_quarter - 1, cutoff, basis))
    if previous is None:
        return None, "missing_predecessor", ()
    if not previous.verified:
        return None, "unverified_predecessor", (previous.event_id,)
    if previous.basis != basis:
        return None, "incompatible_predecessor", (previous.event_id,)
    try:
        previous_actual = _finite_number(previous.actual, "predecessor actual")
    except (TypeError, ValueError):
        return None, "invalid_predecessor", (previous.event_id,)
    result = actual - previous_actual
    return (result, None, (previous.event_id,)) if math.isfinite(result) else (None, "non_finite", (previous.event_id,))


def _consensus_value(event: EarningsAnnouncement, cutoff: datetime) -> tuple[Optional[float], Optional[str]]:
    consensus = event.consensus
    if consensus is None:
        return None, "missing_consensus"
    announced = _aware_ict(event.announced_at)
    vintage = _aware_ict(consensus.vintage_at)
    available = _aware_ict(consensus.available_at)
    if not consensus.verified:
        return None, "unverified_consensus"
    if (announced is None or vintage is None or available is None
            or not vintage <= available < announced or available > cutoff):
        return None, "invalid_consensus_timing"
    if (consensus.issuer != event.issuer or consensus.fiscal_year != event.fiscal_year
            or consensus.fiscal_quarter != event.fiscal_quarter or consensus.basis != event.basis):
        return None, "incompatible_consensus"
    try:
        return _finite_number(consensus.value, "consensus value"), None
    except (TypeError, ValueError):
        return None, "invalid_consensus"


class PEADDriftEngine:
    """Build issuer-aligned point-in-time PEAD features from an earnings ledger."""

    def __init__(self, ledger: EarningsLedger, half_life_sessions: float = 20, max_age_sessions: int = 60):
        if not isinstance(ledger, EarningsLedger):
            raise TypeError("ledger must be an EarningsLedger")
        drift_decay(0.0, 0, half_life_sessions, max_age_sessions)
        self.ledger = ledger
        self.half_life_sessions = half_life_sessions
        self.max_age_sessions = max_age_sessions
        self._calendar_cache: dict[date, Optional[bool]] = {}
        self._entry_cache: dict[date, Optional[date]] = {}
        self._age_cache: dict[tuple[date, date], Optional[int]] = {}
        self._session_dates: list[date] = []
        self._session_start: Optional[date] = None
        self._session_end: Optional[date] = None

    def _calendar_day(self, day: date) -> Optional[bool]:
        if day.year not in VNTradingCalendar.SUPPORTED_YEARS:
            return None
        try:
            return VNTradingCalendar.is_trading_day(datetime.combine(day, time(9), _ICT))
        except ValueError:
            return None

    def _entry_date(self, ready_at: datetime) -> Optional[date]:
        ready_date = ready_at.astimezone(_ICT).date()
        if ready_date in self._entry_cache:
            return self._entry_cache[ready_date]
        current = ready_date
        for _ in range(370):
            try:
                current += timedelta(days=1)
            except OverflowError:
                self._entry_cache[ready_date] = None
                return None
            trading = self._calendar_day(current)
            if trading is None:
                self._entry_cache[ready_date] = None
                return None
            if trading:
                self._entry_cache[ready_date] = current
                return current
        self._entry_cache[ready_date] = None
        return None

    def _age(self, entry: date, session: date) -> Optional[int]:
        key = entry, session
        if key in self._age_cache:
            return self._age_cache[key]
        if session < entry:
            self._age_cache[key] = None
            return None
        start = min(entry, self._session_start) if self._session_start else entry
        end = max(session, self._session_end) if self._session_end else session
        if (end - start).days > 36_600:
            self._age_cache[key] = None
            return None
        if self._session_start is not None and start < self._session_start:
            day, dates = start, []
            while day < self._session_start:
                trading = self._calendar_day(day)
                if trading is None:
                    self._age_cache[key] = None
                    return None
                if trading:
                    dates.append(day)
                day += timedelta(days=1)
            self._session_dates = sorted(dates + self._session_dates)
            self._session_start = start
        if self._session_end is None or end > self._session_end:
            day = (self._session_end + timedelta(days=1)) if self._session_end else start
            while day <= end:
                trading = self._calendar_day(day)
                if trading is None:
                    self._age_cache[key] = None
                    return None
                if trading:
                    self._session_dates.append(day)
                day += timedelta(days=1)
            self._session_end = end
        self._session_start = start
        age = bisect_left(self._session_dates, session) - bisect_left(self._session_dates, entry)
        self._age_cache[key] = age
        return age

    def _sue(self, event: EarningsAnnouncement, events: Sequence[EarningsAnnouncement]) -> SurpriseResult:
        cutoff = _aware_ict(event.ready_at)
        if cutoff is None:
            return SurpriseResult(None, None, None, "invalid_timestamp")
        index = _period_index(events, event.issuer)
        actual, reason, predecessor_ids = _normalized_actual(event, events, cutoff, index)
        if reason:
            return SurpriseResult(None, None, None, reason, predecessor_ids)
        expected, reason = _consensus_value(event, cutoff)
        if reason:
            return SurpriseResult(None, None, None, reason, predecessor_ids)
        if event.basis.period_basis == "cumulative" and event.fiscal_quarter > 1:
            predecessor = _latest_from_index(index, event.fiscal_year, event.fiscal_quarter - 1,
                                             event.basis, cutoff)
            if predecessor is None:
                return SurpriseResult(None, None, None, "missing_predecessor", predecessor_ids)
            if not predecessor.verified or predecessor.basis != event.basis:
                why = "unverified_predecessor" if not predecessor.verified else "incompatible_predecessor"
                return SurpriseResult(None, None, None, why, predecessor_ids + (predecessor.event_id,))
            expected -= _finite_number(predecessor.actual, "predecessor actual")
        latest_by_period: dict[int, EarningsAnnouncement] = {}
        for revisions in index.values():
            for candidate in revisions:
                if candidate.basis != event.basis or _period(candidate) >= _period(event):
                    continue
                if candidate.ready_at > cutoff:
                    continue
                period = _period(candidate)
                previous = latest_by_period.get(period)
                if previous is None or _event_key(candidate) > _event_key(previous):
                    latest_by_period[period] = candidate
        eligible_errors: deque[tuple[float, Tuple[str, ...]]] = deque(maxlen=_HISTORY)
        for old in (latest_by_period[period] for period in sorted(latest_by_period)):
            if not old.verified:
                continue
            old_actual, old_reason, old_predecessor_ids = _normalized_actual(old, events, cutoff, index)
            old_expected, expected_reason = _consensus_value(old, cutoff)
            if old_reason or expected_reason:
                continue
            old_dependencies = list(old_predecessor_ids)
            if old.basis.period_basis == "cumulative" and old.fiscal_quarter > 1:
                previous = _latest_from_index(index, old.fiscal_year, old.fiscal_quarter - 1,
                                              old.basis, cutoff)
                if previous is None or not previous.verified or previous.basis != old.basis:
                    continue
                old_expected -= _finite_number(previous.actual, "predecessor actual")
                old_dependencies.append(previous.event_id)
            error = old_actual - old_expected
            if math.isfinite(error):
                eligible_errors.append((error, tuple(old_dependencies) + (old.event_id,)))
        errors = [error for error, _ in eligible_errors]
        history_ids = list(predecessor_ids)
        for _, dependency_ids in eligible_errors:
            history_ids.extend(dependency_ids)
        result = _standardize(actual - expected, errors)
        return SurpriseResult(result.value, result.raw, result.sigma, result.reason,
                              tuple(dict.fromkeys(history_ids)))

    def _sec(self, event: EarningsAnnouncement, events: Sequence[EarningsAnnouncement]) -> SurpriseResult:
        cutoff = _aware_ict(event.ready_at)
        if cutoff is None:
            return SurpriseResult(None, None, None, "invalid_timestamp")
        index = _period_index(events, event.issuer)
        actual, reason, predecessor_ids = _normalized_actual(event, events, cutoff, index)
        if reason:
            return SurpriseResult(None, None, None, reason, predecessor_ids)
        year_ago = _latest_from_index(index, event.fiscal_year - 1, event.fiscal_quarter, event.basis, cutoff)
        if year_ago is None:
            return SurpriseResult(None, None, None, "missing_predecessor")
        if not year_ago.verified:
            return SurpriseResult(None, None, None, "unverified_predecessor", (year_ago.event_id,))
        if year_ago.basis != event.basis:
            return SurpriseResult(None, None, None, "incompatible_predecessor", (year_ago.event_id,))
        year_ago_actual, reason, year_ago_ids = _normalized_actual(year_ago, events, cutoff, index)
        if reason:
            return SurpriseResult(None, None, None, reason, year_ago_ids)
        numerator = actual - year_ago_actual
        if not math.isfinite(numerator):
            return SurpriseResult(None, None, None, "non_finite")
        latest_by_period: dict[int, EarningsAnnouncement] = {}
        for revisions in index.values():
            for candidate in revisions:
                if candidate.basis != event.basis or _period(candidate) >= _period(event):
                    continue
                if candidate.ready_at > cutoff:
                    continue
                period = _period(candidate)
                previous = latest_by_period.get(period)
                if previous is None or _event_key(candidate) > _event_key(previous):
                    latest_by_period[period] = candidate
        changes: dict[int, tuple[float, Tuple[str, ...]]] = {}
        for period, current in sorted(latest_by_period.items()):
            if not current.verified:
                continue
            year, quarter = current.fiscal_year, current.fiscal_quarter
            prior = _latest_from_index(index, year - 1, quarter, event.basis, cutoff)
            if prior is None or not prior.verified:
                continue
            current_actual, current_reason, current_ids = _normalized_actual(current, events, cutoff, index)
            prior_actual, prior_reason, prior_ids = _normalized_actual(prior, events, cutoff, index)
            if current_reason or prior_reason:
                continue
            change = current_actual - prior_actual
            if math.isfinite(change):
                changes[period] = (change, tuple(current_ids) + (prior.event_id,) + tuple(prior_ids) + (current.event_id,))
        selected = [changes[key] for key in sorted(changes)][-_HISTORY:]
        standardized = _standardize(numerator, [value for value, _ in selected])
        ids = list(predecessor_ids) + [year_ago.event_id] + list(year_ago_ids)
        for _, historical_ids in selected:
            ids.extend(historical_ids)
        return SurpriseResult(standardized.value, standardized.raw, standardized.sigma,
                              standardized.reason, tuple(dict.fromkeys(ids)))

    def _calculate(self, event: EarningsAnnouncement, events: Sequence[EarningsAnnouncement]) -> dict[str, SurpriseResult]:
        if event.announced_at is None:
            unavailable = SurpriseResult(None, None, None, "unknown_announcement")
            return {"sue": unavailable, "sec": unavailable}
        if not event.verified:
            unavailable = SurpriseResult(None, None, None, "unverified")
            return {"sue": unavailable, "sec": unavailable}
        return {"sue": self._sue(event, events), "sec": self._sec(event, events)}

    def event_surprises(self, event: EarningsAnnouncement) -> dict[str, SurpriseResult]:
        """Calculate surprises only for this exact, verified ledger event."""
        if not isinstance(event, EarningsAnnouncement):
            raise TypeError("event must be an EarningsAnnouncement")
        cutoff = _aware_ict(event.ready_at)
        if cutoff is None or event.announced_at is None:
            unavailable = SurpriseResult(None, None, None, "unknown_announcement")
            return {"sue": unavailable, "sec": unavailable}
        events = tuple(self.ledger.snapshot(as_of=event.ready_at))
        if len(events) > _MAX_EVENTS:
            raise ValueError("ledger exceeds 10000 events")
        if event not in events:
            raise ValueError("event is not present in ledger snapshot at ready_at")
        return self._calculate(event, events)

    def features(self, panel: pd.DataFrame, as_of: Optional[datetime] = None) -> pd.DataFrame:
        if not isinstance(panel, pd.DataFrame):
            raise TypeError("panel must be a pandas DataFrame")
        if not isinstance(panel.index, pd.MultiIndex) or panel.index.nlevels != 2:
            raise ValueError("panel index must be a two-level MultiIndex named date and symbol")
        names = list(panel.index.names)
        if set(names) != {"date", "symbol"}:
            raise ValueError("panel index levels must be named date and symbol")
        if not panel.index.is_unique:
            raise ValueError("panel index keys must be unique")
        if len(panel) > _MAX_ROWS:
            raise ValueError("panel exceeds 1000000 rows")
        cutoff_as_of = None if as_of is None else _aware_ict(as_of)
        if as_of is not None and cutoff_as_of is None:
            raise ValueError("as_of must be timezone-aware")
        date_pos, symbol_pos = names.index("date"), names.index("symbol")
        labels, symbols, normalized_keys = [], [], set()
        for key in panel.index.tolist():
            label, symbol = _date_label(key[date_pos]), key[symbol_pos]
            if not isinstance(symbol, str) or re.fullmatch(r"[A-Z0-9]{1,12}", symbol) is None:
                raise ValueError("issuer symbols must match [A-Z0-9]{1,12}")
            normalized_key = label, symbol
            if normalized_key in normalized_keys:
                raise ValueError("panel contains duplicate normalized (date, symbol) keys")
            normalized_keys.add(normalized_key)
            labels.append(label)
            symbols.append(symbol)
        if len(set(labels)) > _MAX_SESSIONS:
            raise ValueError("panel exceeds 10000 unique sessions")
        self._calendar_cache.clear()
        self._entry_cache.clear()
        self._age_cache.clear()
        self._session_dates.clear()
        self._session_start = self._session_end = None
        events = tuple(self.ledger.snapshot())
        if len(events) > _MAX_EVENTS:
            raise ValueError("ledger exceeds 10000 events")
        by_issuer: dict[str, list[EarningsAnnouncement]] = {}
        for event in events:
            if event.announced_at is not None:
                by_issuer.setdefault(event.issuer, []).append(event)
        surprise_cache: dict[str, dict[str, SurpriseResult]] = {}
        entry_cache: dict[str, Optional[date]] = {}
        eligible_by_issuer: dict[str, list[EarningsAnnouncement]] = {}
        eligible_entries: dict[str, list[date]] = {}
        known_ready: dict[str, list[datetime]] = {}
        for issuer, issuer_events in by_issuer.items():
            issuer_events.sort(key=_event_key)
            known_ready[issuer] = [event.ready_at for event in issuer_events]
            eligible: list[EarningsAnnouncement] = []
            for event in issuer_events:
                entry_cache[event.event_id] = self._entry_date(event.ready_at)
                if entry_cache[event.event_id] is not None:
                    eligible.append(event)
            eligible_by_issuer[issuer] = eligible
            eligible_entries[issuer] = [entry_cache[event.event_id] for event in eligible]
        columns: dict[str, list[Any]] = {name: [] for name in (
            "pead_sue", "pead_sec", "pead_sue_drift", "pead_sec_drift", "pead_age_sessions",
            "pead_sue_valid", "pead_sec_valid", "pead_sue_reason", "pead_sec_reason",
        )}
        for session, symbol in zip(labels, symbols):
            reason = None
            trading = self._calendar_day(session)
            if trading is None:
                reason = "calendar_unavailable"
            elif not trading:
                reason = "non_trading_day"
            open_at = datetime.combine(session, time(9), _ICT)
            if reason is None and cutoff_as_of is not None and cutoff_as_of < open_at:
                reason = "before_session_open"
            event = None
            awaiting = False
            if reason is None:
                ready_position = bisect_right(known_ready.get(symbol, ()), open_at) - 1
                eligible = eligible_by_issuer.get(symbol, ())
                position = bisect_right(eligible_entries.get(symbol, ()), session) - 1
                if position >= 0:
                    event = eligible[position]
                awaiting = event is None and ready_position >= 0
            age = None
            if reason is not None:
                unavailable = SurpriseResult(None, None, None, reason)
                sue = sec = unavailable
            elif event is None:
                unavailable = SurpriseResult(None, None, None, "awaiting_entry" if awaiting else "no_event")
                sue = sec = unavailable
            else:
                entry = entry_cache.get(event.event_id)
                age = None if entry is None else self._age(entry, session)
                if age is None:
                    unavailable = SurpriseResult(None, None, None, "calendar_unavailable")
                    sue = sec = unavailable
                else:
                    if event.event_id not in surprise_cache:
                        surprise_cache[event.event_id] = self._calculate(event, events)
                    sue, sec = surprise_cache[event.event_id]["sue"], surprise_cache[event.event_id]["sec"]
            expired = age is not None and age >= self.max_age_sessions
            columns["pead_sue"].append(float("nan") if sue.value is None else sue.value)
            columns["pead_sec"].append(float("nan") if sec.value is None else sec.value)
            columns["pead_sue_drift"].append(float("nan") if sue.value is None or age is None else drift_decay(sue.value, age, self.half_life_sessions, self.max_age_sessions))
            columns["pead_sec_drift"].append(float("nan") if sec.value is None or age is None else drift_decay(sec.value, age, self.half_life_sessions, self.max_age_sessions))
            columns["pead_age_sessions"].append(float("nan") if age is None else age)
            columns["pead_sue_valid"].append(sue.value is not None and not expired)
            columns["pead_sec_valid"].append(sec.value is not None and not expired)
            columns["pead_sue_reason"].append("expired" if expired else (sue.reason or ""))
            columns["pead_sec_reason"].append("expired" if expired else (sec.reason or ""))
        result = pd.DataFrame(columns, index=panel.index)
        for name in ("pead_sue", "pead_sec", "pead_sue_drift", "pead_sec_drift", "pead_age_sessions"):
            result[name] = result[name].astype("float64")
        for name in ("pead_sue_valid", "pead_sec_valid"):
            result[name] = result[name].astype("bool")
        for name in ("pead_sue_reason", "pead_sec_reason"):
            result[name] = result[name].astype("string")
        return result
