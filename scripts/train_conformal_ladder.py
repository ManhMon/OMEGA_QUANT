#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from omega.core.pit import to_utc_aware
from omega.core.registry.persistence import DatabaseRegistry
from omega.quant.models.conformal_predictor import ConformalTrendPredictor


def train(report_date: datetime.date, horizon: int = 1, calib_days: int = 252) -> Path:
    rng = np.random.default_rng(42)
    n = max(400, calib_days + 100)
    dates = pd.date_range(end=pd.Timestamp(report_date) - pd.Timedelta(days=horizon + 1), periods=n, freq="B")
    x = pd.DataFrame({"ret_1d": rng.normal(0, 0.02, n), "volume": rng.lognormal(10, 0.3, n)})
    y = x["ret_1d"] * 0.6 + rng.normal(0, 0.01, n)
    groups = pd.DataFrame({"regime": np.where(x["ret_1d"] >= 0, "bull", "bear"), "liquidity_bucket": pd.qcut(x["volume"], 3, labels=["low", "mid", "high"]).astype(str)})
    split = n - calib_days
    model = ConformalTrendPredictor(alpha=0.2, min_group_size=20, alphas=[0.5, 0.2, 0.1, 0.05])
    model.fit(x.iloc[:split], y.iloc[:split], x.iloc[split:], y.iloc[split:], groups.iloc[split:])
    out_dir = REPO_ROOT / "models" / "conformal_ladder"
    out_dir.mkdir(parents=True, exist_ok=True)
    version = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = out_dir / f"{version}.joblib"
    joblib.dump(model, path)
    registry = DatabaseRegistry(database_url=f"sqlite:///{(REPO_ROOT / '.ly_state' / 'session' / 'conformal_registry.sqlite').as_posix()}")
    registry.register_model(name="conformal_ladder", version=version, path=str(path), status="ready", metrics={"alphas": model.alphas, "feature_list": list(x.columns)}, pit_embargo=to_utc_aware(datetime.combine(dates[split - 1].date(), datetime.min.time())))
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--calib-days", type=int, default=252)
    args = parser.parse_args()
    train(datetime.strptime(args.date, "%Y-%m-%d").date(), args.horizon, args.calib_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
