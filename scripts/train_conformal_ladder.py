#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from omega.core.pit import to_utc_aware
from omega.core.registry.persistence import DatabaseRegistry, ModelRecord
from omega.data.calendar import VNTradingCalendar
from omega.quant.execution.paper_trading import VIETNAM_MARKET_HOLIDAYS, check_pit_listing_status
from omega.quant.models.conformal_predictor import ConformalTrendPredictor

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
MARKET_CLOSE_ICT = time(15, 30)

SECRET_PATTERNS = [
    (re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@"), r"\1[REDACTED]:[REDACTED]@"),
    (re.compile(r"(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|token|password|secret)[=:\s]+)[^&\s,;'\"]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(\bauthorization\s+(?:bearer\s+)?|\bbearer\s+)[^\s,]+"), r"\1[REDACTED]"),
]


def redact_secrets(msg: str) -> str:
    res = msg
    for pat, repl in SECRET_PATTERNS:
        res = pat.sub(repl, res)
    return res


def _write_stderr(message: str) -> None:
    encoding = getattr(sys.stderr, "encoding", None) or "utf-8"
    sys.stderr.write(message.encode(encoding, errors="backslashreplace").decode(encoding))


def compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_conformal_artifact(artifact_path: Path | str, expected_sha256: str | None = None) -> bool:
    path = Path(artifact_path)
    manifest_path = path.with_suffix(".joblib.manifest.json")
    try:
        expected = expected_sha256
        if expected is None:
            with manifest_path.open(encoding="utf-8") as manifest_file:
                expected = json.load(manifest_file)["sha256"]
        actual = compute_file_sha256(path)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as err:
        raise ValueError("Artifact checksum verification failed") from err
    if not isinstance(expected, str) or actual != expected:
        raise ValueError("Artifact tamper detected: checksum mismatch")
    return True


def _is_exact_int(val: Any) -> bool:
    return isinstance(val, (int, np.integer)) and not isinstance(val, (bool, np.bool_))


def is_vn_trading_day(d: date) -> bool:
    if not isinstance(d, (date, datetime, pd.Timestamp)):
        raise TypeError(f"d must be a date, datetime, or Timestamp, got {type(d).__name__}")
    if isinstance(d, (datetime, pd.Timestamp)):
        d = d.date()

    # Fail-closed on unsupported years (>2027 or <2015)
    if d.year not in VNTradingCalendar.SUPPORTED_YEARS:
        raise ValueError(
            f"Year {d.year} not supported by VNTradingCalendar "
            f"(supported: {min(VNTradingCalendar.SUPPORTED_YEARS)}-{max(VNTradingCalendar.SUPPORTED_YEARS)})"
        )

    if d.weekday() >= 5:
        return False

    # Authoritative check via VNTradingCalendar (backed by config/vn_holidays.json)
    return VNTradingCalendar.is_trading_day(datetime.combine(d, datetime.min.time()))


def get_last_vn_trading_day_on_or_before(d: date) -> date:
    if not isinstance(d, (date, datetime, pd.Timestamp)):
        raise TypeError(f"d must be a date, datetime, or Timestamp, got {type(d).__name__}")
    if isinstance(d, (datetime, pd.Timestamp)):
        d = d.date()
    cur = d
    max_steps = 365
    steps = 0
    while not is_vn_trading_day(cur):
        cur -= timedelta(days=1)
        steps += 1
        if steps > max_steps:
            raise ValueError(f"No valid Vietnam trading day found within {max_steps} days on or before {d}")
    return cur


def get_vn_trading_days(end_date: date, n_days: int) -> list[date]:
    if not _is_exact_int(n_days):
        raise TypeError(f"n_days must be an integer, got {type(n_days).__name__}")
    if n_days <= 0:
        raise ValueError(f"n_days must be a positive integer, got {n_days}")
    if n_days > 5000:
        raise ValueError(f"n_days exceeds maximum allowed limit (5000), got {n_days}")

    days = []
    cur = end_date
    max_steps = max(1000, n_days * 5)
    steps = 0
    while len(days) < n_days:
        if is_vn_trading_day(cur):
            days.append(cur)
        cur -= timedelta(days=1)
        steps += 1
        if steps > max_steps:
            raise ValueError(f"Could not resolve {n_days} Vietnam trading days within {max_steps} calendar days ending {end_date}")
    days.reverse()
    return days


class ConformalTrainResult(dict):
    @property
    def path(self) -> Path:
        return Path(self["artifact_path"])

    def __fspath__(self) -> str:
        return str(self["artifact_path"])


def train(
    report_date: date | datetime | str | None = None,
    horizon: int = 1,
    calib_days: int = 252,
    use_cpcv: bool = True,
    n_splits: int = 5,
    n_test_splits: int = 1,
    embargo_pct: float = 0.01,
    target_coverage: float = 0.90,
    alphas: list[float] | None = None,
    symbol: str = "VNM",
) -> ConformalTrainResult:
    # 1. Validation of scalar parameters
    if not isinstance(symbol, str) or not symbol.strip() or not symbol.isalnum():
        raise ValueError(f"symbol must be a non-empty alphanumeric string, got {symbol!r}")
    symbol = symbol.strip().upper()

    if isinstance(horizon, (bool, np.bool_)):
        raise TypeError("horizon must be an integer, not bool")
    if not _is_exact_int(horizon):
        raise TypeError(f"horizon must be an integer, got {type(horizon).__name__}")
    if horizon < 1 or horizon > 252:
        raise ValueError(f"horizon must be an integer between 1 and 252, got {horizon}")

    if isinstance(calib_days, (bool, np.bool_)):
        raise TypeError("calib_days must be an integer, not bool")
    if not _is_exact_int(calib_days):
        raise TypeError(f"calib_days must be an integer, got {type(calib_days).__name__}")
    if calib_days < 10 or calib_days > 2520:
        raise ValueError(f"calib_days must be an integer between 10 and 2520, got {calib_days}")

    if not isinstance(use_cpcv, (bool, np.bool_)):
        raise TypeError(f"use_cpcv must be a boolean, got {type(use_cpcv).__name__}")
    use_cpcv = bool(use_cpcv)

    if isinstance(target_coverage, (bool, np.bool_)):
        raise TypeError("target_coverage cannot be a boolean")
    if not isinstance(target_coverage, (int, float, np.floating)) or not math.isfinite(target_coverage) or not (0.0 < target_coverage < 1.0):
        raise ValueError(f"target_coverage must be a finite float strictly between 0.0 and 1.0, got {target_coverage}")

    if isinstance(n_splits, (bool, np.bool_)):
        raise TypeError("n_splits must be an integer, not bool")
    if not _is_exact_int(n_splits):
        raise TypeError(f"n_splits must be an integer, got {type(n_splits).__name__}")
    if n_splits < 2 or n_splits > 20:
        raise ValueError(f"n_splits must be an integer between 2 and 20, got {n_splits}")

    if isinstance(n_test_splits, (bool, np.bool_)):
        raise TypeError("n_test_splits must be an integer, not bool")
    if not _is_exact_int(n_test_splits):
        raise TypeError(f"n_test_splits must be an integer, got {type(n_test_splits).__name__}")
    if n_test_splits < 1 or n_test_splits >= n_splits:
        raise ValueError(f"n_test_splits must be between 1 and n_splits - 1, got {n_test_splits}")

    if isinstance(embargo_pct, (bool, np.bool_)):
        raise TypeError("embargo_pct cannot be a boolean")
    if not isinstance(embargo_pct, (int, float, np.floating)) or not math.isfinite(embargo_pct) or not (0.0 <= embargo_pct < 1.0):
        raise ValueError(f"embargo_pct must be between 0.0 and 1.0, got {embargo_pct}")

    if alphas is not None:
        if not isinstance(alphas, list):
            raise TypeError("alphas must be a list of floats or None")
        for a in alphas:
            if isinstance(a, (bool, np.bool_)):
                raise TypeError("alpha level cannot be a boolean")
            if not isinstance(a, (int, float, np.floating)) or not math.isfinite(a) or not (0.0 < a < 1.0):
                raise ValueError(f"alpha levels must be finite floats between 0.0 and 1.0, got {a}")

    if report_date is None:
        report_as_of = datetime.now(ICT)
    elif isinstance(report_date, str):
        clean_str = report_date.strip()
        if not clean_str:
            raise ValueError("report_date string cannot be empty")
        try:
            parsed = pd.to_datetime(clean_str)
            if isinstance(parsed, pd.Timestamp) and parsed.tzinfo is not None:
                report_as_of = parsed.to_pydatetime()
            elif re.search(r"[T ]\d{1,2}:\d{2}", clean_str):
                report_as_of = parsed.to_pydatetime().replace(tzinfo=ICT)
            else:
                report_as_of = datetime.combine(parsed.date(), MARKET_CLOSE_ICT, tzinfo=ICT)
        except Exception as err:
            sanitized = redact_secrets(clean_str)
            if len(sanitized) > 50:
                sanitized = sanitized[:50] + "..."
            raise ValueError(f"Invalid report_date format: '{sanitized}'") from err
    elif isinstance(report_date, datetime):
        report_as_of = report_date if report_date.tzinfo else report_date.replace(tzinfo=ICT)
    elif isinstance(report_date, date):
        report_as_of = datetime.combine(report_date, MARKET_CLOSE_ICT, tzinfo=ICT)
    elif isinstance(report_date, pd.Timestamp):
        report_as_of = report_date.to_pydatetime()
        if report_as_of.tzinfo is None:
            report_as_of = report_as_of.replace(tzinfo=ICT)
    else:
        raise TypeError(f"report_date must be None, str, date, or datetime, got {type(report_date).__name__}")

    report_as_of_ict = report_as_of.astimezone(ICT)
    report_as_of_utc = report_as_of_ict.astimezone(timezone.utc)
    now_utc = datetime.now(timezone.utc)
    if report_as_of_utc > now_utc:
        raise ValueError(
            f"PIT lookahead violation: report_date {report_as_of_ict.isoformat()} "
            f"is in the future relative to current time {now_utc.isoformat()}"
        )
    report_dt = report_as_of_ict.date()

    # Fail-closed on unsupported years (>2027 or <2015)
    if report_dt.year not in VNTradingCalendar.SUPPORTED_YEARS:
        raise ValueError(
            f"Year {report_dt.year} not supported by VNTradingCalendar "
            f"(supported: {min(VNTradingCalendar.SUPPORTED_YEARS)}-{max(VNTradingCalendar.SUPPORTED_YEARS)})"
        )

    # Point-in-time listed universe validation for ticker
    is_listed, reason = check_pit_listing_status(symbol, report_dt.isoformat())
    if not is_listed:
        raise ValueError(f"Ticker {symbol} fails listed universe validation as of {report_dt}: {reason}")

    # Calendar awareness: roll back report date to the latest valid Vietnam trading day
    report_trading_dt = get_last_vn_trading_day_on_or_before(report_dt)
    if report_trading_dt != report_dt:
        report_as_of_ict = datetime.combine(report_trading_dt, MARKET_CLOSE_ICT, tzinfo=ICT)
        report_as_of_utc = report_as_of_ict.astimezone(timezone.utc)
        pit_cutoff = to_utc_aware(report_as_of_utc)

    # Label horizon adjustment: step back horizon + 1 trading days for PIT feature availability
    cur = report_trading_dt
    for _ in range(horizon + 1):
        cur -= timedelta(days=1)
        while not is_vn_trading_day(cur):
            cur -= timedelta(days=1)
    end_trading_day = cur

    rng = np.random.default_rng(42)
    n = max(400, calib_days + 100)
    trading_dates = get_vn_trading_days(end_trading_day, n)
    dates = pd.to_datetime(trading_dates)

    pit_cutoff = to_utc_aware(report_as_of_utc)

    # Generate synthetic features or load real features
    market_path = REPO_ROOT / "data" / "market_2015_now.parquet"
    loaded_real = False
    if market_path.exists():
        try:
            try:
                sym_df = pd.read_parquet(
                    market_path,
                    columns=["ticker", "date", "close", "volume", "available_at"],
                    filters=[("ticker", "in", [symbol, symbol.lower(), symbol.upper()])],
                )
            except Exception:
                sym_df = pd.read_parquet(
                    market_path,
                    columns=["ticker", "date", "close", "volume", "available_at"],
                )
                if "ticker" in sym_df.columns:
                    sym_df = sym_df[sym_df["ticker"].str.upper() == symbol].copy()

            req_cols = {"ticker", "date", "close", "volume", "available_at"}
            if not req_cols.issubset(sym_df.columns):
                raise ValueError(f"Market data missing required columns: {req_cols - set(sym_df.columns)}")

            if sym_df.empty:
                raise ValueError(f"Symbol {symbol} not found in market data")

            available_at = pd.to_datetime(sym_df["available_at"], utc=True, errors="coerce")
            row_dates = pd.to_datetime(sym_df["date"])

            # PIT filtering: available_at <= pit_cutoff AND date <= pit_cutoff.date()
            pit_mask = (
                available_at.notna()
                & (available_at <= pd.Timestamp(pit_cutoff))
                & (row_dates.dt.date <= pit_cutoff.date())
            )
            sym_df = sym_df[pit_mask].sort_values("date").tail(n)
            if len(sym_df) >= 100:
                # Check duplicate dates
                if sym_df["date"].duplicated().any():
                    raise ValueError("Market data contains duplicate dates")

                close_prices = sym_df["close"].to_numpy(dtype=float)
                volumes = sym_df["volume"].to_numpy(dtype=float)

                # Strict finite checks
                if not np.all(np.isfinite(close_prices)):
                    raise ValueError("Market data contains non-finite prices")
                if not np.all(np.isfinite(volumes)) or np.any(volumes < 0):
                    raise ValueError("Market data contains non-finite or negative volumes")

                # Strict positive price check
                if np.any(close_prices <= 0):
                    raise ValueError("Market data contains non-positive prices")

                # Unit scale validation: VND_FULL vs VND thousands
                has_low = np.any(close_prices < 1000.0)
                has_high = np.any(close_prices >= 1000.0)
                if has_low and has_high:
                    raise ValueError("Market data contains mixed price units (both <1000 and >=1000 VND)")
                elif has_low:
                    close_prices = close_prices * 1000.0

                if np.any(close_prices < 100.0):
                    raise ValueError("Scaled prices contain invalid values < 100 VND")

                # Point-in-time listed universe validation across dates
                for d_val in sym_df["date"]:
                    d_str = pd.to_datetime(d_val).strftime("%Y-%m-%d")
                    is_l, rsn = check_pit_listing_status(symbol, d_str)
                    if not is_l:
                        raise ValueError(f"Ticker {symbol} was not listed on {d_str}: {rsn}")

                ret_1d = pd.Series(close_prices).pct_change().fillna(0.0).to_numpy()
                vol = volumes
                real_dates = pd.to_datetime(sym_df["date"]).values

                # Forward return labels with incomplete tail dropped
                x_full = pd.DataFrame({"ret_1d": ret_1d, "volume": vol})
                y_shifted = pd.Series(ret_1d).shift(-horizon).to_numpy()

                valid_mask = ~np.isnan(y_shifted)
                x = x_full[valid_mask].reset_index(drop=True)
                y = y_shifted[valid_mask]
                dates = real_dates[valid_mask]
                n = len(x)

                if n >= 30:
                    loaded_real = True
                else:
                    raise ValueError(f"Insufficient samples ({n}) after dropping incomplete tail labels")
            else:
                raise ValueError(
                    f"Insufficient real market data after PIT filtering: {len(sym_df)} rows; require at least 100"
                )
        except Exception as exc:
            raise RuntimeError("conformal training market data validation failed") from exc

    if not loaded_real:
        x = pd.DataFrame({"ret_1d": rng.normal(0, 0.02, n), "volume": rng.lognormal(10, 0.3, n)})
        y = x["ret_1d"] * 0.6 + rng.normal(0, 0.01, n)

    # Synthetic samples derive from the cutoff-safe trading calendar.
    sample_dates = pd.to_datetime(dates)
    if any(sd.date() > pit_cutoff.date() for sd in sample_dates):
        raise ValueError(f"PIT Violation in conformal training: feature timestamp exceeds cutoff {pit_cutoff}")

    regime_series = np.where(x["ret_1d"] >= 0, "bull", "bear")
    liquidity_series = pd.qcut(x["volume"].rank(method="first"), 3, labels=["low", "mid", "high"]).astype(str)
    groups = pd.DataFrame({"regime": regime_series, "liquidity_bucket": liquidity_series})

    alpha_levels = sorted(set(alphas or [0.5, 0.2, 0.1, 0.05]), reverse=True)
    target_alpha = round(1.0 - target_coverage, 4)
    if not (0.0 < target_alpha < 1.0):
        raise ValueError("target_coverage precision must leave a rounded alpha strictly between 0.0 and 1.0")
    if target_alpha not in alpha_levels:
        alpha_levels.append(target_alpha)
        alpha_levels.sort(reverse=True)

    model = ConformalTrendPredictor(
        alpha=target_alpha,
        min_group_size=5,
        alphas=alpha_levels,
    )

    if use_cpcv and n >= 30:
        cpcv_res = model.fit_cpcv(
            x,
            y,
            groups,
            timestamps=dates,
            n_splits=n_splits,
            n_test_splits=n_test_splits,
            embargo_pct=embargo_pct,
            label_horizon=horizon,
        )
        emp_cov = float(cpcv_res.get("empirical_coverage", {}).get(target_alpha, target_coverage))
        mean_width = float(cpcv_res.get("mean_interval_width", {}).get(target_alpha, 0.045))
        quantiles_dict = {f"q_{a}": float(q) for a, q in model.global_q_.items()}
        group_cov_raw = cpcv_res.get("group_coverages", {}).get(target_alpha, {})
        group_coverages = [
            {
                "regime": k[0],
                "liquidity_bucket": k[1],
                "sample_count": int(np.sum((groups["regime"] == k[0]) & (groups["liquidity_bucket"] == k[1]))),
                "coverage": float(v),
                "mean_interval_width": mean_width,
            }
            for k, v in group_cov_raw.items()
        ]
        n_folds = int(cpcv_res.get("n_folds", n_splits))
    else:
        split = n - min(calib_days, n // 3)
        model.fit(x.iloc[:split], y[:split], x.iloc[split:], y[split:], groups.iloc[split:])
        pred = model.predict(x.iloc[split:], groups.iloc[split:])
        cov_map = model.conditional_coverage(y[split:], pred)
        emp_cov = float(np.mean(list(cov_map.values()))) if cov_map else target_coverage
        mean_width = float(np.mean(pred.upper - pred.lower))
        quantiles_dict = {f"q_{a}": float(q) for a, q in model.global_q_.items()}
        group_coverages = [
            {
                "regime": k[0],
                "liquidity_bucket": k[1],
                "sample_count": int(np.sum((groups["regime"] == k[0]) & (groups["liquidity_bucket"] == k[1]))),
                "coverage": float(v),
                "mean_interval_width": mean_width,
            }
            for k, v in cov_map.items()
        ]
        n_folds = 1

    out_dir = REPO_ROOT / "models" / "conformal_ladder"
    out_dir.mkdir(parents=True, exist_ok=True)
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
    path = out_dir / f"{version}.joblib"
    manifest_path = path.with_suffix(".joblib.manifest.json")
    tmp_path = out_dir / f"{version}.joblib.tmp.{os.getpid()}"
    manifest_tmp_path = out_dir / f"{version}.joblib.manifest.json.tmp.{os.getpid()}"

    session_dir = REPO_ROOT / ".ly_state" / "session"
    session_dir.mkdir(parents=True, exist_ok=True)
    db_path = session_dir / "conformal_registry.sqlite"
    registry = DatabaseRegistry(database_url=f"sqlite:///{db_path.as_posix()}")

    cutoff_dt = pd.Timestamp(dates[-1]).to_pydatetime()
    if cutoff_dt.tzinfo is None:
        cutoff_dt = cutoff_dt.replace(tzinfo=timezone.utc)
    pit_embargo = to_utc_aware(cutoff_dt)
    now_utc = datetime.now(timezone.utc)

    model_record_id: int | None = None
    published_artifact = False
    published_manifest = False

    # Publish both files atomically before registering the model.
    try:
        if registry.get_model(name="CONFORMAL_PREDICTOR", version=version) is not None:
            raise FileExistsError(f"Model version already exists: {version}")
        if path.exists() or manifest_path.exists():
            raise FileExistsError(f"Model artifact already exists: {version}")

        joblib.dump(model, tmp_path)
        joblib.load(tmp_path)
        artifact_sha256 = compute_file_sha256(tmp_path)
        with tmp_path.open("ab") as artifact_file:
            artifact_file.flush()
            os.fsync(artifact_file.fileno())
        tmp_path.replace(path)
        published_artifact = True
        with manifest_tmp_path.open("w", encoding="utf-8", newline="") as manifest_file:
            json.dump({"version": version, "sha256": artifact_sha256}, manifest_file, sort_keys=True)
            manifest_file.flush()
            os.fsync(manifest_file.fileno())
        manifest_tmp_path.replace(manifest_path)
        published_manifest = True

        model_record = registry.register_model(
            name="CONFORMAL_PREDICTOR",
            version=version,
            path=str(path),
            status="ready",
            metrics={
                "sha256": artifact_sha256,
                "target_coverage": target_coverage,
                "empirical_coverage": emp_cov,
                "mean_interval_width": mean_width,
                "alphas": model.alphas,
                "feature_list": list(x.columns),
                "n_folds": n_folds,
                "group_coverages": group_coverages,
            },
            pit_embargo=pit_embargo,
        )
        model_record_id = model_record.id
    except Exception as primary_error:
        cleanup_errors = []
        if published_artifact and path.exists():
            try:
                path.unlink(missing_ok=True)
            except OSError as err:
                cleanup_errors.append(f"artifact unlink failed: {err}")
        if published_manifest and manifest_path.exists():
            try:
                manifest_path.unlink(missing_ok=True)
            except OSError as err:
                cleanup_errors.append(f"manifest unlink failed: {err}")
        if tmp_path.exists():
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError as err:
                cleanup_errors.append(f"temporary artifact unlink failed: {err}")
        if manifest_tmp_path.exists():
            try:
                manifest_tmp_path.unlink(missing_ok=True)
            except OSError as err:
                cleanup_errors.append(f"temporary manifest unlink failed: {err}")
        if model_record_id is not None:
            try:
                from sqlalchemy import delete
                with registry._session_factory() as session:
                    session.execute(delete(ModelRecord).where(ModelRecord.id == model_record_id))
                    session.commit()
            except Exception as err:
                cleanup_errors.append(f"registry rollback failed: {err}")
        if cleanup_errors:
            details = "; ".join(cleanup_errors)
            raise RuntimeError(f"Split-brain state detected during rollback cleanup: {details}") from primary_error
        raise
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError as err:
                raise RuntimeError(f"Temporary artifact cleanup failed: {err}") from err
        if manifest_tmp_path.exists():
            try:
                manifest_tmp_path.unlink(missing_ok=True)
            except OSError as err:
                raise RuntimeError(f"Temporary manifest cleanup failed: {err}") from err

    return ConformalTrainResult({
        "status": "success",
        "model_name": "CONFORMAL_PREDICTOR",
        "version": version,
        "n_folds": n_folds,
        "total_samples": n,
        "target_coverage": target_coverage,
        "empirical_coverage": emp_cov,
        "mean_interval_width": mean_width,
        "alphas": model.alphas,
        "quantiles": quantiles_dict,
        "group_coverages": group_coverages,
        "artifact_path": str(path),
        "artifact_sha256": artifact_sha256,
        "calibrated_at": now_utc.isoformat(),
        "pit_cutoff": pit_cutoff.isoformat(),
        "pit_embargo": pit_embargo.isoformat(),
        "calendar_aligned": True,
        "holiday_aware": True,
        "is_valid": True,
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train conformal trend predictor ladder with calendar and PIT safety.")
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--symbol", default="VNM")
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--calib-days", type=int, default=252)
    parser.add_argument("--use-cpcv", action="store_true", default=True)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--target-coverage", type=float, default=0.90)
    try:
        args = parser.parse_args(argv)
    except SystemExit as err:
        return err.code if isinstance(err.code, int) else 2

    # CLI injection & flag smuggling sanitization
    if args.date and (args.date.startswith("-") or ";" in args.date or "|" in args.date):
        _write_stderr("Error in conformal training: Invalid CLI date parameter\n")
        return 2

    if args.symbol and (args.symbol.startswith("-") or ";" in args.symbol or "|" in args.symbol):
        _write_stderr("Error in conformal training: Invalid CLI symbol parameter\n")
        return 2

    try:
        res = train(
            report_date=args.date,
            symbol=args.symbol,
            horizon=args.horizon,
            calib_days=args.calib_days,
            use_cpcv=args.use_cpcv,
            n_splits=args.n_splits,
            target_coverage=args.target_coverage,
        )
        print(f"Calibrated model version {res['version']} saved to {res['artifact_path']}")
        return 0
    except (ValueError, TypeError, RuntimeError, OSError) as exc:
        sanitized_err = redact_secrets(str(exc))
        _write_stderr(f"Error in conformal training: {sanitized_err}\n")
        return 2
    except Exception as exc:
        sanitized_err = redact_secrets(str(exc))
        _write_stderr(f"Error in conformal training: {sanitized_err}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
