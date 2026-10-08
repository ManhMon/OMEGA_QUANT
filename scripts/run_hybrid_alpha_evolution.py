#!/usr/bin/env python3
from __future__ import annotations

import argparse
import inspect
import json
import logging
import math
import os
import random
import sys
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from omega.quant.evolution.hybrid_alpha_miner import HybridAlphaMiner, HybridAlphaMinerConfig
from omega.quant.evolution.llm_symbolic_synthesizer import FormulaSafetyParser, LLMSymbolicSynthesizer
from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
from omega.core.registry.persistence import DatabaseRegistry
from omega.core.structure_features import SECTOR_MAP, get_market_cap_features
from omega.core.llm_config import ALPHA_LLM_CONFIG_ENV, SUPPORTED_LLM_PROVIDERS, load_external_alpha_config, resolve_alpha_llm_config
from omega.quant.validation.dsr import deflated_sharpe_ratio

LOGGER = logging.getLogger("hybrid_alpha_real_market")

MARKET_DATA_PATH = Path("data/market_2015_now.parquet")
OUTPUT_PATH = Path(".ly_state/session/evolved_alphas.json")
CONFORMAL_REGISTRY_PATH = Path(".ly_state/session/conformal_registry.sqlite")
HYBRID_REGISTRY_ARTIFACT_DIR = Path(".ly_state/session/hybrid_alpha_registry")
HYBRID_REGISTRY_MODEL_PREFIX = "hybrid_alpha_llm_"

TARGET_HORIZON = 5
PURGE_EMBARGO_SESSIONS = 5
LOCKBOX_START = pd.Timestamp("2024-04-01")
LOCKBOX_END = pd.Timestamp("2026-06-30")
SEED = 42
MIN_CROSS_SECTION = 10
TRADING_COST_BPS = 0.0025

DEFAULT_PROMOTION_THRESHOLDS = {
    "mean_ic": 0.010,
    "icir": 0.300,
    "signal_pnl_score": 0.080,
    "dsr": 0.50,
    "pairwise_corr": 0.50,
}

BASE_FEATURE_COLUMNS = ["open", "high", "low", "close", "volume"]
ALT_FEATURE_COUNT = 25
ALT_DATA_FEATURE_COUNT = 14
ALT_DATA_FEATURE_COLUMNS = [
    "foreign_flow",
    "foreign_flow_ma5",
    "margin_proxy",
    "margin_trend",
    "sector_rotation",
    "rotation_momentum",
    "order_imbalance",
    "liquidity_shock",
    "vsi_score",
    "focal_stress_score",
    "interbank_on_spread",
    "term_structure_slope",
    "interbank_vol_5d",
    "macro_monetary_regime",
]
REQUIRED_FEATURE_COUNT = ALT_FEATURE_COUNT + ALT_DATA_FEATURE_COUNT
ACTIVE_FEATURE_COLUMNS = list(BASE_FEATURE_COLUMNS)
ALLOWED_UNARY = ["abs", "log", "sqrt", "exp", "sigmoid", "rank", "neg"]
ALLOWED_BINARY = ["+", "-", "*", "/", "max", "min"]
ALLOWED_TS = ["ts_std", "ts_mean", "ts_rank", "decay_linear"]


@dataclass(frozen=True)
class FoldWindow:
    name: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    pre_validation_purge_dates: tuple[str, ...]
    post_validation_embargo_dates: tuple[str, ...]


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return str(pd.Timestamp(value).date())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Unsupported JSON type: {type(value)!r}")


def get_fold_windows() -> list[FoldWindow]:
    return [
        FoldWindow(
            name="fold_1",
            train_start=pd.Timestamp("2015-01-05"),
            train_end=pd.Timestamp("2018-12-21"),
            validation_start=pd.Timestamp("2019-01-02"),
            validation_end=pd.Timestamp("2019-12-24"),
            pre_validation_purge_dates=("2018-12-24", "2018-12-25", "2018-12-26", "2018-12-27", "2018-12-28"),
            post_validation_embargo_dates=("2019-12-25", "2019-12-26", "2019-12-27", "2019-12-30", "2019-12-31"),
        ),
        FoldWindow(
            name="fold_2",
            train_start=pd.Timestamp("2015-01-05"),
            train_end=pd.Timestamp("2020-12-24"),
            validation_start=pd.Timestamp("2021-01-04"),
            validation_end=pd.Timestamp("2021-12-24"),
            pre_validation_purge_dates=("2020-12-25", "2020-12-28", "2020-12-29", "2020-12-30", "2020-12-31"),
            post_validation_embargo_dates=("2021-12-27", "2021-12-28", "2021-12-29", "2021-12-30", "2021-12-31"),
        ),
        FoldWindow(
            name="fold_3",
            train_start=pd.Timestamp("2015-01-05"),
            train_end=pd.Timestamp("2022-12-23"),
            validation_start=pd.Timestamp("2023-01-03"),
            validation_end=pd.Timestamp("2024-03-22"),
            pre_validation_purge_dates=("2022-12-26", "2022-12-27", "2022-12-28", "2022-12-29", "2022-12-30"),
            post_validation_embargo_dates=("2024-03-25", "2024-03-26", "2024-03-27", "2024-03-28", "2024-03-29"),
        ),
    ]


