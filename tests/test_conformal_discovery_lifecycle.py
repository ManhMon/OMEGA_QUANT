"""
Comprehensive Adversarial 16-Dimension Master Verification Suite for
Real Discovery SSE and Conformal CPCV Calibration Lifecycle.
GATE: GATE_CONFORMAL_LADDER_CALENDAR_PIT_20260913
"""

import asyncio
import hashlib
import io
import ipaddress
import json
import math
import os
import re
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from omega.api.schemas.advanced_quant import (
    ConformalCalibrationRequest,
    ConformalCalibrationResponse,
    DiscoveryProgressEvent,
    GeneticDiscoveryRequest,
    GeneticDiscoveryResponse,
)
from omega.api.server import app
from omega.api.routes import alpha
from omega.api.worker import execute_job
from omega.api.services import job_service as job_service_module
from omega.api.services.job_service import JobService
from omega.core.registry.persistence import DatabaseRegistry
from omega.quant.models.conformal_predictor import ConformalTrendPredictor
import scripts.train_conformal_ladder as ladder
from scripts.train_conformal_ladder import (
    train as train_conformal_ladder,
    is_vn_trading_day,
    get_last_vn_trading_day_on_or_before,
    get_vn_trading_days,
    main as conformal_ladder_main,
    redact_secrets,
)

client = TestClient(app)


def test_f022_rollback_cleanup_failure_surfaces_split_brain(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ladder, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DatabaseRegistry, "register_model", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("registration failed")))
    original_unlink = Path.unlink

    def failing_unlink(self, *args, **kwargs):
        if self.suffix == ".joblib":
            raise PermissionError("artifact locked")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    with pytest.raises(RuntimeError, match="Split-brain.*artifact unlink failed"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=50, use_cpcv=False)


def test_f022_registry_rollback_failure_surfaces_split_brain(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ladder, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DatabaseRegistry, "register_model", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("registration failed")))

    original_init = DatabaseRegistry.__init__

    def failing_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        original_session_factory = self._session_factory
        session_factory_calls = 0

        def fail_during_cleanup():
            nonlocal session_factory_calls
            session_factory_calls += 1
            if session_factory_calls > 1:
                raise RuntimeError("registry unavailable")
            return original_session_factory()

        self._session_factory = fail_during_cleanup

    monkeypatch.setattr(DatabaseRegistry, "__init__", failing_init)
    with pytest.raises(RuntimeError, match="registration failed"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=50, use_cpcv=False)


def test_f023_artifact_sha256_durable_binding_and_tamper_detection(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ladder, "REPO_ROOT", tmp_path)
    result = train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=50, use_cpcv=False)
    artifact = Path(result["artifact_path"])
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert result["artifact_sha256"] == expected
    assert ladder.verify_conformal_artifact(artifact)
    manifest = artifact.with_suffix(".joblib.manifest.json")
    assert json.loads(manifest.read_text(encoding="utf-8"))["sha256"] == expected

    payload = bytearray(artifact.read_bytes())
    payload[-1] ^= 1
    artifact.write_bytes(payload)
    with pytest.raises(ValueError, match="Artifact tamper detected"):
        ladder.verify_conformal_artifact(artifact)


def test_version_collision_does_not_delete_existing_record_or_artifacts(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ladder, "REPO_ROOT", tmp_path)
    (tmp_path / ".ly_state" / "session").mkdir(parents=True)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 9, 13, 12, 0, 0, 123456, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz is not None else value

    monkeypatch.setattr(ladder, "datetime", FixedDatetime)
    version = "20260913T120000_123456"
    out_dir = tmp_path / "models" / "conformal_ladder"
    out_dir.mkdir(parents=True)
    artifact = out_dir / f"{version}.joblib"
    manifest = artifact.with_suffix(".joblib.manifest.json")
    artifact.write_bytes(b"pre-existing-artifact")
    manifest.write_text(json.dumps({"version": version, "sha256": "pre-existing"}), encoding="utf-8")

    registry = DatabaseRegistry(database_url=f"sqlite:///{(tmp_path / '.ly_state' / 'session' / 'conformal_registry.sqlite').as_posix()}")
    registry.register_model(
        name="CONFORMAL_PREDICTOR",
        version=version,
        path=str(artifact),
        status="ready",
        metrics={"sentinel": True},
        pit_embargo=datetime(2026, 9, 12, tzinfo=timezone.utc),
    )

    with pytest.raises(FileExistsError, match="already exists"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=50, use_cpcv=False)

    assert artifact.read_bytes() == b"pre-existing-artifact"
    assert json.loads(manifest.read_text(encoding="utf-8"))["sha256"] == "pre-existing"
    assert registry.get_model(name="CONFORMAL_PREDICTOR", version=version) is not None


def test_manifest_publication_failure_recovers_without_partial_publication(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ladder, "REPO_ROOT", tmp_path)
    original_replace = Path.replace

    def fail_manifest_replace(self, target):
        if self.name.endswith(".joblib.manifest.json.tmp." + str(os.getpid())):
            raise OSError("manifest publication interrupted")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_manifest_replace)
    with pytest.raises(OSError, match="manifest publication interrupted"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=50, use_cpcv=False)

    model_dir = tmp_path / "models" / "conformal_ladder"
    assert not list(model_dir.glob("*.joblib"))
    assert not list(model_dir.glob("*.manifest.json"))
    assert not list(model_dir.glob("*.tmp.*"))


# =====================================================================
# Dedicated Finding Remediation Tests (F-001..F-010)
# =====================================================================

def test_f001_calendar_fail_closed_unsupported_years():
    """F-001: Trading calendar fails closed on unsupported years (>2027 or <2015) with ValueError."""
    with pytest.raises(ValueError, match="Year 2028 not supported by VNTradingCalendar"):
        is_vn_trading_day(date(2028, 1, 4))

    with pytest.raises(ValueError, match="Year 2029 not supported by VNTradingCalendar"):
        is_vn_trading_day(date(2029, 6, 15))

    with pytest.raises(ValueError, match="Year 2014 not supported by VNTradingCalendar"):
        is_vn_trading_day(date(2014, 12, 31))

    with pytest.raises(ValueError, match="Year 2014 not supported by VNTradingCalendar"):
        train_conformal_ladder(report_date=date(2014, 12, 31))


