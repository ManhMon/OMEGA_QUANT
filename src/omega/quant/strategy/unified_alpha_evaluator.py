"""P6 frozen alpha blend, execution-cost comparison, and OOS diagnostics."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from numbers import Real
from typing import Any

import numpy as np
import pandas as pd

from omega.data.calendar import ICT, VNTradingCalendar

__all__ = ["blend_features", "annotate_execution_costs", "evaluate_walk_forward"]

_MAX_PANEL_ROWS = 2_000_000
_MAX_CALENDAR_SESSIONS = 10_000
_MAX_TRIALS = 1_000
_RESERVED_PANEL_COLUMNS = {
    "decision_session", "execution_session", "label_end_session",
}

_STREAMS = ("direct_news", "spillover", "pead")
_FEATURE_COLUMNS = (*_STREAMS, "feature_as_of", "feature_available_at", "lineage")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_LEDGER_COLUMNS = ("fill_id", "side", "quantity", "price_vnd", "nav_vnd")


def _identifier(value: Any, name: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError(f"invalid {name}")
    return value


def _number(value: Any, name: str, low: float | None = None, high: float | None = None) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"invalid {name}")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not math.isfinite(result) or (low is not None and result < low) or (high is not None and result > high):
        raise ValueError(f"invalid {name}")
    return result


def _finite_numeric_series(values: pd.Series, name: str) -> pd.Series:
    parsed: list[float] = []
    for value in values.to_numpy(dtype=object):
        missing = pd.isna(value)
        if isinstance(missing, (bool, np.bool_)) and missing:
            parsed.append(float("nan"))
        elif isinstance(missing, (bool, np.bool_)):
            parsed.append(_number(value, name))
        else:
            raise ValueError(f"invalid {name}")
    return pd.Series(parsed, index=values.index, dtype=float)


def _timestamp(value: Any, name: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError
        return result
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name} must be timezone-aware") from None


def _weights(weights: Any) -> dict[str, float]:
    if type(weights) is not dict or set(weights) != set(_STREAMS):
        raise ValueError("weights must contain exactly direct_news, spillover, pead")
    result = {key: _number(weights[key], f"{key} weight", 0.0, 0.1) for key in _STREAMS}
    if math.fsum(result.values()) > 0.1:
        raise ValueError("aggregate feature weight exceeds 0.1")
    return result


def blend_features(
    quant: pd.Series,
    features: pd.DataFrame,
    *,
    weights: dict[str, float],
    decision_time: Any,
    macro_multiplier: float = 1.0,
    hard_veto: bool = False,
) -> pd.DataFrame:
    """Blend bounded, PIT-eligible optional streams without renormalizing missing ones."""
    if not isinstance(quant, pd.Series) or not isinstance(features, pd.DataFrame):
        raise TypeError("quant and features must be pandas Series/DataFrame")
    if not quant.index.is_unique or quant.index.hasnans or not all(type(x) is str and x for x in quant.index):
        raise ValueError("quant index must contain unique nonempty symbols")
    if len(quant) > 4096:
        raise ValueError("blend exceeds supported universe size")
    for symbol in quant.index:
        _identifier(symbol, "symbol")
    if not features.index.is_unique or not features.index.equals(quant.index):
        raise ValueError("feature index must exactly match ordered quant index")
    if len(features.columns) != len(_FEATURE_COLUMNS) or set(features.columns) != set(_FEATURE_COLUMNS):
        raise ValueError(f"features columns must be exactly {list(_FEATURE_COLUMNS)}")
    features = features.loc[:, list(_FEATURE_COLUMNS)]
    if type(hard_veto) is not bool:
        raise ValueError("hard_veto must be bool")
    weights = _weights(weights)
    multiplier = _number(macro_multiplier, "macro_multiplier", 0.0, 1.0)
    cutoff = _timestamp(decision_time, "decision_time")

    q_values: list[float] = []
    for value in quant.to_numpy(dtype=object):
        if value is None or value is pd.NA or (isinstance(value, (float, np.floating)) and math.isnan(float(value))):
            q_values.append(float("nan"))
        else:
            q_values.append(_number(value, "quant score", -1.0, 1.0))

    valid: dict[str, list[bool]] = {key: [] for key in _STREAMS}
    feature_values: dict[str, list[float]] = {key: [] for key in _STREAMS}
    for row in features.itertuples(index=False, name=None):
        observed = _timestamp(row[3], "feature_as_of")
        available = _timestamp(row[4], "feature_available_at")
        if not observed <= available <= cutoff:
            raise ValueError("feature timestamps violate PIT ordering")
        _identifier(row[5], "lineage")
        for i, key in enumerate(_STREAMS):
            value = row[i]
            if value is None or value is pd.NA or (isinstance(value, (float, np.floating)) and math.isnan(float(value))):
                valid[key].append(False)
                feature_values[key].append(0.0)
            else:
                valid[key].append(True)
                feature_values[key].append(_number(value, f"{key} feature", -1.0, 1.0))

    scores: list[float] = []
    raw_scores: list[float] = []
    for index, q_value in enumerate(q_values):
        if math.isnan(q_value):
            raw_scores.append(float("nan"))
            scores.append(float("nan"))
            continue
        raw = (1.0 - math.fsum(weights.values())) * q_value + math.fsum(
            weights[key] * feature_values[key][index] for key in _STREAMS if valid[key][index]
        )
        before_macro = 0.0 if hard_veto else raw
        raw_scores.append(before_macro)
        scores.append(before_macro * multiplier)

    result = features.copy()
    result.insert(0, "quant", q_values)
    for key in _STREAMS:
        result[f"{key}_valid"] = valid[key]
    result["score_before_macro"] = raw_scores
    result["score"] = scores
    result["macro_multiplier"] = multiplier
    return result


def annotate_execution_costs(
    fills: pd.DataFrame,
    *,
    cost_scenario: str = "p6_17_27_bps",
) -> pd.DataFrame:
    """Add the P6 comparison ledger; never mutates or replaces W7 booked fees."""
    if not isinstance(fills, pd.DataFrame) or list(fills.columns) != list(_LEDGER_COLUMNS):
        raise ValueError(f"fills columns must be exactly {list(_LEDGER_COLUMNS)}")
    if cost_scenario != "p6_17_27_bps":
        raise ValueError("unsupported P6 cost scenario")
    if len(fills) > 100_000:
        raise ValueError("execution ledger exceeds supported row count")
    if fills["fill_id"].duplicated().any():
        raise ValueError("fill_id values must be unique")
    out = fills.copy()
    notionals: list[int] = []
    fees_bps: list[int] = []
    fees: list[int] = []
    net_cash: list[int] = []
    turnover: list[float] = []
    for fill_id, side, quantity, price, nav in fills.itertuples(index=False, name=None):
        _identifier(fill_id, "fill_id")
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if isinstance(quantity, (bool, np.bool_)) or not isinstance(quantity, (int, np.integer)) or not 0 < quantity <= 10**12:
            raise ValueError("quantity must be a positive integer")
        if isinstance(price, (bool, np.bool_)) or not isinstance(price, (int, np.integer)) or not 0 < price <= 10**9:
            raise ValueError("price_vnd must be a positive integer VND_FULL amount")
        if isinstance(nav, (bool, np.bool_)) or not isinstance(nav, (int, np.integer)) or not 0 < nav <= 10**18:
            raise ValueError("nav_vnd must be a positive integer VND_FULL amount")
        notional = int(quantity) * int(price)
        bps = 17 if side == "BUY" else 27
        fee = int((Decimal(notional) * bps / Decimal(10_000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        signed_cash = (-notional if side == "BUY" else notional) - fee
        try:
            fraction = notional / int(nav) / 2.0
        except OverflowError as exc:
            raise ValueError("execution cost arithmetic overflow") from exc
        if not math.isfinite(fraction):
            raise ValueError("execution cost arithmetic overflow")
        notionals.append(notional)
        fees_bps.append(bps)
        fees.append(fee)
        net_cash.append(signed_cash)
        turnover.append(float(fraction))
    out["notional_vnd"] = notionals
    out["cost_bps"] = fees_bps
    out["cost_vnd"] = fees
    out["net_cash_vnd"] = net_cash
    out["one_way_turnover"] = turnover
    return out


def _ordinal(value: Any, name: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer session ordinal")
    return int(value)


def _interval(value: Any, name: str, calendar_size: int) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must be a half-open [start, end) interval")
    start, end = (_ordinal(value[0], name), _ordinal(value[1], name))
    if start < 0 or end <= start or end > calendar_size:
        raise ValueError(f"invalid {name} interval")
    return start, end


def _rank_ic_metrics(
    frame: pd.DataFrame,
    score_col: str,
    return_col: str,
    eval_cutoff: pd.Timestamp,
    *,
    block_length: int = 5,
    familywise_tests: int = 1,
) -> dict[str, Any]:
    eligible = frame["label_available_at"].map(lambda value: value is not None and not pd.isna(value) and _timestamp(value, "label_available_at") <= eval_cutoff)
    rows = frame.loc[eligible & frame[score_col].notna() & frame[return_col].notna()]
    daily: list[dict[str, Any]] = []
    total_sessions = int(frame["session"].nunique())
    constant_sessions = 0
    for session, group in rows.groupby("session", sort=True):
        pair = group[[score_col, return_col]].astype(float)
        if len(pair) < 2 or pair[score_col].nunique() < 2 or pair[return_col].nunique() < 2:
            constant_sessions += 1
            continue
        ic = float(pair[score_col].corr(pair[return_col], method="spearman"))
        if math.isfinite(ic):
            daily.append({"session": int(session), "rank_ic": ic, "n": int(len(pair))})
        else:
            constant_sessions += 1
    values = np.asarray([item["rank_ic"] for item in daily], dtype=float)
    mean = float(values.mean()) if values.size else None
    std = float(values.std(ddof=1)) if values.size > 1 else None
    consecutive = all(b["session"] == a["session"] + 1 for a, b in zip(daily, daily[1:]))
    hac_p = None
    long_run_variance = 0.0
    if values.size > 1 and consecutive:
        centered = values - mean
        lag_count = min(max(block_length - 1, 0), values.size - 1)
        long_run_variance = float(np.dot(centered, centered) / values.size)
        for lag in range(1, lag_count + 1):
            covariance = float(np.dot(centered[lag:], centered[:-lag]) / values.size)
            long_run_variance += 2.0 * (1.0 - lag / (lag_count + 1.0)) * covariance
        if math.isfinite(long_run_variance) and long_run_variance > 0.0:
            z_score = abs(mean / math.sqrt(long_run_variance / values.size))
            hac_p = min(1.0, math.erfc(z_score / math.sqrt(2.0)))
    adjusted_p = min(1.0, hac_p * familywise_tests) if hac_p is not None else None
    hac_se = math.sqrt(long_run_variance / values.size) if values.size > 1 and long_run_variance > 0 else None
    hac_ci = [mean - 1.96 * hac_se, mean + 1.96 * hac_se] if hac_se is not None else None
    bootstrap_ci = None
    bootstrap_status = "insufficient_samples" if consecutive else "unavailable_nonconsecutive_sessions"
    if consecutive and values.size >= max(2, block_length):
        rng = np.random.default_rng(0)
        starts = np.arange(values.size)
        estimates = np.empty(512, dtype=float)
        blocks_needed = math.ceil(values.size / block_length)
        for replicate in range(len(estimates)):
            selected = np.concatenate([
                values[(start + np.arange(block_length)) % values.size]
                for start in rng.choice(starts, size=blocks_needed, replace=True)
            ])[:values.size]
            estimates[replicate] = float(selected.mean())
        if np.isfinite(estimates).all():
            bootstrap_ci = [float(x) for x in np.quantile(estimates, [0.025, 0.975])]
            bootstrap_status = "deterministic_circular_moving_block_percentile_95"
        else:
            bootstrap_status = "nonfinite_bootstrap"
    return {
        "mean_rank_ic": mean,
        "std_rank_ic": std,
        "ic_ir": mean / std if mean is not None and std not in (None, 0.0) else None,
        "hac_standard_error": hac_se,
        "hac_normal_95_ci": hac_ci,
        "hac_normal_p": hac_p,
        "block_bootstrap_95_ci": bootstrap_ci,
        "block_bootstrap_replicates": 512 if bootstrap_ci is not None else 0,
        "block_bootstrap_length_sessions": int(block_length),
        "block_bootstrap_status": bootstrap_status,
        "bonferroni_familywise_p": adjusted_p,
        "familywise_test_count": int(familywise_tests),
        "sessions_total": total_sessions,
        "sessions_with_rank_ic": len(daily),
        "constant_or_insufficient_sessions": int(constant_sessions),
        "rank_ic_session_coverage": len(daily) / total_sessions if total_sessions else None,
        "label_rows_available": int(len(rows)),
        "label_row_coverage": int(len(rows)) / len(frame) if len(frame) else None,
        "per_session": daily,
    }


def evaluate_walk_forward(panel: pd.DataFrame, *, trial_registry: dict[str, Any]) -> dict[str, Any]:
    """Replay fixed chronological windows, purge realized label overlap, report gross rank IC only."""
    if not isinstance(panel, pd.DataFrame):
        raise TypeError("panel must be a pandas DataFrame")
    if len(panel) > _MAX_PANEL_ROWS:
        raise ValueError("panel exceeds supported row count")
    if len(panel.columns) != len(set(panel.columns)):
        raise ValueError("panel columns must be unique")
    if not panel.index.is_unique:
        raise ValueError("panel row index must be unique")
    registry_keys = {"schema_version", "session_calendar", "evaluation_time", "embargo_sessions", "final_holdout", "trials"}
    if type(trial_registry) is not dict or set(trial_registry) != registry_keys or trial_registry["schema_version"] != "p6/trials-v1":
        raise ValueError("invalid P6 trial registry schema")
    raw_calendar = trial_registry["session_calendar"]
    if not isinstance(raw_calendar, (list, tuple)) or not raw_calendar:
        raise ValueError("session_calendar must map ordered session ordinals to timestamps")
    calendar = [_timestamp(value, "session calendar entry") for value in raw_calendar]
    if len(calendar) > _MAX_CALENDAR_SESSIONS:
        raise ValueError("session calendar exceeds supported size")
    local_dates = [value.tz_convert("Asia/Ho_Chi_Minh").date() for value in calendar]
    if local_dates != sorted(set(local_dates)):
        raise ValueError("session calendar dates must be unique and chronological")
    expected = []
    current = local_dates[0]
    while current <= local_dates[-1]:
        local_midday = datetime.combine(current, time(12), tzinfo=ICT)
        if VNTradingCalendar.is_trading_day(local_midday):
            expected.append(current)
        current += timedelta(days=1)
    if expected != local_dates:
        raise ValueError("session_calendar omits or adds trading dates under VNTradingCalendar")
    size = len(calendar)
    holdout = _interval(trial_registry["final_holdout"], "final_holdout", size)
    embargo = _ordinal(trial_registry["embargo_sessions"], "embargo_sessions")
    if embargo < 0:
        raise ValueError("embargo_sessions must be nonnegative")
    evaluation_time = _timestamp(trial_registry["evaluation_time"], "evaluation_time")
    raw_trials = trial_registry["trials"]
    if not isinstance(raw_trials, (list, tuple)) or not raw_trials:
        raise ValueError("trial registry must contain every predeclared trial")
    if len(raw_trials) > _MAX_TRIALS:
        raise ValueError("trial registry exceeds supported size")

    trial_keys = {"trial_id", "ablation", "score_col", "return_col", "label_horizon_sessions", "validation_windows", "final_holdout", "weights"}
    trials: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    shared_windows: tuple[tuple[int, int], ...] | None = None
    for raw in raw_trials:
        if type(raw) is not dict or set(raw) != trial_keys:
            raise ValueError("invalid trial entry")
        trial_id = _identifier(raw["trial_id"], "trial_id")
        ablation = _identifier(raw["ablation"], "ablation")
        score_col = _identifier(raw["score_col"], "score_col")
        return_col = _identifier(raw["return_col"], "return_col")
        if score_col == return_col or score_col in _RESERVED_PANEL_COLUMNS or return_col in _RESERVED_PANEL_COLUMNS:
            raise ValueError("registered score and return columns must be distinct from reserved columns")
        if trial_id in seen_ids:
            raise ValueError("trial_id values must be unique")
        seen_ids.add(trial_id)
        horizon = _ordinal(raw["label_horizon_sessions"], "label_horizon_sessions")
        if horizon <= 0 or embargo < horizon:
            raise ValueError("session embargo must cover every registered label horizon")
        if _interval(raw["final_holdout"], "trial final_holdout", size) != holdout:
            raise ValueError("all trials must bind the same final holdout")
        window_values = raw["validation_windows"]
        if not isinstance(window_values, (list, tuple)) or not window_values:
            raise ValueError("each trial requires fixed validation windows")
        windows = tuple(_interval(value, "validation window", size) for value in window_values)
        if any(end > holdout[0] for _, end in windows) or any(a[1] > b[0] for a, b in zip(windows, windows[1:])):
            raise ValueError("validation windows must be ordered, disjoint, before final holdout")
        if shared_windows is not None and windows != shared_windows:
            raise ValueError("all trials must bind identical validation windows")
        shared_windows = windows
        trials.append({**raw, "trial_id": trial_id, "ablation": ablation, "score_col": score_col, "return_col": return_col, "label_horizon_sessions": horizon, "windows": windows, "weights": _weights(raw["weights"])})
    if not any(trial["ablation"] == "quant_only" and not any(trial["weights"].values()) for trial in trials):
        raise ValueError("registry must include a zero-weight quant_only benchmark")
    if len({trial["score_col"] for trial in trials}) != len(trials):
        raise ValueError("generated score columns must be unique across trials")
    familywise_tests = len(trials) * (len(shared_windows) + 1)

    required = {"symbol", "session", "decision_time", "execution_time", "label_end_time", "label_available_at", "event_group", "quant", *_FEATURE_COLUMNS}
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"panel missing required columns: {sorted(missing)}")
    for trial in trials:
        if trial["return_col"] not in panel.columns:
            raise ValueError(f"panel missing registered return column {trial['return_col']}")
        if trial["score_col"] in panel.columns:
            raise ValueError(f"registered score column {trial['score_col']} must be computed from the frozen blend")
        _finite_numeric_series(panel[trial["return_col"]], "registered return")
    reserved = required | _RESERVED_PANEL_COLUMNS | {trial["score_col"] for trial in trials}
    if reserved.intersection(trial["return_col"] for trial in trials):
        raise ValueError("registered return columns cannot collide with panel or score columns")
    if _RESERVED_PANEL_COLUMNS.intersection(panel.columns):
        raise ValueError("panel contains reserved internal columns")
    if panel.empty:
        raise ValueError("panel must contain rows")
    if panel.duplicated(["session", "symbol"]).any():
        raise ValueError("panel has duplicate symbol/session rows")

    data = panel.copy()
    for return_col in {trial["return_col"] for trial in trials}:
        data[return_col] = _finite_numeric_series(data[return_col], "registered return")
    data["quant"] = _finite_numeric_series(data["quant"], "quant")
    if (data["quant"].notna() & ~data["quant"].between(-1.0, 1.0)).any():
        raise ValueError("quant scores must be bounded in [-1, 1]")
    data["session"] = [_ordinal(value, "panel session") for value in data["session"]]
    session_dates = {i: value for i, value in enumerate(local_dates)}
    session_ordinals: dict[str, list[int]] = {name: [] for name in ("decision_time", "execution_time", "label_end_time")}
    for row in data.itertuples(index=False):
        values = row._asdict()
        session = values["session"]
        if session not in session_dates:
            raise ValueError("panel session outside registered calendar")
        decision_stamp = _timestamp(values["decision_time"], "decision_time")
        decision_date = decision_stamp.tz_convert("Asia/Ho_Chi_Minh").date()
        if decision_date != session_dates[session]:
            raise ValueError("decision_time must map exactly to its registered session")
        for name in ("decision_time", "execution_time", "label_end_time"):
            stamp = _timestamp(values[name], name)
            local_date = stamp.tz_convert("Asia/Ho_Chi_Minh").date()
            ordinal = session if name == "decision_time" else next(
                (index for index, day in session_dates.items() if day == local_date), None
            )
            if ordinal is None:
                raise ValueError(f"{name} does not map to the registered session calendar")
            local_clock = stamp.tz_convert(ICT).time()
            if name in ("execution_time", "label_end_time") and not (
                time(9) <= local_clock <= time(11, 30) or time(13) <= local_clock <= time(14, 45)
            ):
                raise ValueError("execution and label endpoints require active exchange hours")
            if name == "execution_time" and (
                ordinal <= session or stamp <= decision_stamp or
                not VNTradingCalendar.is_valid_trading_timestamp(stamp.tz_convert(ICT).to_pydatetime())
            ):
                raise ValueError("execution must occur in active hours on a later trading session")
            if name == "label_end_time" and (ordinal < session or stamp < _timestamp(values["execution_time"], "execution_time")):
                raise ValueError("label_end_time precedes execution")
            session_ordinals[name].append(ordinal)
        label_available = values["label_available_at"]
        if label_available is not None and not pd.isna(label_available):
            if _timestamp(label_available, "label_available_at") < _timestamp(values["label_end_time"], "label_end_time"):
                raise ValueError("label cannot be available before its endpoint")
        _identifier(values["symbol"], "symbol")
        _identifier(values["event_group"], "event_group")
    data["decision_session"] = session_ordinals["decision_time"]
    data["execution_session"] = session_ordinals["execution_time"]
    data["label_end_session"] = session_ordinals["label_end_time"]
    evaluated_groups: set[str] = set()
    for start, end in (*shared_windows, holdout):
        groups = set(data.loc[data["session"].between(start, end - 1), "event_group"])
        if evaluated_groups.intersection(groups):
            raise ValueError("connected event groups cannot cross evaluation windows")
        evaluated_groups.update(groups)

    # All registered trials share one fixed calendar; future row insertion cannot move fold boundaries.
    for trial in trials:
        actual = data["label_end_session"] - data["decision_session"]
        if (actual > trial["label_horizon_sessions"]).any():
            raise ValueError(f"observed label exceeds registered horizon for {trial['trial_id']}")
        if trial["ablation"] == "quant_only":
            scores = data["quant"].copy()
            if (scores.notna() & ~scores.between(-1.0, 1.0)).any():
                raise ValueError("quant-only benchmark scores must be bounded in [-1, 1]")
        else:
            scores = pd.Series(index=data.index, dtype=float)
            for _, indices in data.groupby("decision_time", sort=True).groups.items():
                batch = data.loc[indices]
                q = batch.set_index("symbol")["quant"]
                f = batch.set_index("symbol")[list(_FEATURE_COLUMNS)]
                blended = blend_features(q, f, weights=trial["weights"], decision_time=batch["decision_time"].iloc[0])
                scores.loc[indices] = blended["score_before_macro"].to_numpy(dtype=float)
        data[trial["score_col"]] = scores

    results: dict[str, Any] = {}
    for trial in trials:
        windows_result: list[dict[str, Any]] = []
        for start, end in trial["windows"]:
            window_rows = data[(data["decision_session"] >= start) & (data["decision_session"] < end)]
            validation_groups = set(window_rows["event_group"])
            validation = window_rows[window_rows["label_end_session"] < end]
            first_decision = min((_timestamp(v, "decision_time") for v in validation["decision_time"]), default=None)
            candidate = data[data["decision_session"] < start]
            eligible = candidate[
                (candidate["label_end_session"] < start)
                & (candidate["decision_session"] <= start - embargo - 1)
                & (~candidate["event_group"].isin(validation_groups))
            ]
            if first_decision is not None:
                eligible = eligible[eligible["label_available_at"].map(
                    lambda value: value is not None and not pd.isna(value) and _timestamp(value, "label_available_at") <= first_decision
                )]
            else:
                eligible = eligible.iloc[0:0]
            metrics = _rank_ic_metrics(validation, trial["score_col"], trial["return_col"], evaluation_time, block_length=embargo + 1, familywise_tests=familywise_tests)
            metrics["n_train_after_purge"] = int(len(eligible))
            metrics["candidate_train_rows"] = int(len(candidate))
            windows_result.append({
                "session_window": [start, end],
                "n_train_candidates": int(len(candidate)),
                "n_train_after_interval_purge_group_purge_embargo_and_availability": int(len(eligible)),
                "oos_gross": metrics,
            })
        holdout_frame = data[(data["decision_session"] >= holdout[0]) & (data["decision_session"] < holdout[1])
                             & (data["label_end_session"] < holdout[1])]
        results[trial["trial_id"]] = {
            "ablation": trial["ablation"],
            "weights": trial["weights"],
            "transform": "frozen_identity_transform",
            "score_column": trial["score_col"],
            "return_column": trial["return_col"],
            "label_horizon_sessions": trial["label_horizon_sessions"],
            "validation": windows_result,
            "final_holdout": {
                "session_window": list(holdout),
                "status": "fixed_chronological_holdout_diagnostic",
                "oos_gross": _rank_ic_metrics(holdout_frame, trial["score_col"], trial["return_col"], evaluation_time, block_length=embargo + 1, familywise_tests=familywise_tests),
                "n_rows": int(len(holdout_frame)),
                "attempted_trial_count": int(len(trials)),
            },
            "net_pnl": None,
            "net_performance_status": "unavailable_without_trial_specific_portfolio_fills_and_cash_ledger",
        }
    registry_digest = hashlib.sha256(json.dumps(trial_registry, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str).encode("utf-8")).hexdigest()
    return {
        "schema_version": "p6/evaluation-v1",
        "trial_registry_digest": registry_digest,
        "trial_registry_provenance": "caller_supplied_unverified",
        "historical_eligible": False,
        "deployment_evidence": False,
        "session_calendar_size": size,
        "embargo_sessions": embargo,
        "frozen_identity_transform": True,
        "final_holdout": list(holdout),
        "ablations": results,
        "cost_scenario": "p6_17_27_bps",
        "net_oos_performance": None,
        "net_oos_status": "unavailable_without_trial_specific_portfolio_fills_and_cash_ledger",
    }
