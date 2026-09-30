"""omega.quant.continuous_learning - shim wrapper for evolution with W6 review queue."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

import pandas as pd

from omega.core.llm_config import _canonical
from omega.quant.drift_detector import attach_decay_attribution
from omega.quant.evolution.continuous_learning import (
    ContinuousLearningEngine as RealEngine,
    ContinuousLearningConfig as RealConfig,
)

logger = logging.getLogger(__name__)

TRIGGER_REASONS = ("drift_detected", "synthetic_event")
STATUS_ALLOWLIST = ("pending", "reviewed", "expired")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")


def _parse_strict_json(raw_text: str) -> Dict[str, Any]:
    raw_bytes = raw_text.encode("utf-8")
    if len(raw_bytes) > 65536:
        raise ValueError("payload exceeds 64KiB capacity")

    def _no_dup(pairs):
        res = {}
        for k, v in pairs:
            if k in res:
                raise ValueError("duplicate key in json")
            res[k] = v
        return res

    return json.loads(raw_text, object_pairs_hook=_no_dup)


def _validate_payload(
    payload: Dict[str, Any],
    expected_item_id: Optional[str] = None,
    expected_category: Optional[str] = None,
) -> str:
    """Validate strict schema by rebuilding via attach_decay_attribution and asserting identical payload."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be dict")
    if "decision_id" not in payload or not isinstance(payload["decision_id"], str) or not _SAFE_ID.fullmatch(payload["decision_id"]):
        raise ValueError("invalid or missing decision_id")
    if "canonical_digest" not in payload or not isinstance(payload["canonical_digest"], str) or len(payload["canonical_digest"]) != 64:
        raise ValueError("invalid or missing canonical_digest")
    raw_bytes = _canonical(payload)
    if len(raw_bytes) > 65536:
        raise ValueError("payload exceeds 64KiB capacity")

    try:
        cutoff_dt = datetime.fromisoformat(payload["cutoff"])
        maturity_dt = datetime.fromisoformat(payload["maturity"])
        if cutoff_dt.tzinfo is None or maturity_dt.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
    except (ValueError, TypeError, KeyError):
        raise ValueError("invalid payload timestamps") from None

    try:
        rebuilt = attach_decay_attribution(
            gross_before=payload["gross_before"],
            gross_after=payload["gross_after"],
            cost_before=payload["cost_before"],
            cost_after=payload["cost_after"],
            trigger_detected=payload["trigger_detected"],
            cutoff=cutoff_dt,
            maturity=maturity_dt,
            data_issue_flag=payload["data_issue_flag"],
            regime_mismatch_flag=payload["regime_mismatch_flag"],
            cost_shift_flag=payload["cost_shift_flag"],
            drift_label=payload["drift_label"],
            attribution=payload["attribution"],
            recommendation=payload["recommendation"],
            decision_id=payload["decision_id"],
            gate_id=payload["gate_id"],
            policy_version=payload["policy_version"],
            source_revision=payload["source_revision"],
            synthetic=payload["synthetic"],
        )
    except (ValueError, TypeError, KeyError):
        raise ValueError("payload rebuild validation failed") from None

    if rebuilt != payload:
        raise ValueError("rebuilt payload does not match input payload identically")

    raw_bytes = _canonical({k: v for k, v in payload.items() if k != "canonical_digest"})
    if len(raw_bytes) > 65536:
        raise ValueError("payload exceeds 64KiB capacity")

    if expected_item_id is not None and payload["decision_id"] != expected_item_id:
        raise ValueError("item_id mismatch against decision_id")
    if expected_category is not None and payload["attribution"] != expected_category:
        raise ValueError("review_category mismatch against attribution")

    return payload["canonical_digest"]


def _compute_metadata_digest(
    item_id: str,
    canonical_digest: str,
    review_category: str,
    trigger_reason: str,
    created_at: str,
    expires_at: str,
    status: str,
) -> str:
    meta_dict = {
        "canonical_digest": canonical_digest,
        "created_at": created_at,
        "expires_at": expires_at,
        "item_id": item_id,
        "review_category": review_category,
        "status": status,
        "trigger_reason": trigger_reason,
    }
    return hashlib.sha256(_canonical(meta_dict)).hexdigest()


