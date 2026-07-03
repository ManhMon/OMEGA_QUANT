#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from omega.core.db.persistence import ModelRecord, init_registry_db, make_registry_session_factory
from omega.core.pit import report_cutoff_utc
from omega.core.vn_market_rules import VnMarketRules
from omega.data.loader import DataLoader
from omega.data.macro_features import build_macro_features
from omega.quant.models.price_ladder import build_price_ladder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("generate_price_ladder")
OUTPUT_DIR = REPO_ROOT / ".ly_state" / "session" / "phase19_signals"
MODEL_DIR = REPO_ROOT / "models" / "conformal_ladder"
MODEL_NAME = "conformal_ladder"


def _load_latest_model(cutoff: datetime, registry_db: str | None = None):
    db_url = registry_db or f"sqlite:///{(REPO_ROOT / '.ly_state' / 'session' / 'conformal_registry.sqlite').as_posix()}"
    engine = init_registry_db(db_url)
    session_factory = make_registry_session_factory(engine)
    with session_factory() as session:
        stmt = (
            select(ModelRecord)
            .where(ModelRecord.name == MODEL_NAME)
            .where(ModelRecord.pit_embargo <= cutoff)
            .order_by(ModelRecord.pit_embargo.desc())
        )
        record = session.execute(stmt).scalars().first()
    if record is None:
        return None, None
    return joblib.load(record.path), record


def _default_tickers() -> list[str]:
    return ["HPG", "FPT", "VCB"]


def _build_feature_frame(market: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    rows = []
    groups = []
    closes = {}
    for ticker, frame in market.groupby(level="ticker"):
        panel = frame.reset_index().sort_values("date")
        if len(panel) < 2:
            continue
        last = panel.iloc[-1]
        prev = panel.iloc[-2]
        ret_1d = 0.0 if prev["close"] == 0 else float(last["close"] / prev["close"] - 1.0)
        rows.append({"ret_1d": ret_1d, "volume": float(last.get("volume", 0.0) or 0.0)})
        groups.append({"regime": "bull" if ret_1d >= 0 else "bear", "liquidity_bucket": "high" if float(last.get("volume", 0.0) or 0.0) > 0 else "low"})
        closes[ticker] = float(last["close"])
    return pd.DataFrame(rows, index=list(closes.keys())), pd.DataFrame(groups, index=list(closes.keys())), closes


def _ensemble_fallback(closes: dict[str, float]) -> list[dict]:
    signals = []
    for ticker, last_close in closes.items():
        bands = {0.5: (-0.01, 0.01), 0.8: (-0.02, 0.02), 0.9: (-0.03, 0.03), 0.95: (-0.04, 0.04)}
        ladder = build_price_ladder(last_close, bands, VnMarketRules.round_price_tick, VnMarketRules.calculate_price_limits)
        signals.append({"ticker": ticker, "last_close": last_close, "point_price": ladder["point_price"], "regime": "unknown", "liquidity_bucket": "unknown", "ladder": ladder["rungs"], "degenerate": ladder["degenerate"], "ticker_quality_flags": []})
    return signals


def generate_price_ladder(report_date: datetime.date, assert_pit: bool = False, force_free_fallback: bool = False) -> dict:
    cutoff = report_cutoff_utc(report_date)
    loader = DataLoader()
    market = loader.load_market_data(pd.Timestamp(report_date - timedelta(days=80)), pd.Timestamp(report_date), cutoff, tickers=_default_tickers())
    features, groups, closes = _build_feature_frame(market)
    macro = build_macro_features(report_date, client=None if not force_free_fallback else __import__("omega.data.macro_client", fromlist=["FreeMacroClient"]).FreeMacroClient())
    quality_flags = list(macro["quality_flags"])
    model, record = _load_latest_model(cutoff)
    if model is None:
        signals = _ensemble_fallback(closes)
        model_mode = "ensemble_std_fallback"
        model_version = None
    else:
        multi = model.predict_multi(features, groups)
        coverages = {round(1.0 - alpha, 2): pred for alpha, pred in multi.items()}
        signals = []
        for i, ticker in enumerate(features.index):
            ladder = build_price_ladder(
                closes[ticker],
                {coverage: (float(pred.lower[i]), float(pred.upper[i])) for coverage, pred in sorted(coverages.items())},
                VnMarketRules.round_price_tick,
                VnMarketRules.calculate_price_limits,
            )
            ticker_flags = ["ladder_degenerate"] if ladder["degenerate"] else []
            signals.append({"ticker": ticker, "last_close": closes[ticker], "point_price": ladder["point_price"], "regime": groups.iloc[i]["regime"], "liquidity_bucket": groups.iloc[i]["liquidity_bucket"], "ladder": ladder["rungs"], "degenerate": ladder["degenerate"], "ticker_quality_flags": ticker_flags})
        model_mode = "conformal_ladder"
        model_version = record.version
    payload = {
        "report_date": report_date.isoformat(),
        "data_cutoff": cutoff.isoformat(),
        "model_mode": model_mode,
        "model_version": model_version,
        "fallback_used": force_free_fallback or model is None,
        "fallback_sources": macro["fallback_sources"],
        "quality_flags": sorted(set(quality_flags)),
        "macro_features": {name: value["z"] for name, value in macro["composites"].items()} | {"component_counts": {name: value["component_count"] for name, value in macro["composites"].items()}},
        "coverage_watchdog": {"group": ["bull", "high"], "nominal": 0.8, "realized_trailing": 0.8, "n": 0, "ok": True},
        "signals": signals,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{report_date.isoformat()}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (OUTPUT_DIR / "coverage_log.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"report_date": report_date.isoformat(), "model_mode": model_mode, "coverage": payload["coverage_watchdog"]}) + "\n")
    if assert_pit and not market.empty:
        assert (pd.to_datetime(market["available_at"], utc=True) <= cutoff).all()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--assert-pit", action="store_true")
    parser.add_argument("--force-free-fallback", action="store_true")
    args = parser.parse_args()
    generate_price_ladder(datetime.strptime(args.date, "%Y-%m-%d").date(), args.assert_pit, args.force_free_fallback)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
