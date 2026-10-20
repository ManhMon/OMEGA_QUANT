"""Point-in-time safe sentiment alpha scoring."""

from __future__ import annotations

import math
from datetime import datetime
from numbers import Real
from typing import Mapping

from omega.data.llm_sentiment_scorer import (
    FROZEN_LEXICON_SHA256,
    FROZEN_LEXICON_VERSION,
    JEVResult,
    frozen_lexicon_score,
)

import numpy as np
import pandas as pd


MAX_AGE_DAYS = 90


def _direct_number(value: object, name: str, *, positive: bool = False) -> float:
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
            or not 0 <= value <= 1e12 or not math.isfinite(value)
            or (positive and value == 0)):
        raise ValueError(f"invalid_{name}")
    return float(value)


def _direct_time(value: datetime, name: str) -> pd.Timestamp:
    if not isinstance(value, (datetime, pd.Timestamp)) or pd.isna(value):
        raise ValueError(f"invalid_{name}")
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError(f"invalid_{name}_timezone")
    return stamp.tz_convert("UTC")


def direct_news_features(
    results: list[JEVResult], *, decision_time: datetime,
    session_ages: Mapping[tuple[str, str], float], half_life_sessions: float = 3.0,
) -> pd.DataFrame:
    """Paired research baseline on one pinned run; ages are elapsed VN sessions.

    Ages count completed sessions at decision_time (the run's bound reference).
    Revisions replace an event, never increase its count. Both scores use the
    same successful, ready events and confidence * attribution weights. Counts
    include source-eligible events even when scoring failed. No history, calendar
    or deployability is certified by this pure transform.
    """
    cutoff = _direct_time(decision_time, "decision_time")
    half_life = _direct_number(half_life_sessions, "half_life_sessions", positive=True)
    if type(results) is not list or len(results) > 100_000:
        raise ValueError("invalid_direct_news_results")
    if not isinstance(session_ages, Mapping) or len(session_ages) > 100_000:
        raise ValueError("invalid_session_ages")
    latest = {}
    pin = None
    seen = {}
    for result in results:
        if type(result) is not JEVResult:
            raise ValueError("invalid_direct_news_result")
        result.__post_init__()
        request = result.request
        current_pin = (result.run_id, result.registry_sha256,
                       result.model.name, result.model.version,
                       request.cutoff_at, request.decision_time, request.evidence_mode)
        if pin is not None and pin != current_pin:
            raise ValueError("mixed_direct_news_run")
        pin = current_pin
        if request.decision_time != cutoff or request.cutoff_at > cutoff:
            raise ValueError("invalid_direct_news_cutoff")
        identity = (request.issuer, request.event_id, request.revision_id)
        if identity in seen and seen[identity] != result.replay_key:
            raise ValueError("conflicting_direct_news_revision")
        seen[identity] = result.replay_key
        if request.source_available_at > request.cutoff_at:
            continue
        key = identity[:2]
        previous = latest.get(key)
        if previous is not None:
            previous_time = previous.request.source_available_at
            if request.source_available_at == previous_time and result.replay_key != previous.replay_key:
                raise ValueError("ambiguous_direct_news_revision")
            if request.source_available_at <= previous_time:
                continue
        latest[key] = result

    rows = {}
    for key, result in sorted(latest.items()):
        issuer, _ = key
        row = rows.setdefault(issuer, {
            "news_count": 0, "scored_count": 0, "effective_weight": 0.0,
            "scorer_mass": 0.0, "lexicon_mass": 0.0,
        })
        row["news_count"] += 1
        if result.outcome.status != "ok" or result.available_at > result.request.cutoff_at:
            continue
        if key not in session_ages:
            raise ValueError("missing_session_age")
        age = _direct_number(session_ages[key], "session_age")
        if not age.is_integer():
            raise ValueError("invalid_session_age_integer")
        # ponytail: caller supplies completed session ages; trusted calendar joins belong in the ledger.
        with np.errstate(over="ignore", under="ignore"):
            decay = float(np.exp2(-np.float64(age) / half_life))
        weight = result.outcome.confidence * result.outcome.attribution * decay
        row["scored_count"] += 1
        row["effective_weight"] += weight
        row["scorer_mass"] += weight * result.outcome.score
        row["lexicon_mass"] += weight * frozen_lexicon_score(result.request.text)

    columns = ["news_count", "scored_count", "effective_weight", "scorer_mass", "lexicon_mass",
               "direct_news", "lexicon_news", "coverage", "status"]
    for row in rows.values():
        denominator = max(1.0, row["effective_weight"])
        supported = row["effective_weight"] > 0
        row["direct_news"] = row["scorer_mass"] / denominator if supported else np.nan
        row["lexicon_news"] = row["lexicon_mass"] / denominator if supported else np.nan
        row["coverage"] = row["scored_count"] / row["news_count"]
        row["status"] = "ok" if supported else "unavailable"
    frame = pd.DataFrame.from_dict(rows, orient="index", columns=columns).rename_axis("issuer")
    frame.attrs.update({
        "evidence_mode": pin[-1] if pin else "retrospective", "historical_eligible": False,
        "half_life_sessions": half_life, "age_reference_time": cutoff.isoformat(),
        "session_convention": "completed_caller_sessions",
        "lexicon_version": FROZEN_LEXICON_VERSION,
        "lexicon_sha256": FROZEN_LEXICON_SHA256, "pinned_run": pin,
        "result_bindings": tuple(sorted(seen.values())),
    })
    return frame