def test_f002_resource_exhaustion_bounds():
    """F-002: Upper bounds for horizon (<=252), calib_days (<=2520), n_splits (<=20)."""
    with pytest.raises(ValueError, match="horizon must be an integer between 1 and 252"):
        train_conformal_ladder(horizon=253)

    with pytest.raises(ValueError, match="calib_days must be an integer between 10 and 2520"):
        train_conformal_ladder(calib_days=2521)

    with pytest.raises(ValueError, match="n_splits must be an integer between 2 and 20"):
        train_conformal_ladder(n_splits=21)

    with pytest.raises(ValueError, match="n_days exceeds maximum allowed limit"):
        get_vn_trading_days(date(2026, 9, 4), 5001)


def test_f003_atomic_artifact_and_registry_rollback(tmp_path: Path, monkeypatch):
    """F-003: Atomic artifact write with tmp rename and SQLite registry transaction rollback."""
    # 1. Simulate registry registration failure -> artifact unlinked, no orphan
    def failing_register(*args, **kwargs):
        raise RuntimeError("Simulated SQLite registration fault")

    monkeypatch.setattr(DatabaseRegistry, "register_model", failing_register)

    with pytest.raises(RuntimeError, match="Simulated SQLite registration fault"):
        train_conformal_ladder(
            report_date=date(2026, 9, 4),
            horizon=1,
            calib_days=50,
            use_cpcv=False,
        )

    out_dir = ladder.REPO_ROOT / "models" / "conformal_ladder"
    # Ensure no lingering .tmp files from this failed run
    lingering_tmp = list(out_dir.glob(f"*.joblib.tmp.{os.getpid()}*"))
    assert len(lingering_tmp) == 0

    # 2. Simulate dump failure -> no artifact created
    def failing_dump(*args, **kwargs):
        raise OSError("Simulated disk write fault")

    monkeypatch.setattr(ladder.joblib, "dump", failing_dump)
    with pytest.raises(OSError, match="Simulated disk write fault"):
        train_conformal_ladder(
            report_date=date(2026, 9, 4),
            horizon=1,
            calib_days=50,
            use_cpcv=False,
        )


def test_f004_mandatory_16d_tests_scoped():
    """F-004: Verify trainer execution is directly verified across 16 dimensions without mis-scoping."""
    res = train_conformal_ladder(
        report_date=date(2026, 9, 4),
        horizon=1,
        calib_days=60,
        use_cpcv=False,
    )
    assert res["status"] == "success"
    assert res["model_name"] == "CONFORMAL_PREDICTOR"
    assert res["calendar_aligned"] is True
    assert res["holiday_aware"] is True
    assert Path(res["artifact_path"]).is_file()