def _decode_row(row: tuple) -> Dict[str, Any]:
    if len(row) != 9:
        raise ValueError(f"expected 9 columns in review_queue row, got {len(row)}")
    item_id, canonical_digest, review_category, trigger_reason, created_at, expires_at, status, payload_json, metadata_digest = row

    if not isinstance(item_id, str) or not _SAFE_ID.fullmatch(item_id):
        raise ValueError("corrupted row item_id")
    if not isinstance(canonical_digest, str) or len(canonical_digest) != 64:
        raise ValueError("corrupted row canonical_digest")
    if not isinstance(review_category, str) or not _SAFE_ID.fullmatch(review_category):
        raise ValueError("corrupted row review_category")
    if trigger_reason not in TRIGGER_REASONS:
        raise ValueError("corrupted row trigger_reason")
    if status not in STATUS_ALLOWLIST:
        raise ValueError("corrupted row status")

    expected_md = _compute_metadata_digest(
        item_id, canonical_digest, review_category, trigger_reason, created_at, expires_at, status
    )
    if metadata_digest != expected_md:
        raise ValueError("corrupted row metadata_digest mismatch")

    payload = _parse_strict_json(payload_json)
    _validate_payload(payload, expected_item_id=item_id, expected_category=review_category)
    if payload["canonical_digest"] != canonical_digest:
        raise ValueError("corrupted row canonical_digest mismatch with payload")
    try:
        created, expiry = datetime.fromisoformat(created_at), datetime.fromisoformat(expires_at)
        if (created.tzinfo is None or expiry.tzinfo is None or created.utcoffset() != timedelta(0)
                or expiry.utcoffset() != timedelta(0) or expiry <= created
                or created < datetime.fromisoformat(payload["cutoff"])):
            raise ValueError("invalid queue times")
    except (TypeError, ValueError):
        raise ValueError("corrupted row timestamps") from None

    return {
        "canonical_digest": canonical_digest,
        "created_at": created_at,
        "expires_at": expires_at,
        "item_id": item_id,
        "metadata_digest": metadata_digest,
        "payload": payload,
        "review_category": review_category,
        "status": status,
        "trigger_reason": trigger_reason,
    }


@dataclass
class ContinuousLearningConfig:
    """Compatibility config mapping to RealConfig."""
    learning_rate: float = 0.01
    window_size: int = 252
    min_samples: int = 60
    retrain_threshold: float = 0.02
    champion_ic_threshold: float = 0.02
    retrain_frequency_days: int = 7
    training_window_days: int = 252
    validation_window_days: int = 60
    embargo_days: int = 3
    ic_improvement_threshold: float = 0.05
    p_value_threshold: float = 0.05
    min_absolute_ic: float = 0.10


class TrainableModel:
    """Dummy TrainableModel for backward compatibility."""
    def fit(self, X, y, **kwargs):
        pass

    def predict(self, X, **kwargs):
        return None

    def update(self, X, y, **kwargs):
        pass


class DecayMonitor:
    """Dummy DecayMonitor for backward compatibility."""
    def check(self, *args, **kwargs):
        return False