def ecosystem_sentiment_spillover(
    news: pd.DataFrame, edges: pd.DataFrame, *, decision_time: datetime,
    lag_time: datetime, graph_complete: bool = False,
) -> pd.DataFrame:
    """Research-only one-hop baseline: A[target, source], incoming rows <= 1.

    News is one caller-supplied snapshot per issuer at the previous session cutoff.
    Expected news must be training-fitted before that observation. Edge vintages
    are full replacements per pair, active on [as_of, valid_until). Zero weights
    can retire edges. Unknown inputs/coverage stay unavailable, never known zero.
    No propagated value is reused as direct news; diagonal edges are discarded.
    Caller dates, sectors and completeness do not certify historical provenance.
    """
    cutoff = _direct_time(decision_time, "decision_time")
    lag = _direct_time(lag_time, "lag_time")
    if lag >= cutoff or type(graph_complete) is not bool:
        raise ValueError("invalid_spillover_cutoff_or_coverage")
    news_columns = {"issuer", "observed", "expected", "sector", "as_of",
                    "available_at", "expected_available_at"}
    edge_columns = {"source", "target", "weight", "as_of", "available_at", "valid_until"}
    for frame, columns, limit in ((news, news_columns, 10_000), (edges, edge_columns, 100_000)):
        if (not isinstance(frame, pd.DataFrame) or not frame.columns.is_unique
                or set(frame.columns) != columns or len(frame) > limit):
            raise ValueError("invalid_spillover_schema_or_size")
    news, edges = news.copy(), edges.copy()
    for frame, columns in ((news, ("issuer", "sector")), (edges, ("source", "target"))):
        for column in columns:
            if any(not isinstance(value, str) or not value.strip() or len(value) > 128
                   or value != value.strip() or any(ord(char) < 32 for char in value)
                   for value in frame[column]):
                raise ValueError("invalid_spillover_identifier")
    if news["issuer"].duplicated().any():
        raise ValueError("duplicate_spillover_issuer")
    for frame in (news, edges):
        for column in ("as_of", "available_at"):
            frame[column] = pd.to_datetime([_direct_time(value, column) for value in frame[column]], utc=True)
        if (frame["as_of"] > frame["available_at"]).any():
            raise ValueError("invalid_spillover_time_order")
    news["expected_available_at"] = pd.to_datetime(
        [_direct_time(value, "expected_available_at") for value in news["expected_available_at"]], utc=True)
    if (news["expected_available_at"] >= news["as_of"]).any():
        raise ValueError("invalid_spillover_expectation_time")
    for column in ("observed", "expected"):
        values = []
        for value in news[column]:
            if value is None or value is pd.NA or (isinstance(value, (float, np.floating)) and np.isnan(value)):
                values.append(np.nan)
            elif (isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
                  or not -1 <= value <= 1 or not math.isfinite(value)):
                raise ValueError("invalid_spillover_score")
            else:
                values.append(float(value))
        news[column] = np.asarray(values, dtype=float)
    edges["weight"] = np.asarray([_direct_number(value, "edge_weight") for value in edges["weight"]])
    edges["valid_until"] = pd.to_datetime([
        pd.NaT if value is None or value is pd.NaT else _direct_time(value, "valid_until")
        for value in edges["valid_until"]], utc=True)
    if (edges["valid_until"] <= edges["as_of"]).any():
        raise ValueError("invalid_spillover_edge_interval")
    if edges.duplicated(["source", "target", "available_at"]).any():
        raise ValueError("duplicate_spillover_edge_vintage")
    edges = edges.loc[edges["available_at"] <= lag].sort_values("available_at")
    edges = edges.drop_duplicates(["source", "target"], keep="last")
    edges = edges.loc[(edges["valid_until"].isna() | (lag < edges["valid_until"]))
                      & (edges["source"] != edges["target"]) & (edges["weight"] > 0)]
    issuers = pd.Index(sorted(set(news["issuer"]) | set(edges["source"]) | set(edges["target"])), name="issuer")
    if len(issuers) > 10_000 or (edges.groupby("target").size() > 1_000).any():
        raise ValueError("invalid_spillover_graph_size")
    ready = news["available_at"] <= lag
    panel = news.set_index("issuer").reindex(issuers)
    direct = news.set_index("issuer")["observed"].where(ready.to_numpy()).reindex(issuers)
    expected = panel["expected"]
    innovation = (direct - expected).clip(-1.0, 1.0)
    sector_news = direct.groupby(panel["sector"]).transform("mean")
    incomplete_sector = direct.isna().groupby(panel["sector"]).transform("any").fillna(True)
    sector_news = sector_news.mask(incomplete_sector)
    denominator = edges.groupby("target")["weight"].transform("sum").clip(lower=1.0)
    edges["normalized_weight"] = edges["weight"] / denominator
    edges["innovation"] = edges["source"].map(innovation)
    spillover = (edges["normalized_weight"] * edges["innovation"]).groupby(edges["target"]).sum()
    missing = edges["innovation"].isna().groupby(edges["target"]).any()
    spillover = spillover.reindex(issuers, fill_value=0.0).mask(missing.reindex(issuers, fill_value=False))
    if not graph_complete:
        spillover[:] = np.nan
    if (spillover.abs() > 1.0 + 1e-12).any():
        raise ValueError("invalid_spillover_bound")
    result = pd.DataFrame({"direct_news": direct, "innovation": innovation,
                           "sector_news": sector_news, "spillover": spillover.clip(-1.0, 1.0)})
    # ponytail: caller certifies prior-session lag/coverage; ledger integration must verify both.
    result.attrs.update({"historical_eligible": False, "decision_time": cutoff.isoformat(),
                         "lag_time": lag.isoformat(), "graph_complete": graph_complete,
                         "lag_convention": "caller_previous_session_cutoff",
                         "training_provenance_verified": False,
                         "orientation": "A[target,source]", "hops": 1,
                         "news_vintages": tuple(news[["issuer", "as_of", "available_at",
                                                       "expected_available_at"]]
                                                .sort_values("issuer").itertuples(index=False, name=None)),
                         "edge_vintages": tuple(edges[["source", "target", "as_of", "available_at",
                                                        "valid_until", "normalized_weight"]]
                                                .sort_values(["target", "source"]).itertuples(index=False, name=None))})
    return result