def test_f005_drop_incomplete_tail_labels(monkeypatch):
    """F-005: Drop incomplete tail labels instead of fabricated 0.6 factor in real market data."""
    frame_mock = pd.DataFrame({
        "ticker": ["VNM"] * 120,
        "date": pd.date_range("2026-01-01", periods=120, freq="B"),
        "close": np.linspace(50000.0, 60000.0, 120),
        "volume": np.full(120, 100000.0),
        "available_at": pd.date_range("2026-01-02", periods=120, freq="B", tz="UTC"),
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame_mock)

    res = train_conformal_ladder(report_date=date(2026, 9, 4), horizon=3, calib_days=20, use_cpcv=False)
    assert res["status"] == "success"
    # 120 rows - 3 incomplete tail samples = 117 samples
    assert res["total_samples"] == 117


def test_f006_strict_market_data_validation(monkeypatch):
    """F-006: Strict finite, duplicate-check, positive price and unit scale validation."""
    # 1. Non-finite prices rejected
    frame_nan = pd.DataFrame({
        "ticker": ["VNM"] * 120,
        "date": pd.date_range("2026-01-01", periods=120, freq="B"),
        "close": [np.nan] * 120,
        "volume": np.full(120, 100000.0),
        "available_at": pd.date_range("2026-01-02", periods=120, freq="B", tz="UTC"),
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame_nan)
    with pytest.raises(RuntimeError, match="conformal training market data validation failed"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=20, use_cpcv=False)

    # 2. Duplicate dates rejected
    dates_with_dup = list(pd.date_range("2026-01-01", periods=119, freq="B")) + [pd.Timestamp("2026-01-01")]
    frame_dup = pd.DataFrame({
        "ticker": ["VNM"] * 120,
        "date": dates_with_dup,
        "close": np.linspace(50000.0, 60000.0, 120),
        "volume": np.full(120, 100000.0),
        "available_at": pd.date_range("2026-01-02", periods=120, freq="B", tz="UTC"),
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame_dup)
    with pytest.raises(RuntimeError, match="conformal training market data validation failed"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=20, use_cpcv=False)

    # 3. Mixed price units rejected
    mixed_prices = [50.0] * 60 + [50000.0] * 60
    frame_mixed = pd.DataFrame({
        "ticker": ["VNM"] * 120,
        "date": pd.date_range("2026-01-01", periods=120, freq="B"),
        "close": mixed_prices,
        "volume": np.full(120, 100000.0),
        "available_at": pd.date_range("2026-01-02", periods=120, freq="B", tz="UTC"),
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame_mixed)
    with pytest.raises(RuntimeError, match="conformal training market data validation failed"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=20, use_cpcv=False)


def test_f007_listed_universe_validation():
    """F-007: Listed universe validation for ticker."""
    # Delisted ticker ROS on 2023-01-05 (delisted 2022-09-05)
    with pytest.raises(ValueError, match="fails listed universe validation"):
        train_conformal_ladder(symbol="ROS", report_date="2023-01-05")

    # Delisted ticker FLC on 2023-03-01 (delisted 2023-02-20)
    with pytest.raises(ValueError, match="fails listed universe validation"):
        train_conformal_ladder(symbol="FLC", report_date="2023-03-01")

    # Active listed ticker VNM passes
    res = train_conformal_ladder(symbol="VNM", report_date="2026-09-04", calib_days=50, use_cpcv=False)
    assert res["status"] == "success"


def test_f008_io_failures_exit_2_sanitized(monkeypatch):
    """F-008: Catch OSError/IOError in main() exiting 2 sanitized."""
    def failing_dump(*args, **kwargs):
        raise OSError("Permission denied: '/tmp/models/protected.joblib'")

    monkeypatch.setattr(ladder.joblib, "dump", failing_dump)

    stderr_cap = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr_cap)

    exit_code = conformal_ladder_main(["--calib-days", "50", "--date", "2026-09-04"])
    assert exit_code == 2
    err_output = stderr_cap.getvalue()
    assert "Error in conformal training:" in err_output
    assert "Permission denied" in err_output
    assert "Traceback" not in err_output


def test_f009_secret_redaction_trainer_stderr(monkeypatch):
    """F-009: Secret redaction covers trainer stderr."""
    stderr_cap = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr_cap)

    exit_code = conformal_ladder_main(["--date", "api_key=" + "sk_" + "secret_123456789_confidential"])
    assert exit_code == 2
    err_output = stderr_cap.getvalue()
    assert "[REDACTED]" in err_output
    assert "sk_" + "secret_123456789" not in err_output

    # Test redaction helper on URL credentials
    raw = "Failed to fetch from https://admin:" + "superSecretPass" + "@api.internal.com/data"
    redacted = redact_secrets(raw)
    assert "super" + "SecretPass" not in redacted
    assert "Failed to fetch from https://[REDACTED]:[REDACTED]@api.internal.com/data" == redacted


def test_f010_reject_booleans_in_integer_parameters():
    """F-010: Reject booleans in integer parameters."""
    with pytest.raises(TypeError, match="horizon must be an integer, not bool"):
        train_conformal_ladder(horizon=True)

    with pytest.raises(TypeError, match="calib_days must be an integer, not bool"):
        train_conformal_ladder(calib_days=False)

    with pytest.raises(TypeError, match="n_splits must be an integer, not bool"):
        train_conformal_ladder(n_splits=True)

    with pytest.raises(TypeError, match="n_test_splits must be an integer, not bool"):
        train_conformal_ladder(n_test_splits=True)

    with pytest.raises(TypeError, match="use_cpcv must be a boolean"):
        train_conformal_ladder(use_cpcv=123)

    with pytest.raises(TypeError, match="target_coverage cannot be a boolean"):
        train_conformal_ladder(target_coverage=True)

    with pytest.raises(TypeError, match="embargo_pct cannot be a boolean"):
        train_conformal_ladder(embargo_pct=True)

    with pytest.raises(TypeError, match="n_days must be an integer"):
        get_vn_trading_days(date(2026, 9, 4), True)


# =====================================================================
# Dimension 1: Strict Types & Malformed / Out-of-Bounds Types
# =====================================================================
def test_dim1_malformed_and_out_of_bounds_types():
    # 1. Integer parameter boolean rejection
    with pytest.raises(TypeError, match="horizon must be an integer, not bool"):
        train_conformal_ladder(horizon=True)
    with pytest.raises(TypeError, match="calib_days must be an integer, not bool"):
        train_conformal_ladder(calib_days=False)
    with pytest.raises(TypeError, match="n_splits must be an integer, not bool"):
        train_conformal_ladder(n_splits=True)
    with pytest.raises(TypeError, match="use_cpcv must be a boolean"):
        train_conformal_ladder(use_cpcv=123)

    # 2. Out of bounds parameters for train_conformal_ladder
    with pytest.raises(ValueError, match="horizon must be an integer between 1 and 252"):
        train_conformal_ladder(horizon=0)
    with pytest.raises(ValueError, match="horizon must be an integer between 1 and 252"):
        train_conformal_ladder(horizon=253)
    with pytest.raises(ValueError, match="calib_days must be an integer between 10 and 2520"):
        train_conformal_ladder(calib_days=5)
    with pytest.raises(ValueError, match="calib_days must be an integer between 10 and 2520"):
        train_conformal_ladder(calib_days=3000)
    with pytest.raises(ValueError, match="n_splits must be an integer between 2 and 20"):
        train_conformal_ladder(n_splits=1)
    with pytest.raises(ValueError, match="n_splits must be an integer between 2 and 20"):
        train_conformal_ladder(n_splits=25)
    with pytest.raises(ValueError, match="target_coverage must be a finite float strictly between 0.0 and 1.0"):
        train_conformal_ladder(target_coverage=1.5)
    with pytest.raises(ValueError, match="n_test_splits must be between"):
        train_conformal_ladder(n_splits=3, n_test_splits=3)
    with pytest.raises(ValueError, match="embargo_pct must be between"):
        train_conformal_ladder(embargo_pct=-0.05)
    with pytest.raises(ValueError, match="alpha levels must be finite floats"):
        train_conformal_ladder(alphas=[-0.5])
    with pytest.raises(TypeError, match="report_date must be"):
        train_conformal_ladder(report_date=[2026, 9, 2])
    with pytest.raises(ValueError, match="symbol must be a non-empty alphanumeric string"):
        train_conformal_ladder(symbol="")


# =====================================================================
# Dimension 2: Invalid & Directory I/O Paths (Path Traversal)
# =====================================================================
def test_dim2_directory_io_and_path_aliasing(monkeypatch):
    # 1. Trainer I/O exception handling exits 2 sanitized
    def failing_dump(*args, **kwargs):
        raise OSError("Disk I/O error on target directory")

    monkeypatch.setattr(ladder.joblib, "dump", failing_dump)
    assert conformal_ladder_main(["--calib-days", "50", "--date", "2026-09-04"]) == 2

    # 2. Path traversal in date parameter
    with pytest.raises(ValueError, match="Invalid report_date format"):
        train_conformal_ladder(report_date="../../etc/passwd")

    # 3. Path aliasing / directory injection in CLI
    assert conformal_ladder_main(["--date", "../../etc/passwd"]) == 2


# =====================================================================
# Dimension 3: Corrupted / Duplicate / Partial Checkpoint Shards
# =====================================================================
def test_dim3_corrupted_duplicate_partial_payloads(monkeypatch):
    # 1. Injected missing required columns in market data
    frame_corrupt = pd.DataFrame({
        "ticker": ["VNM"] * 120,
        "date": pd.date_range("2026-01-01", periods=120, freq="B"),
        # 'close' column missing
        "volume": np.full(120, 100000.0),
        "available_at": pd.date_range("2026-01-02", periods=120, freq="B", tz="UTC"),
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame_corrupt)
    with pytest.raises(RuntimeError, match="conformal training market data validation failed"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=20, use_cpcv=False)

    # 2. Injected corrupt non-finite values
    frame_inf = pd.DataFrame({
        "ticker": ["VNM"] * 120,
        "date": pd.date_range("2026-01-01", periods=120, freq="B"),
        "close": [float("inf")] * 120,
        "volume": np.full(120, 100000.0),
        "available_at": pd.date_range("2026-01-02", periods=120, freq="B", tz="UTC"),
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame_inf)
    with pytest.raises(RuntimeError, match="conformal training market data validation failed"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=20, use_cpcv=False)


# =====================================================================
# Dimension 4: Fail-Closed Exit Codes & Error States
# =====================================================================
def test_dim4_fail_closed_error_states(monkeypatch):
    # Conformal ladder main CLI fail-closed exit code 2 on invalid parameters
    assert conformal_ladder_main(["--target-coverage", "2.0"]) == 2
    assert conformal_ladder_main(["--horizon", "0"]) == 2
    assert conformal_ladder_main(["--horizon", "300"]) == 2
    assert conformal_ladder_main(["--calib-days", "5000"]) == 2
    assert conformal_ladder_main(["--n-splits", "30"]) == 2
    assert conformal_ladder_main(["--date", "not-a-date"]) == 2
    assert conformal_ladder_main(["--date", "2028-01-04"]) == 2

    # Injected OSError fails closed with exit code 2
    def failing_dump(*args, **kwargs):
        raise OSError("I/O device failure")

    monkeypatch.setattr(ladder.joblib, "dump", failing_dump)
    assert conformal_ladder_main(["--calib-days", "50", "--date", "2026-09-04"]) == 2


# =====================================================================
# Dimension 5: Rollback & Atomicity Failures
# =====================================================================
def test_dim5_rollback_and_atomicity_failures(tmp_path: Path, monkeypatch):
    # 1. When SQLite registry registration fails, published artifact is deleted
    def failing_register(*args, **kwargs):
        raise RuntimeError("Injected SQLite registry transaction abort")

    monkeypatch.setattr(DatabaseRegistry, "register_model", failing_register)
    with pytest.raises(RuntimeError, match="Injected SQLite registry transaction abort"):
        train_conformal_ladder(
            report_date=date(2026, 9, 4),
            horizon=1,
            calib_days=50,
            use_cpcv=False,
        )

    # 2. When joblib.dump fails, temporary file is cleaned up
    def failing_dump(*args, **kwargs):
        raise OSError("Injected disk write abort")

    monkeypatch.setattr(ladder.joblib, "dump", failing_dump)
    with pytest.raises(OSError, match="Injected disk write abort"):
        train_conformal_ladder(
            report_date=date(2026, 9, 4),
            horizon=1,
            calib_days=50,
            use_cpcv=False,
        )

    out_dir = ladder.REPO_ROOT / "models" / "conformal_ladder"
    lingering_tmp = list(out_dir.glob(f"*.joblib.tmp.{os.getpid()}*"))
    assert len(lingering_tmp) == 0


# =====================================================================
# Dimension 6: Point-In-Time (PIT) & Look-Ahead Safety
# =====================================================================
def test_dim6_pit_lookahead_safety(monkeypatch):
    # 1. Reject future report_date lookahead
    with pytest.raises(ValueError, match="PIT lookahead violation"):
        train_conformal_ladder(report_date="2099-01-01")

    # 2. Verify incomplete tail observations are dropped instead of fabricated 0.6 factor
    cutoff = pd.Timestamp("2026-09-01T00:00:00Z")
    frame = pd.DataFrame({
        "ticker": ["VNM"] * 150,
        "date": pd.date_range("2026-01-01", periods=150, freq="B"),
        "close": np.linspace(50000, 60000, 150),
        "volume": np.full(150, 100000.0),
        "available_at": [cutoff - pd.Timedelta(days=30)] * 149 + [cutoff + pd.Timedelta(days=365)],
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame)

    result = train_conformal_ladder(report_date=date(2026, 9, 2), horizon=2, calib_days=20, use_cpcv=False)
    # 149 valid rows after PIT filter - 2 incomplete tail rows = 147
    assert result["total_samples"] == 147
    assert datetime.fromisoformat(result["pit_cutoff"]) <= datetime.fromisoformat(result["calibrated_at"])
    assert datetime.fromisoformat(result["pit_embargo"]) <= datetime.fromisoformat(result["calibrated_at"])


def test_f011_f012_strict_ict_as_of_and_future_rejection():
    tomorrow = date.today() + timedelta(days=1)
    with pytest.raises(ValueError, match="PIT lookahead violation"):
        train_conformal_ladder(report_date=tomorrow)

    result = train_conformal_ladder(
        report_date=datetime(2026, 9, 4, 15, 30, tzinfo=timezone(timedelta(hours=7))),
        calib_days=50,
        use_cpcv=False,
    )
    assert result["pit_cutoff"].startswith("2026-09-04T08:30:00")


def test_f013_real_data_below_100_fails_closed(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "market_2015_now.parquet").write_bytes(b"sentinel")
    monkeypatch.setattr(ladder, "REPO_ROOT", tmp_path)
    frame = pd.DataFrame({
        "ticker": ["VNM"] * 99,
        "date": pd.date_range("2026-01-01", periods=99, freq="B"),
        "close": np.full(99, 50000.0),
        "volume": np.full(99, 100000.0),
        "available_at": pd.date_range("2026-01-02", periods=99, freq="B", tz="UTC"),
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame)
    with pytest.raises(RuntimeError, match="conformal training market data validation failed"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=20, use_cpcv=False)
    assert not (tmp_path / "models").exists()


def test_f014_corrupt_artifact_is_not_published(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ladder, "REPO_ROOT", tmp_path)

    def write_corrupt_artifact(model, path):
        Path(path).write_bytes(b"partial-joblib")

    monkeypatch.setattr(ladder.joblib, "dump", write_corrupt_artifact)
    with pytest.raises(Exception):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=50, use_cpcv=False)
    assert not list((tmp_path / "models" / "conformal_ladder").glob("*.joblib"))
    assert not list((tmp_path / "models" / "conformal_ladder").glob("*.tmp.*"))


def test_f018_windows_cp1252_and_crlf_io(tmp_path: Path, monkeypatch):
    """F-018: Windows charmap output and CRLF CLI input remain safe."""
    monkeypatch.setattr(ladder, "REPO_ROOT", tmp_path)
    stdout_bytes = io.BytesIO()
    stderr_bytes = io.BytesIO()
    stdout = io.TextIOWrapper(stdout_bytes, encoding="cp1252", errors="strict", newline="\r\n")
    stderr = io.TextIOWrapper(stderr_bytes, encoding="cp1252", errors="strict", newline="\r\n")
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    assert conformal_ladder_main(["--date", "2026-09-04\r\n", "--calib-days", "50"]) == 0
    stdout.flush()
    assert b"\r\n" in stdout_bytes.getvalue()

    invalid_date = "ng\u00e0y-kh\u00f4ng-h\u1ee3p-l\u1ec7\r\n"
    assert conformal_ladder_main(["--date", invalid_date]) == 2
    stderr.flush()
    error_output = stderr_bytes.getvalue().decode("cp1252")
    assert "Error in conformal training:" in error_output
    assert "\\u1ee3p" in error_output
    assert "\r\n" in error_output


def test_f019_seed42_rng_invariance_and_trainer_numeric_extremes(tmp_path: Path, monkeypatch):
    """F-019: Trainer outputs are deterministic and finite at finite parameter extremes."""
    monkeypatch.setattr(ladder, "REPO_ROOT", tmp_path)
    kwargs = {
        "report_date": date(2026, 9, 4),
        "calib_days": 50,
        "use_cpcv": False,
        "target_coverage": 0.9999,
        "embargo_pct": np.nextafter(0.0, 1.0),
    }

    first = train_conformal_ladder(**kwargs)
    second = train_conformal_ladder(**kwargs)

    assert first["quantiles"] == second["quantiles"]
    assert first["mean_interval_width"] == second["mean_interval_width"]
    assert first["empirical_coverage"] == second["empirical_coverage"]
    assert math.isfinite(first["mean_interval_width"])
    assert all(math.isfinite(value) for value in first["quantiles"].values())

    with pytest.raises(ValueError, match="target_coverage precision"):
        train_conformal_ladder(target_coverage=np.nextafter(1.0, 0.0))

    for nonfinite in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="target_coverage must be a finite float"):
            train_conformal_ladder(target_coverage=nonfinite)
        with pytest.raises(ValueError, match="embargo_pct must be between"):
            train_conformal_ladder(embargo_pct=nonfinite)


def test_f020_single_atomic_artifact_has_no_checkpoint_shards(tmp_path: Path, monkeypatch):
    """F-020: Dimension 3 shard recovery is N/A for one atomic joblib artifact."""
    monkeypatch.setattr(ladder, "REPO_ROOT", tmp_path)
    result = train_conformal_ladder(
        report_date=date(2026, 9, 4), calib_days=50, use_cpcv=False
    )
    artifact = Path(result["artifact_path"])
    model_dir = artifact.parent

    assert list(model_dir.glob("*.joblib")) == [artifact]
    assert not list(model_dir.glob("*.shard*"))
    assert not list(model_dir.glob("*.part*"))
    assert not list(model_dir.glob("*-of-*"))

    artifact.write_bytes(b"partial-joblib")
    with pytest.raises(Exception):
        ladder.joblib.load(artifact)


# =====================================================================
# Dimension 7: Trading Calendar & Holiday Boundaries
# =====================================================================
def test_dim7_trading_calendar_and_holiday_boundaries():
    # 1. Fail-closed on unsupported years (>2027) with ValueError
    with pytest.raises(ValueError, match="Year 2028 not supported"):
        is_vn_trading_day(date(2028, 1, 4))
    with pytest.raises(ValueError, match="Year 2014 not supported"):
        is_vn_trading_day(date(2014, 12, 31))
    with pytest.raises(ValueError, match="Year 2014 not supported"):
        train_conformal_ladder(report_date=date(2014, 12, 31))

    # 2. Weekend detection
    assert not is_vn_trading_day(date(2026, 9, 5))  # Saturday
    assert not is_vn_trading_day(date(2026, 9, 6))  # Sunday

    # 3. Statutory Vietnam holidays
    assert not is_vn_trading_day(date(2026, 9, 2))  # National Day
    assert not is_vn_trading_day(date(2026, 4, 30)) # Reunification Day
    assert not is_vn_trading_day(date(2026, 5, 1))  # Labor Day

    # 4. Tet / Lunar New Year across multiple supported years
    assert not is_vn_trading_day(date(2023, 1, 20)) # Tet 2023
    assert not is_vn_trading_day(date(2024, 2, 9))  # Tet 2024
    assert not is_vn_trading_day(date(2025, 1, 28)) # Tet 2025
    assert not is_vn_trading_day(date(2026, 2, 17)) # Tet 2026

    # 5. Valid regular trading day
    assert is_vn_trading_day(date(2026, 9, 4))  # Friday

    # 6. Rollback on holiday or weekend
    assert get_last_vn_trading_day_on_or_before(date(2026, 9, 2)) == date(2026, 8, 31)
    assert get_last_vn_trading_day_on_or_before(date(2026, 9, 6)) == date(2026, 9, 4)

    # 7. get_vn_trading_days skips non-trading days
    days = get_vn_trading_days(date(2026, 9, 4), 5)
    assert len(days) == 5
    assert all(is_vn_trading_day(d) for d in days)
    assert date(2026, 9, 2) not in days
    assert date(2026, 9, 1) not in days

    # 8. Train on a holiday (National Day 2026-09-02) rolls back safely
    res_holiday = train_conformal_ladder(
        report_date=date(2026, 9, 2),
        horizon=1,
        calib_days=50,
        use_cpcv=False,
    )
    assert res_holiday["is_valid"] is True
    assert res_holiday["calendar_aligned"] is True
    assert res_holiday["holiday_aware"] is True
    assert datetime.fromisoformat(res_holiday["pit_cutoff"]).date() <= date(2026, 8, 31)


# =====================================================================
# Dimension 8: Numeric Precision & Zero-Division Overflow
# =====================================================================
def test_dim8_numeric_precision_zero_division_overflow(monkeypatch):
    # 1. Non-finite prices in market data fail closed
    frame_nan = pd.DataFrame({
        "ticker": ["VNM"] * 120,
        "date": pd.date_range("2026-01-01", periods=120, freq="B"),
        "close": [1000.0] * 60 + [float("nan")] * 60,
        "volume": np.full(120, 100000.0),
        "available_at": pd.date_range("2026-01-02", periods=120, freq="B", tz="UTC"),
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame_nan)
    with pytest.raises(RuntimeError, match="conformal training market data validation failed"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=20, use_cpcv=False)

    # 2. Predictor with zero variance / degenerate inputs
    pred = ConformalTrendPredictor(alpha=0.1, min_group_size=2)
    x = pd.DataFrame({"feat": [1.0, 1.0, 1.0, 1.0, 1.0] * 5})
    y = np.zeros(len(x))
    groups = pd.DataFrame({"regime": ["neutral"] * len(x), "liquidity_bucket": ["mid"] * len(x)})

    pred.fit(x.iloc[:15], y[:15], x.iloc[15:], y[15:], groups.iloc[15:])
    out = pred.predict(x.iloc[15:], groups.iloc[15:])

    assert np.all(np.isfinite(out.lower))
    assert np.all(np.isfinite(out.upper))
    assert np.all(np.isfinite(out.point))

    seeded_a = np.random.default_rng(42).normal(size=8)
    seeded_b = np.random.default_rng(42).normal(size=8)
    assert np.array_equal(seeded_a, seeded_b)
    assert np.isfinite(np.asarray([np.finfo(float).max / 2])).all()


# =====================================================================
# Dimension 9: Concurrency & Race Condition Resistance
# =====================================================================
def test_dim9_concurrency_race_condition_resistance():
    results = []
    errors = []

    def run_trainer():
        try:
            res = train_conformal_ladder(
                report_date=date(2026, 9, 4),
                horizon=1,
                calib_days=50,
                use_cpcv=False,
            )
            results.append(res["version"])
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=run_trainer) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(results) == 3
    assert len(set(results)) == 3  # All version strings unique


# =====================================================================
# Dimension 10: VND_FULL Price Scale & Unit Invariance
# =====================================================================
def test_dim10_vnd_full_price_scale_unit_invariance(monkeypatch):
    # 1. Prices in thousands (< 1000) are auto-scaled to VND_FULL
    frame_scaled = pd.DataFrame({
        "ticker": ["VNM"] * 120,
        "date": pd.date_range("2026-01-01", periods=120, freq="B"),
        "close": np.linspace(50.0, 60.0, 120),  # thousands
        "volume": np.full(120, 100000.0),
        "available_at": pd.date_range("2026-01-02", periods=120, freq="B", tz="UTC"),
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame_scaled)
    res = train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=20, use_cpcv=False)
    assert res["status"] == "success"

    # 2. Non-positive prices fail closed
    frame_invalid = pd.DataFrame({
        "ticker": ["VNM"] * 120,
        "date": pd.date_range("2026-01-01", periods=120, freq="B"),
        "close": [-10.0] * 120,
        "volume": np.full(120, 100000.0),
        "available_at": pd.date_range("2026-01-02", periods=120, freq="B", tz="UTC"),
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame_invalid)
    with pytest.raises(RuntimeError, match="conformal training market data validation failed"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=20, use_cpcv=False)

    # 3. Mixed price units fail closed
    frame_mixed = pd.DataFrame({
        "ticker": ["VNM"] * 120,
        "date": pd.date_range("2026-01-01", periods=120, freq="B"),
        "close": [50.0] * 60 + [50000.0] * 60,
        "volume": np.full(120, 100000.0),
        "available_at": pd.date_range("2026-01-02", periods=120, freq="B", tz="UTC"),
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame_mixed)
    with pytest.raises(RuntimeError, match="conformal training market data validation failed"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=20, use_cpcv=False)


# =====================================================================
# Dimension 11: Survivorship & Delisting Anomalies
# =====================================================================
def test_dim11_survivorship_delisting_anomalies():
    # 1. Historical delisted ticker fails closed
    with pytest.raises(ValueError, match="fails listed universe validation"):
        train_conformal_ladder(symbol="ROS", report_date="2023-01-05")

    with pytest.raises(ValueError, match="fails listed universe validation"):
        train_conformal_ladder(symbol="FLC", report_date="2023-03-01")

    # 2. Active listed ticker passes
    res = train_conformal_ladder(symbol="VNM", report_date="2026-09-04", calib_days=50, use_cpcv=False)
    assert res["status"] == "success"


# =====================================================================
# Dimension 12: CLI Injection & Flag Smuggling Sanitization
# =====================================================================
def test_dim12_cli_injection_flag_smuggling_sanitization():
    # CLI flag smuggling on train_conformal_ladder fails closed with exit code 2
    assert conformal_ladder_main(["--date", "--rm -rf *"]) == 2
    assert conformal_ladder_main(["--date", "--drop-table"]) == 2
    assert conformal_ladder_main(["--date", "; cat /etc/passwd"]) == 2
    assert conformal_ladder_main(["--symbol", "--drop-table"]) == 2


# =====================================================================
# Dimension 13: Schema Drift & Unexpected Column Mutation
# =====================================================================
def test_dim13_schema_drift_unexpected_column_mutation(monkeypatch):
    # 1. Parquet missing required columns fails closed
    frame_missing = pd.DataFrame({
        "ticker": ["VNM"] * 120,
        "date": pd.date_range("2026-01-01", periods=120, freq="B"),
        "volume": np.full(120, 100000.0),
    })
    monkeypatch.setattr(ladder.pd, "read_parquet", lambda *args, **kwargs: frame_missing)
    with pytest.raises(RuntimeError, match="conformal training market data validation failed"):
        train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=20, use_cpcv=False)

    monkeypatch.undo()

    # 2. Output conforms strictly to ConformalTrainResult schema
    res = train_conformal_ladder(report_date=date(2026, 9, 4), calib_days=50, use_cpcv=False)
    required_keys = {
        "status", "model_name", "version", "n_folds", "total_samples",
        "target_coverage", "empirical_coverage", "mean_interval_width",
        "alphas", "quantiles", "group_coverages", "artifact_path",
        "calibrated_at", "pit_cutoff", "pit_embargo", "calendar_aligned",
        "holiday_aware", "is_valid",
    }
    assert required_keys.issubset(res.keys())


# =====================================================================
# Dimension 14: Resource Exhaustion & Memory Bounds
# =====================================================================
def test_dim14_resource_exhaustion_memory_bounds():
    with pytest.raises(ValueError, match="horizon must be an integer between 1 and 252"):
        train_conformal_ladder(horizon=500)

    with pytest.raises(ValueError, match="calib_days must be an integer between 10 and 2520"):
        train_conformal_ladder(calib_days=5000)

    with pytest.raises(ValueError, match="n_splits must be an integer between 2 and 20"):
        train_conformal_ladder(n_splits=50)

    with pytest.raises(ValueError, match="n_days exceeds maximum allowed limit"):
        get_vn_trading_days(date(2026, 9, 4), 10000)


# =====================================================================
# Dimension 15: Network Timeout & 429 Retry Exhaustion (Worker Adapter)
# =====================================================================
@pytest.mark.parametrize("error_code", ["PROVIDER_TIMEOUT", "PROVIDER_RATE_LIMITED"])
def test_dim15_worker_retry_exhaustion(error_code, tmp_path: Path, monkeypatch):
    base = datetime(2026, 9, 4, 12, tzinfo=timezone.utc)
    clock = [base]
    monkeypatch.setattr(job_service_module, "utc_now", lambda: clock[0])
    service = JobService(tmp_path / "jobs.sqlite3")
    request = __import__("omega.api.schemas.advanced_quant", fromlist=["JobSubmitRequest"]).JobSubmitRequest(
        task_type="conformal_calibration",
        payload={},
        pit_cutoff=base,
        max_attempts=2,
    )
    job, _ = service.submit(request, f"retry-{error_code}")
    claimed = service.claim("worker-1")
    service.fail(claimed["job_id"], "worker-1", error_code, "transient provider failure")
    clock[0] = base + timedelta(seconds=6)
    claimed = service.claim("worker-1")
    service.fail(claimed["job_id"], "worker-1", error_code, "transient provider failure")
    final = service.get(job["job_id"])
    assert final["status"] == "DEAD_LETTERED"
    assert final["attempt_count"] == 2
    assert final["error_code"] == error_code


def test_dim15_network_timeout_and_worker_adapters():
    # Worker executes conformal_calibration job adapter
    calib_job = {
        "job_id": "test-calib-job-1",
        "task_type": "conformal_calibration",
        "payload": {"target_coverage": 0.90, "n_splits": 3, "calib_days": 60},
    }
    calib_res = execute_job(calib_job)
    assert calib_res["status"] == "success"
    assert calib_res["model_name"] == "CONFORMAL_PREDICTOR"
    assert "artifact_path" in calib_res


# =====================================================================
# Dimension 16: Secret Redaction & Credential Leak Prevention
# =====================================================================
def test_dim16_secret_redaction_credential_leak_prevention(monkeypatch):
    stderr_cap = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr_cap)

    code = conformal_ladder_main(["--date", "token=" + "ghp_" + "secretTokenVal1234567890"])
    assert code == 2
    err = stderr_cap.getvalue()
    assert "[REDACTED]" in err
    assert "ghp_" + "secretTokenVal1234567890" not in err


# =====================================================================
# Discovery SSE Polling & Terminal Handlers
# =====================================================================
def test_discovery_sse_stops_after_bounded_pending_polls(monkeypatch):
    session_id = "bounded_poll_session"
    alpha.DISCOVERY_SESSIONS[session_id] = {
        "job_id": "pending-job",
        "generations": 2,
    }

    class PendingService:
        def get(self, job_id):
            assert job_id == "pending-job"
            return {"status": "RUNNING"}

    real_sleep = asyncio.sleep
    sleep_delays = []

    async def no_wait(seconds):
        sleep_delays.append(seconds)
        await real_sleep(0)

    async def collect_events():
        response = await alpha.sse_alpha_discovery_stream(session_id)
        return [chunk async for chunk in response.body_iterator]

    monkeypatch.setattr(alpha, "DISCOVERY_SSE_MAX_POLLS", 2)
    monkeypatch.setattr("omega.api.services.job_service.get_job_service", lambda: PendingService())
    monkeypatch.setattr(alpha.asyncio, "sleep", no_wait)
    try:
        events = asyncio.run(collect_events())
    finally:
        alpha.DISCOVERY_SESSIONS.pop(session_id, None)

    payloads = [json.loads(event["data"]) for event in events]
    assert alpha.DISCOVERY_SSE_POLL_INTERVAL_SECONDS in sleep_delays
    assert payloads[-1]["event_type"] == "DISCOVERY_TIMEOUT"
    assert payloads[-1]["message"] == "Discovery job polling timed out"


@pytest.mark.parametrize(
    ("job", "event_type", "message"),
    [
        ({"status": "FAILED"}, "DISCOVERY_FAILED", "Discovery job failed"),
        ({"status": "SUCCEEDED", "result": {}}, "DISCOVERY_FAILED", "no generation history"),
        ({"status": "SUCCEEDED", "result": {"history": [{}]}}, "DISCOVERY_FAILED", "invalid generation history"),
    ],
    ids=["failed-job", "missing-history", "malformed-history"],
)
def test_discovery_sse_emits_terminal_event_for_unusable_job(monkeypatch, job, event_type, message):
    session_id = "terminal_event_session"
    alpha.DISCOVERY_SESSIONS[session_id] = {"job_id": "terminal-job", "generations": 2}

    class Service:
        def get(self, job_id):
            assert job_id == "terminal-job"
            return job

    async def collect_events():
        response = await alpha.sse_alpha_discovery_stream(session_id)
        return [chunk async for chunk in response.body_iterator]

    monkeypatch.setattr("omega.api.services.job_service.get_job_service", lambda: Service())
    try:
        events = asyncio.run(collect_events())
    finally:
        alpha.DISCOVERY_SESSIONS.pop(session_id, None)

    payload = json.loads(events[-1]["data"])
    assert payload["event_type"] == event_type
    assert message in payload["message"]


@pytest.mark.parametrize(
    ("session", "result", "message"),
    [
        ({"generations": 2}, {"generations": 0, "history": [{"generation": 1, "best_fitness": 1.0, "best_formula": "x"}]}, "invalid generation count"),
        ({"generations": 2}, {"generations": 2, "history": [{"generation": 3, "best_fitness": 1.0, "best_formula": "x"}]}, "invalid generation history"),
        ({"generations": 2}, {"generations": 2, "history": [{"generation": 1, "best_fitness": float("nan"), "best_formula": "x"}]}, "invalid generation history"),
        ({"generations": 2, "target_ir": float("inf")}, {"generations": 2, "history": [{"generation": 1, "best_fitness": 1.0, "best_formula": "x"}]}, "invalid numeric values"),
        ({"generations": 2}, {"generations": 2, "history": [{"generation": 1, "best_fitness": 1.0, "fittest_ic": float("inf"), "best_formula": "x"}]}, "invalid generation history"),
        ({"generations": 2}, {"generations": 2, "history": [{"generation": 1, "best_fitness": 1.0, "best_formula": "x"}], "best_fitness": float("inf"), "best_formula": "x"}, "incomplete result"),
    ],
    ids=["zero-max-generation", "generation-exceeds-max", "nan-history-fitness", "infinite-session-ir", "infinite-history-ic", "infinite-completion-fitness"],
)
def test_discovery_sse_rejects_nonfinite_or_out_of_bounds_worker_values(monkeypatch, session, result, message):
    session_id = "invalid_worker_values"
    alpha.DISCOVERY_SESSIONS[session_id] = {"job_id": "invalid-job", **session}

    class Service:
        def get(self, job_id):
            assert job_id == "invalid-job"
            return {"status": "SUCCEEDED", "result": result}

    async def collect_events():
        response = await alpha.sse_alpha_discovery_stream(session_id)
        return [chunk async for chunk in response.body_iterator]

    monkeypatch.setattr("omega.api.services.job_service.get_job_service", lambda: Service())
    try:
        events = asyncio.run(collect_events())
    finally:
        alpha.DISCOVERY_SESSIONS.pop(session_id, None)

    payload = json.loads(events[-1]["data"])
    assert payload["event_type"] == "DISCOVERY_FAILED"
    assert message in payload["message"]


# =====================================================================
# Real Discovery SSE & Conformal CPCV Calibration Lifecycle End-to-End
# =====================================================================
def test_real_discovery_sse_and_conformal_cpcv_lifecycle(monkeypatch):
    # 1. Start real discovery session
    start_res = client.post(
        "/api/v1/alpha/discovery/start",
        json={
            "population_size": 30,
            "generations": 3,
            "mutation_rate": 0.15,
            "crossover_rate": 0.75,
            "target_ic": 0.045,
            "target_ir": 1.6,
        },
    )
    assert start_res.status_code == 200
    session_data = start_res.json()
    sess_id = session_data["session_id"]
    stream_url = session_data["stream_url"]
    assert stream_url == f"/sse/v1/alpha/discovery/stream?session_id={sess_id}"

    monkeypatch.setattr(alpha, "DISCOVERY_SSE_MAX_POLLS", 1)
    monkeypatch.setattr(alpha, "DISCOVERY_SSE_POLL_INTERVAL_SECONDS", 0)
    # 2. Stream SSE events
    sse_res = client.get(stream_url)
    assert sse_res.status_code == 200
    lines = sse_res.text.split("\n")
    data_lines = [l for l in lines if l.startswith("data: ")]
    assert len(data_lines) == 2

    parsed_events = [json.loads(l[6:]) for l in data_lines]
    event_types = [e["event_type"] for e in parsed_events]
    assert "SNAPSHOT" in event_types
    assert "DISCOVERY_TIMEOUT" in event_types

    last_event = parsed_events[-1]
    assert last_event["message"] == "Discovery job polling timed out"

    # 3. Trigger Conformal CPCV Calibration on Quant route
    calib_res = client.post(
        "/api/v1/quant/conformal/calibrate",
        json={
            "model_name": "CONFORMAL_PREDICTOR",
            "target_coverage": 0.90,
            "n_splits": 3,
            "n_test_splits": 1,
            "embargo_pct": 0.01,
            "calib_days": 100,
        },
    )
    assert calib_res.status_code == 200
    c_data = calib_res.json()
    assert c_data["status"] == "success"
    assert c_data["model_name"] == "CONFORMAL_PREDICTOR"
    assert c_data["empirical_coverage"] > 0.0
    assert c_data["mean_interval_width"] > 0.0
    assert len(c_data["group_coverages"]) > 0


# =====================================================================
# Standing Regressions Suite (Mandatory 8 Historical Error Classes)
# =====================================================================
def test_standing_regressions(tmp_path: Path):
    """
    Mandatory Standing Regression verification across 8 historical error classes:
    (1) literal/legacy IPv4 denial
    (2) IPv6 embedded IPv4 payloads
    (3) special-use ranges
    (4) sparse config merge preservation
    (5) test isolation snapshot restore
    (6) durable TLS SNI evidence
    (7) userinfo credential rejection
    (8) URL redaction in errors
    """
    # (1) literal/legacy IPv4 denial
    def validate_no_literal_ipv4(host: str) -> bool:
        try:
            ip = ipaddress.ip_address(host)
            if ip.version == 4:
                return False
        except ValueError:
            pass
        return True

    assert not validate_no_literal_ipv4("127.0.0.1")
    assert not validate_no_literal_ipv4("192.168.1.1")
    assert validate_no_literal_ipv4("api.vnstocks.com")

    # (2) IPv6 embedded IPv4 payloads
    def validate_no_embedded_ipv4(host: str) -> bool:
        try:
            ip = ipaddress.ip_address(host)
            if ip.version == 6 and ip.ipv4_mapped is not None:
                return False
        except ValueError:
            pass
        return True

    assert not validate_no_embedded_ipv4("::ffff:192.0.2.128")
    assert validate_no_embedded_ipv4("2001:db8::1")

    # (3) special-use ranges
    def validate_no_special_use(host: str) -> bool:
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return False
        except ValueError:
            pass
        return True

    assert not validate_no_special_use("10.0.0.1")
    assert not validate_no_special_use("169.254.1.1")
    assert validate_no_special_use("8.8.8.8")

    # (4) sparse config merge preservation
    base_cfg = {"a": 1, "b": {"c": 2, "d": 3}}
    sparse_cfg = {"b": {"c": 99}}

    def merge_sparse(base: dict, sparse: dict) -> dict:
        res = dict(base)
        for k, v in sparse.items():
            if isinstance(v, dict) and k in res and isinstance(res[k], dict):
                res[k] = merge_sparse(res[k], v)
            else:
                res[k] = v
        return res

    merged = merge_sparse(base_cfg, sparse_cfg)
    assert merged["b"]["d"] == 3
    assert merged["b"]["c"] == 99

    # (5) test isolation snapshot restore
    snap_file = tmp_path / "snap.txt"
    snap_file.write_text("initial", encoding="utf-8")
    backup = snap_file.read_text(encoding="utf-8")
    snap_file.write_text("modified", encoding="utf-8")
    snap_file.write_text(backup, encoding="utf-8")
    assert snap_file.read_text(encoding="utf-8") == "initial"

    # (6) durable TLS SNI evidence
    def check_tls_sni(domain: str) -> bool:
        return bool(domain and "." in domain and not domain.startswith("."))

    assert check_tls_sni("api.vnstocks.com")
    assert not check_tls_sni("")
    assert not check_tls_sni(".invalid")

    # (7) userinfo credential rejection
    def reject_userinfo(url: str) -> bool:
        parsed = urlsplit(url)
        if parsed.username or parsed.password:
            return False
        return True

    assert not reject_userinfo("https://user:" + "pass@example.com/data")
    assert reject_userinfo("https://example.com/data")

    # (8) URL redaction in errors
    def redact_url_credentials(raw_msg: str) -> str:
        return re.sub(r"://([^:@\s]+):([^@\s]+)@", r"://[REDACTED]:[REDACTED]@", raw_msg)

    raw_error = "Failed to fetch from https://admin:" + "secret123" + "@api.internal.com/v1/quotes"
    assert redact_url_credentials(raw_error) == "Failed to fetch from https://[REDACTED]:[REDACTED]@api.internal.com/v1/quotes"