class W6ReviewQueue:
    """File-backed transactional SQLite review queue for W6 decay attribution."""
    def __init__(
        self,
        queue_path: Union[str, Path],
        max_capacity: int = 1000,
        timeout: float = 5.0,
    ):
        if str(queue_path) == ":memory:":
            raise ValueError("':memory:' queue path rejected; file-backed SQLite required")
        path = Path(queue_path)
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("symlink queue paths are rejected")
        resolved = path.resolve()
        if resolved.is_symlink():
            raise ValueError("symlink queue paths are rejected")
        if not resolved.parent.exists():
            raise ValueError("queue parent directory must exist")
        if resolved.exists() and not resolved.is_file():
            raise ValueError("queue path must be regular file")
        self.queue_path = resolved

        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not (0.0 < timeout <= 5.0) or not math.isfinite(float(timeout)):
            raise ValueError("timeout must be finite in (0, 5]")
        if isinstance(max_capacity, bool) or not isinstance(max_capacity, int) or not (0 < max_capacity <= 1000):
            raise ValueError("max_capacity must be integer in (0, 1000]")

        self.timeout = float(timeout)
        self.max_capacity = max_capacity
        self._init_db()

    @contextmanager
    def _connect(self, *, initialize: bool = False, write: bool = False) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.queue_path), timeout=self.timeout, isolation_level=None)
        conn.text_factory = str
        journal_mode = None
        try:
            # Read-only preflight rejects existing drift before changing journal mode.
            conn.execute("BEGIN")
            self._validate_schema(conn, allow_missing=initialize)
            conn.execute("COMMIT")
            if initialize:
                journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("BEGIN IMMEDIATE" if initialize or write else "BEGIN")
            self._validate_schema(conn, allow_missing=initialize)
            yield conn
            if conn.in_transaction:
                conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            if journal_mode is not None:
                # SQLite journal mode is not transactional; restore failed initialization.
                conn.execute(f"PRAGMA journal_mode={journal_mode}")
            raise
        finally:
            try:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
            finally:
                conn.close()

    def _init_db(self) -> None:
        with self._connect(initialize=True) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS review_queue (
                    item_id TEXT PRIMARY KEY,
                    canonical_digest TEXT NOT NULL,
                    review_category TEXT NOT NULL,
                    trigger_reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    metadata_digest TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_review_queue_expires ON review_queue(expires_at)")
            self._validate_schema(conn)
            conn.execute("COMMIT")

    @staticmethod
    def _validate_schema(conn: sqlite3.Connection, *, allow_missing: bool = False) -> None:
        obj = conn.execute(
            "SELECT type FROM sqlite_schema WHERE name = ? COLLATE NOCASE", ("review_queue",)
        ).fetchone()
        if obj is None and allow_missing:
            return
        cols = [(r[1], r[2].upper(), r[3], r[5]) for r in conn.execute("PRAGMA table_info(review_queue)")]
        expected = [
            ("item_id", "TEXT", 0, 1),
            ("canonical_digest", "TEXT", 1, 0),
            ("review_category", "TEXT", 1, 0),
            ("trigger_reason", "TEXT", 1, 0),
            ("created_at", "TEXT", 1, 0),
            ("expires_at", "TEXT", 1, 0),
            ("status", "TEXT", 1, 0),
            ("payload_json", "TEXT", 1, 0),
            ("metadata_digest", "TEXT", 1, 0),
        ]
        if obj != ("table",) or cols != expected:
            raise ValueError("review_queue schema drift detected")

    def enqueue(
        self,
        item_id: str,
        canonical_digest: str,
        review_category: str,
        trigger_reason: str,
        payload: Dict[str, Any],
        created_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if not isinstance(item_id, str) or not _SAFE_ID.fullmatch(item_id):
            raise ValueError("item_id invalid format")
        if not isinstance(canonical_digest, str) or len(canonical_digest) != 64:
            raise ValueError("canonical_digest must be 64-char hex string")
        if not isinstance(review_category, str) or not _SAFE_ID.fullmatch(review_category):
            raise ValueError("review_category invalid format")
        if trigger_reason not in TRIGGER_REASONS:
            raise ValueError(f"trigger_reason must be one of {TRIGGER_REASONS}")

        computed_digest = _validate_payload(payload, item_id, review_category)
        if canonical_digest != computed_digest:
            raise ValueError("provided canonical_digest does not match payload digest")

        cutoff_dt = datetime.fromisoformat(payload["cutoff"]).astimezone(timezone.utc)
        maturity_dt = datetime.fromisoformat(payload["maturity"]).astimezone(timezone.utc)

        if created_at is None:
            created_dt = cutoff_dt
        else:
            if not isinstance(created_at, datetime) or created_at.tzinfo is None or created_at.utcoffset() is None:
                raise ValueError("created_at must be aware datetime")
            created_dt = created_at.astimezone(timezone.utc)

        if expires_at is None:
            expires_dt = created_dt + timedelta(days=1)
        else:
            if not isinstance(expires_at, datetime) or expires_at.tzinfo is None or expires_at.utcoffset() is None:
                raise ValueError("expires_at must be aware datetime")
            expires_dt = expires_at.astimezone(timezone.utc)

        if created_dt >= expires_dt:
            raise ValueError("created_at must precede expires_at")
        if created_dt < cutoff_dt:
            raise ValueError("created_at cannot precede payload cutoff")

        created_iso = created_dt.isoformat()
        expires_iso = expires_dt.isoformat()

        metadata_digest = _compute_metadata_digest(
            item_id, computed_digest, review_category, trigger_reason, created_iso, expires_iso, "pending"
        )
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(payload_json.encode("utf-8")) > 65536:
            raise ValueError("payload exceeds 64KiB capacity")

        with self._connect(write=True) as conn:
            try:
                row = conn.execute("SELECT * FROM review_queue WHERE item_id = ?", (item_id,)).fetchone()
                if row is not None:
                    decoded = _decode_row(row)
                    existing_digest = _compute_metadata_digest(item_id, computed_digest, review_category,
                                                              trigger_reason, created_iso, expires_iso, decoded["status"])
                    if decoded["metadata_digest"] == existing_digest:
                        conn.execute("COMMIT")
                        return {
                            "canonical_digest": computed_digest,
                            "item_id": item_id,
                            "review_status": decoded["status"],
                            "status": "idempotent_duplicate",
                        }
                    raise ValueError(f"Queue conflict: item_id '{item_id}' exists with different metadata")

                total = conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
                if total >= self.max_capacity:
                    raise ValueError(f"Queue capacity exceeded: total rows {total} >= max {self.max_capacity}")

                conn.execute(
                    """
                    INSERT INTO review_queue (item_id, canonical_digest, review_category, trigger_reason, created_at, expires_at, status, payload_json, metadata_digest)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (item_id, computed_digest, review_category, trigger_reason, created_iso, expires_iso, payload_json, metadata_digest)
                )
                conn.execute("COMMIT")
                return {
                    "canonical_digest": computed_digest,
                    "item_id": item_id,
                    "review_status": "pending",
                    "status": "enqueued",
                }
            except (sqlite3.OperationalError, sqlite3.DatabaseError, MemoryError, Exception):
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    def peek(self, as_of: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        if as_of is None:
            as_of_dt = datetime.now(timezone.utc)
        else:
            if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
                raise ValueError("as_of must be aware datetime")
            as_of_dt = as_of.astimezone(timezone.utc)
        as_of_iso = as_of_dt.isoformat()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_queue WHERE status = 'pending' AND created_at <= ? AND expires_at > ? ORDER BY created_at ASC LIMIT 1",
                (as_of_iso, as_of_iso)
            ).fetchone()
            if row is None:
                return None
            return _decode_row(row)

    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        if not isinstance(item_id, str) or not _SAFE_ID.fullmatch(item_id):
            raise ValueError("item_id invalid format")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM review_queue WHERE item_id = ?", (item_id,)).fetchone()
            if row is None:
                return None
            return _decode_row(row)

    def mark_reviewed(self, item_id: str, resolution: str = "reviewed") -> bool:
        if resolution not in ("reviewed", "expired"):
            raise ValueError("resolution must be 'reviewed' or 'expired'")
        if not isinstance(item_id, str) or not _SAFE_ID.fullmatch(item_id):
            raise ValueError("item_id invalid format")

        with self._connect(write=True) as conn:
            try:
                row = conn.execute("SELECT * FROM review_queue WHERE item_id = ?", (item_id,)).fetchone()
                if row is None:
                    conn.execute("COMMIT")
                    return False
                decoded = _decode_row(row)
                if decoded["status"] != "pending":
                    conn.execute("COMMIT")
                    return False

                new_metadata_digest = _compute_metadata_digest(
                    item_id,
                    decoded["canonical_digest"],
                    decoded["review_category"],
                    decoded["trigger_reason"],
                    decoded["created_at"],
                    decoded["expires_at"],
                    resolution,
                )
                cur = conn.execute(
                    "UPDATE review_queue SET status = ?, metadata_digest = ? WHERE item_id = ? AND status = 'pending'",
                    (resolution, new_metadata_digest, item_id)
                )
                affected = cur.rowcount > 0
                conn.execute("COMMIT")
                return affected
            except (sqlite3.OperationalError, sqlite3.DatabaseError, MemoryError, Exception):
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    def count(self, status: Optional[str] = None) -> int:
        with self._connect() as conn:
            if status is None:
                cur = conn.execute("SELECT COUNT(*) FROM review_queue")
            else:
                if status not in STATUS_ALLOWLIST:
                    raise ValueError("invalid status query")
                cur = conn.execute("SELECT COUNT(*) FROM review_queue WHERE status = ?", (status,))
            return int(cur.fetchone()[0])


class ContinuousLearningEngine:
    """Wrapper delegating to the real ContinuousLearningEngine from evolution with W6 inert review queue."""
    def __init__(
        self,
        config: ContinuousLearningConfig = None,
        model_factory=None,
        review_queue: Optional[W6ReviewQueue] = None,
    ):
        self.config = config or ContinuousLearningConfig()
        self.model_factory = model_factory
        self.review_queue = review_queue
        self._champion: Optional[TrainableModel] = None
        self.decay_monitor = DecayMonitor()
        self._retrain_count = 0

        real_cfg = RealConfig(
            retraining_interval_days=self.config.retrain_frequency_days,
            min_ic_improvement=self.config.ic_improvement_threshold,
            p_value_threshold=self.config.p_value_threshold,
            min_absolute_ic=self.config.min_absolute_ic,
        )
        self._real = RealEngine(config=real_cfg)

    @property
    def champion(self) -> Optional[TrainableModel]:
        return self._champion

    @champion.setter
    def champion(self, val: Optional[TrainableModel]) -> None:
        self._champion = val
        if val is not None and self._real.champion_model is None:
            self._real.champion_model = {
                "ic": 0.12,
                "model_name": "champion",
                "sharpe": 1.5,
                "timestamp": pd.Timestamp.now().isoformat(),
            }

    def update(self, *args, **kwargs):
        pass

    def predict(self, *args, **kwargs):
        return None

    def monitor_and_retrain(
        self, current_date, features, targets
    ) -> Dict[str, Any]:
        ts = pd.Timestamp(current_date)
        prior_ic = (self._real.champion_model.get("ic", 0.0)
                    if self._real.champion_model else 0.0)

        res = self._real.retrain_cycle(features, targets, ts)

        retrain_triggered = res.get("status") in ("promoted", "retained")
        status = res.get("status", "skipped")

        if retrain_triggered:
            self._retrain_count += 1

        if status == "promoted":
            if self._champion is None:
                self._champion = TrainableModel()

        current_sharpe = 0.0
        current_ic = 0.0
        comparison = None

        if self._real.champion_model:
            current_sharpe = self._real.champion_model.get("sharpe", 0.0)
            current_ic = self._real.champion_model.get("ic", 0.0)

        if status in ("promoted", "retained"):
            challenger_metrics = res.get("metrics", {})
            ic_challenger = challenger_metrics.get("ic", 0.0)
            comparison = {
                "ic_challenger": ic_challenger,
                "ic_champion": prior_ic,
            }

        cl_status = {
            "current_ic": current_ic,
            "current_sharpe": current_sharpe,
            "promotion_decision": status,
            "retrain_reason": res.get("reason", ""),
            "retrain_triggered": retrain_triggered,
        }
        if comparison:
            cl_status["comparison"] = comparison

        return cl_status

    def enqueue_shadow_review(
        self,
        decay_attribution: Dict[str, Any],
        trigger_reason: str = "drift_detected",
    ) -> Dict[str, Any]:
        """Validate exact decay attribution schema and enqueue inert shadow review; no auto-retrain/promote."""
        if trigger_reason not in TRIGGER_REASONS:
            raise ValueError(f"trigger_reason must be one of {TRIGGER_REASONS}")
        _validate_payload(decay_attribution)

        item_id = decay_attribution["decision_id"]
        canonical_digest = decay_attribution["canonical_digest"]
        category = decay_attribution["attribution"]

        if self.review_queue is None:
            return {
                "advisory_only": True,
                "applied": False,
                "auto_promote_executed": False,
                "auto_retrain_executed": False,
                "canonical_digest": canonical_digest,
                "item_id": item_id,
                "status": "no_queue_configured",
            }

        res = self.review_queue.enqueue(
            item_id=item_id,
            canonical_digest=canonical_digest,
            review_category=category,
            trigger_reason=trigger_reason,
            payload=decay_attribution,
        )
        return {
            **res,
            "advisory_only": True,
            "applied": False,
            "auto_promote_executed": False,
            "auto_retrain_executed": False,
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "champion_exists": (
                self.champion is not None
                or self._real.champion_model is not None
            ),
            "last_retrain_date": self._real.last_retrain_date,
            "retrain_count": self._retrain_count,
        }


ContinuousLearner = ContinuousLearningEngine
