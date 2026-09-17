#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from omega.core.database import Database
from omega.core.pit import report_cutoff_utc, to_utc_aware
from omega.core.vn_market_rules import VnMarketRules
from omega.data.loader import DataLoader
from omega.data.macro_features import build_macro_features
from omega.data.vnstock_live import VnStockLiveDataProvider
from omega.quant.portfolio.sector_classifier import SectorClassifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("generate_sector_report")
OUTPUT_DIR = REPO_ROOT / ".ly_state" / "session" / "reports"


def _prev_report_path(report_date: datetime.date) -> Path:
    return OUTPUT_DIR / f"sector_report_{(report_date - timedelta(days=1)).isoformat()}.json"


def _default_tickers() -> list[str]:
    return ["HPG", "FPT", "VCB", "SSI", "PVD", "VNM"]


def _cross_z(series: pd.Series) -> pd.Series:
    med = series.median()
    mad = (series - med).abs().median()
    if mad == 0 or pd.isna(mad):
        return pd.Series([None] * len(series), index=series.index)
    return ((0.6745 * (series - med) / mad).clip(-3, 3)).astype(float)


def _safe_float(value):
    return None if pd.isna(value) else float(value)


def generate_sector_report(report_date: datetime.date, assert_pit: bool = False) -> dict:
    cutoff = report_cutoff_utc(report_date)
    loader = DataLoader()
    market = loader.load_market_data(pd.Timestamp(report_date - timedelta(days=90)), pd.Timestamp(report_date), cutoff, tickers=_default_tickers())
    if assert_pit and not market.empty:
        assert (pd.to_datetime(market["available_at"], utc=True) <= cutoff).all()
    panel = market.reset_index().sort_values(["ticker", "date"])
    panel["ret_1d"] = panel.groupby("ticker")["close"].pct_change()
    panel["ret_5d"] = panel.groupby("ticker")["close"].pct_change(5)
    panel["ret_20d"] = panel.groupby("ticker")["close"].pct_change(20)
    panel["value_5d"] = panel.groupby("ticker")["value"].transform(lambda s: s.rolling(5).mean())
    panel["value_60d"] = panel.groupby("ticker")["value"].transform(lambda s: s.rolling(60).mean())
    db = Database()
    sector_rows = db.get_ticker_sector() if hasattr(db, "get_ticker_sector") else []
    sector_history = pd.DataFrame(sector_rows)
    quality_flags: list[str] = []
    classifier = SectorClassifier()
    mapping_not_pit = sector_history.empty or sector_history.get("effective_date") is None or sector_history.get("effective_date", pd.Series(dtype=object)).isna().any()
    mapping = classifier.get_sector_mapping_pit(report_date, sector_history=sector_history if not sector_history.empty else None, sector_col="sector", effective_col="effective_date")
    if not mapping:
        mapping = {ticker: f"Sector-{index % 3}" for index, ticker in enumerate(panel["ticker"].unique())}
        mapping_not_pit = True
    if mapping_not_pit:
        quality_flags.append("sector_mapping_not_pit")
    panel["sector"] = panel["ticker"].map(mapping)
    snapshot = panel[panel["date"] == panel["date"].max()].copy()
    fetcher = VnStockLiveDataProvider()
    adv = fetcher._compute_adv_vectorized(panel[["ticker", "date", "volume", "value"]].dropna(), window=20)
    snapshot = snapshot.merge(adv, on="ticker", how="left")
    market_ret_20d = snapshot["ret_20d"].mean()
    sector_stats = snapshot.groupby("sector").agg(
        n_tickers=("ticker", "nunique"),
        adv_20d_vnd=("adv_value", "mean"),
        breadth_1d=("ret_1d", lambda s: float((s > 0).mean())),
        breadth_5d=("ret_5d", lambda s: float((s > 0).mean())),
        sector_ret_20d=("ret_20d", "mean"),
        flow_ratio=("value_5d", lambda s: float((s / snapshot.loc[s.index, "value_60d"]).median())),
    )
    sector_stats["rs_raw"] = sector_stats["sector_ret_20d"] - market_ret_20d
    sector_stats["rs_20d_z"] = _cross_z(sector_stats["rs_raw"])
    sector_stats["flow_z"] = _cross_z(sector_stats["flow_ratio"])
    news = db.get_news_articles(end_date=cutoff) if hasattr(db, "get_news_articles") else []
    news_frame = pd.DataFrame(news)
    sentiment_map = {}
    if not news_frame.empty and "metadata" in news_frame.columns:
        for sector in sector_stats.index:
            sentiment_map[sector] = None
    sector_stats["sentiment_z"] = pd.Series(sentiment_map)
    macro = build_macro_features(report_date, db=db)
    thin_count = 0
    rows = []
    for sector, row in sector_stats.iterrows():
        row_flags = []
        if (row["n_tickers"] < 3) or (_safe_float(row["adv_20d_vnd"]) or 0.0) <= 0.0:
            row_flags.append("thin_sector")
            thin_count += 1
        rank_inputs = [row["rs_20d_z"], row["flow_z"], row["breadth_5d"], row.get("sentiment_z")]
        composite_score = float(pd.Series([value for value in rank_inputs if pd.notna(value)]).rank(pct=True).median()) if any(pd.notna(value) for value in rank_inputs) else None
        rows.append({
            "sector": sector,
            "n_tickers": int(row["n_tickers"]),
            "adv_20d_vnd": _safe_float(row["adv_20d_vnd"]),
            "breadth_1d": _safe_float(row["breadth_1d"]),
            "breadth_5d": _safe_float(row["breadth_5d"]),
            "rs_20d_z": _safe_float(row["rs_20d_z"]),
            "flow_z": _safe_float(row["flow_z"]),
            "sentiment_z": _safe_float(row.get("sentiment_z")),
            "composite_score": composite_score,
            "quality_flags": row_flags,
        })
    rows.sort(key=lambda item: ("thin_sector" in item["quality_flags"], -(item["composite_score"] or -999)))
    prior_path = _prev_report_path(report_date)
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else None
    if prior is None:
        quality_flags.append("no_prior_report")
    prior_scores = {row["sector"]: row.get("composite_score") for row in (prior or {}).get("executive_table", [])}
    for index, row in enumerate(rows, start=1):
        prior_score = prior_scores.get(row["sector"])
        row["rank"] = index
        row["score_delta_1d"] = None if prior_score is None or row["composite_score"] is None else float(row["composite_score"] - prior_score)
    fallback_sources = macro["fallback_sources"]
    quality_flags = sorted(set(quality_flags + macro["quality_flags"]))
    audit = {"data_cutoff": cutoff.isoformat(), "pit_rows_rejected": 0, "missing_sector_count": int(snapshot["sector"].isna().sum()), "stale_macro_count": len([flag for flag in macro["quality_flags"] if flag.startswith("macro_stale:")]), "thin_sector_count": thin_count, "sector_mapping_not_pit": mapping_not_pit}
    macro_backdrop = [{"composite": name, "z_score": payload["z"], "component_count": payload["component_count"], "latest_available_at": None, "staleness_days": None, "quality_flag": "macro_composite_sparse" if f"macro_composite_sparse:{name}" in macro["quality_flags"] else None} for name, payload in macro["composites"].items()]
    payload = {"report_date": report_date.isoformat(), "data_cutoff": cutoff.isoformat(), "universe_size": int(snapshot["ticker"].nunique()), "fallback_sources": fallback_sources, "quality_flags": quality_flags, "executive_table": rows, "sector_leaders": [{"sector": row["sector"], "top_positive_tickers": [], "top_negative_tickers": [], "return_attribution": None, "volume_shock_attribution": None} for row in rows[:3]], "macro_backdrop": macro_backdrop, "risk_notes": [{"sector": row["sector"], "note": ",".join(row["quality_flags"]) or "ok", "evidence": f"n={row['n_tickers']}"} for row in rows if row["quality_flags"]], "audit": audit}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"sector_report_{report_date.isoformat()}.json"
    md_path = OUTPUT_DIR / f"sector_report_{report_date.isoformat()}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_lines = [f"# Sector Flow Report - {report_date.isoformat()}", "", f"Data cutoff: {cutoff.isoformat()}", f"Universe: {payload['universe_size']} tickers", f"Fallback sources: {', '.join(fallback_sources) if fallback_sources else '[]'}", f"Quality flags: {', '.join(quality_flags) if quality_flags else '[]'}", "", "## Executive Table", "| rank | sector | n_tickers | adv_20d_vnd | breadth_1d | breadth_5d | rs_20d_z | flow_z | sentiment_z | composite_score | score_delta_1d |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        md_lines.append(f"| {row['rank']} | {row['sector']} | {row['n_tickers']} | {row['adv_20d_vnd']} | {row['breadth_1d']} | {row['breadth_5d']} | {row['rs_20d_z']} | {row['flow_z']} | {row['sentiment_z']} | {row['composite_score']} | {row['score_delta_1d']} |")
    md_lines.extend(["", "## Sector Leaders", "| sector | top_positive_tickers | top_negative_tickers | return_attribution | volume_shock_attribution |", "|---|---|---|---|---|"])
    for row in payload["sector_leaders"]:
        md_lines.append(f"| {row['sector']} | [] | [] |  |  |")
    md_lines.extend(["", "## Macro Backdrop", "| composite | z_score | component_count | latest_available_at | staleness_days | quality_flag |", "|---|---:|---:|---|---:|---|"])
    for row in macro_backdrop:
        md_lines.append(f"| {row['composite']} | {row['z_score']} | {row['component_count']} | {row['latest_available_at']} | {row['staleness_days']} | {row['quality_flag']} |")
    md_lines.extend(["", "## Risk Notes", "| sector | note | evidence |", "|---|---|---|"])
    for row in payload["risk_notes"]:
        md_lines.append(f"| {row['sector']} | {row['note']} | {row['evidence']} |")
    md_lines.extend(["", "## Audit", "| check | value |", "|---|---|"])
    for key, value in audit.items():
        md_lines.append(f"| {key} | {value} |")
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--assert-pit", action="store_true")
    args = parser.parse_args()
    generate_sector_report(datetime.strptime(args.date, "%Y-%m-%d").date(), assert_pit=args.assert_pit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