def load_market_panel(parquet_path: Path = MARKET_DATA_PATH) -> pd.DataFrame:
    if not parquet_path.exists():
        raise FileNotFoundError(f"Missing market parquet: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    required = {"ticker", "date", "open", "high", "low", "close", "volume", "as_of", "available_at", "price_scale", "adjusted"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Missing required market columns: {missing}")

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["as_of"] = pd.to_datetime(df["as_of"])
    df["available_at"] = pd.to_datetime(df["available_at"])
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    if df["as_of"].isna().any() or df["available_at"].isna().any():
        raise ValueError("PIT violation: missing as_of or available_at metadata")
    if set(df["price_scale"].dropna().unique()) != {"VND"}:
        raise ValueError("price_scale must be exactly {'VND'}")
    if not (df["available_at"] >= df["date"] + pd.Timedelta(days=1)).all():
        raise ValueError("available_at must be at least T+1 for all rows")
    if not (df["adjusted"] == "backward_adjusted").all():
        raise ValueError("Corporate action availability check failed: adjusted != 'backward_adjusted'")

    return df


def add_target_h5(df: pd.DataFrame, horizon: int = TARGET_HORIZON) -> pd.DataFrame:
    out = df.copy()
    out["target_h5"] = (
        out.groupby("ticker", sort=False)["close"].shift(-horizon) / out["close"]
    ) - 1.0
    return out


