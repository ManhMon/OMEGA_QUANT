"""
Layer 01 macro context features for VN equities.

This module derives slow-moving macro indicators from a daily macro frame.
All rolling statistics are shifted by one period to preserve point-in-time
correctness when the features are used on the current date.
"""

from __future__ import annotations

from typing import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import json
import math
from statistics import median

from omega.data.calendar import ICT
from omega.data.macro_rates import OMO_NET_INJECTION_LIMIT, MacroRateSource, MacroRateVintage, _aware_datetime


import numpy as np
import pandas as pd


def _pick_column(frame: pd.DataFrame, candidates: Iterable[str], feature_name: str) -> str:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    available = ", ".join(frame.columns.astype(str))
    raise ValueError(
        f"Missing source column for {feature_name}. "
        f"Expected one of {list(candidates)}, available columns: [{available}]"
    )


def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    shifted = series.shift(1)
    mean = shifted.rolling(window=window, min_periods=max(20, window // 3)).mean()
    std = shifted.rolling(window=window, min_periods=max(20, window // 3)).std()
    result = (shifted - mean) / std.replace(0, np.nan)
    return result.where(np.isfinite(result))


def get_fx_omo_indicators(macro_frame: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Derive PIT-safe FX/OMO regime features using only prior observations."""
    frame = macro_frame.sort_index()
    usd_col = _pick_column(frame, ["usd_vnd", "usd_vnd_rate", "usdvnd"], "usd_vnd_zscore")
    omo_col = _pick_column(frame, ["omo_net_injection", "net_injection", "sbv_omo_net"], "omo_net_injection_20d_sum")
    usd = frame[usd_col].astype(float)
    usd = usd.where(np.isfinite(usd) & (usd > 0))
    omo = frame[omo_col].astype(float)
    # Invalid magnitudes are unavailable, never clipped into valid OMO observations.
    omo = omo.where(np.isfinite(omo) & (omo.abs() <= OMO_NET_INJECTION_LIMIT))

    result = pd.DataFrame(index=frame.index)
    result["usd_vnd_zscore"] = _rolling_zscore(usd, window)
    changes = usd.pct_change(fill_method=None).shift(1)
    changes = changes.where(np.isfinite(changes))
    result["usd_vnd_vol_20d"] = changes.rolling(20, min_periods=5).std()
    result["omo_net_injection_20d_sum"] = omo.shift(1).rolling(20, min_periods=5).sum()
    result = result.where(np.isfinite(result))
    result["macro_fx_liquidity_regime"] = np.select(
        [
            (result["usd_vnd_zscore"] > 1.0) & (result["omo_net_injection_20d_sum"] < 0),
            (result["usd_vnd_zscore"] < -1.0) & (result["omo_net_injection_20d_sum"] > 0),
        ],
        [-1, 1],
        default=0,
    )
    result["macro_fx_liquidity_regime"] = result["macro_fx_liquidity_regime"].where(
        result["usd_vnd_zscore"].notna() & result["omo_net_injection_20d_sum"].notna()
    )
    return result


def get_macro_indicators(macro_frame: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """
    Build point-in-time macro indicators for the VN market.

    Required inputs are resolved by alias to avoid coupling this utility to a
    single vendor schema.

    Output columns:
    - ``usd_vnd_zscore``: z-score of USD/VND FX level stress.
    - ``gold_vn_ratio``: SJC gold price divided by the VN-Index level.
    - ``bond_stress_idx``: z-score of corporate bond stress. When direct
      corporate-credit data is unavailable, this falls back to the spread
      between the VN 10Y yield and the policy rate as a proxy for systemic
      credit stress.
    """
    if not isinstance(macro_frame, pd.DataFrame):
        raise TypeError("macro_frame must be a pandas DataFrame")
    if macro_frame.empty:
        return pd.DataFrame(index=macro_frame.index)
    if window < 20:
        raise ValueError("window must be at least 20 trading days")

    frame = macro_frame.sort_index().copy()
    result = pd.DataFrame(index=frame.index)

    usd_vnd_col = _pick_column(
        frame,
        ["usd_vnd", "usd_vnd_rate", "fx_usd_vnd", "usdvnd", "USDVND"],
        "usd_vnd_zscore",
    )
    vn_gold_col = _pick_column(
        frame,
        ["gold_vn", "gold_vn_price", "sjc_gold", "vn_gold_price"],
        "gold_vn_ratio",
    )
    vn_index_col = _pick_column(
        frame,
        ["vn_index", "vnindex", "vn_index_level", "vni", "VNINDEX"],
        "gold_vn_ratio",
    )
    corporate_spread_candidates = [
        "corp_bond_stress",
        "corp_credit_spread",
        "corporate_bond_spread",
        "corporate_credit_spread",
        "corp_ig_aaa_spread",
        "vn_corp_bond_spread",
        "credit_spread",
    ]
    corporate_level_candidates = [
        "corp_bond_yield",
        "corporate_bond_yield",
        "vn_corp_bond_yield",
    ]
    bond_stress_series: pd.Series | None = None

    for candidate in corporate_spread_candidates:
        if candidate in frame.columns:
            bond_stress_series = frame[candidate].astype(float)
            break

    if bond_stress_series is None:
        corporate_yield_col = next(
            (candidate for candidate in corporate_level_candidates if candidate in frame.columns),
            None,
        )
        if corporate_yield_col is not None:
            short_rate_col = _pick_column(
                frame,
                ["policy_rate", "interbank_overnight", "short_rate", "vn_1m_rate"],
                "bond_stress_idx",
            )
            bond_stress_series = (
                frame[corporate_yield_col].astype(float) - frame[short_rate_col].astype(float)
            )

    if bond_stress_series is None:
        bond_10y_col = _pick_column(
            frame,
            ["vn10y_yield", "bond_10y", "gov_bond_10y", "vn_bond_10y_yield"],
            "bond_stress_idx",
        )
        short_rate_col = _pick_column(
            frame,
            ["policy_rate", "interbank_overnight", "short_rate", "vn_1m_rate"],
            "bond_stress_idx",
        )
        bond_stress_series = frame[bond_10y_col].astype(float) - frame[short_rate_col].astype(float)

    result["usd_vnd_zscore"] = _rolling_zscore(frame[usd_vnd_col].astype(float), window=window)

    result["gold_vn_ratio"] = frame[vn_gold_col].astype(float).shift(1) / frame[vn_index_col].astype(float).shift(1).replace(0, np.nan)

    result["bond_stress_idx"] = _rolling_zscore(bond_stress_series, window=window)

    return result.where(np.isfinite(result))


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class LiquidityState:
    """Research v1; caller ledger owns atomic persistence and checkpoint antirollback."""

    source_fingerprint: str
    regime: str = "NORMAL"
    entry_count: int = 0
    exit_count: int = 0
    last_decision: datetime | None = None
    last_batch: date | None = None

    def __post_init__(self) -> None:
        digest = self.source_fingerprint
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid source fingerprint")
        if self.regime not in ("NORMAL", "STRESS"):
            raise ValueError("invalid liquidity regime")
        if type(self.entry_count) is not int or type(self.exit_count) is not int:
            raise ValueError("invalid hysteresis counters")
        if not 0 <= self.entry_count < 2 or not 0 <= self.exit_count < 3:
            raise ValueError("invalid hysteresis counters")
        if (self.regime == "NORMAL" and self.exit_count) or (self.regime == "STRESS" and self.entry_count):
            raise ValueError("inconsistent hysteresis counters")
        if self.last_decision is not None:
            object.__setattr__(self, "last_decision", _aware_datetime(self.last_decision, "last_decision"))
        if self.last_batch is not None:
            if type(self.last_batch) is not date or self.last_decision is None:
                raise ValueError("invalid last batch")
            if self.last_batch >= self.last_decision.astimezone(ICT).date():
                raise ValueError("last batch must precede decision session")
        if self.last_batch is None and (self.entry_count or self.exit_count or self.regime != "NORMAL"):
            raise ValueError("hysteresis requires a prior batch")

    def to_json(self) -> str:
        payload = asdict(self)
        for key in ("last_decision", "last_batch"):
            payload[key] = payload[key].isoformat() if payload[key] is not None else None
        payload["version"] = 1
        digest = hashlib.sha256(_canonical_json(payload).encode()).hexdigest()
        return _canonical_json({"payload": payload, "sha256": digest})

    @classmethod
    def from_json(cls, text: str) -> LiquidityState:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate checkpoint key")
                result[key] = value
            return result

        if not isinstance(text, str) or len(text) > 4096:
            raise ValueError("invalid liquidity checkpoint")
        try:
            envelope = json.loads(text, object_pairs_hook=unique)
            if not isinstance(envelope, dict) or set(envelope) != {"payload", "sha256"}:
                raise ValueError("invalid checkpoint envelope")
            payload = envelope["payload"]
            expected = {"version", "source_fingerprint", "regime", "entry_count", "exit_count", "last_decision", "last_batch"}
            if not isinstance(payload, dict) or set(payload) != expected or type(payload["version"]) is not int or payload["version"] != 1:
                raise ValueError("invalid checkpoint schema")
            if hashlib.sha256(_canonical_json(payload).encode()).hexdigest() != envelope["sha256"]:
                raise ValueError("checkpoint checksum mismatch")
            payload.pop("version")
            if payload["last_batch"] is not None:
                payload["last_batch"] = date.fromisoformat(payload["last_batch"])
            return cls(**payload)
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("invalid liquidity checkpoint") from exc


@dataclass(frozen=True)
class LiquidityOverlay:
    state: LiquidityState
    status: str
    stress_index: float | None
    components: tuple[float | None, float | None, float | None]
    observation_date: date | None
    stale_age_sessions: int | None
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.state, LiquidityState) or self.status not in ("NORMAL", "STRESS", "UNKNOWN"):
            raise ValueError("invalid liquidity result")
        if not isinstance(self.components, tuple) or len(self.components) != 3:
            raise ValueError("invalid stress components")
        for value in (*self.components, self.stress_index):
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not -5 <= value <= 5):
                raise ValueError("invalid stress value")
        if self.status == "UNKNOWN" and self.stress_index is not None:
            raise ValueError("unknown result cannot carry a valid index")
        if self.status != "UNKNOWN":
            if self.observation_date != self.state.last_batch:
                raise ValueError("result batch does not match state")
            if self.status != self.state.regime or self.stress_index is None or any(v is None for v in self.components):
                raise ValueError("incomplete liquidity result")
            if not math.isclose(self.stress_index, sum(self.components) / 3, abs_tol=1e-12):
                raise ValueError("inconsistent stress index")

    @property
    def multiplier(self) -> float | None:
        return None if self.status == "UNKNOWN" else (0.5 if self.status == "STRESS" else 1.0)

    def target_exposure(self, base_target: float, current_exposure: float) -> float:
        """Consume an already risk-limited long-only target; never authorize an order."""
        for value in (base_target, current_exposure):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("exposure must be finite in [0, 1]")
        if self.multiplier is None:
            return min(base_target, current_exposure)
        return base_target * self.multiplier


def _robust_component(value: float | None, past: list[float]) -> float | None:
    prior = past[-60:]
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in prior):
        raise ValueError("stress history must be finite numeric values")
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
        raise ValueError("stress observation must be finite numeric")
    if value is None or len(prior) < 40:
        return None
    center = median(prior)
    mad = median(abs(x - center) for x in prior)
    if not math.isfinite(center) or not math.isfinite(mad):
        raise ValueError("stress history arithmetic overflow")
    if mad <= 1e-12:
        return None
    scale = 1.4826 * mad
    zscore = (value - center) / scale
    if not math.isfinite(scale) or not math.isfinite(zscore):
        raise ValueError("stress arithmetic overflow")
    return max(-5.0, min(5.0, zscore))


def _advance_liquidity(state: LiquidityState, index: float | None, batch: date | None, decision: datetime) -> LiquidityState:
    regime, entry, exit_count = state.regime, state.entry_count, state.exit_count
    if index is None:
        entry = exit_count = 0
    elif batch is not None and (state.last_batch is None or batch > state.last_batch):
        if regime == "NORMAL":
            entry = entry + 1 if index >= 2 else 0
            if entry == 2:
                regime, entry = "STRESS", 0
        else:
            exit_count = exit_count + 1 if index < 1 else 0
            if exit_count == 3:
                regime, exit_count = "NORMAL", 0
    consumed = batch if index is not None else None
    return LiquidityState(state.source_fingerprint, regime, entry, exit_count, decision,
                          max(filter(None, (state.last_batch, consumed)), default=None))


def macro_liquidity_overlay(
    vintages: Iterable[MacroRateVintage], source: MacroRateSource, decision_time: datetime,
    state: LiquidityState | None = None,
) -> LiquidityOverlay:
    """Shadow-only P4 policy. Eligibility includes an economic-session T-1 boundary."""
    if not isinstance(source, MacroRateSource):
        raise TypeError("source must be a MacroRateSource")
    decision = _aware_datetime(decision_time, "decision_time")
    decision_date = decision.astimezone(ICT).date()
    if decision_date > source.coverage_through:
        raise ValueError("source schedule does not cover decision")
    state = LiquidityState(source.fingerprint) if state is None else state
    if not isinstance(state, LiquidityState) or state.source_fingerprint != source.fingerprint:
        raise ValueError("liquidity state source mismatch")
    if state.last_decision is not None and decision <= state.last_decision:
        raise ValueError("decision must advance; replay from the preceding checkpoint")
    if isinstance(vintages, (str, bytes, dict)) or vintages is None:
        raise TypeError("vintages must be typed observations")
    selected = {}
    seen = {}
    for count, row in enumerate(vintages, 1):
        if count > 100000:
            raise ValueError("too many macro vintages")
        if not isinstance(row, MacroRateVintage) or row.source != source:
            raise ValueError("unverified or incompatible macro vintage")
        identity = (row.observation_date, row.tenor, row.knowledge_at)
        if identity in seen and seen[identity] != row:
            raise ValueError("conflicting macro vintage")
        seen[identity] = row
        if row.knowledge_at > decision or row.observation_date >= decision_date:
            continue
        key = (row.observation_date, row.tenor)
        if key not in selected or row.knowledge_at > selected[key].knowledge_at:
            selected[key] = row
    sessions = [d for d, publication in source.schedule if d < decision_date and publication <= decision]
    positions = {d: i for i, d in enumerate(sessions)}
    on_dates = sorted(d for d, tenor in selected if tenor == "overnight" and d in positions)
    batch = on_dates[-1] if on_dates else None
    stale = len(sessions) - 1 - positions[batch] if batch is not None else None
    components = (None, None, None)
    reason = "missing_overnight"
    if batch is not None and state.last_batch is not None and batch < state.last_batch:
        updated = _advance_liquidity(state, None, None, decision)
        reason = "stale_source" if stale > source.max_age_sessions else "batch_regression"
        return LiquidityOverlay(updated, "UNKNOWN", None, components, batch, stale, reason)
    if batch is not None:
        histories = [[], [], []]
        for d in on_dates:
            level = selected[d, "overnight"].rate
            p = positions[d]
            endpoint = selected.get((sessions[p - 5], "overnight")) if p >= 5 else None
            week = selected.get((d, "1w"))
            values = (level, level - endpoint.rate if endpoint else None, level - week.rate if week else None)
            if d == batch:
                components = tuple(_robust_component(v, h) for v, h in zip(values, histories))
            for value, history in zip(values, histories):
                if value is not None:
                    history.append(value)
        reason = "ok" if all(x is not None for x in components) else "incomplete_components"
        if stale > source.max_age_sessions:
            reason = "stale_source"
    index = sum(components) / 3 if reason == "ok" else None
    updated = _advance_liquidity(state, index, batch, decision)
    return LiquidityOverlay(updated, updated.regime if index is not None else "UNKNOWN",
                            index, components, batch, stale, reason)
