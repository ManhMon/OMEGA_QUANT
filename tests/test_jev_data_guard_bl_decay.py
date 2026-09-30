"""W6 test suite covering data guard, calibrated Black-Litterman overlay, and decay review queue."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone, tzinfo
import hashlib
import json
import math
import re
import sqlite3
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytest

from omega.core.llm_config import _canonical
from features.pit_guard import (
    check_leakage,
    enforce_t_minus_1_lag,
    validate_shadow_data_guard,
    verify_no_lookahead,
)
from omega.quant.continuous_learning import (
    ContinuousLearningEngine,
    W6ReviewQueue,
    _compute_metadata_digest,
    _decode_row,
    _parse_strict_json,
    _validate_payload,
)
from omega.quant.drift_detector import (
    W6_DECAY_SCHEMA_VERSION,
    attach_decay_attribution,
)
from omega.quant.portfolio.black_litterman_overlay import (
    GATE_ID_W6,
    apply_calibrated_black_litterman_overlay,
)


# =====================================================================
# FIXTURES & HELPERS
# =====================================================================

@pytest.fixture
def base_timestamps() -> tuple[datetime, datetime]:
    cutoff = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
    maturity = datetime(2026, 9, 30, 9, 0, 0, tzinfo=timezone.utc)
    return cutoff, maturity


@pytest.fixture
def bl_hand_reference_inputs(base_timestamps):
    cutoff, maturity = base_timestamps
    assets = ["A", "B", "C"]
    w0 = pd.Series([0.5, 0.3, 0.2], index=assets, dtype=np.float64)
    cov = np.diag([0.04, 0.09, 0.16]).astype(np.float64)
    view_ids = ["view_AB"]
    P = np.array([[1.0, -1.0, 0.0]], dtype=np.float64)
    Q = np.array([0.02], dtype=np.float64)
    errors = np.full((1, 20), 0.02, dtype=np.float64)
    return {
        "baseline_weights": w0,
        "ordered_assets": assets,
        "cutoff": cutoff,
        "calibration_maturity": maturity,
        "covariance_matrix": cov,
        "ordered_view_ids": view_ids,
        "P": P,
        "Q": Q,
        "calibration_errors": errors,
        "tau": 0.05,
        "delta": 2.5,
        "rho": 0.0001,
    }


def make_valid_guard_df(cutoff: datetime) -> pd.DataFrame:
    as_of = cutoff - timedelta(hours=2)
    avail = cutoff - timedelta(hours=1)
    return pd.DataFrame({
        "symbol": ["TCB", "VCB"],
        "as_of": [as_of, as_of],
        "available_at": [avail, avail],
        "open": [25000.0, 85000.0],
        "high": [26000.0, 86000.0],
        "low": [24500.0, 84000.0],
        "close": [25500.0, 85500.0],
        "volume": [100000.0, 50000.0],
    })


def make_decay_payload(
    cutoff: datetime,
    maturity: datetime,
    decision_id: str = "DECAY_W6_TEST_01",
    **kwargs: Any,
) -> Dict[str, Any]:
    params = {
        "gross_before": 0.10,
        "gross_after": 0.08,
        "cost_before": 0.01,
        "cost_after": 0.02,
        "trigger_detected": True,
        "cutoff": cutoff,
        "maturity": maturity,
        "data_issue_flag": False,
        "regime_mismatch_flag": False,
        "cost_shift_flag": False,
        "drift_label": "noise",
        "attribution": "unclear",
        "recommendation": "wait",
        "decision_id": decision_id,
        "gate_id": "GATE_JEV_DEEP_INTEGRATION_W6_20260930",
        "policy_version": "1.0.0",
        "source_revision": "HEAD",
        "synthetic": False,
    }
    params.update(kwargs)
    return attach_decay_attribution(**params)


class SqliteConnProxy:
    """Connection wrapper proxy intercepting specific SQL statements to inject MemoryError."""
    def __init__(self, real_conn: sqlite3.Connection, fail_sql_substr: str):
        self._real = real_conn
        self.fail_sql_substr = fail_sql_substr

    def execute(self, sql: str, *args: Any):
        if self.fail_sql_substr in sql:
            raise MemoryError(f"simulated OOM on {self.fail_sql_substr}")
        return self._real.execute(sql, *args)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


W6_REVIEW_QUEUE_NON_KEY_COLUMNS = [
    "canonical_digest",
    "review_category",
    "trigger_reason",
    "created_at",
    "expires_at",
    "status",
    "payload_json",
    "metadata_digest",
]

INVALID_FULLMATCH_IDENTIFIERS = [
    "ITEM\n",
    "\nITEM",
    "ITEM\r\n",
    "\r\nITEM",
    "a" * 128 + "\n",
    "a" * 129,
    "",
    "   ",
    "ITEM WITH SPACE",
    "ITEM;DROP TABLE review_queue",
    "ITEM@SPECIAL",
    "ITEM#1",
    "ITEM$TEST",
]

NONSTRING_FULLMATCH_IDENTIFIERS = [
    None,
    123,
    0,
    12.34,
    False,
    True,
    ["invalid"],
    {"invalid": "item"},
]

VALID_BOUNDARY_IDENTIFIERS = [
    "x",
    "A",
    "0",
    "_",
    "-",
    ".",
    "a" * 128,
    "A" * 60 + "_" + "-" * 30 + "." + "0" * 36,
    "DEC-123_45.67",
    "valid.source-revision_v1",
]


def make_review_queue_schema_with_nullable_column(nullable_col: str) -> str:
    col_defs = ["item_id TEXT PRIMARY KEY"]
    for c in W6_REVIEW_QUEUE_NON_KEY_COLUMNS:
        if c == nullable_col:
            col_defs.append(f"{c} TEXT")
        else:
            col_defs.append(f"{c} TEXT NOT NULL")
    return f"CREATE TABLE review_queue ({', '.join(col_defs)})"


QUEUE_WRITE_OPERATIONS = [
    "enqueue", "enqueue-duplicate", "enqueue-conflict", "enqueue-capacity",
    "mark-reviewed", "mark-expired", "mark-missing", "mark-terminal",
]
QUEUE_READ_OPERATIONS = [
    "get", "get-missing", "peek", "peek-expired",
    "count", "count-pending", "count-reviewed", "count-expired",
]


def prepare_interleaving_queue(tmp_path, base_timestamps, operation):
    queue = W6ReviewQueue(tmp_path / "interleaving.db")
    payload = make_decay_payload(*base_timestamps, decision_id="INTERLEAVED_ITEM")
    queue.enqueue(payload["decision_id"], payload["canonical_digest"], payload["attribution"], "drift_detected", payload)
    if operation == "enqueue-capacity":
        queue.max_capacity = 1
    if operation == "mark-terminal":
        queue.mark_reviewed(payload["decision_id"])
    return queue, payload


def run_queue_operation(queue, payload, operation):
    cutoff = datetime.fromisoformat(payload["cutoff"])
    if operation.startswith("enqueue"):
        candidate = payload if operation in ("enqueue-duplicate", "enqueue-conflict") else make_decay_payload(
            cutoff, datetime.fromisoformat(payload["maturity"]), decision_id="INTERLEAVED_NEW",
        )
        return queue.enqueue(
            candidate["decision_id"], candidate["canonical_digest"], candidate["attribution"],
            "synthetic_event" if operation == "enqueue-conflict" else "drift_detected", candidate,
        )
    if operation.startswith("mark-"):
        return queue.mark_reviewed(
            "MISSING" if operation == "mark-missing" else payload["decision_id"],
            resolution="expired" if operation == "mark-expired" else "reviewed",
        )
    if operation.startswith("get"):
        return queue.get("MISSING" if operation == "get-missing" else payload["decision_id"])
    if operation.startswith("peek"):
        return queue.peek(cutoff + timedelta(days=1) if operation == "peek-expired" else cutoff)
    if operation == "initialize":
        return W6ReviewQueue(queue.queue_path)
    return queue.count(None if operation == "count" else operation.removeprefix("count-"))


def replace_queue_with_nullable_schema(conn, *, preserve_rows=True):
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("ALTER TABLE review_queue RENAME TO original_queue")
    conn.execute(make_review_queue_schema_with_nullable_column("payload_json"))
    if preserve_rows:
        conn.execute("INSERT INTO review_queue SELECT * FROM original_queue")
    conn.execute("DROP TABLE original_queue")
    conn.execute("CREATE INDEX idx_review_queue_status ON review_queue(status)")
    conn.execute("CREATE INDEX idx_review_queue_expires ON review_queue(expires_at)")
    conn.execute("COMMIT")


def queue_database_snapshot(conn):
    return (
        conn.execute("SELECT * FROM sqlite_schema ORDER BY name").fetchall(),
        conn.execute("SELECT * FROM review_queue ORDER BY item_id").fetchall(),
        conn.execute("PRAGMA journal_mode").fetchone(),
    )


# =====================================================================
# BLACK-LITTERMAN OVERLAY TESTS
# =====================================================================

def test_w6_bl_hand_reference_n3_k1(bl_hand_reference_inputs):
    out_w, meta = apply_calibrated_black_litterman_overlay(**bl_hand_reference_inputs)

    # Output series contract
    assert isinstance(out_w, pd.Series)
    assert out_w.equals(bl_hand_reference_inputs["baseline_weights"])
    assert out_w.dtype == bl_hand_reference_inputs["baseline_weights"].dtype
    assert list(out_w.index) == list(bl_hand_reference_inputs["baseline_weights"].index)
    assert out_w is not bl_hand_reference_inputs["baseline_weights"]

    # Metadata status and advisory invariants
    assert meta["status"] == "proposal_ready"
    assert meta["reason"] == "SUCCESS"
    assert meta["advisory_only"] is True
    assert meta["applied"] is False
    assert meta["live_influence"] == 0.0

    prop = meta["posterior_proposal"]
    assert prop is not None

    # Exact hand reference checks:
    # Sigma_r = diag([0.0401, 0.0901, 0.1601])
    # tau*Sigma_r = diag([0.002005, 0.004505, 0.008005])
    # v = [1, -1, 0] @ tau*Sigma_r @ [1, -1, 0]^T = 0.00651
    # s^2 = 0.02^2 = 0.0004
    # r = 0.0004 / 0.00651 ~= 0.0614439324; clipped to [0.01, 100.0] -> c = r
    # omega = max(1e-6, c * v) = 0.0004 -> independent scalar denominator
    assert prop["omega_diag"] == [pytest.approx(0.0004, abs=1e-12)]

    # pi = delta * Sigma_r @ w0 = 2.5 * [0.02005, 0.02703, 0.03202] = [0.050125, 0.067575, 0.08005]
    assert prop["pi"] == [
        pytest.approx(0.050125, abs=1e-9),
        pytest.approx(0.067575, abs=1e-9),
        pytest.approx(0.080050, abs=1e-9),
    ]

    # A = v + omega = 0.00651 + 0.0004 = 0.00691
    # P @ pi = 0.050125 - 0.067575 = -0.01745
    # rhs = Q - P @ pi = 0.02 - (-0.01745) = 0.03745
    # x = 0.03745 / 0.00691 = 3745 / 691
    # mu_BL = pi + tau*Sigma_r @ P^T * x
    # mu_BL[0] = 0.050125 + 0.002005 * (3745/691) = 42.1451 / 691 ~= 0.0609914616
    # mu_BL[1] = 0.067575 - 0.004505 * (3745/691) = 29.8231 / 691 ~= 0.0431593343
    # mu_BL[2] = 0.080050
    assert prop["mu_BL"][0] == pytest.approx(42.1451 / 691, abs=1e-9)
    assert prop["mu_BL"][1] == pytest.approx(29.8231 / 691, abs=1e-9)
    assert prop["mu_BL"][2] == pytest.approx(0.080050, abs=1e-9)
    assert prop["clipping_rate"] == 0.0
    assert prop["solve_residual"] <= 1e-4


def test_w6_bl_baseline_exact_equals_dtype_and_order(bl_hand_reference_inputs):
    out_w, meta = apply_calibrated_black_litterman_overlay(**bl_hand_reference_inputs)
    pd.testing.assert_series_equal(out_w, bl_hand_reference_inputs["baseline_weights"], check_exact=True)
    assert out_w.index.equals(bl_hand_reference_inputs["baseline_weights"].index)


def test_w6_bl_k0_bypass_no_views(bl_hand_reference_inputs):
    inputs = dict(bl_hand_reference_inputs)
    inputs["ordered_view_ids"] = []
    inputs["P"] = np.empty((0, 3), dtype=np.float64)
    inputs["Q"] = np.empty((0,), dtype=np.float64)

    out_w, meta = apply_calibrated_black_litterman_overlay(**inputs)
    assert out_w.equals(inputs["baseline_weights"])
    assert meta["status"] == "k0_bypass"
    assert meta["reason"] == "K0_BYPASS"
    assert meta["posterior_proposal"] is None
    assert meta["advisory_only"] is True
    assert meta["applied"] is False


def test_w6_bl_baseline_strict_validation(bl_hand_reference_inputs):
    cutoff = bl_hand_reference_inputs["cutoff"]
    mat = bl_hand_reference_inputs["calibration_maturity"]
    assets = bl_hand_reference_inputs["ordered_assets"]

    # Non-Series
    with pytest.raises(TypeError, match="must be a pd.Series"):
        apply_calibrated_black_litterman_overlay([0.5, 0.3, 0.2], assets, cutoff, mat)

    # Non-numeric dtype
    bad_series = pd.Series(["a", "b", "c"], index=assets)
    with pytest.raises(TypeError, match="must have numeric float/int dtype"):
        apply_calibrated_black_litterman_overlay(bad_series, assets, cutoff, mat)

    # Boolean dtype
    bool_series = pd.Series([True, False, False], index=assets)
    with pytest.raises(TypeError, match="must have numeric float/int dtype"):
        apply_calibrated_black_litterman_overlay(bool_series, assets, cutoff, mat)

    # Asset length mismatch
    wrong_assets = ["A", "B"]
    with pytest.raises(ValueError, match="strictly match"):
        apply_calibrated_black_litterman_overlay(bl_hand_reference_inputs["baseline_weights"], wrong_assets, cutoff, mat)

    # Duplicate assets
    with pytest.raises(ValueError, match="unique string IDs"):
        apply_calibrated_black_litterman_overlay(
            pd.Series([0.5, 0.5], index=["A", "A"]), ["A", "A"], cutoff, mat
        )

    # Negative baseline weights
    neg_w = pd.Series([-0.1, 0.6, 0.5], index=assets)
    with pytest.raises(ValueError, match="finite, non-negative, and sum <= 1"):
        apply_calibrated_black_litterman_overlay(neg_w, assets, cutoff, mat)

    # Sum > 1 + 1e-6
    over_w = pd.Series([0.6, 0.5, 0.2], index=assets)
    with pytest.raises(ValueError, match="finite, non-negative, and sum <= 1"):
        apply_calibrated_black_litterman_overlay(over_w, assets, cutoff, mat)

    # Non-finite weights
    nan_w = pd.Series([np.nan, 0.3, 0.2], index=assets)
    with pytest.raises(ValueError, match="finite, non-negative, and sum <= 1"):
        apply_calibrated_black_litterman_overlay(nan_w, assets, cutoff, mat)


def test_w6_bl_malformed_scalar_params_and_views(bl_hand_reference_inputs):
    # Malformed hyperparameter scalar types and values
    for bad_tau in (True, False, float("nan"), float("inf"), "0.05", [0.05]):
        inp = dict(bl_hand_reference_inputs, tau=bad_tau)
        _, meta = apply_calibrated_black_litterman_overlay(**inp)
        assert meta["status"] == "fallback"
        assert meta["reason"] == "INVALID_HYPERPARAMETERS"

    for bad_delta in (-2.5, 0.0, float("nan"), "2.5"):
        inp = dict(bl_hand_reference_inputs, delta=bad_delta)
        _, meta = apply_calibrated_black_litterman_overlay(**inp)
        assert meta["status"] == "fallback"
        assert meta["reason"] == "INVALID_HYPERPARAMETERS"

    for bad_sat in (True, -0.1, 1.5, float("nan"), "0.5"):
        inp = dict(bl_hand_reference_inputs, max_saturation_rate=bad_sat)
        _, meta = apply_calibrated_black_litterman_overlay(**inp)
        assert meta["status"] == "fallback"
        assert meta["reason"] == "INVALID_HYPERPARAMETERS"

    # c_min > c_max
    inp_c = dict(bl_hand_reference_inputs, c_min=10.0, c_max=5.0)
    _, meta_c = apply_calibrated_black_litterman_overlay(**inp_c)
    assert meta_c["status"] == "fallback"
    assert meta_c["reason"] == "INVALID_HYPERPARAMETERS"

    # Malformed ordered_view_ids
    for bad_views in ("not_a_list", {"view_AB": 1}, [123], [True], ["view_AB", "view_AB"], [""], ["x" * 65]):
        inp_v = dict(bl_hand_reference_inputs, ordered_view_ids=bad_views)
        _, meta_v = apply_calibrated_black_litterman_overlay(**inp_v)
        assert meta_v["status"] == "fallback"
        assert meta_v["reason"] in ("INVALID_VIEWS", "INVALID_IDENTIFIERS")


def test_w6_bl_sentinel_fallbacks_and_bounds(bl_hand_reference_inputs):
    # Future calibration maturity
    inputs = dict(bl_hand_reference_inputs)
    inputs["calibration_maturity"] = inputs["cutoff"] + timedelta(seconds=1)
    out_w, meta = apply_calibrated_black_litterman_overlay(**inputs)
    assert meta["status"] == "fallback"
    assert meta["reason"] == "CALIBRATION_NOT_MATURE"

    # Naive cutoff timezone
    inputs = dict(bl_hand_reference_inputs)
    inputs["cutoff"] = datetime(2026, 9, 30, 10, 0, 0)
    out_w, meta = apply_calibrated_black_litterman_overlay(**inputs)
    assert meta["status"] == "fallback"
    assert meta["reason"] == "INVALID_CUTOFF"

    # Invalid horizon
    inputs = dict(bl_hand_reference_inputs)
    inputs["return_horizon"] = "weekly"
    out_w, meta = apply_calibrated_black_litterman_overlay(**inputs)
    assert meta["status"] == "fallback"
    assert meta["reason"] == "INVALID_HORIZON_OR_UNITS"

    # Invalid P shape
    inputs = dict(bl_hand_reference_inputs)
    inputs["P"] = np.array([[1.0, -1.0]], dtype=np.float64)  # (1, 2) instead of (1, 3)
    out_w, meta = apply_calibrated_black_litterman_overlay(**inputs)
    assert meta["status"] == "fallback"
    assert meta["reason"] == "INVALID_P_MATRIX"

    # Invalid Q shape
    inputs = dict(bl_hand_reference_inputs)
    inputs["Q"] = np.array([0.02, 0.05], dtype=np.float64)  # (2,) instead of (1,)
    out_w, meta = apply_calibrated_black_litterman_overlay(**inputs)
    assert meta["status"] == "fallback"
    assert meta["reason"] == "INVALID_Q_VECTOR"

    # Calibration sample bound: M < 20
    inputs = dict(bl_hand_reference_inputs)
    inputs["calibration_errors"] = np.full((1, 19), 0.02, dtype=np.float64)
    out_w, meta = apply_calibrated_black_litterman_overlay(**inputs)
    assert meta["status"] == "fallback"
    assert meta["reason"] == "INVALID_CALIBRATION_ERRORS"

    # Asymmetric covariance
    inputs = dict(bl_hand_reference_inputs)
    asym_cov = np.diag([0.04, 0.09, 0.16]).astype(np.float64)
    asym_cov[0, 1] = 0.01
    asym_cov[1, 0] = 0.02
    inputs["covariance_matrix"] = asym_cov
    out_w, meta = apply_calibrated_black_litterman_overlay(**inputs)
    assert meta["status"] == "fallback"
    assert meta["reason"] == "INVALID_COVARIANCE"

    # Non-PSD covariance
    inputs = dict(bl_hand_reference_inputs)
    non_psd = np.diag([-0.05, 0.09, 0.16]).astype(np.float64)
    inputs["covariance_matrix"] = non_psd
    out_w, meta = apply_calibrated_black_litterman_overlay(**inputs)
    assert meta["status"] == "fallback"
    assert meta["reason"] == "COVARIANCE_NOT_PSD"


def test_w6_bl_numerical_or_memory_fault_solve(bl_hand_reference_inputs, monkeypatch):
    def _raise_linalg(*args, **kwargs):
        raise np.linalg.LinAlgError("singular matrix")

    monkeypatch.setattr(np.linalg, "solve", _raise_linalg)
    out_w, meta = apply_calibrated_black_litterman_overlay(**bl_hand_reference_inputs)
    assert meta["status"] == "fallback"
    assert meta["reason"] == "NUMERICAL_OR_MEMORY_ERROR"


def test_w6_bl_input_digest_determinism_and_mutation(bl_hand_reference_inputs):
    _, meta1 = apply_calibrated_black_litterman_overlay(**bl_hand_reference_inputs)
    _, meta2 = apply_calibrated_black_litterman_overlay(**bl_hand_reference_inputs)

    assert meta1["input_digest"] == meta2["input_digest"]
    assert meta1["decision_digest"] == meta2["decision_digest"]

    # Mutate P
    mutated_p = dict(bl_hand_reference_inputs)
    mutated_p["P"] = np.array([[0.0, 1.0, -1.0]], dtype=np.float64)
    _, meta_p = apply_calibrated_black_litterman_overlay(**mutated_p)
    assert meta_p["input_digest"] != meta1["input_digest"]

    # Mutate Q
    mutated_q = dict(bl_hand_reference_inputs)
    mutated_q["Q"] = np.array([0.05], dtype=np.float64)
    _, meta_q = apply_calibrated_black_litterman_overlay(**mutated_q)
    assert meta_q["input_digest"] != meta1["input_digest"]

    # Mutate Covariance
    mutated_cov = dict(bl_hand_reference_inputs)
    mutated_cov["covariance_matrix"] = np.diag([0.05, 0.09, 0.16]).astype(np.float64)
    _, meta_cov = apply_calibrated_black_litterman_overlay(**mutated_cov)
    assert meta_cov["input_digest"] != meta1["input_digest"]

    # Mutate Calibration errors
    mutated_err = dict(bl_hand_reference_inputs)
    mutated_err["calibration_errors"] = np.full((1, 20), 0.03, dtype=np.float64)
    _, meta_err = apply_calibrated_black_litterman_overlay(**mutated_err)
    assert meta_err["input_digest"] != meta1["input_digest"]

    # Explicit decision_id preserved
    custom_id = dict(bl_hand_reference_inputs)
    custom_id["decision_id"] = "BL_CUSTOM_DECISION_ID"
    _, meta_id = apply_calibrated_black_litterman_overlay(**custom_id)
    assert meta_id["decision_id"] == "BL_CUSTOM_DECISION_ID"


@pytest.mark.parametrize("parameter", [
    "tau", "delta", "rho", "kappa_max", "residual_tol", "v_floor", "omega_floor",
    "c_min", "c_max", "max_saturation_rate",
])
@pytest.mark.parametrize("value", [10**1000, -(10**1000)], ids=["positive", "negative"])
@pytest.mark.parametrize("branch", [
    "validation", "cutoff", "maturity", "future", "horizon", "units", "gate", "identifiers", "canonical_ids",
])
def test_w6_bl_oversized_integer_fallback(bl_hand_reference_inputs, monkeypatch, parameter, value, branch):
    inputs = dict(bl_hand_reference_inputs, **{parameter: value})
    reason = "INVALID_HYPERPARAMETERS"
    if branch == "cutoff":
        inputs["cutoff"] = None
        reason = "INVALID_CUTOFF"
    elif branch == "maturity":
        inputs["calibration_maturity"] = None
        reason = "INVALID_CUTOFF"
    elif branch == "future":
        inputs["calibration_maturity"] = inputs["cutoff"] + timedelta(seconds=1)
        reason = "CALIBRATION_NOT_MATURE"
    elif branch == "horizon":
        inputs["return_horizon"] = "weekly"
        reason = "INVALID_HORIZON_OR_UNITS"
    elif branch == "units":
        inputs["return_units"] = "log_return"
        reason = "INVALID_HORIZON_OR_UNITS"
    elif branch == "gate":
        inputs["gate_id"] = "OTHER_GATE"
        reason = "INVALID_HORIZON_OR_UNITS"
    elif branch == "identifiers":
        inputs["source_revision"] = "invalid revision"
        reason = "INVALID_IDENTIFIERS"
    elif branch == "canonical_ids":
        inputs["source_revision"] = "sk-invalid"
        reason = "INVALID_IDENTIFIERS"

    def unexpected_solve(*args, **kwargs):
        raise AssertionError("invalid scalar reached solver")

    monkeypatch.setattr(np.linalg, "solve", unexpected_solve)
    before = inputs["baseline_weights"].copy(deep=True)
    out, meta = apply_calibrated_black_litterman_overlay(**inputs)
    pd.testing.assert_series_equal(out, before, check_exact=True)
    pd.testing.assert_series_equal(inputs["baseline_weights"], before, check_exact=True)
    assert out is not inputs["baseline_weights"]
    assert meta["reason"] == reason
    assert meta["status"] == "fallback"
    assert meta["advisory_only"] is True
    assert meta["applied"] is False
    assert meta["live_influence"] == 0.0
    assert meta["posterior_proposal"] is None
    assert apply_calibrated_black_litterman_overlay(**inputs)[1] == meta
    assert json.loads(json.dumps(meta, allow_nan=False)) == meta
    payload = {k: v for k, v in meta.items() if k != "decision_digest"}
    assert meta["decision_digest"] == hashlib.sha256(_canonical(payload)).hexdigest()
    if branch != "validation":
        normalized = dict(inputs, **{parameter: 0.0})
        assert apply_calibrated_black_litterman_overlay(**normalized)[1] == meta


@pytest.mark.parametrize("parameter,value", [
    (name, 10**6) for name in (
        "tau", "delta", "rho", "kappa_max", "residual_tol", "v_floor", "omega_floor", "c_min", "c_max",
    )
] + [("max_saturation_rate", 0), ("max_saturation_rate", 1)])
@pytest.mark.parametrize("scalar_type", [int, float], ids=["int", "float"])
def test_w6_bl_scalar_bounds_preserve_k0_bypass(bl_hand_reference_inputs, parameter, value, scalar_type):
    inputs = dict(bl_hand_reference_inputs, ordered_view_ids=[], **{parameter: scalar_type(value)})
    if parameter == "c_min":
        inputs["c_max"] = 10**6
    out, meta = apply_calibrated_black_litterman_overlay(**inputs)
    pd.testing.assert_series_equal(out, inputs["baseline_weights"], check_exact=True)
    assert meta["status"] == "k0_bypass"
    assert meta["reason"] == "K0_BYPASS"
    floating = dict(inputs, **{parameter: float(value)})
    assert apply_calibrated_black_litterman_overlay(**floating)[1] == meta


@pytest.mark.parametrize("parameter", ["gross_before", "gross_after", "cost_before", "cost_after"])
@pytest.mark.parametrize("value", [10**1000, -(10**1000)], ids=["positive", "negative"])
def test_w6_decay_oversized_integer_rejected(base_timestamps, parameter, value):
    with pytest.raises(ValueError, match="must be finite"):
        make_decay_payload(*base_timestamps, **{parameter: value})


@pytest.mark.parametrize("parameter", ["gross_before", "gross_after", "cost_before", "cost_after"])
@pytest.mark.parametrize("value", [10**1000, -(10**1000)], ids=["positive", "negative"])
def test_w6_queue_oversized_decay_payload_rejected(tmp_path, base_timestamps, monkeypatch, parameter, value):
    queue = W6ReviewQueue(tmp_path / "oversized_payload.db")
    payload = make_decay_payload(*base_timestamps)
    queue.enqueue(payload["decision_id"], payload["canonical_digest"], payload["attribution"], "drift_detected", payload)
    before = queue.queue_path.read_bytes()
    forged = dict(payload, **{parameter: value})
    forged["canonical_digest"] = hashlib.sha256(_canonical({k: v for k, v in forged.items() if k != "canonical_digest"})).hexdigest()

    def unexpected_connect(*args, **kwargs):
        raise AssertionError("invalid payload opened database")

    with monkeypatch.context() as patch:
        patch.setattr(queue, "_connect", unexpected_connect)
        with pytest.raises(ValueError, match="payload rebuild validation failed"):
            queue.enqueue(forged["decision_id"], forged["canonical_digest"], forged["attribution"], "drift_detected", forged)
        with pytest.raises(ValueError, match="payload rebuild validation failed"):
            ContinuousLearningEngine(review_queue=queue).enqueue_shadow_review(forged)
    assert queue.queue_path.read_bytes() == before
    assert queue.count() == 1
    assert queue.get(payload["decision_id"])["payload"] == payload


@pytest.mark.parametrize("timeout", [10**1000, -(10**1000)], ids=["positive", "negative"])
def test_w6_queue_oversized_timeout_rejected_before_db(tmp_path, monkeypatch, timeout):
    def unexpected_connect(*args, **kwargs):
        raise AssertionError("invalid timeout opened database")

    monkeypatch.setattr(sqlite3, "connect", unexpected_connect)
    path = tmp_path / "oversized_timeout.db"
    with pytest.raises(ValueError, match="timeout must be finite"):
        W6ReviewQueue(path, timeout=timeout)
    assert not path.exists()


# =====================================================================
# DATA GUARD TESTS
# =====================================================================

def test_w6_guard_immutable_frame_annotation_invariance(base_timestamps):
    cutoff, _ = base_timestamps
    df = make_valid_guard_df(cutoff)
    df_snapshot = df.copy(deep=True)

    labels = (
        None,
        "valid_market_breakout",
        "unadjusted_corporate_action_gap",
        "block_trade_noise",
        "stale_feed_error",
    )
    digests: List[str] = []
    raw_digests: List[str] = []

    for label in labels:
        res = validate_shadow_data_guard(df, cutoff=cutoff, annotation=label)
        assert res["status"] == "valid"
        assert res["reasons"] == []
        assert res["advisory_only"] is True
        assert res["applied"] is False
        digests.append(res["canonical_digest"])
        raw_digests.append(res["raw_digest"])

    # Digest invariance across all annotations
    assert len(set(digests)) == 1
    assert len(set(raw_digests)) == 1

    # Frame immutability verified
    pd.testing.assert_frame_equal(df, df_snapshot)

    # Invalid anomaly annotation rejected
    with pytest.raises(ValueError, match="invalid anomaly annotation"):
        validate_shadow_data_guard(df, cutoff=cutoff, annotation="unauthorized_label")


def test_w6_guard_quarantine_violations(base_timestamps):
    cutoff, _ = base_timestamps
    valid_df = make_valid_guard_df(cutoff)

    # PIT order violation: observed (as_of) > available_at
    pit_df = valid_df.copy()
    pit_df["as_of"] = pit_df["available_at"] + timedelta(minutes=1)
    res_pit = validate_shadow_data_guard(pit_df, cutoff=cutoff)
    assert res_pit["status"] == "quarantined"
    assert "PIT_ORDER" in res_pit["reasons"]

    # Not available: available_at > cutoff
    future_df = valid_df.copy()
    future_df["available_at"] = cutoff + timedelta(minutes=1)
    res_future = validate_shadow_data_guard(future_df, cutoff=cutoff)
    assert res_future["status"] == "quarantined"
    assert "NOT_AVAILABLE" in res_future["reasons"]

    # Non-positive price
    zero_df = valid_df.copy()
    zero_df.loc[0, "close"] = 0.0
    res_zero = validate_shadow_data_guard(zero_df, cutoff=cutoff)
    assert res_zero["status"] == "quarantined"
    assert "NON_POSITIVE_PRICE" in res_zero["reasons"]

    # Negative volume
    neg_vol_df = valid_df.copy()
    neg_vol_df.loc[0, "volume"] = -10.0
    res_vol = validate_shadow_data_guard(neg_vol_df, cutoff=cutoff)
    assert res_vol["status"] == "quarantined"
    assert "NEGATIVE_VOLUME" in res_vol["reasons"]

    # OHLC order invalid
    ohlc_df = valid_df.copy()
    ohlc_df.loc[0, "high"] = ohlc_df.loc[0, "open"] - 100.0  # high < open
    res_ohlc = validate_shadow_data_guard(ohlc_df, cutoff=cutoff)
    assert res_ohlc["status"] == "quarantined"
    assert "OHLC_ORDER" in res_ohlc["reasons"]

    # Duplicate symbol + as_of
    dup_df = pd.concat([valid_df.iloc[:1], valid_df.iloc[:1]], ignore_index=True)
    res_dup = validate_shadow_data_guard(dup_df, cutoff=cutoff)
    assert res_dup["status"] == "quarantined"
    assert "DUPLICATE" in res_dup["reasons"]


def test_w6_guard_schema_and_finite_bounds(base_timestamps):
    cutoff, _ = base_timestamps
    valid_df = make_valid_guard_df(cutoff)

    # Missing column
    bad_schema = valid_df.drop(columns=["volume"])
    with pytest.raises(ValueError, match="invalid guard schema or units"):
        validate_shadow_data_guard(bad_schema, cutoff=cutoff)

    # Non-finite values
    nan_df = valid_df.copy()
    nan_df.loc[0, "open"] = np.nan
    with pytest.raises(ValueError, match="non-finite guard values"):
        validate_shadow_data_guard(nan_df, cutoff=cutoff)

    # Price units must be VND_FULL
    with pytest.raises(ValueError, match="invalid guard schema or units"):
        validate_shadow_data_guard(valid_df, cutoff=cutoff, price_units="USD")

    # Frame exceeding 10000 rows
    big_df = pd.concat([valid_df] * 5001, ignore_index=True)
    with pytest.raises(ValueError, match="invalid guard frame"):
        validate_shadow_data_guard(big_df, cutoff=cutoff)


def test_w6_guard_timezone_utc_ict_equivalence(base_timestamps):
    cutoff_utc, _ = base_timestamps
    ict_zone = timezone(timedelta(hours=7))
    cutoff_ict = cutoff_utc.astimezone(ict_zone)

    df_utc = make_valid_guard_df(cutoff_utc)
    df_ict = df_utc.copy()
    df_ict["as_of"] = df_ict["as_of"].dt.tz_convert(ict_zone)
    df_ict["available_at"] = df_ict["available_at"].dt.tz_convert(ict_zone)

    res_utc = validate_shadow_data_guard(df_utc, cutoff=cutoff_utc)
    res_ict = validate_shadow_data_guard(df_ict, cutoff=cutoff_ict)

    assert res_utc["cutoff"] == res_ict["cutoff"]
    assert res_utc["status"] == res_ict["status"] == "valid"


def test_w6_guard_lag_and_leakage_helpers():
    ts = pd.date_range("2026-09-01", periods=5, freq="D", tz="UTC")
    df = pd.DataFrame({"time": ts, "price": [10.0, 11.0, 12.0, 13.0, 14.0]})

    # Monotonicity helper
    verify_no_lookahead(df, time_col="time")
    bad_df = df.copy()
    bad_df.loc[2, "time"] = ts[1]
    with pytest.raises(ValueError, match="not strictly monotonic"):
        verify_no_lookahead(bad_df, time_col="time")

    # T-1 lag enforcement
    lagged = enforce_t_minus_1_lag(df, columns=["price"])
    assert pd.isna(lagged.loc[0, "price"])
    assert lagged.loc[1, "price"] == 10.0

    # Leakage checker
    check_leakage(df, time_col="time", cutoff_time=ts[-1])
    with pytest.raises(ValueError, match="Leakage detected"):
        check_leakage(df, time_col="time", cutoff_time=ts[2])


# =====================================================================
# DECAY ATTRIBUTION TESTS
# =====================================================================

def test_w6_decay_delta_identity_and_decomposition(base_timestamps):
    cutoff, maturity = base_timestamps
    gb, ga = 0.12, 0.09
    cb, ca = 0.02, 0.04

    res = attach_decay_attribution(
        gross_before=gb,
        gross_after=ga,
        cost_before=cb,
        cost_after=ca,
        trigger_detected=True,
        cutoff=cutoff,
        maturity=maturity,
    )

    # Arithmetic decomposition identity
    net_b = gb - cb
    net_a = ga - ca
    d_gross = ga - gb
    d_cost = ca - cb
    d_net = net_a - net_b

    assert res["net_before"] == pytest.approx(net_b)
    assert res["net_after"] == pytest.approx(net_a)
    assert res["delta_gross"] == pytest.approx(d_gross)
    assert res["delta_cost"] == pytest.approx(d_cost)
    assert res["delta_net"] == pytest.approx(d_net)
    assert math.isclose(res["delta_net"], res["delta_gross"] - res["delta_cost"], abs_tol=1e-12)

    # Advisory & safety invariants
    assert res["advisory_only"] is True
    assert res["applied"] is False
    assert res["auto_retrain_executed"] is False
    assert res["auto_promote_executed"] is False
    assert res["execution_status"] == "no_execution"
    assert res["schema_version"] == W6_DECAY_SCHEMA_VERSION


def test_w6_decay_ambiguous_evidence_resolution(base_timestamps):
    cutoff, maturity = base_timestamps

    # Competing evidence cannot be overridden by explicit request
    res = attach_decay_attribution(
        gross_before=0.10,
        gross_after=0.08,
        cost_before=0.01,
        cost_after=0.02,
        trigger_detected=True,
        cutoff=cutoff,
        maturity=maturity,
        data_issue_flag=True,
        regime_mismatch_flag=True,
        attribution="data_issue",
    )
    assert res["attribution"] == "unclear"
    assert res["recommendation"] == "wait"


def test_w6_decay_regime_mismatch_default_noise(base_timestamps):
    cutoff, maturity = base_timestamps
    res = attach_decay_attribution(
        gross_before=0.10,
        gross_after=0.08,
        cost_before=0.01,
        cost_after=0.01,
        trigger_detected=True,
        cutoff=cutoff,
        maturity=maturity,
        regime_mismatch_flag=True,
    )
    assert res["attribution"] == "regime_mismatch"
    assert res["recommendation"] == "incremental_update"
    assert res["drift_label"] == "noise"


def test_w6_decay_trigger_required_unless_synthetic(base_timestamps):
    cutoff, maturity = base_timestamps

    # Trigger detected False without synthetic raises
    with pytest.raises(ValueError, match="trigger required for decay attribution"):
        attach_decay_attribution(
            gross_before=0.10,
            gross_after=0.08,
            cost_before=0.01,
            cost_after=0.02,
            trigger_detected=False,
            cutoff=cutoff,
            maturity=maturity,
            synthetic=False,
        )

    # Synthetic allows trigger_detected=False
    res_syn = attach_decay_attribution(
        gross_before=0.10,
        gross_after=0.08,
        cost_before=0.01,
        cost_after=0.02,
        trigger_detected=False,
        cutoff=cutoff,
        maturity=maturity,
        synthetic=True,
    )
    assert res_syn["synthetic"] is True
    assert res_syn["trigger_detected"] is False


def test_w6_decay_finite_and_pit_validation(base_timestamps):
    cutoff, maturity = base_timestamps

    # Non-finite values
    with pytest.raises((ValueError, TypeError)):
        attach_decay_attribution(
            gross_before=float("nan"),
            gross_after=0.08,
            cost_before=0.01,
            cost_after=0.02,
            trigger_detected=True,
            cutoff=cutoff,
            maturity=maturity,
        )

    # Negative costs
    with pytest.raises(ValueError, match="costs must be non-negative"):
        attach_decay_attribution(
            gross_before=0.10,
            gross_after=0.08,
            cost_before=-0.01,
            cost_after=0.02,
            trigger_detected=True,
            cutoff=cutoff,
            maturity=maturity,
        )

    # Maturity exceeds cutoff
    with pytest.raises(ValueError, match="PIT violation: maturity exceeds cutoff"):
        attach_decay_attribution(
            gross_before=0.10,
            gross_after=0.08,
            cost_before=0.01,
            cost_after=0.02,
            trigger_detected=True,
            cutoff=cutoff,
            maturity=cutoff + timedelta(days=1),
        )


def test_w6_decay_identifiers_and_secrets_sanitized(base_timestamps):
    cutoff, maturity = base_timestamps

    # Identifier containing invalid characters (spaces, tokens, semicolons)
    with pytest.raises(ValueError, match="decision_id invalid format"):
        attach_decay_attribution(
            gross_before=0.10,
            gross_after=0.08,
            cost_before=0.01,
            cost_after=0.02,
            trigger_detected=True,
            cutoff=cutoff,
            maturity=maturity,
            decision_id="DECAY ID WITH SPACES",
        )

    with pytest.raises(ValueError, match="unsupported decay context"):
        attach_decay_attribution(
            gross_before=0.10,
            gross_after=0.08,
            cost_before=0.01,
            cost_after=0.02,
            trigger_detected=True,
            cutoff=cutoff,
            maturity=maturity,
            gate_id="GATE;DROP TABLE review_queue",
        )


def test_w6_identifier_generation_and_fullmatch(base_timestamps):
    cutoff, maturity = base_timestamps

    # 1. Default generation produces valid fullmatch identifier without newlines
    payload_gen = attach_decay_attribution(
        gross_before=0.10,
        gross_after=0.08,
        cost_before=0.01,
        cost_after=0.02,
        trigger_detected=True,
        cutoff=cutoff,
        maturity=maturity,
        decision_id=None,
    )
    gen_id = payload_gen["decision_id"]
    assert re.fullmatch(r"^[A-Za-z0-9_.\-]{1,128}$", gen_id) is not None
    assert not gen_id.endswith("\n")
    assert not gen_id.endswith("\r\n")
    assert 1 <= len(gen_id) <= 128

    # 2. Valid boundary decision_id and source_revision
    for valid_id in VALID_BOUNDARY_IDENTIFIERS:
        p = attach_decay_attribution(
            gross_before=0.10,
            gross_after=0.08,
            cost_before=0.01,
            cost_after=0.02,
            trigger_detected=True,
            cutoff=cutoff,
            maturity=maturity,
            decision_id=valid_id,
            source_revision=valid_id,
        )
        assert p["decision_id"] == valid_id
        assert p["source_revision"] == valid_id
        assert re.fullmatch(r"^[A-Za-z0-9_.\-]{1,128}$", p["decision_id"]) is not None
        assert re.fullmatch(r"^[A-Za-z0-9_.\-]{1,128}$", p["source_revision"]) is not None

    # 3. Invalid decision_id rejected
    for invalid_id in INVALID_FULLMATCH_IDENTIFIERS + [x for x in NONSTRING_FULLMATCH_IDENTIFIERS if x is not None]:
        with pytest.raises((ValueError, TypeError)):
            attach_decay_attribution(
                gross_before=0.10,
                gross_after=0.08,
                cost_before=0.01,
                cost_after=0.02,
                trigger_detected=True,
                cutoff=cutoff,
                maturity=maturity,
                decision_id=invalid_id,
            )

    # 4. Invalid source_revision rejected
    for invalid_rev in INVALID_FULLMATCH_IDENTIFIERS + NONSTRING_FULLMATCH_IDENTIFIERS:
        with pytest.raises((ValueError, TypeError)):
            attach_decay_attribution(
                gross_before=0.10,
                gross_after=0.08,
                cost_before=0.01,
                cost_after=0.02,
                trigger_detected=True,
                cutoff=cutoff,
                maturity=maturity,
                source_revision=invalid_rev,
            )


def test_w6_validate_payload_forged_and_invalid_decision_id(base_timestamps):
    cutoff, maturity = base_timestamps
    payload = make_decay_payload(cutoff, maturity, decision_id="VALID_DECISION_ID")

    # 1. Valid payload passes
    digest = _validate_payload(payload, expected_item_id="VALID_DECISION_ID")
    assert digest == payload["canonical_digest"]

    # 2. Forged decision_id rejected
    forged = dict(payload)
    forged["decision_id"] = "FORGED_ANOTHER_VALID_ID"
    with pytest.raises(ValueError):
        _validate_payload(forged)

    # 3. Expected item_id mismatch rejected
    with pytest.raises(ValueError, match="item_id mismatch against decision_id"):
        _validate_payload(payload, expected_item_id="MISMATCHED_ITEM_ID")

    # 4. Invalid decision_id values rejected
    for invalid_id in INVALID_FULLMATCH_IDENTIFIERS + NONSTRING_FULLMATCH_IDENTIFIERS:
        bad_payload = dict(payload)
        bad_payload["decision_id"] = invalid_id
        with pytest.raises((ValueError, TypeError)):
            _validate_payload(bad_payload)

    # 5. Valid boundary decision_id values pass
    for valid_id in VALID_BOUNDARY_IDENTIFIERS:
        p_boundary = make_decay_payload(cutoff, maturity, decision_id=valid_id)
        d = _validate_payload(p_boundary, expected_item_id=valid_id)
        assert d == p_boundary["canonical_digest"]


# =====================================================================
# REVIEW QUEUE TESTS
# =====================================================================

@pytest.mark.parametrize("parameter,state", [
    (parameter, state)
    for parameter in ("created_at", "expires_at")
    for state in ("empty", "new", "duplicate", "conflict", "capacity", "locked")
] + [("as_of", state) for state in ("empty", "new", "locked")])
@pytest.mark.parametrize("invalid_kind", ["naive", "undefined-offset", "normalization-trap", "offset-error"])
def test_w6_queue_invalid_datetime_rejected_before_io_preserves_state(
    tmp_path, base_timestamps, monkeypatch, parameter, state, invalid_kind,
):
    class UndefinedOffset(tzinfo):
        def utcoffset(self, dt):
            return None

    class FaultyOffset(tzinfo):
        def utcoffset(self, dt):
            raise RuntimeError("injected UTC offset failure")

    class NoNormalizationDatetime(datetime):
        def astimezone(self, *args, **kwargs):
            raise AssertionError("invalid datetime reached normalization")

    cutoff, maturity = base_timestamps
    queue = W6ReviewQueue(tmp_path / "invalid_datetime.db", max_capacity=1 if state == "capacity" else 10, timeout=0.01)
    original = make_decay_payload(cutoff, maturity, decision_id="TIME_ORIGINAL")
    if state != "empty":
        queue.enqueue(original["decision_id"], original["canonical_digest"], original["attribution"], "drift_detected", original)
    candidate = original if state in ("duplicate", "conflict") else make_decay_payload(
        cutoff, maturity, decision_id="TIME_NEW",
    )
    value = cutoff + timedelta(days=1) if parameter == "expires_at" else cutoff
    zone = None if invalid_kind == "naive" else FaultyOffset() if invalid_kind == "offset-error" else UndefinedOffset()
    dt_type = NoNormalizationDatetime if invalid_kind == "normalization-trap" else datetime
    invalid = dt_type.fromisoformat(value.isoformat()).replace(tzinfo=zone)

    def unexpected_connect(*args, **kwargs):
        raise AssertionError("invalid datetime opened database")

    with closing(sqlite3.connect(queue.queue_path, isolation_level=None)) as conn:
        conn.execute("PRAGMA journal_mode=DELETE")
        if state == "locked":
            conn.execute("BEGIN EXCLUSIVE")
        before = queue_database_snapshot(conn)
        before_bytes = queue.queue_path.read_bytes()
        try:
            with monkeypatch.context() as patch:
                patch.setattr(sqlite3, "connect", unexpected_connect)
                error = RuntimeError if invalid_kind == "offset-error" else ValueError
                message = "injected UTC offset failure" if invalid_kind == "offset-error" else f"{parameter} must be aware datetime"
                with pytest.raises(error, match=message):
                    if parameter == "as_of":
                        queue.peek(as_of=invalid)
                    else:
                        queue.enqueue(
                            candidate["decision_id"], candidate["canonical_digest"], candidate["attribution"],
                            "synthetic_event" if state == "conflict" else "drift_detected", candidate,
                            **{parameter: invalid},
                        )
            assert queue_database_snapshot(conn) == before
            assert queue.queue_path.read_bytes() == before_bytes
            assert not queue.queue_path.with_name(queue.queue_path.name + "-wal").exists()
            assert not queue.queue_path.with_name(queue.queue_path.name + "-shm").exists()
        finally:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
    restarted = W6ReviewQueue(queue.queue_path)
    assert restarted.count() == (0 if state == "empty" else 1)
    if state != "empty":
        assert restarted.get(original["decision_id"])["payload"] == original
        assert restarted.get(original["decision_id"])["status"] == "pending"


@pytest.mark.parametrize("variant", ["created_at", "expires_at", "both", "defaults"])
def test_w6_queue_utc_ict_equivalence_and_defaults(tmp_path, base_timestamps, variant):
    cutoff, maturity = base_timestamps
    ict = timezone(timedelta(hours=7))
    expiry = cutoff + timedelta(days=1)
    queue = W6ReviewQueue(tmp_path / "equivalent_datetime.db")
    payload = make_decay_payload(cutoff, maturity, decision_id="TIME_EQUIVALENT")
    args = (payload["decision_id"], payload["canonical_digest"], payload["attribution"], "drift_detected", payload)
    assert queue.enqueue(*args, created_at=cutoff, expires_at=expiry)["status"] == "enqueued"
    before = queue.get(payload["decision_id"])
    kwargs = {} if variant == "defaults" else {
        "created_at": cutoff.astimezone(ict) if variant in ("created_at", "both") else cutoff,
        "expires_at": expiry.astimezone(ict) if variant in ("expires_at", "both") else expiry,
    }
    assert queue.enqueue(*args, **kwargs)["status"] == "idempotent_duplicate"
    assert queue.get(payload["decision_id"]) == before
    assert before["created_at"] == cutoff.isoformat()
    assert before["expires_at"] == expiry.isoformat()
    for instant, expected in (
        (cutoff - timedelta(microseconds=1), None), (cutoff, before),
        (expiry - timedelta(microseconds=1), before), (expiry, None),
    ):
        assert queue.peek(instant) == queue.peek(instant.astimezone(ict)) == expected
    assert queue.count() == 1
    assert queue.mark_reviewed(payload["decision_id"]) is True
    assert queue.peek(cutoff) is queue.peek(cutoff.astimezone(ict)) is None
    duplicate = queue.enqueue(*args, **kwargs)
    assert duplicate["status"] == "idempotent_duplicate"
    assert duplicate["review_status"] == "reviewed"


def test_w6_queue_tmp_path_per_call_and_lifecycle(tmp_path, base_timestamps):
    cutoff, maturity = base_timestamps
    db_file = tmp_path / "review_queue.db"
    queue = W6ReviewQueue(queue_path=db_file, max_capacity=10)

    payload = make_decay_payload(cutoff, maturity, decision_id="ITEM_001")
    item_id = payload["decision_id"]
    digest = payload["canonical_digest"]
    cat = payload["attribution"]

    enq_res = queue.enqueue(
        item_id=item_id,
        canonical_digest=digest,
        review_category=cat,
        trigger_reason="drift_detected",
        payload=payload,
    )
    assert enq_res["status"] == "enqueued"
    assert enq_res["review_status"] == "pending"
    assert queue.count() == 1
    assert queue.count(status="pending") == 1

    # Peek item using explicit as_of for deterministic filtering
    peeked = queue.peek(as_of=cutoff)
    assert peeked is not None
    assert peeked["item_id"] == item_id
    assert peeked["canonical_digest"] == digest
    assert peeked["status"] == "pending"

    # Get item
    fetched = queue.get(item_id)
    assert fetched is not None
    assert fetched["item_id"] == item_id

    # Mark reviewed
    assert queue.mark_reviewed(item_id, resolution="reviewed") is True
    assert queue.count(status="reviewed") == 1
    assert queue.count(status="pending") == 0
    assert queue.peek(as_of=cutoff) is None


def test_w6_queue_idempotency_and_conflict(tmp_path, base_timestamps):
    cutoff, maturity = base_timestamps
    queue = W6ReviewQueue(tmp_path / "queue_idem.db")
    payload = make_decay_payload(cutoff, maturity, decision_id="ITEM_IDEM")

    # First enqueue
    r1 = queue.enqueue(
        item_id=payload["decision_id"],
        canonical_digest=payload["canonical_digest"],
        review_category=payload["attribution"],
        trigger_reason="drift_detected",
        payload=payload,
    )
    assert r1["status"] == "enqueued"

    # Exact duplicate: idempotent
    r2 = queue.enqueue(
        item_id=payload["decision_id"],
        canonical_digest=payload["canonical_digest"],
        review_category=payload["attribution"],
        trigger_reason="drift_detected",
        payload=payload,
    )
    assert r2["status"] == "idempotent_duplicate"
    assert queue.count() == 1

    # Conflict: valid alternative trigger_reason (synthetic_event) causes metadata mismatch
    with pytest.raises(ValueError, match="Queue conflict: item_id 'ITEM_IDEM' exists with different metadata"):
        queue.enqueue(
            item_id=payload["decision_id"],
            canonical_digest=payload["canonical_digest"],
            review_category=payload["attribution"],
            trigger_reason="synthetic_event",
            payload=payload,
        )


def test_w6_queue_mutated_payload_and_forged_rehash_rejection(tmp_path, base_timestamps):
    cutoff, maturity = base_timestamps
    queue = W6ReviewQueue(tmp_path / "queue_mutate.db")
    payload = make_decay_payload(cutoff, maturity, decision_id="ITEM_MUT")

    # Mismatched rebuild upon tampering
    with pytest.raises(ValueError, match="rebuilt payload|validation failed|canonical_digest"):
        queue.enqueue(
            item_id=payload["decision_id"],
            canonical_digest=payload["canonical_digest"],
            review_category=payload["attribution"],
            trigger_reason="drift_detected",
            payload={**payload, "delta_gross": 999.0},
        )

    # Authority forged rehash cannot turn an inert recommendation into execution.
    forged = dict(payload)
    forged["applied"] = True
    from omega.core.llm_config import _canonical
    raw_forged = _canonical({k: v for k, v in forged.items() if k != "canonical_digest"})
    forged["canonical_digest"] = hashlib.sha256(raw_forged).hexdigest()

    with pytest.raises(ValueError, match="rebuilt payload does not match input payload identically"):
        queue.enqueue(
            item_id=forged["decision_id"],
            canonical_digest=forged["canonical_digest"],
            review_category=forged["attribution"],
            trigger_reason="drift_detected",
            payload=forged,
        )


def test_w6_queue_capacity_strict_cap(tmp_path, base_timestamps):
    cutoff, maturity = base_timestamps
    queue = W6ReviewQueue(tmp_path / "queue_cap.db", max_capacity=2)

    p1 = make_decay_payload(cutoff, maturity, decision_id="ITEM_C1")
    p2 = make_decay_payload(cutoff, maturity, decision_id="ITEM_C2")
    p3 = make_decay_payload(cutoff, maturity, decision_id="ITEM_C3")

    queue.enqueue(p1["decision_id"], p1["canonical_digest"], p1["attribution"], "drift_detected", p1)
    queue.enqueue(p2["decision_id"], p2["canonical_digest"], p2["attribution"], "drift_detected", p2)

    with pytest.raises(ValueError, match="Queue capacity exceeded: total rows 2 >= max 2"):
        queue.enqueue(p3["decision_id"], p3["canonical_digest"], p3["attribution"], "drift_detected", p3)

    assert queue.count() == 2


def test_w6_queue_expiry_filtering_and_equality(tmp_path, base_timestamps):
    cutoff, maturity = base_timestamps
    queue = W6ReviewQueue(tmp_path / "queue_exp.db")

    # Expired past item: valid lifecycle earlier in history
    cutoff_past = cutoff - timedelta(days=5)
    mat_past = cutoff - timedelta(days=6)
    p_past = make_decay_payload(cutoff_past, mat_past, decision_id="ITEM_EXP_PAST")
    created_past = cutoff_past
    expires_past = cutoff - timedelta(days=4)

    queue.enqueue(
        p_past["decision_id"], p_past["canonical_digest"], p_past["attribution"], "drift_detected", p_past,
        created_at=created_past, expires_at=expires_past,
    )

    # Active future item
    p_fut = make_decay_payload(cutoff, maturity, decision_id="ITEM_EXP_FUT")
    created_fut = cutoff
    expires_fut = cutoff + timedelta(days=1)
    queue.enqueue(
        p_fut["decision_id"], p_fut["canonical_digest"], p_fut["attribution"], "drift_detected", p_fut,
        created_at=created_fut, expires_at=expires_fut,
    )

    # Expiry equality boundary item: expires_at == as_of (not strictly > as_of)
    cutoff_eq = cutoff - timedelta(hours=2)
    mat_eq = cutoff - timedelta(hours=3)
    p_eq = make_decay_payload(cutoff_eq, mat_eq, decision_id="ITEM_EXP_EQUAL")
    queue.enqueue(
        p_eq["decision_id"], p_eq["canonical_digest"], p_eq["attribution"], "drift_detected", p_eq,
        created_at=cutoff_eq, expires_at=cutoff,
    )

    # Peek at exact cutoff: p_past is expired, p_eq expires_at == cutoff (filtered out), p_fut is returned
    peeked = queue.peek(as_of=cutoff)
    assert peeked is not None
    assert peeked["item_id"] == "ITEM_EXP_FUT"

    # Query 1 second before cutoff: p_eq is active (expires_at > as_of) and returned before p_fut (created earlier)
    peeked_before = queue.peek(as_of=cutoff - timedelta(seconds=1))
    assert peeked_before is not None
    assert peeked_before["item_id"] == "ITEM_EXP_EQUAL"

    # Mark expired
    assert queue.mark_reviewed("ITEM_EXP_PAST", resolution="expired") is True
    assert queue.count(status="expired") == 1


def test_w6_queue_restart_persistence(tmp_path, base_timestamps):
    cutoff, maturity = base_timestamps
    db_file = tmp_path / "queue_persist.db"

    q1 = W6ReviewQueue(db_file)
    payload = make_decay_payload(cutoff, maturity, decision_id="ITEM_PERSIST")
    q1.enqueue(payload["decision_id"], payload["canonical_digest"], payload["attribution"], "drift_detected", payload)
    del q1

    # Restart
    q2 = W6ReviewQueue(db_file)
    fetched = q2.get("ITEM_PERSIST")
    assert fetched is not None
    assert fetched["item_id"] == "ITEM_PERSIST"
    assert fetched["canonical_digest"] == payload["canonical_digest"]


def test_w6_queue_concurrent_enqueue(tmp_path, base_timestamps):
    cutoff, maturity = base_timestamps
    db_file = tmp_path / "queue_conc.db"
    queue = W6ReviewQueue(db_file, max_capacity=50)

    payloads = [
        make_decay_payload(cutoff, maturity, decision_id=f"ITEM_CONC_{i}")
        for i in range(10)
    ]

    def _worker(p: Dict[str, Any]):
        return queue.enqueue(p["decision_id"], p["canonical_digest"], p["attribution"], "drift_detected", p)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(_worker, payloads))

    assert len(results) == 10
    assert all(r["status"] == "enqueued" for r in results)
    assert queue.count() == 10


def test_w6_queue_owned_lock_timeout(tmp_path, base_timestamps):
    cutoff, maturity = base_timestamps
    db_file = tmp_path / "queue_lock.db"
    queue = W6ReviewQueue(db_file, timeout=0.05)
    payload = make_decay_payload(cutoff, maturity, decision_id="ITEM_LOCK")

    # Acquire exclusive external lock
    lock_conn = sqlite3.connect(str(db_file), timeout=0.01)
    lock_conn.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            queue.enqueue(payload["decision_id"], payload["canonical_digest"], payload["attribution"], "drift_detected", payload)
    finally:
        lock_conn.execute("COMMIT")
        lock_conn.close()


def test_w6_queue_corruption_rollback_via_trigger(tmp_path, base_timestamps):
    cutoff, maturity = base_timestamps
    db_file = tmp_path / "queue_trig.db"
    queue = W6ReviewQueue(db_file)
    payload = make_decay_payload(cutoff, maturity, decision_id="ITEM_TRIG")

    # Install trigger that forces failure during insert
    with queue._connect(write=True) as conn:
        conn.execute("""
            CREATE TRIGGER trigger_fail_insert
            BEFORE INSERT ON review_queue
            BEGIN
                SELECT RAISE(FAIL, 'simulated corruption trigger');
            END;
        """)

    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="simulated corruption trigger"):
        queue.enqueue(payload["decision_id"], payload["canonical_digest"], payload["attribution"], "drift_detected", payload)

    # Transaction rolled back, count remains 0
    assert queue.count() == 0


def test_w6_queue_adversarial_stored_corruption_and_duplicate_json(tmp_path, base_timestamps):
    cutoff, maturity = base_timestamps
    db_file = tmp_path / "queue_adv.db"
    queue = W6ReviewQueue(db_file)
    payload = make_decay_payload(cutoff, maturity, decision_id="ITEM_ADV")
    queue.enqueue(payload["decision_id"], payload["canonical_digest"], payload["attribution"], "drift_detected", payload)

    # Corrupt stored metadata_digest
    with queue._connect(write=True) as conn:
        conn.execute("UPDATE review_queue SET metadata_digest = 'corrupted_metadata_digest' WHERE item_id = 'ITEM_ADV'")
    with pytest.raises(ValueError, match="corrupted row metadata_digest mismatch"):
        queue.get("ITEM_ADV")

    # Corrupt stored status
    with queue._connect(write=True) as conn:
        conn.execute("UPDATE review_queue SET status = 'unauthorized_status' WHERE item_id = 'ITEM_ADV'")
    with pytest.raises(ValueError, match="corrupted row status"):
        queue.get("ITEM_ADV")

    # Corrupt stored trigger_reason
    with queue._connect(write=True) as conn:
        conn.execute("UPDATE review_queue SET status = 'pending', trigger_reason = 'unauthorized_reason' WHERE item_id = 'ITEM_ADV'")
    with pytest.raises(ValueError, match="corrupted row trigger_reason"):
        queue.get("ITEM_ADV")

    # Duplicate key in stored JSON
    dup_json = '{"decision_id":"ITEM_ADV","decision_id":"ITEM_ADV"}'
    with queue._connect(write=True) as conn:
        conn.execute("UPDATE review_queue SET payload_json = ? WHERE item_id = 'ITEM_ADV'", (dup_json,))
    with pytest.raises(ValueError, match="duplicate key in json"):
        _parse_strict_json(dup_json)


def test_w6_queue_mark_reviewed_corruption_handling(tmp_path, base_timestamps):
    cutoff, maturity = base_timestamps
    db_file = tmp_path / "queue_mark_adv.db"
    queue = W6ReviewQueue(db_file)
    payload = make_decay_payload(cutoff, maturity, decision_id="ITEM_MARK")
    queue.enqueue(payload["decision_id"], payload["canonical_digest"], payload["attribution"], "drift_detected", payload)

    # Tamper with stored metadata before mark_reviewed
    with queue._connect(write=True) as conn:
        conn.execute("UPDATE review_queue SET metadata_digest = 'bad_digest' WHERE item_id = 'ITEM_MARK'")

    with pytest.raises(ValueError, match="corrupted row metadata_digest mismatch"):
        queue.mark_reviewed("ITEM_MARK", resolution="reviewed")


@pytest.mark.parametrize("schema", [
    "CREATE TABLE review_queue (item_id TEXT PRIMARY KEY, status TEXT, expires_at TEXT)",
    "CREATE VIEW review_queue AS SELECT 'x' AS item_id, 'pending' AS status, 'x' AS expires_at",
    "CREATE TABLE REVIEW_QUEUE (item_id INTEGER PRIMARY KEY)",
], ids=["drifted-table", "view", "case-variant"])
def test_w6_queue_schema_rejection_preserves_database(tmp_path, schema):
    db_file = tmp_path / "schema.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute(schema)
        before_schema = conn.execute("SELECT * FROM sqlite_schema").fetchall()
        assert conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    before = db_file.read_bytes()
    with pytest.raises(ValueError, match="schema drift"):
        W6ReviewQueue(db_file)
    assert db_file.read_bytes() == before
    assert not (tmp_path / "schema.db-wal").exists()
    assert not (tmp_path / "schema.db-shm").exists()
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT * FROM sqlite_schema").fetchall() == before_schema
        assert conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)


@pytest.mark.parametrize("nullable_col", W6_REVIEW_QUEUE_NON_KEY_COLUMNS)
def test_w6_queue_constructor_rejects_nullable_column_drift(tmp_path, nullable_col):
    db_file = tmp_path / f"schema_nullable_{nullable_col}.db"
    schema = make_review_queue_schema_with_nullable_column(nullable_col)
    with sqlite3.connect(db_file) as conn:
        conn.execute(schema)
        conn.execute("CREATE TABLE sentinel_data (key TEXT PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO sentinel_data VALUES ('sentinel_k', 'sentinel_v')")
        conn.execute(
            "INSERT INTO review_queue VALUES ('ITEM_SENTINEL', 'a' * 64, 'unclear', 'drift_detected', "
            "'2026-09-30T09:00:00+00:00', '2026-10-01T09:00:00+00:00', 'pending', '{}', 'm' * 64)"
        )
        conn.commit()
        conn.execute("PRAGMA journal_mode=DELETE")
        info = conn.execute("PRAGMA table_info(review_queue)").fetchall()
        assert info[0][1] == "item_id" and info[0][3] == 0 and info[0][5] == 1
        for row in info[1:]:
            if row[1] == nullable_col:
                assert row[3] == 0
            else:
                assert row[3] == 1
        before_schema = conn.execute("SELECT * FROM sqlite_schema ORDER BY name").fetchall()
        before_sentinel = conn.execute("SELECT * FROM sentinel_data").fetchall()
        before_queue = conn.execute("SELECT * FROM review_queue").fetchall()
        before_indexes = conn.execute("SELECT name FROM sqlite_schema WHERE type='index' ORDER BY name").fetchall()
        assert conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    before_bytes = db_file.read_bytes()
    with pytest.raises(ValueError, match="schema drift"):
        W6ReviewQueue(db_file)
    assert db_file.read_bytes() == before_bytes
    assert not (tmp_path / f"{db_file.name}-wal").exists()
    assert not (tmp_path / f"{db_file.name}-shm").exists()
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT * FROM sqlite_schema ORDER BY name").fetchall() == before_schema
        assert conn.execute("SELECT * FROM sentinel_data").fetchall() == before_sentinel
        assert conn.execute("SELECT * FROM review_queue").fetchall() == before_queue
        assert conn.execute("SELECT name FROM sqlite_schema WHERE type='index' ORDER BY name").fetchall() == before_indexes
        assert conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)


@pytest.mark.parametrize("operation", ["get", "peek", "count", "mark_reviewed", "enqueue"])
def test_w6_queue_runtime_schema_rejection(tmp_path, base_timestamps, operation):
    db_file = tmp_path / "runtime.db"
    queue = W6ReviewQueue(db_file)
    with sqlite3.connect(db_file) as conn:
        conn.execute("ALTER TABLE review_queue ADD COLUMN unexpected TEXT")
        conn.execute("PRAGMA journal_mode=DELETE")
    before = db_file.read_bytes()
    payload = make_decay_payload(*base_timestamps, decision_id="RUNTIME")
    calls = {
        "get": lambda: queue.get("RUNTIME"),
        "peek": queue.peek,
        "count": queue.count,
        "mark_reviewed": lambda: queue.mark_reviewed("RUNTIME"),
        "enqueue": lambda: queue.enqueue("RUNTIME", payload["canonical_digest"], payload["attribution"], "drift_detected", payload),
    }
    with pytest.raises(ValueError, match="schema drift"):
        calls[operation]()
    assert db_file.read_bytes() == before
    assert not (tmp_path / "runtime.db-wal").exists()


@pytest.mark.parametrize("operation", ["get", "peek", "count", "mark_reviewed", "enqueue"])
@pytest.mark.parametrize("nullable_col", W6_REVIEW_QUEUE_NON_KEY_COLUMNS)
def test_w6_queue_runtime_nullable_schema_rejection(tmp_path, base_timestamps, operation, nullable_col):
    cutoff, maturity = base_timestamps
    db_file = tmp_path / f"runtime_nullable_{operation}_{nullable_col}.db"
    queue = W6ReviewQueue(db_file)
    payload = make_decay_payload(cutoff, maturity, decision_id="RUNTIME_ITEM")
    queue.enqueue("RUNTIME_ITEM", payload["canonical_digest"], payload["attribution"], "drift_detected", payload)

    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE sentinel_runtime (key TEXT PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO sentinel_runtime VALUES ('sentinel_k', 'sentinel_v')")
        conn.execute("ALTER TABLE review_queue RENAME TO review_queue_orig")
        schema = make_review_queue_schema_with_nullable_column(nullable_col)
        conn.execute(schema)
        conn.execute("INSERT INTO review_queue SELECT * FROM review_queue_orig")
        conn.execute("DROP TABLE review_queue_orig")
        conn.execute("CREATE INDEX idx_review_queue_status ON review_queue(status)")
        conn.execute("CREATE INDEX idx_review_queue_expires ON review_queue(expires_at)")
        conn.commit()
        conn.execute("PRAGMA journal_mode=DELETE")
        before_schema = conn.execute("SELECT * FROM sqlite_schema ORDER BY name").fetchall()
        before_data = conn.execute("SELECT * FROM review_queue").fetchall()
        before_sentinel = conn.execute("SELECT * FROM sentinel_runtime").fetchall()
        before_indexes = conn.execute("SELECT name FROM sqlite_schema WHERE type='index' ORDER BY name").fetchall()
        assert conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    before_bytes = db_file.read_bytes()

    new_payload = make_decay_payload(cutoff, maturity, decision_id="RUNTIME_NEW")
    calls = {
        "get": lambda: queue.get("RUNTIME_ITEM"),
        "peek": queue.peek,
        "count": queue.count,
        "mark_reviewed": lambda: queue.mark_reviewed("RUNTIME_ITEM"),
        "enqueue": lambda: queue.enqueue(
            "RUNTIME_NEW",
            new_payload["canonical_digest"],
            new_payload["attribution"],
            "drift_detected",
            new_payload,
        ),
    }
    with pytest.raises(ValueError, match="schema drift"):
        calls[operation]()
    assert db_file.read_bytes() == before_bytes
    assert not (tmp_path / f"{db_file.name}-wal").exists()
    assert not (tmp_path / f"{db_file.name}-shm").exists()
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT * FROM sqlite_schema ORDER BY name").fetchall() == before_schema
        assert conn.execute("SELECT * FROM review_queue").fetchall() == before_data
        assert conn.execute("SELECT * FROM sentinel_runtime").fetchall() == before_sentinel
        assert conn.execute("SELECT name FROM sqlite_schema WHERE type='index' ORDER BY name").fetchall() == before_indexes
        assert conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)


@pytest.mark.parametrize("operation", QUEUE_WRITE_OPERATIONS + QUEUE_READ_OPERATIONS + ["initialize"])
def test_w6_queue_interleaved_schema_swap_fails_closed(tmp_path, base_timestamps, monkeypatch, operation):
    queue, payload = prepare_interleaving_queue(tmp_path, base_timestamps, operation)
    real_connect = sqlite3.connect
    connections, swapped = [], []

    class InterleavedConnection(sqlite3.Connection):
        def execute(self, sql, *args):
            result = super().execute(sql, *args)
            if sql == "PRAGMA synchronous=FULL" and not swapped:
                with closing(real_connect(queue.queue_path, isolation_level=None, timeout=0.01)) as other:
                    replace_queue_with_nullable_schema(other)
                    swapped.append(queue_database_snapshot(other))
            return result

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs, factory=InterleavedConnection)
        connections.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(ValueError, match="schema drift"):
        run_queue_operation(queue, payload, operation)
    assert len(swapped) == 1
    with closing(real_connect(queue.queue_path)) as conn:
        assert queue_database_snapshot(conn) == swapped[0]
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")


@pytest.mark.parametrize("operation", QUEUE_WRITE_OPERATIONS + ["initialize"])
def test_w6_queue_write_validation_blocks_external_schema_swap(tmp_path, base_timestamps, monkeypatch, operation):
    queue, payload = prepare_interleaving_queue(tmp_path, base_timestamps, operation)
    real_connect = sqlite3.connect
    original = W6ReviewQueue._validate_schema
    validation_calls = 0
    blocked = []

    def validate(conn, *, allow_missing=False):
        nonlocal validation_calls
        validation_calls += 1
        original(conn, allow_missing=allow_missing)
        if validation_calls == 2:
            with closing(real_connect(queue.queue_path, isolation_level=None, timeout=0.01)) as other:
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    replace_queue_with_nullable_schema(other)
                if other.in_transaction:
                    other.execute("ROLLBACK")
                blocked.append(True)

    with monkeypatch.context() as patch:
        patch.setattr(W6ReviewQueue, "_validate_schema", staticmethod(validate))
        if operation in ("enqueue-conflict", "enqueue-capacity"):
            with pytest.raises(ValueError, match="Queue conflict|Queue capacity"):
                run_queue_operation(queue, payload, operation)
        else:
            result = run_queue_operation(queue, payload, operation)
            if operation == "enqueue":
                assert result["status"] == "enqueued"
            elif operation == "enqueue-duplicate":
                assert result["status"] == "idempotent_duplicate"
            elif operation.startswith("mark-"):
                assert result is (operation in ("mark-reviewed", "mark-expired"))
    assert blocked == [True]
    with closing(real_connect(queue.queue_path)) as conn:
        original(conn)
    assert queue.count() == (2 if operation == "enqueue" else 1)
    expected = "expired" if operation == "mark-expired" else "reviewed" if operation in ("mark-reviewed", "mark-terminal") else "pending"
    assert queue.get(payload["decision_id"])["status"] == expected


@pytest.mark.parametrize("operation", QUEUE_READ_OPERATIONS)
def test_w6_queue_read_retains_validated_snapshot(tmp_path, base_timestamps, monkeypatch, operation):
    queue, payload = prepare_interleaving_queue(tmp_path, base_timestamps, operation)
    expected = run_queue_operation(queue, payload, operation)
    real_connect = sqlite3.connect
    swapped = []

    class InterleavedConnection(sqlite3.Connection):
        def execute(self, sql, *args):
            if (sql.startswith("SELECT * FROM review_queue") or sql.startswith("SELECT COUNT(*) FROM review_queue")) and not swapped:
                # WAL replacement commits after validation, immediately before the operation reads.
                with closing(real_connect(queue.queue_path, isolation_level=None, timeout=0.01)) as other:
                    replace_queue_with_nullable_schema(other, preserve_rows=False)
                    swapped.append(queue_database_snapshot(other))
            return super().execute(sql, *args)

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", lambda *args, **kwargs: real_connect(*args, **kwargs, factory=InterleavedConnection))
        assert run_queue_operation(queue, payload, operation) == expected
    assert len(swapped) == 1
    with closing(real_connect(queue.queue_path)) as conn:
        assert queue_database_snapshot(conn) == swapped[0]
    with pytest.raises(ValueError, match="schema drift"):
        run_queue_operation(queue, payload, operation)


@pytest.mark.parametrize("stage,operation", [
    (stage, operation)
    for stage in ("begin", "validation", "operation", "commit")
    for operation in ("enqueue", "mark-reviewed", "get", "peek", "count", "initialize")
] + [("commit", operation) for operation in (
    "enqueue-duplicate", "mark-missing", "mark-terminal", "get-missing", "peek-expired",
    "count-pending", "count-reviewed", "count-expired",
)])
@pytest.mark.parametrize("error_type", [MemoryError, sqlite3.OperationalError, KeyboardInterrupt], ids=["memory", "database", "cancel"])
def test_w6_queue_transaction_fault_rolls_back_and_recovers(tmp_path, base_timestamps, monkeypatch, operation, stage, error_type):
    queue, payload = prepare_interleaving_queue(tmp_path, base_timestamps, operation)
    real_connect = sqlite3.connect
    with closing(real_connect(queue.queue_path)) as conn:
        before = queue_database_snapshot(conn)
    connections, injected = [], []
    operation_sql = {
        "enqueue": "INSERT INTO review_queue", "mark-reviewed": "UPDATE review_queue",
        "get": "SELECT * FROM review_queue", "peek": "SELECT * FROM review_queue",
        "count": "SELECT COUNT(*) FROM review_queue", "initialize": "CREATE INDEX",
    }.get(operation, "")

    class FaultConnection(sqlite3.Connection):
        operation_transaction = False
        begins = 0

        def execute(self, sql, *args):
            if sql.startswith("BEGIN"):
                self.begins += 1
                self.operation_transaction = self.begins == 2
            if self.operation_transaction and not injected:
                fail = (
                    (stage == "begin" and sql.startswith("BEGIN"))
                    or (stage == "validation" and sql.startswith("PRAGMA table_info"))
                    or (stage == "operation" and operation_sql in sql)
                    or (stage == "commit" and sql == "COMMIT")
                )
                if fail:
                    if stage == "operation":
                        super().execute(sql, *args)
                    injected.append(True)
                    raise error_type("injected transaction fault")
            return super().execute(sql, *args)

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs, factory=FaultConnection)
        connections.append(conn)
        return conn

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", connect)
        with pytest.raises(error_type, match="injected transaction fault"):
            run_queue_operation(queue, payload, operation)
    assert injected == [True]
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")
    with closing(real_connect(queue.queue_path)) as conn:
        assert queue_database_snapshot(conn) == before
    run_queue_operation(queue, payload, operation)
    assert W6ReviewQueue(queue.queue_path).count() == (2 if operation == "enqueue" else 1)


@pytest.mark.parametrize("operation", ["get", "peek", "enqueue-duplicate", "mark-reviewed", "mark-expired"])
def test_w6_queue_decode_failure_closes_validated_transaction(tmp_path, base_timestamps, monkeypatch, operation):
    queue, payload = prepare_interleaving_queue(tmp_path, base_timestamps, operation)
    real_connect = sqlite3.connect
    with closing(real_connect(queue.queue_path)) as conn:
        conn.execute("UPDATE review_queue SET metadata_digest = 'corrupted'")
        conn.commit()
        before = queue_database_snapshot(conn)
    connections = []

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        connections.append(conn)
        return conn

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", connect)
        with pytest.raises(ValueError, match="metadata_digest mismatch"):
            run_queue_operation(queue, payload, operation)
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")
    with closing(real_connect(queue.queue_path)) as conn:
        assert queue_database_snapshot(conn) == before


@pytest.mark.parametrize("statement", ["PRAGMA table_info", "PRAGMA journal_mode=WAL", "PRAGMA synchronous=FULL", "CREATE TABLE", "CREATE INDEX", "COMMIT"], ids=["validation", "wal", "sync", "table", "index", "commit"])
def test_w6_queue_initialization_fault_cleanup(tmp_path, monkeypatch, statement):
    db_file = tmp_path / "fault.db"
    real_connect = sqlite3.connect
    connections = []

    class FaultConnection(sqlite3.Connection):
        def execute(self, sql, *args):
            # Fail the DDL commit, not the read-only validation commit.
            if statement in sql and (statement != "COMMIT" or self.ddl_started):
                raise MemoryError("initialization fault")
            if "CREATE TABLE" in sql:
                self.ddl_started = True
            return super().execute(sql, *args)

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs, factory=FaultConnection)
        conn.ddl_started = False
        connections.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(MemoryError, match="initialization fault"):
        W6ReviewQueue(db_file)
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")
    with real_connect(db_file) as conn:
        assert conn.execute("SELECT name FROM sqlite_schema").fetchall() == []
        assert conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    monkeypatch.setattr(sqlite3, "connect", real_connect)
    assert W6ReviewQueue(db_file).count() == 0


def test_w6_queue_existing_database_ddl_failure_preserves_state(tmp_path, monkeypatch):
    db_file = tmp_path / "existing.db"
    W6ReviewQueue(db_file)
    with sqlite3.connect(db_file) as conn:
        conn.execute("DROP INDEX idx_review_queue_status")
        conn.execute("DROP INDEX idx_review_queue_expires")
        conn.execute("CREATE TABLE unrelated (value TEXT)")
        conn.execute("INSERT INTO unrelated VALUES ('preserve')")
        conn.commit()
        conn.execute("PRAGMA journal_mode=DELETE")
        before = conn.execute("SELECT * FROM sqlite_schema").fetchall()
    real_connect = sqlite3.connect

    class FaultConnection(sqlite3.Connection):
        def execute(self, sql, *args):
            if "idx_review_queue_expires" in sql:
                raise sqlite3.OperationalError("second index fault")
            return super().execute(sql, *args)

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **kw: real_connect(*a, **kw, factory=FaultConnection))
    with pytest.raises(sqlite3.OperationalError, match="second index fault"):
        W6ReviewQueue(db_file)
    with real_connect(db_file) as conn:
        assert conn.execute("SELECT * FROM sqlite_schema").fetchall() == before
        assert conn.execute("SELECT * FROM unrelated").fetchall() == [("preserve",)]
        assert conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)


@pytest.mark.parametrize("fail_stage", ["pre_ddl", "post_ddl"])
def test_w6_queue_initializer_rechecks_concurrent_schema(tmp_path, monkeypatch, fail_stage):
    db_file = tmp_path / "race.db"
    original = W6ReviewQueue._validate_schema
    calls = 0

    def validate(conn, *, allow_missing=False):
        nonlocal calls
        calls += 1
        if calls == 2 and fail_stage == "pre_ddl":
            # Simulate a competing initializer winning before BEGIN IMMEDIATE.
            conn.execute("ROLLBACK")
            conn.execute("CREATE TABLE review_queue (item_id INTEGER PRIMARY KEY)")
            conn.execute("BEGIN IMMEDIATE")
        elif calls == 3 and fail_stage == "post_ddl":
            conn.execute("ALTER TABLE review_queue ADD COLUMN drift TEXT")
        return original(conn, allow_missing=allow_missing)

    monkeypatch.setattr(W6ReviewQueue, "_validate_schema", staticmethod(validate))
    with pytest.raises(ValueError, match="schema drift"):
        W6ReviewQueue(db_file)
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT name FROM sqlite_schema WHERE type = 'index'").fetchall() == []


@pytest.mark.parametrize("fail_stage", ["pre_ddl", "post_ddl"])
@pytest.mark.parametrize("nullable_col", W6_REVIEW_QUEUE_NON_KEY_COLUMNS)
def test_w6_queue_initializer_rechecks_concurrent_nullable_schema(tmp_path, monkeypatch, fail_stage, nullable_col):
    db_file = tmp_path / f"race_nullable_{fail_stage}_{nullable_col}.db"
    original = W6ReviewQueue._validate_schema
    calls = 0
    real_connect = sqlite3.connect
    connections = []

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)

    def validate(conn, *, allow_missing=False):
        nonlocal calls
        calls += 1
        if calls == 2 and fail_stage == "pre_ddl":
            conn.execute("ROLLBACK")
            schema = make_review_queue_schema_with_nullable_column(nullable_col)
            conn.execute(schema)
            conn.execute("BEGIN IMMEDIATE")
        elif calls == 3 and fail_stage == "post_ddl":
            conn.execute("ALTER TABLE review_queue RENAME TO review_queue_stage")
            schema = make_review_queue_schema_with_nullable_column(nullable_col)
            conn.execute(schema)
            conn.execute("DROP TABLE review_queue_stage")
        return original(conn, allow_missing=allow_missing)

    monkeypatch.setattr(W6ReviewQueue, "_validate_schema", staticmethod(validate))
    with pytest.raises(ValueError, match="schema drift"):
        W6ReviewQueue(db_file)
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")
    with real_connect(db_file) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        if fail_stage == "post_ddl":
            assert conn.execute("SELECT name FROM sqlite_schema").fetchall() == []
        else:
            info = conn.execute("PRAGMA table_info(review_queue)").fetchall()
            assert next(row[3] for row in info if row[1] == nullable_col) == 0
    assert not (tmp_path / f"{db_file.name}-wal").exists()
    assert not (tmp_path / f"{db_file.name}-shm").exists()


def test_w6_queue_concurrent_initialization(tmp_path):
    db_file = tmp_path / "init.db"

    def initialize(_):
        try:
            return W6ReviewQueue(db_file)
        except sqlite3.OperationalError as exc:
            # Journal-mode contention must fail closed, never leave partial DDL.
            assert "locked" in str(exc)
            return None

    with ThreadPoolExecutor(max_workers=4) as executor:
        queues = list(executor.map(initialize, range(8)))
    assert any(queue is not None for queue in queues)
    assert W6ReviewQueue(db_file).count() == 0


def test_w6_queue_path_dirs_memory_and_corrupt_file(tmp_path):
    # Memory rejected
    with pytest.raises(ValueError, match="':memory:' queue path rejected"):
        W6ReviewQueue(":memory:")

    # Missing parent directory
    with pytest.raises(ValueError, match="queue parent directory must exist"):
        W6ReviewQueue(tmp_path / "missing_dir" / "queue.db")

    # Directory instead of file
    with pytest.raises(ValueError, match="queue path must be regular file"):
        W6ReviewQueue(tmp_path)

    # Corrupt non-SQLite file
    corrupt_file = tmp_path / "corrupt.db"
    corrupt_file.write_bytes(b"\xff\xfe\x00\x01NOT_SQLITE\x80\x90\xff")
    with pytest.raises((sqlite3.DatabaseError, ValueError)):
        W6ReviewQueue(corrupt_file)


def test_w6_queue_proxy_memory_error_insert_and_commit_rollback(tmp_path, base_timestamps, monkeypatch):
    cutoff, maturity = base_timestamps
    db_file = tmp_path / "queue_proxy_mem.db"
    queue = W6ReviewQueue(db_file)
    payload = make_decay_payload(cutoff, maturity, decision_id="ITEM_PROXY_1")

    real_connect = queue._connect

    # Inject MemoryError on INSERT
    @contextmanager
    def _proxy_insert(self_obj, **kwargs):
        with real_connect(**kwargs) as conn:
            yield SqliteConnProxy(conn, "INSERT INTO review_queue")

    monkeypatch.setattr(W6ReviewQueue, "_connect", _proxy_insert)
    with pytest.raises(MemoryError, match="simulated OOM on INSERT INTO review_queue"):
        queue.enqueue(
            payload["decision_id"],
            payload["canonical_digest"],
            payload["attribution"],
            "drift_detected",
            payload,
        )
    assert queue.count() == 0

    # Inject MemoryError on COMMIT
    @contextmanager
    def _proxy_commit(self_obj, **kwargs):
        with real_connect(**kwargs) as conn:
            yield SqliteConnProxy(conn, "COMMIT")

    monkeypatch.setattr(W6ReviewQueue, "_connect", _proxy_commit)
    with pytest.raises(MemoryError, match="simulated OOM on COMMIT"):
        queue.enqueue(
            payload["decision_id"],
            payload["canonical_digest"],
            payload["attribution"],
            "drift_detected",
            payload,
        )
    assert queue.count() == 0


@pytest.mark.parametrize("invalid_id", INVALID_FULLMATCH_IDENTIFIERS + NONSTRING_FULLMATCH_IDENTIFIERS, ids=lambda value: hashlib.sha256(repr(value).encode()).hexdigest()[:8])
def test_w6_queue_enqueue_and_get_mark_reject_invalid_identifiers_pre_db(tmp_path, base_timestamps, monkeypatch, invalid_id):
    cutoff, maturity = base_timestamps
    db_file = tmp_path / "queue_no_mutate.db"
    queue = W6ReviewQueue(db_file)
    payload = make_decay_payload(cutoff, maturity, decision_id="ITEM_ORIGINAL")
    queue.enqueue("ITEM_ORIGINAL", payload["canonical_digest"], payload["attribution"], "drift_detected", payload)

    before_bytes = db_file.read_bytes()

    # Disallow database connections to guarantee validation rejects before DB access
    def _disallowed_connect(*args, **kwargs):
        raise AssertionError("Database connection attempted during input validation rejection")

    monkeypatch.setattr(queue, "_connect", _disallowed_connect)

    # 1. enqueue invalid item_id
    with pytest.raises((ValueError, TypeError)):
        queue.enqueue(
            item_id=invalid_id,
            canonical_digest=payload["canonical_digest"],
            review_category=payload["attribution"],
            trigger_reason="drift_detected",
            payload=payload,
        )
    assert db_file.read_bytes() == before_bytes

    # 2. enqueue invalid review_category
    with pytest.raises((ValueError, TypeError)):
        queue.enqueue(
            item_id="ITEM_ORIGINAL",
            canonical_digest=payload["canonical_digest"],
            review_category=invalid_id,
            trigger_reason="drift_detected",
            payload=payload,
        )
    assert db_file.read_bytes() == before_bytes

    # 3. get invalid item_id
    with pytest.raises((ValueError, TypeError)):
        queue.get(invalid_id)
    assert db_file.read_bytes() == before_bytes

    # 4. mark_reviewed invalid item_id
    with pytest.raises((ValueError, TypeError)):
        queue.mark_reviewed(invalid_id)
    assert db_file.read_bytes() == before_bytes


@pytest.mark.parametrize("valid_id", VALID_BOUNDARY_IDENTIFIERS, ids=lambda value: hashlib.sha256(value.encode()).hexdigest()[:8])
def test_w6_queue_valid_boundary_identifiers_lifecycle(tmp_path, base_timestamps, valid_id):
    cutoff, maturity = base_timestamps
    db_file = tmp_path / "queue_valid_boundaries.db"
    queue = W6ReviewQueue(db_file)
    payload = make_decay_payload(cutoff, maturity, decision_id=valid_id)

    res = queue.enqueue(
        item_id=valid_id,
        canonical_digest=payload["canonical_digest"],
        review_category=payload["attribution"],
        trigger_reason="drift_detected",
        payload=payload,
    )
    assert res["status"] == "enqueued"
    assert res["item_id"] == valid_id

    item = queue.get(valid_id)
    assert item is not None
    assert item["item_id"] == valid_id

    assert queue.mark_reviewed(valid_id, resolution="reviewed") is True
    assert queue.get(valid_id)["status"] == "reviewed"


@pytest.mark.parametrize("invalid_id", INVALID_FULLMATCH_IDENTIFIERS + NONSTRING_FULLMATCH_IDENTIFIERS, ids=lambda value: hashlib.sha256(repr(value).encode()).hexdigest()[:8])
def test_w6_decode_row_rejects_corrupted_identifiers(base_timestamps, invalid_id):
    cutoff, maturity = base_timestamps
    payload = make_decay_payload(cutoff, maturity, decision_id="ITEM_ROW")
    created_iso = cutoff.isoformat()
    expires_iso = (cutoff + timedelta(days=1)).isoformat()
    meta_digest = _compute_metadata_digest(
        "ITEM_ROW",
        payload["canonical_digest"],
        payload["attribution"],
        "drift_detected",
        created_iso,
        expires_iso,
        "pending",
    )
    valid_row = (
        "ITEM_ROW",
        payload["canonical_digest"],
        payload["attribution"],
        "drift_detected",
        created_iso,
        expires_iso,
        "pending",
        json.dumps(payload, sort_keys=True),
        meta_digest,
    )
    assert _decode_row(valid_row)["item_id"] == "ITEM_ROW"

    # Corrupted item_id
    with pytest.raises(ValueError, match="corrupted row item_id"):
        _decode_row((invalid_id, *valid_row[1:]))

    # Corrupted review_category
    with pytest.raises(ValueError, match="corrupted row review_category"):
        _decode_row((valid_row[0], valid_row[1], invalid_id, *valid_row[3:]))


@pytest.mark.parametrize("valid_id", VALID_BOUNDARY_IDENTIFIERS, ids=lambda value: hashlib.sha256(value.encode()).hexdigest()[:8])
def test_w6_decode_row_accepts_valid_boundary_identifiers(base_timestamps, valid_id):
    cutoff, maturity = base_timestamps
    payload = make_decay_payload(cutoff, maturity, decision_id=valid_id)
    created_iso = cutoff.isoformat()
    expires_iso = (cutoff + timedelta(days=1)).isoformat()
    meta_digest = _compute_metadata_digest(
        valid_id,
        payload["canonical_digest"],
        payload["attribution"],
        "drift_detected",
        created_iso,
        expires_iso,
        "pending",
    )
    row = (
        valid_id,
        payload["canonical_digest"],
        payload["attribution"],
        "drift_detected",
        created_iso,
        expires_iso,
        "pending",
        json.dumps(payload, sort_keys=True),
        meta_digest,
    )
    decoded = _decode_row(row)
    assert decoded["item_id"] == valid_id
    assert decoded["canonical_digest"] == payload["canonical_digest"]


# =====================================================================
# CONTINUOUS LEARNING ENGINE TESTS
# =====================================================================

def test_w6_engine_inert_shadow_review_no_retrain_or_promotion(tmp_path, base_timestamps):
    cutoff, maturity = base_timestamps
    queue = W6ReviewQueue(tmp_path / "engine_queue.db")
    engine = ContinuousLearningEngine(review_queue=queue)

    payload = make_decay_payload(cutoff, maturity, decision_id="ENG_SHADOW_01")
    res = engine.enqueue_shadow_review(payload)

    # Invariants: advisory, no auto-retrain, no auto-promote
    assert res["status"] == "enqueued"
    assert res["advisory_only"] is True
    assert res["applied"] is False
    assert res["auto_retrain_executed"] is False
    assert res["auto_promote_executed"] is False

    # Engine status remains completely inert
    status = engine.get_status()
    assert status["retrain_count"] == 0
    assert status["last_retrain_date"] is None
    assert engine.champion is None


def test_w6_engine_shadow_review_no_queue_configured(base_timestamps):
    cutoff, maturity = base_timestamps
    engine = ContinuousLearningEngine(review_queue=None)
    payload = make_decay_payload(cutoff, maturity, decision_id="ENG_NO_QUEUE_01")

    res = engine.enqueue_shadow_review(payload)
    assert res["status"] == "no_queue_configured"
    assert res["advisory_only"] is True
    assert res["applied"] is False
    assert res["auto_retrain_executed"] is False
    assert res["auto_promote_executed"] is False
    assert engine.get_status()["retrain_count"] == 0
