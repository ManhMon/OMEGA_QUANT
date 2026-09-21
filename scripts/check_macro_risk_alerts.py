#!/usr/bin/env python3
"""Macro Risk Alert Monitor with Strict PIT, Numeric Stability, and Schema Validation."""
from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {"usd_vnd", "omo_net", "on_rate", "rate_1m"}


def compute_macro_risk_metrics(
    df_macro: pd.DataFrame,
    as_of: pd.Timestamp | str | None = None,
    z_window: int = 60,
    vol_window: int = 20,
    caution_z: float = 1.0,
    alert_z: float = 1.5,
    on_caution: float = 5.0,
    on_alert: float = 6.0,
) -> Dict[str, Any]:
    if not isinstance(z_window, int) or z_window <= 0:
        raise ValueError("z_window_must_be_positive")
    if not isinstance(vol_window, int) or vol_window <= 0:
        raise ValueError("vol_window_must_be_positive")

    if not REQUIRED_COLUMNS.issubset(df_macro.columns):
        raise ValueError("missing_schema")

    df = df_macro.copy()

    # Explicit PIT boundary enforcement: require timestamp if as_of is provided
    if as_of is not None:
        if "timestamp" not in df.columns:
            raise ValueError("as_of_requires_timestamp_column")
        cutoff = pd.to_datetime(as_of, errors="coerce", utc=True)
        if cutoff is pd.NaT:
            raise ValueError("invalid_as_of_cutoff")
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        if df["timestamp"].isna().any():
            raise ValueError("invalid_timestamp")
        if (df["timestamp"] > cutoff).any():
            raise ValueError("future_rows_exceed_cutoff")
        df = df[df["timestamp"] <= cutoff].sort_values("timestamp")
    elif "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        if df["timestamp"].isna().any():
            raise ValueError("invalid_timestamp")
        df = df.sort_values("timestamp")

    # Explicit numeric schema coercion and finite verification
    for col in REQUIRED_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isna().any() or not np.isfinite(df[col]).all():
            raise ValueError(f"invalid_numeric_{col}")

    if len(df) < z_window:
        raise ValueError("insufficient_pit_window")

    fx = df["usd_vnd"]

    # Explicit denominator finite/non-zero guard preventing any NaN / RuntimeWarning
    roll_std = fx.rolling(z_window).std()
    roll_mean = fx.rolling(z_window).mean()
    std_val = float(roll_std.iloc[-1]) if len(roll_std) > 0 and pd.notna(roll_std.iloc[-1]) else 0.0
    mean_val = float(roll_mean.iloc[-1]) if len(roll_mean) > 0 and pd.notna(roll_mean.iloc[-1]) else 0.0

    if not math.isfinite(std_val) or std_val <= 1e-8:
        z = 0.0
    else:
        last_val = float(fx.iloc[-1])
        z = (last_val - mean_val) / std_val
        if not math.isfinite(z):
            z = 0.0
    z = float(z)

    vol_series = fx.pct_change().rolling(vol_window).std()
    vol_val = float(vol_series.iloc[-1]) if len(vol_series) > 0 and pd.notna(vol_series.iloc[-1]) else 0.0
    if not math.isfinite(vol_val) or vol_val <= 1e-8:
        vol = 0.0
    else:
        vol = float(vol_val * math.sqrt(252))
        if not math.isfinite(vol):
            vol = 0.0
    vol = float(vol)

    on = float(df["on_rate"].iloc[-1])
    omo = float(df["omo_net"].tail(20).sum())
    slope = float(df["rate_1m"].iloc[-1] - on)

    if z >= alert_z or on > on_alert or (z >= caution_z and omo < 0):
        regime = 2
    elif z >= caution_z or on > on_caution or omo < 0:
        regime = 1
    else:
        regime = 0

    return {
        "fx_zscore": z,
        "fx_vol_20d": vol,
        "omo_net_20d": omo,
        "on_rate": on,
        "yield_curve_slope": slope,
        "regime": regime,
    }


def evaluate_macro_regime(
    metrics: Dict[str, Any],
    on_rate: float | None = None,
    omo_net_20d: float | None = None,
    caution_z: float = 1.0,
    alert_z: float = 1.5,
    on_caution: float = 5.0,
    on_alert: float = 6.0,
) -> tuple[int, str, Dict[str, Any]]:
    z = float(metrics["fx_zscore"]) if isinstance(metrics, dict) else float(metrics)
    on = float(metrics.get("on_rate", on_rate if on_rate is not None else 0.0))
    omo = float(metrics.get("omo_net_20d", omo_net_20d if omo_net_20d is not None else 0.0))

    if z >= alert_z or on > on_alert or (z >= caution_z and omo < 0):
        return 2, "ALERT/RISK-OFF", metrics
    if z >= caution_z or on > on_caution or omo < 0:
        return 1, "CAUTION", metrics
    return 0, "NORMAL", metrics


def run_monitor(data_path: str = "data/macro_indicators.parquet", **kwargs: Any) -> int:
    try:
        df = pd.read_parquet(Path(data_path))
        result = compute_macro_risk_metrics(
            df,
            **{
                k: v
                for k, v in kwargs.items()
                if k in {"as_of", "z_window", "vol_window", "caution_z", "alert_z", "on_caution", "on_alert"}
            },
        )
        code, name, metrics = evaluate_macro_regime(
            result,
            **{
                k: v
                for k, v in kwargs.items()
                if k in {"caution_z", "alert_z", "on_caution", "on_alert"}
            },
        )
        if kwargs.get("as_json"):
            print(json.dumps({"code": code, "regime": name, "metrics": metrics}, default=str))
        elif not kwargs.get("silent"):
            print(name)
        return code
    except Exception:
        return 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Macro Risk Alert Monitor CLI")
    parser.add_argument("--data-path", default="data/macro_indicators.parquet")
    parser.add_argument("--as-of", default=None, help="Explicit PIT cutoff timestamp (ISO format)")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--silent", action="store_true", help="Suppress output, exit code only")
    parser.add_argument("--caution-z", type=float, default=1.0)
    parser.add_argument("--alert-z", type=float, default=1.5)
    parser.add_argument("--on-caution", type=float, default=5.0)
    parser.add_argument("--on-alert", type=float, default=6.0)
    args = parser.parse_args()

    try:
        df = pd.read_parquet(Path(args.data_path))
        result = compute_macro_risk_metrics(
            df,
            as_of=args.as_of,
            caution_z=args.caution_z,
            alert_z=args.alert_z,
            on_caution=args.on_caution,
            on_alert=args.on_alert,
        )
        code, name, metrics = evaluate_macro_regime(
            result,
            caution_z=args.caution_z,
            alert_z=args.alert_z,
            on_caution=args.on_caution,
            on_alert=args.on_alert,
        )
    except Exception:
        sys.exit(3)

    if not args.silent:
        if args.json:
            print(json.dumps({"code": code, "regime": name, "metrics": metrics}, default=str))
        else:
            print(
                f"[{name}] Code: {code}, USD/VND Z: {metrics['fx_zscore']:.2f}, "
                f"ON: {metrics['on_rate']:.2f}%, OMO: {metrics['omo_net_20d']:.0f}"
            )

    sys.exit(code)


if __name__ == "__main__":
    main()
