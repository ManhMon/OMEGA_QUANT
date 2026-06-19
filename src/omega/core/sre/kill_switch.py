"""
OMEGA_QUANT SRE Kill Switch
============================
Global emergency kill-switch with graceful shutdown:
  - Flushes all log handlers
  - Dumps in-memory metrics state to disk
  - Triggers order cancellation callbacks
  - Thread-safe, idempotent activation

Author: DevOps Engineer (Role 11)
Date: 2026-05-20
Version: 1.0.0
Phase: 7.1 SRE Foundation
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ShutdownCallback = Callable[[], None]

# ---------------------------------------------------------------------------
# Kill Switch
# ---------------------------------------------------------------------------

class KillSwitch:
    """
    Global emergency kill-switch for OMEGA_QUANT.

    Activation is idempotent — calling :meth:`activate` multiple times is safe.
    All registered shutdown callbacks are invoked exactly once in LIFO order
    (last registered, first called — mirrors Python atexit semantics).

    Shutdown sequence
    -----------------
    1. Set the internal ``_activated`` flag (atomic via threading.Event).
    2. Invoke all registered :class:`ShutdownCallback` in LIFO order.
    3. Flush all active :mod:`logging` handlers.
    4. Dump metrics snapshot to *dump_dir* (if a collector is registered).
    5. Record activation evidence to ``<dump_dir>/kill_switch_event.json``.
    """

    def __init__(
        self,
        dump_dir: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Args:
            dump_dir: Directory for state dumps on activation.
                      Defaults to the ``OMEGA_DUMP_DIR`` env var, then ``/tmp/omega_dump``.
            logger:   Logger to use for internal messages.
        """
        self._activated = threading.Event()
        self._lock = threading.Lock()
        self._callbacks: List[ShutdownCallback] = []
        self._activation_time: Optional[datetime] = None
        self._activation_reason: str = ""
        self._activation_id: str = ""

        self._dump_dir = Path(
            dump_dir
            or os.environ.get("OMEGA_DUMP_DIR", "")
            or "/tmp/omega_dump"
        )

        self._logger = logger or logging.getLogger(__name__)

        # Optional metrics collector reference (set via register_metrics_collector)
        self._metrics_collector: Optional[object] = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_callback(self, callback: ShutdownCallback) -> None:
        """
        Register a shutdown callback.

        Callbacks are called in LIFO order on activation.
        Registering after activation raises :class:`RuntimeError`.

        Args:
            callback: Zero-argument callable invoked during shutdown.

        Raises:
            RuntimeError: If the kill switch is already activated.
        """
        if self._activated.is_set():
            raise RuntimeError(
                "KillSwitch already activated — cannot register new callbacks."
            )
        with self._lock:
            self._callbacks.append(callback)

    def register_metrics_collector(self, collector: object) -> None:
        """
        Register a MetricsCollector whose snapshot will be dumped on activation.

        Args:
            collector: Any object with a ``snapshot() -> dict`` method.
        """
        self._metrics_collector = collector

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_activated(self) -> bool:
        """True if the kill switch has been activated."""
        return self._activated.is_set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """
        Block until the kill switch is activated or *timeout* seconds elapse.

        Returns:
            True if activated, False if timed out.
        """
        return self._activated.wait(timeout=timeout)

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self, reason: str = "manual") -> None:
        """
        Activate the kill switch and execute the full shutdown sequence.

        Idempotent — safe to call from multiple threads simultaneously.

        Args:
            reason: Human-readable reason string recorded in the event dump.
        """
        # Only the first caller proceeds; subsequent calls return immediately.
        with self._lock:
            if self._activated.is_set():
                return
            self._activated.set()
            self._activation_time = datetime.now(tz=timezone.utc)
            self._activation_reason = reason
            self._activation_id = str(uuid.uuid4())

        self._logger.critical(
            "KILL SWITCH ACTIVATED",
            extra={
                "activation_id": self._activation_id,
                "reason": reason,
                "timestamp": self._activation_time.isoformat(),
            },
        )

        self._run_callbacks()
        self._flush_logs()
        self._dump_state()

    # ------------------------------------------------------------------
    # Internal shutdown steps
    # ------------------------------------------------------------------

    def _run_callbacks(self) -> None:
        """Invoke registered callbacks in LIFO order, catching all exceptions."""
        for callback in reversed(self._callbacks):
            try:
                callback()
            except Exception as exc:  # noqa: BLE001
                self._logger.error(
                    "Kill switch callback raised an exception",
                    extra={"callback": repr(callback), "error": str(exc)},
                )

    def _flush_logs(self) -> None:
        """Flush every handler on every active logger in the logging manager."""
        manager = logging.Logger.manager
        # logging.Manager stores loggers in .loggerDict (name -> Logger | PlaceHolder)
        for logger_or_placeholder in list(manager.loggerDict.values()):
            if isinstance(logger_or_placeholder, logging.Logger):
                for handler in logger_or_placeholder.handlers:
                    try:
                        handler.flush()
                    except Exception:  # noqa: BLE001
                        pass

        # Also flush root logger handlers
        for handler in logging.root.handlers:
            try:
                handler.flush()
            except Exception:  # noqa: BLE001
                pass

    def _dump_state(self) -> None:
        """Write metrics snapshot and kill-switch event record to dump_dir."""
        try:
            self._dump_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._logger.error(
                "Failed to create dump directory",
                extra={"dump_dir": str(self._dump_dir), "error": str(exc)},
            )
            return

        # --- metrics snapshot ---
        if self._metrics_collector is not None:
            try:
                snapshot = self._metrics_collector.snapshot()  # type: ignore[union-attr]
                metrics_path = self._dump_dir / "metrics_snapshot.json"
                metrics_path.write_text(
                    json.dumps(snapshot, indent=2, default=str),
                    encoding="utf-8",
                )
                self._logger.info(
                    "Metrics snapshot written",
                    extra={"path": str(metrics_path)},
                )
            except Exception as exc:  # noqa: BLE001
                self._logger.error(
                    "Failed to dump metrics snapshot",
                    extra={"error": str(exc)},
                )

        # --- kill switch event record ---
        event: dict[str, object] = {
            "activation_id": self._activation_id,
            "reason": self._activation_reason,
            "activated_at": (
                self._activation_time.isoformat()
                if self._activation_time
                else None
            ),
            "dump_dir": str(self._dump_dir),
        }
        try:
            event_path = self._dump_dir / "kill_switch_event.json"
            event_path.write_text(
                json.dumps(event, indent=2),
                encoding="utf-8",
            )
            self._logger.info(
                "Kill switch event record written",
                extra={"path": str(event_path)},
            )
        except OSError as exc:
            self._logger.error(
                "Failed to write kill switch event record",
                extra={"error": str(exc)},
            )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_kill_switch: Optional[KillSwitch] = None