def add_next_session_return(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["next_session_return"] = (out.groupby("ticker", sort=False)["close"].shift(-1) / out["close"]) - 1.0
    return out


def get_terminal_purge_dates(df: pd.DataFrame, lockbox_end: pd.Timestamp = LOCKBOX_END, sessions: int = PURGE_EMBARGO_SESSIONS) -> list[pd.Timestamp]:
    dates = sorted(pd.to_datetime(df.loc[df["date"] <= lockbox_end, "date"]).unique())[-sessions:]
    if len(dates) != sessions:
        raise ValueError(f"Expected exactly {sessions} terminal purge dates at lockbox end {lockbox_end.date()}, found {len(dates)}")
    return [pd.Timestamp(x) for x in dates]


def _assert_dates_equal(actual: Iterable[pd.Timestamp], expected: Iterable[str], label: str) -> None:
    actual_list = [pd.Timestamp(x) for x in actual]
    expected_list = [pd.Timestamp(x) for x in expected]
    if actual_list != expected_list:
        raise ValueError(f"{label} mismatch. actual={actual_list} expected={expected_list}")
    if len(actual_list) != PURGE_EMBARGO_SESSIONS:
        raise ValueError(f"{label} must contain {PURGE_EMBARGO_SESSIONS} sessions")


def build_walk_forward_splits(df: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    unique_dates = pd.Index(sorted(pd.to_datetime(df["date"]).unique()))
    folds: list[dict[str, Any]] = []

    for window in get_fold_windows():
        purge_dates = unique_dates[(unique_dates > window.train_end) & (unique_dates < window.validation_start)][:PURGE_EMBARGO_SESSIONS]
        _assert_dates_equal(purge_dates, window.pre_validation_purge_dates, f"{window.name} purge")
        post_validation_embargo = unique_dates[(unique_dates > window.validation_end)][:PURGE_EMBARGO_SESSIONS]
        _assert_dates_equal(post_validation_embargo, window.post_validation_embargo_dates, f"{window.name} post-validation embargo")

        train_dates = set(unique_dates[(unique_dates >= window.train_start) & (unique_dates <= window.train_end)])
        validation_dates = set(unique_dates[(unique_dates >= window.validation_start) & (unique_dates <= window.validation_end)])
        purge_set = set(pd.Timestamp(x) for x in purge_dates)
        post_validation_embargo_set = set(pd.Timestamp(x) for x in post_validation_embargo)
        if train_dates & purge_set or validation_dates & purge_set:
            raise ValueError(f"{window.name} purge/embargo overlaps train or validation")
        if train_dates & post_validation_embargo_set or validation_dates & post_validation_embargo_set:
            raise ValueError(f"{window.name} post-validation embargo overlaps train or validation")

        folds.append(
            {
                "name": window.name,
                "train_start": window.train_start,
                "train_end": window.train_end,
                "validation_start": window.validation_start,
                "validation_end": window.validation_end,
                "purge_dates": list(purge_set),
                "post_validation_embargo_dates": list(post_validation_embargo_set),
            }
        )

    pre_lockbox_gap = unique_dates[(unique_dates > get_fold_windows()[-1].validation_end) & (unique_dates < LOCKBOX_START)][:PURGE_EMBARGO_SESSIONS]
    _assert_dates_equal(pre_lockbox_gap, ["2024-03-25", "2024-03-26", "2024-03-27", "2024-03-28", "2024-03-29"], "lockbox boundary purge")
    terminal_purge = get_terminal_purge_dates(df)
    lockbox_dates = set(unique_dates[(unique_dates >= LOCKBOX_START) & (unique_dates <= LOCKBOX_END)])
    eval_lockbox_dates = lockbox_dates.difference(terminal_purge)
    if not eval_lockbox_dates:
        raise ValueError("Lockbox evaluation window empty after terminal purge")
    evaluation_end = max(eval_lockbox_dates)
    if evaluation_end != pd.Timestamp("2026-06-23"):
        raise ValueError(f"Unexpected lockbox evaluation_end: {evaluation_end.date()}")

    lockbox = {
        "start": LOCKBOX_START,
        "end": LOCKBOX_END,
        "evaluation_end": evaluation_end,
        "pre_start_purge": [pd.Timestamp(x) for x in pre_lockbox_gap],
        "terminal_purge": terminal_purge,
    }
    return folds, lockbox


def filter_model_panel(df: pd.DataFrame) -> pd.DataFrame:
    panel = df.copy()
    feature_columns = [col for col in ACTIVE_FEATURE_COLUMNS if col in panel.columns]
    shifted = panel.groupby("ticker", sort=False)[feature_columns].shift(1)
    shifted = shifted.groupby(panel["ticker"], sort=False).ffill().fillna(0.0)
    panel.loc[:, feature_columns] = shifted
    panel = panel.dropna(subset=["target_h5", "next_session_return"]).reset_index(drop=True)
    return panel


def get_validation_panel(panel: pd.DataFrame, folds: list[dict[str, Any]]) -> pd.DataFrame:
    validation_frames = []
    for fold in folds:
        fold_panel = panel[
            (panel["date"] >= fold["validation_start"])
            & (panel["date"] <= fold["validation_end"])
            & (~panel["date"].isin(fold["post_validation_embargo_dates"]))
        ]
        validation_frames.append(fold_panel)
    return pd.concat(validation_frames, ignore_index=True) if validation_frames else panel.iloc[0:0].copy()


def build_formula_parser(max_depth: int = 10, feature_columns: list[str] | None = None) -> FormulaSafetyParser:
    return FormulaSafetyParser(
        allowed_terminals=ACTIVE_FEATURE_COLUMNS if feature_columns is None else feature_columns,
        allowed_unary=ALLOWED_UNARY,
        allowed_binary=ALLOWED_BINARY,
        allowed_ts=ALLOWED_TS,
        max_depth=max_depth,
        min_lookback=2,
        max_lookback=60,
        max_formulas=200,
    )


def _load_external_alpha_config() -> dict[str, Any]:
    return load_external_alpha_config(REPO_ROOT)


def resolve_alpha_config(provider: str | None = None) -> dict[str, Any]:
    return resolve_alpha_llm_config(REPO_ROOT, provider)


def resolve_llm_provider(
    provider: str | None = None,
    effective_alpha_config: dict[str, Any] | None = None,
) -> str:
    config = effective_alpha_config if effective_alpha_config is not None else resolve_alpha_config(provider)
    return config["provider"]


def validate_candidate_node(node: Any, max_depth: int = 10) -> None:
    allowed_ops = set(ALLOWED_UNARY + ALLOWED_BINARY + ALLOWED_TS)
    allowed_terminals = set(ACTIVE_FEATURE_COLUMNS)

    def _walk(curr: Any) -> None:
        if not curr.children:
            if curr.value is None:
                raise ValueError("Terminal node missing value")
            if curr.value in allowed_terminals:
                return
            try:
                float(curr.value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Unknown terminal: {curr.value}") from exc
            return
        if curr.operator not in allowed_ops:
            raise ValueError(f"Unknown operator: {curr.operator}")
        if curr.depth() > max_depth:
            raise ValueError(f"Depth {curr.depth()} exceeds max {max_depth}")
        if curr.operator in ALLOWED_TS:
            if len(curr.children) != 2:
                raise ValueError(f"Time-series operator {curr.operator} must have 2 children")
            lookback_value = curr.children[1].value
            if lookback_value is not None:
                try:
                    lookback = int(float(lookback_value))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid lookback for {curr.operator}") from exc
                if lookback < 2 or lookback > 60:
                    raise ValueError(f"Lookback {lookback} outside range [2, 60]")
        for child in curr.children:
            _walk(child)

    _walk(node)


def compute_daily_ic_series(panel: pd.DataFrame, alpha_values: np.ndarray, target_col: str = "target_h5", neutralize: bool = True) -> pd.Series:
    work = panel[["date", target_col]].copy()
    work["alpha"] = neutralize_alpha_by_date(panel, alpha_values, enabled=neutralize)
    daily_ics: list[tuple[pd.Timestamp, float]] = []
    for date, group in work.groupby("date", sort=True):
        valid = group[["alpha", target_col]].dropna()
        if len(valid) < MIN_CROSS_SECTION:
            continue
        if float(np.nanvar(valid["alpha"].to_numpy())) <= 1e-12:
            daily_ics.append((pd.Timestamp(date), 0.0))
            continue
        alpha_rank = rankdata(valid["alpha"].to_numpy(), method="average")
        target_rank = rankdata(valid[target_col].to_numpy(), method="average")
        corr, _ = spearmanr(alpha_rank, target_rank)
        daily_ics.append((pd.Timestamp(date), 0.0 if np.isnan(corr) else float(corr)))
    return pd.Series({date: value for date, value in daily_ics}, dtype=float).sort_index()


def compute_signal_pnl_series(panel: pd.DataFrame, alpha_values: np.ndarray, neutralize: bool = True) -> pd.Series:
    work = panel[["date", "ticker", "next_session_return"]].copy()
    work["alpha"] = neutralize_alpha_by_date(panel, alpha_values, enabled=neutralize)
    work = work.dropna(subset=["alpha", "next_session_return"])
    pnls: list[tuple[pd.Timestamp, float]] = []
    prev_weights: dict[str, float] = {}

    for date, group in work.groupby("date", sort=True):
        centered = group["alpha"] - group["alpha"].median()
        denom = float(centered.abs().sum())
        if denom <= 1e-12:
            continue
        weights = centered / denom
        curr_weights = dict(zip(group["ticker"], weights))
        universe = set(curr_weights) | set(prev_weights)
        turnover = sum(abs(curr_weights.get(t, 0.0) - prev_weights.get(t, 0.0)) for t in universe)
        net_pnl = float(np.dot(weights.to_numpy(), group["next_session_return"].to_numpy()) - turnover * TRADING_COST_BPS)
        pnls.append((pd.Timestamp(date), net_pnl))
        prev_weights = curr_weights

    return pd.Series({date: value for date, value in pnls}, dtype=float).sort_index()


def compute_candidate_metrics(panel: pd.DataFrame, alpha_values: np.ndarray, n_trials: int, neutralize: bool = True) -> dict[str, float]:
    daily_ic = compute_daily_ic_series(panel, alpha_values, neutralize=neutralize)
    mean_ic = float(daily_ic.mean()) if not daily_ic.empty else 0.0
    if len(daily_ic) > 1:
        ic_std = float(daily_ic.std(ddof=1))
        icir = 0.0 if ic_std <= 1e-12 else mean_ic / ic_std
    else:
        icir = 0.0

    pnl = compute_signal_pnl_series(panel, alpha_values, neutralize=neutralize)
    if len(pnl) > 1:
        pnl_std = float(pnl.std(ddof=1))
        signal_pnl_score = 0.0 if pnl_std <= 1e-12 else math.sqrt(252.0) * float(pnl.mean()) / pnl_std
    else:
        signal_pnl_score = 0.0
    dsr = float(deflated_sharpe_ratio(pnl.to_numpy(), n_trials=max(n_trials, 1)).dsr) if len(pnl) >= 2 else 0.0
    coverage = float(np.isfinite(alpha_values).sum() / len(alpha_values)) if len(alpha_values) else 0.0

    return {
        "mean_ic": mean_ic,
        "icir": float(icir),
        "signal_pnl_score": float(signal_pnl_score),
        "dsr": dsr,
        "coverage": coverage,
        "n_ic_days": int(len(daily_ic)),
        "n_pnl_days": int(len(pnl)),
    }


def compute_pairwise_corr(candidate_values: np.ndarray, selected_values: list[np.ndarray]) -> float:
    max_corr = 0.0
    for prev in selected_values:
        mask = np.isfinite(candidate_values) & np.isfinite(prev)
        if mask.sum() < MIN_CROSS_SECTION:
            continue
        corr, _ = spearmanr(candidate_values[mask], prev[mask])
        if not np.isnan(corr):
            max_corr = max(max_corr, abs(float(corr)))
    return max_corr


def deterministic_candidate_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    metrics = candidate["metrics"]
    return (
        -float(metrics["dsr"]),
        -float(metrics["mean_ic"]),
        int(candidate["ast_depth"]),
        str(candidate["formula_hash"]),
    )


def _clone_thresholds(thresholds: dict[str, float] | None = None) -> dict[str, float]:
    source = DEFAULT_PROMOTION_THRESHOLDS if thresholds is None else thresholds
    return {key: float(source[key]) for key in DEFAULT_PROMOTION_THRESHOLDS}


def select_promoted_candidates(candidates: list[dict[str, Any]], thresholds: dict[str, float] | None = None) -> list[dict[str, Any]]:
    thresholds = _clone_thresholds(thresholds)
    promoted: list[dict[str, Any]] = []
    selected_values: list[np.ndarray] = []
    for candidate in sorted(candidates, key=deterministic_candidate_sort_key):
        alpha_values = candidate.pop("_alpha_values")
        pairwise_corr = compute_pairwise_corr(alpha_values, selected_values)
        candidate["metrics"]["pairwise_corr"] = pairwise_corr
        thresholds_pass = (
            candidate["metrics"]["mean_ic"] >= thresholds["mean_ic"]
            and candidate["metrics"]["icir"] >= thresholds["icir"]
            and candidate["metrics"]["signal_pnl_score"] >= thresholds["signal_pnl_score"]
            and candidate["metrics"]["dsr"] >= thresholds["dsr"]
            and pairwise_corr < thresholds["pairwise_corr"]
        )
        candidate["promotion_passed"] = thresholds_pass
        if thresholds_pass:
            promoted.append(candidate)
            selected_values.append(alpha_values)
    return promoted


def build_top_candidates_diagnostic(selected_candidates: list[dict[str, Any]], lockbox_panel: pd.DataFrame, synthesizer: LLMSymbolicSynthesizer, feature_columns: list[str], n_trials: int, neutralize: bool = True) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for candidate in sorted(selected_candidates, key=deterministic_candidate_sort_key):
        try:
            alpha_values = synthesizer.execute_node_grouped(candidate["node"], lockbox_panel, feature_columns, ticker_col="ticker", date_col="date")
            metrics = _compute_candidate_metrics(lockbox_panel, alpha_values, n_trials=n_trials, neutralize=neutralize)
        except Exception as exc:
            LOGGER.warning("Top-candidate OOS diagnostic failed for %s: %s", candidate["formula_hash"], exc)
            return []
        diagnostics.append(
            {
                "alpha_id": candidate["alpha_id"],
                "formula": candidate["formula"],
                "formula_hash": candidate["formula_hash"],
                "source": candidate["source"],
                "ast_depth": candidate["ast_depth"],
                "oos_mean_ic": metrics["mean_ic"],
                "oos_icir": metrics["icir"],
                "oos_signal_pnl_score": metrics["signal_pnl_score"],
                "oos_dsr": metrics["dsr"],
            }
        )
    return diagnostics


def build_lockbox_report(promoted: list[dict[str, Any]], lockbox_panel: pd.DataFrame, synthesizer: LLMSymbolicSynthesizer, feature_columns: list[str], n_trials: int, neutralize: bool = True) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for candidate in promoted:
        alpha_values = synthesizer.execute_node_grouped(candidate["node"], lockbox_panel, feature_columns, ticker_col="ticker", date_col="date")
        reports.append(
            {
                "alpha_id": candidate["alpha_id"],
                "formula_hash": candidate["formula_hash"],
                "metrics": _compute_candidate_metrics(lockbox_panel, alpha_values, n_trials=n_trials, neutralize=neutralize),
            }
        )
    return reports


def _registry_db_url(registry_path: Path) -> str:
    return f"sqlite:///{(REPO_ROOT / registry_path).as_posix()}"


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default))


def _utc_midnight(ts: pd.Timestamp) -> datetime:
    stamp = pd.Timestamp(ts)
    return datetime(stamp.year, stamp.month, stamp.day, tzinfo=timezone.utc)


def persist_promoted_hybrid_alphas(
    promoted: list[dict[str, Any]],
    *,
    lockbox_report: list[dict[str, Any]],
    thresholds: dict[str, float],
    feature_columns: list[str],
    provider: str,
    neutralize: bool,
    registry_path: Path = CONFORMAL_REGISTRY_PATH,
    artifact_dir: Path = HYBRID_REGISTRY_ARTIFACT_DIR,
    pit_embargo: pd.Timestamp = LOCKBOX_END,
) -> list[dict[str, Any]]:
    if not promoted:
        return []

    registry_file = REPO_ROOT / registry_path
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    registry = DatabaseRegistry(database_url=_registry_db_url(registry_path))
    artifact_root = REPO_ROOT / artifact_dir
    artifact_root.mkdir(parents=True, exist_ok=True)
    lockbox_by_hash = {entry["formula_hash"]: entry["metrics"] for entry in lockbox_report}
    persisted: list[dict[str, Any]] = []
    metric_keys = ("mean_ic", "icir", "signal_pnl_score", "dsr", "coverage", "pairwise_corr")

    for index, candidate in enumerate(promoted, start=1):
        model_name = f"{HYBRID_REGISTRY_MODEL_PREFIX}{candidate['alpha_id']}"
        version = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{index:02d}_{candidate['formula_hash'][:12]}"
        artifact_path = artifact_root / f"{version}.json"
        artifact_payload = {
            "alpha_id": candidate["alpha_id"],
            "formula": candidate["formula"],
            "formula_hash": candidate["formula_hash"],
            "source": candidate["source"],
            "ast_depth": candidate["ast_depth"],
            "selection_window": candidate["selection_window"],
            "validation_metrics": candidate["metrics"],
            "lockbox_metrics": lockbox_by_hash.get(candidate["formula_hash"], {}),
            "thresholds": thresholds,
            "feature_columns": feature_columns,
            "provider": provider,
            "neutralize": bool(neutralize),
            "registry_kind": "hybrid_llm_promoted_alpha",
        }
        with artifact_path.open("w", encoding="utf-8") as handle:
            json.dump(artifact_payload, handle, indent=2, default=_json_default)
        metrics_payload = {
            "alpha_id": candidate["alpha_id"],
            "formula": candidate["formula"],
            "formula_hash": candidate["formula_hash"],
            "source": candidate["source"],
            "ast_depth": candidate["ast_depth"],
            "selection_window": candidate["selection_window"],
            "validation_metrics": candidate["metrics"],
            "lockbox_metrics": lockbox_by_hash.get(candidate["formula_hash"], {}),
            "thresholds": thresholds,
            "feature_columns": feature_columns,
            "provider": provider,
            "neutralize": bool(neutralize),
            "artifact_path": str(artifact_path),
            "registry_kind": "hybrid_llm_promoted_alpha",
        }
        metrics_payload.update({key: candidate["metrics"].get(key) for key in metric_keys})
        registry.register_model(
            name=model_name,
            version=version,
            path=str(artifact_path),
            status="ready",
            metrics=_json_safe(metrics_payload),
            pit_embargo=_utc_midnight(pit_embargo),
        )
        persisted.append(
            {
                "model_name": model_name,
                "version": version,
                "path": str(artifact_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            }
        )

    return persisted


def _compute_candidate_metrics(panel: pd.DataFrame, alpha_values: np.ndarray, n_trials: int, neutralize: bool) -> dict[str, float]:
    if "neutralize" in inspect.signature(compute_candidate_metrics).parameters:
        return compute_candidate_metrics(panel, alpha_values, n_trials=n_trials, neutralize=neutralize)
    return compute_candidate_metrics(panel, alpha_values, n_trials=n_trials)


def get_model_feature_columns(df: pd.DataFrame | None = None) -> list[str]:
    feature_columns = list(BASE_FEATURE_COLUMNS)
    if df is None:
        return feature_columns
    extra_columns = [
        col
        for col in df.columns
        if col not in feature_columns and col not in {"ticker", "date", "target_h5", "next_session_return", "as_of", "available_at", "price_scale", "adjusted", "sector", "log_market_cap"}
    ]
    return feature_columns + extra_columns


def enrich_with_unified_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    global ACTIVE_FEATURE_COLUMNS
    panel = df.set_index(["date", "ticker"])[BASE_FEATURE_COLUMNS].sort_index()
    panel.index.names = ["date", "symbol"]
    adapter = UnifiedFeatureAdapter(use_arsenal=False, use_alt_features=True, use_alt_data=True, use_llm_synth=False)
    enriched_panel = adapter.generate_all(panel)
    feature_groups = adapter.get_feature_groups()
    alt_features = list(feature_groups.get("alt_features", []))
    alt_data_features = list(feature_groups.get("alt_data", []))
    expected_features = alt_features + alt_data_features
    if len(alt_features) != ALT_FEATURE_COUNT or len(alt_data_features) != ALT_DATA_FEATURE_COUNT:
        raise ValueError(
            f"UnifiedFeatureAdapter feature schema mismatch: alt_features={len(alt_features)} alt_data={len(alt_data_features)}"
        )
    missing = sorted(set(expected_features).difference(enriched_panel.columns))
    if missing:
        raise ValueError(f"UnifiedFeatureAdapter missing required features: {missing}")
    if sorted(alt_data_features) != sorted(ALT_DATA_FEATURE_COLUMNS):
        raise ValueError(f"UnifiedFeatureAdapter alt/sentiment schema mismatch: {sorted(alt_data_features)}")
    enriched = df.merge(
        enriched_panel.reset_index().rename(columns={"symbol": "ticker"})[["date", "ticker", *expected_features]],
        on=["date", "ticker"],
        how="left",
        validate="one_to_one",
    )
    missing_after_merge = [col for col in expected_features if col not in enriched.columns]
    if missing_after_merge:
        raise ValueError(f"UnifiedFeatureAdapter merge missing features: {missing_after_merge}")
    ACTIVE_FEATURE_COLUMNS = BASE_FEATURE_COLUMNS + expected_features
    return add_cross_sectional_metadata(enriched), ACTIVE_FEATURE_COLUMNS


def add_cross_sectional_metadata(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["sector"] = out["ticker"].map(SECTOR_MAP).fillna("Other")
    out["log_market_cap"] = get_market_cap_features(out)["log_market_cap"].to_numpy(dtype=float)
    return out


def _sector_demean(values: pd.Series, sectors: pd.Series) -> pd.Series:
    return values.groupby(sectors).transform(lambda group: group - group.mean())


def neutralize_alpha_by_date(panel: pd.DataFrame, alpha_values: np.ndarray, enabled: bool = True) -> np.ndarray:
    if not enabled:
        return np.asarray(alpha_values, dtype=float)
    if "sector" not in panel.columns or "log_market_cap" not in panel.columns:
        return np.asarray(alpha_values, dtype=float)
    work = panel[["date", "sector", "log_market_cap"]].copy()
    work["alpha"] = np.asarray(alpha_values, dtype=float)
    residuals = np.full(len(work), np.nan, dtype=float)
    for _date, group in work.groupby("date", sort=True):
        valid = group[["alpha", "sector", "log_market_cap"]].dropna()
        if valid.empty:
            continue
        fallback = _sector_demean(valid["alpha"], valid["sector"]).to_numpy(dtype=float)
        if len(valid) < MIN_CROSS_SECTION:
            residuals[valid.index.to_numpy()] = fallback
            continue
        sector_dummies = pd.get_dummies(valid["sector"], drop_first=True, dtype=float)
        log_market_cap = valid["log_market_cap"].to_numpy(dtype=float)
        log_market_cap = log_market_cap - float(np.mean(log_market_cap))
        x = np.column_stack([
            np.ones(len(valid), dtype=float),
            log_market_cap,
            sector_dummies.to_numpy(dtype=float),
        ])
        rank = np.linalg.matrix_rank(x)
        if rank < x.shape[1]:
            residuals[valid.index.to_numpy()] = fallback
            continue
        beta, *_ = np.linalg.lstsq(x, valid["alpha"].to_numpy(dtype=float), rcond=None)
        residuals[valid.index.to_numpy()] = valid["alpha"].to_numpy(dtype=float) - x @ beta
    return residuals


def run_hybrid_real_market_integration(
    parquet_path: Path = MARKET_DATA_PATH,
    output_path: Path = OUTPUT_PATH,
    provider: str | None = None,
    budget: int = 40,
    top_k: int = 10,
    max_depth: int = 10,
    min_ic: float = DEFAULT_PROMOTION_THRESHOLDS["mean_ic"],
    min_icir: float = DEFAULT_PROMOTION_THRESHOLDS["icir"],
    min_pnl_score: float = DEFAULT_PROMOTION_THRESHOLDS["signal_pnl_score"],
    min_dsr: float = DEFAULT_PROMOTION_THRESHOLDS["dsr"],
    max_corr: float = DEFAULT_PROMOTION_THRESHOLDS["pairwise_corr"],
    neutralize: bool = True,
) -> dict[str, Any]:
    random.seed(SEED)
    np.random.seed(SEED)
    effective_alpha_config = resolve_alpha_config(provider)
    resolved_provider = resolve_llm_provider(effective_alpha_config=effective_alpha_config)
    thresholds = {
        "mean_ic": _non_negative_float(min_ic, "min-ic"),
        "icir": _non_negative_float(min_icir, "min-icir"),
        "signal_pnl_score": _non_negative_float(min_pnl_score, "min-pnl-score"),
        "dsr": _non_negative_float(min_dsr, "min-dsr"),
        "pairwise_corr": _bounded_unit_float(max_corr, "max-corr"),
    }

    raw = load_market_panel(parquet_path)
    raw, feature_columns = enrich_with_unified_features(raw)
    raw = add_target_h5(raw)
    raw = add_next_session_return(raw)
    folds, lockbox = build_walk_forward_splits(raw)
    panel = filter_model_panel(raw)

    train_panel = panel[panel["date"] < LOCKBOX_START].reset_index(drop=True)
    validation_panel = get_validation_panel(train_panel, folds)
    terminal_purge = set(lockbox["terminal_purge"])
    lockbox_panel = panel[
        (panel["date"] >= LOCKBOX_START)
        & (panel["date"] <= LOCKBOX_END)
        & (~panel["date"].isin(terminal_purge))
    ].reset_index(drop=True)
    if train_panel.empty or validation_panel.empty or lockbox_panel.empty:
        raise ValueError("Train, validation, or lockbox panel is empty after PIT filtering")

    labels = train_panel["target_h5"].to_numpy(dtype=float)
    config = HybridAlphaMinerConfig(
        candidate_budget=budget,
        top_k=top_k,
        n_outer_folds=3,
        n_inner_folds=3,
        llm_provider=resolved_provider,
        min_deploy_ic=thresholds["mean_ic"],
        min_deploy_dsr=thresholds["dsr"],
        max_deploy_correlation=thresholds["pairwise_corr"],
    )
    miner = HybridAlphaMiner(config)
    selected, evidence = miner.run(train_panel, feature_columns, labels, ticker_col="ticker", date_col="date")

    build_formula_parser(max_depth=max_depth)
    synthesizer = LLMSymbolicSynthesizer(
        use_mock=resolved_provider == "mock",
        provider=resolved_provider,
        effective_alpha_config=effective_alpha_config,
        prompt_version="vn_alpha_search_v3_closed_loop",
        max_candidates=10,
    )
    evaluated: list[dict[str, Any]] = []
    n_trials = max(evidence.get("total_generated", len(selected)), 1)
    for idx, candidate in enumerate(selected):
        formula = candidate.formula_str
        validate_candidate_node(candidate.node, max_depth=max_depth)
        alpha_values = synthesizer.execute_node_grouped(candidate.node, validation_panel, feature_columns, ticker_col="ticker", date_col="date")
        metrics = _compute_candidate_metrics(validation_panel, alpha_values, n_trials=n_trials, neutralize=neutralize)
        evaluated.append(
            {
                "alpha_id": f"hybrid_alpha_{idx:03d}",
                "formula": formula,
                "formula_hash": candidate.formula_hash,
                "source": candidate.source.value,
                "node": candidate.node,
                "ast_depth": int(candidate.node.depth()),
                "metrics": metrics,
                "selection_window": {"start": min(validation_panel["date"]), "end": max(validation_panel["date"])},
                "_alpha_values": alpha_values,
            }
        )

    promoted = select_promoted_candidates(evaluated, thresholds=thresholds)
    lockbox_report = build_lockbox_report(promoted, lockbox_panel, synthesizer, feature_columns, n_trials, neutralize=neutralize)
    top_candidates_diagnostic = build_top_candidates_diagnostic(evaluated, lockbox_panel, synthesizer, feature_columns, n_trials, neutralize=neutralize)
    for candidate in promoted:
        candidate.pop("_alpha_values", None)
        candidate.pop("node", None)

    registry_rows = persist_promoted_hybrid_alphas(
        promoted,
        lockbox_report=lockbox_report,
        thresholds=thresholds,
        feature_columns=feature_columns,
        provider=resolved_provider,
        neutralize=neutralize,
        pit_embargo=lockbox["end"],
    )

    payload = {
        "gate": "gp_hybrid_real_market_integration",
        "seed": SEED,
        "data_path": str(parquet_path).replace("\\", "/"),
        "provider": resolved_provider,
        "neutralize": bool(neutralize),
        "requested_provider": getattr(synthesizer, "requested_provider", resolved_provider),
        "effective_provider": getattr(synthesizer, "effective_provider", resolved_provider),
        "target": "target_h5",
        "purge_embargo_sessions": PURGE_EMBARGO_SESSIONS,
        "thresholds": thresholds,
        "folds": [
            {
                "name": fold["name"],
                "train_start": fold["train_start"],
                "train_end": fold["train_end"],
                "validation_start": fold["validation_start"],
                "validation_end": fold["validation_end"],
                "purge_dates": sorted(fold["purge_dates"]),
                "post_validation_embargo_dates": sorted(fold["post_validation_embargo_dates"]),
            }
            for fold in folds
        ],
        "lockbox": {
            "start": lockbox["start"],
            "end": lockbox["end"],
            "evaluation_end": lockbox["evaluation_end"],
            "pre_start_purge": lockbox["pre_start_purge"],
            "terminal_purge": lockbox["terminal_purge"],
        },
        "pit_safety": {
            "t_minus_1_feature_lag": True,
            "t_minus_1_feature_count": REQUIRED_FEATURE_COUNT,
            "target_per_ticker_sorted": True,
            "corporate_action_fail_closed": True,
            "ast_allowlist_enforced": True,
            "lockbox_selection_excluded": True,
            "pnl_uses_next_session_return": True,
            "neutralize_size_sector": bool(neutralize),
        },
        "risk_adjusted_selection_evidence": {
            "total_generated": evidence.get("total_generated", 0),
            "total_selected": evidence.get("total_selected", 0),
            "selected_candidates": len(selected),
            "promoted_count": len(promoted),
            "selection_source": "pre_lockbox_validation_only",
            "feature_columns": feature_columns,
            "promoted": promoted,
        },
        "alphas": promoted,
        "lockbox_oos_report": {
            "window": {"start": lockbox["start"], "end": lockbox["evaluation_end"]},
            "candidates": lockbox_report,
            "top_candidates_diagnostic": top_candidates_diagnostic,
        },
        "model_registry_persistence": {
            "db_path": str(CONFORMAL_REGISTRY_PATH).replace("\\", "/"),
            "persisted_count": len(registry_rows),
            "persisted": registry_rows,
        },
        "miner_evidence": evidence,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=_json_default)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Hybrid Alpha Miner on real Vietnam market data.")
    parser.add_argument("--data", default=str(MARKET_DATA_PATH), help="Repo-relative parquet path")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Repo-relative output path")
    parser.add_argument(
        "--provider",
        choices=sorted(SUPPORTED_LLM_PROVIDERS),
        default=None,
        help="LLM provider override. Default: auto-detect from env.",
    )
    parser.add_argument("--budget", type=_positive_int, default=40, help="Candidate budget for hybrid alpha search")
    parser.add_argument("--top-k", type=_positive_int, default=10, help="Top-K candidates to keep during search")
    parser.add_argument("--max-depth", type=_positive_int, default=10, help="Maximum AST depth allowed during formula validation")
    parser.add_argument("--min-ic", type=lambda value: _non_negative_float(value, "min-ic"), default=DEFAULT_PROMOTION_THRESHOLDS["mean_ic"], help="Minimum validation mean IC threshold")
    parser.add_argument("--min-icir", type=lambda value: _non_negative_float(value, "min-icir"), default=DEFAULT_PROMOTION_THRESHOLDS["icir"], help="Minimum validation ICIR threshold")
    parser.add_argument("--min-pnl-score", type=lambda value: _non_negative_float(value, "min-pnl-score"), default=DEFAULT_PROMOTION_THRESHOLDS["signal_pnl_score"], help="Minimum validation signal PnL score threshold")
    parser.add_argument("--min-dsr", type=lambda value: _non_negative_float(value, "min-dsr"), default=DEFAULT_PROMOTION_THRESHOLDS["dsr"], help="Minimum validation DSR threshold")
    parser.add_argument("--max-corr", type=lambda value: _bounded_unit_float(value, "max-corr"), default=DEFAULT_PROMOTION_THRESHOLDS["pairwise_corr"], help="Maximum promoted pairwise correlation threshold")
    parser.add_argument("--neutralize", dest="neutralize", action="store_true", default=True, help="Enable per-date sector and log-market-cap neutralization")
    parser.add_argument("--no-neutralize", dest="neutralize", action="store_false", help="Disable per-date sector and log-market-cap neutralization")
    return parser.parse_args()


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _non_negative_float(value: str | float, flag_name: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        raise argparse.ArgumentTypeError(f"{flag_name} must be a finite float >= 0")
    return parsed


def _bounded_unit_float(value: str | float, flag_name: str) -> float:
    parsed = _non_negative_float(value, flag_name)
    if parsed > 1.0:
        raise argparse.ArgumentTypeError(f"{flag_name} must be <= 1.0")
    return parsed


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    args = _parse_args()
    payload = run_hybrid_real_market_integration(
        Path(args.data),
        Path(args.output),
        provider=args.provider,
        budget=args.budget,
        top_k=args.top_k,
        max_depth=args.max_depth,
        min_ic=args.min_ic,
        min_icir=args.min_icir,
        min_pnl_score=args.min_pnl_score,
        min_dsr=args.min_dsr,
        max_corr=args.max_corr,
        neutralize=args.neutralize,
    )
    LOGGER.info("Promoted %d real-market hybrid alphas", payload["risk_adjusted_selection_evidence"]["promoted_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