def news_count_surprise(
    counts: pd.Series, *, available_at: pd.Series, decision_time: datetime,
    window: int = 60, min_history: int = 20,
) -> pd.DataFrame:
    """Prior-session population moments, clipped at +/-5; unavailable warm-up.

    One issuer, one explicit count per session (including zero-news sessions).
    Delayed-publication semantics: each row is evaluated at available_at[t],
    not at session time. Only the previous window sessions knowable then enter
    moments. A delayed row must not be backdated to its session label for trading.
    Missing/unknown sessions are not invented as zeros. Inputs are research data,
    not proof of historical availability or an exchange-calendar certificate.
    """
    cutoff = _direct_time(decision_time, "decision_time")
    if (type(window) is not int or not 2 <= window <= 252
            or type(min_history) is not int or not 2 <= min_history <= window):
        raise ValueError("invalid_count_history_window")
    if (not isinstance(counts, pd.Series) or len(counts) > 100_000
            or not isinstance(counts.index, pd.DatetimeIndex)
            or counts.index.tz is None or counts.index.hasnans
            or counts.index.has_duplicates or not counts.index.is_monotonic_increasing):
        raise ValueError("invalid_count_sessions")
    if (not isinstance(available_at, pd.Series) or not counts.index.equals(available_at.index)):
        raise ValueError("invalid_count_availability_index")
    values = np.array([_direct_number(value, "news_count") for value in counts], dtype=float)
    if (values != np.floor(values)).any():
        raise ValueError("invalid_news_count_integer")
    times = pd.DatetimeIndex([_direct_time(value, "available_at") for value in available_at])
    sessions = counts.index.tz_convert("UTC")
    if len(times) and (times < sessions).any():
        raise ValueError("invalid_count_time_order")
    eligible = (sessions <= cutoff) & (times <= cutoff) if len(times) else np.array([], dtype=bool)
    positions = np.flatnonzero(eligible)
    rows = []
    for position in positions:
        start = max(0, position - window)
        prior = values[start:position][times[start:position] <= times[position]]
        mean = float(prior.mean()) if len(prior) else np.nan
        sigma = float(prior.std(ddof=0)) if len(prior) else np.nan
        status = "insufficient_history" if len(prior) < min_history else (
            "zero_variance" if sigma <= 1e-12 else "ok")
        surprise = float(np.clip((values[position] - mean) / sigma, -5, 5)) if status == "ok" else np.nan
        rows.append((values[position], len(prior), mean, sigma, surprise, status, times[position]))
    frame = pd.DataFrame(rows, index=counts.index[positions], columns=[
        "news_count", "history_count", "prior_mean", "prior_std", "surprise", "status", "available_at",
    ])
    frame.attrs.update({"historical_eligible": False, "window": window,
                        "min_history": min_history, "std_ddof": 0,
                        "evaluation_time": "available_at"})
    return frame