_ks_lock = threading.Lock()


def get_kill_switch(dump_dir: Optional[str] = None) -> KillSwitch:
    """
    Return the process-wide KillSwitch singleton.

    Args:
        dump_dir: Passed to :class:`KillSwitch` only on first call.
    """
    global _kill_switch
    if _kill_switch is None:
        with _ks_lock:
            if _kill_switch is None:
                _kill_switch = KillSwitch(dump_dir=dump_dir)
    return _kill_switch


def reset_kill_switch(auth_token: str = "") -> None:
    """
    Reset the singleton — **restricted API, fail-closed**.

    LIVE-04 FIX2: The public ``reset_kill_switch()`` can no longer silently
    clear the kill-switch state.  Callers **must** supply a valid
    ``auth_token`` (``"OMEGA_TEST"``) to proceed.  Unauthorized calls
    raise :class:`PermissionError` and do **not** clear the singleton.

    This prevents accidental or malicious clearing of an active kill switch
    in production runtime code.

    Args:
        auth_token: Must equal ``"OMEGA_TEST"`` for the reset to proceed.

    Raises:
        PermissionError: If auth_token is missing or incorrect.
    """
    if auth_token != "OMEGA_TEST":
        raise PermissionError(
            "reset_kill_switch requires auth_token='OMEGA_TEST' — "
            "unauthorized call: state NOT cleared."
        )
    _do_reset()


def _reset_kill_switch_for_testing(auth_token: str = "") -> None:
    """
    Reset the singleton — restricted to test/ops authorization.

    LIVE-04 FIX: Requires an explicit auth_token to prevent accidental
    misuse in production code. Tests must pass the token ``"OMEGA_TEST"``.

    Args:
        auth_token: Must equal ``"OMEGA_TEST"`` for the reset to proceed.

    Raises:
        PermissionError: If auth_token is missing or incorrect.
    """
    if auth_token != "OMEGA_TEST":
        raise PermissionError(
            "reset_kill_switch requires auth_token='OMEGA_TEST' — "
            "this API is restricted to test/ops authorization."
        )
    _do_reset()


def _do_reset() -> None:
    """Internal: clear the module-level singleton."""
    global _kill_switch
    with _ks_lock:
        _kill_switch = None