class SentimentAlphaEngine:
    """Combine baseline signals with age-decayed sentiment adjustments."""

    def __init__(
        self, sentiment_scale: float = 0.05, default_score: float = 0.0,
        sentiment_decay: float = 0.0,
    ) -> None:
        if not math.isfinite(sentiment_decay) or sentiment_decay < 0:
            raise ValueError("sentiment_decay must be finite and non-negative")
        if not math.isfinite(sentiment_scale):
            raise ValueError("sentiment_scale must be finite")
        if not math.isfinite(default_score):
            raise ValueError("default_score must be finite")
        self.sentiment_scale = sentiment_scale
        self.default_score = default_score
        self.sentiment_decay = sentiment_decay

    @staticmethod
    def _validate_pit(
        as_of: datetime, available_at: datetime | pd.Series,
        timestamp: datetime | pd.Series, symbols: pd.Index,
    ) -> None:
        if as_of is None or available_at is None or timestamp is None:
            raise ValueError("PIT violation: as_of/available_at/timestamp required")
        as_of_timestamp = pd.Timestamp(as_of)
        available = SentimentAlphaEngine._normalize_pit_timestamp(available_at, symbols, "available_at")
        observed = SentimentAlphaEngine._normalize_pit_timestamp(timestamp, symbols, "timestamp")
        if (available.dt.tz is None) != (as_of_timestamp.tzinfo is None) or (
            available.dt.tz is None
        ) != (observed.dt.tz is None):
            raise ValueError("PIT violation: timestamps must use compatible timezones")
        if (available > as_of_timestamp).any():
            raise ValueError("PIT violation: available_at must not exceed as_of")
        if (as_of_timestamp > observed).any():
            raise ValueError("PIT violation: as_of must not exceed timestamp")
        if (available >= observed).any():
            raise ValueError("PIT violation: available_at must be strictly less than timestamp")

    @staticmethod
    def _normalize_pit_timestamp(
        value: datetime | pd.Series, symbols: pd.Index, name: str,
    ) -> pd.Series:
        if isinstance(value, pd.Series):
            if value.index.has_duplicates:
                raise ValueError(f"PIT violation: {name} must have unique index")
            values = pd.to_datetime(value).reindex(symbols)
        else:
            values = pd.Series(pd.Timestamp(value), index=symbols)
        if values.isna().any():
            raise ValueError(f"PIT violation: {name} contains NaT")
        return values

    def combine_sentiment_alpha(
        self, base_signals: pd.Series, sentiment_scores: pd.Series, as_of: datetime,
        available_at: datetime | pd.Series, timestamp: datetime | pd.Series,
        sentiment_age_days: float | pd.Series = 0.0, article_counts: pd.Series | None = None,
        sectors: pd.Series | Mapping[str, str] | None = None,
    ) -> pd.Series:
        if base_signals.index.has_duplicates:
            raise ValueError("base_signals must have unique index")
        if not np.isfinite(base_signals.to_numpy(dtype=float)).all():
            raise ValueError("base_signals must be finite")
        self._validate_pit(as_of, available_at, timestamp, base_signals.index)
        if base_signals.empty:
            return pd.Series(dtype=float)
        all_symbols = base_signals.index
        age = self._validate_age(sentiment_age_days, all_symbols)
        aligned_sentiment = sentiment_scores.reindex(all_symbols).fillna(self.default_score)
        clamped = np.clip(aligned_sentiment.to_numpy(dtype=float), -1.0, 1.0)
        decay_factor = np.exp(-self.sentiment_decay * age.to_numpy(dtype=float))
        decay_factor = np.where(age.to_numpy(dtype=float) >= MAX_AGE_DAYS, 0.0, decay_factor)
        adjustment = clamped * self.sentiment_scale * decay_factor
        if article_counts is not None:
            original_counts = article_counts.to_numpy(dtype=float)
            if not np.isfinite(original_counts).all() or (original_counts < 0).any():
                raise ValueError("article_counts must be finite and non-negative")
            counts = article_counts.reindex(all_symbols).fillna(0.0).to_numpy(dtype=float)
            adjustment *= np.log1p(counts)
        adjustment = pd.Series(adjustment, index=all_symbols)
        if sectors is not None:
            sector_series = pd.Series(sectors).reindex(all_symbols).fillna("Unclassified")
            adjustment -= adjustment.groupby(sector_series).transform("mean")
        return (base_signals.astype(float) + adjustment).sort_index()

    @staticmethod
    def _validate_age(sentiment_age_days: float | pd.Series, symbols: pd.Index) -> pd.Series:
        if isinstance(sentiment_age_days, pd.Series):
            if sentiment_age_days.isna().any():
                raise ValueError("sentiment_age_days contains NaN values")
            if sentiment_age_days.index.has_duplicates:
                raise ValueError("sentiment_age_days must have unique index")
            values = sentiment_age_days.to_numpy(dtype=float)
            if not np.isfinite(values).all() or (values < 0).any():
                raise ValueError("sentiment_age_days must be finite and non-negative")
            return sentiment_age_days.reindex(symbols).fillna(MAX_AGE_DAYS)
        if not math.isfinite(sentiment_age_days) or sentiment_age_days < 0:
            raise ValueError("sentiment_age_days must be finite and non-negative")
        return pd.Series(sentiment_age_days, index=symbols)

    def compute_weighted_allocation(self, signals: pd.Series, target_sum: float = 1.0) -> pd.Series:
        """Convert positive signals into weights normalized to ``target_sum``."""
        if signals.empty:
            return pd.Series(dtype=float)
        positive_signals = np.maximum(signals.values, 0.0)
        total = np.sum(positive_signals)
        weights = positive_signals / total * target_sum if total > 0 else np.zeros_like(positive_signals)
        return pd.Series(weights, index=signals.index)
