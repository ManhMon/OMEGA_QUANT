"""
OMEGA_QUANT SRE Logger
======================
Structured JSON logging with trace_id propagation and severity filtering.

Author: DevOps Engineer (Role 11)
Date: 2026-05-20
Version: 1.0.0
Phase: 7.1 SRE Foundation
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Context variable — propagates trace_id across async/sync call stacks
# ---------------------------------------------------------------------------
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    """Return the current trace_id, generating one if absent."""
    tid = _trace_id_var.get()
    if not tid:
        tid = str(uuid.uuid4())
        _trace_id_var.set(tid)
    return tid


def set_trace_id(trace_id: str) -> None:
    """Explicitly set the trace_id for the current context."""
    _trace_id_var.set(trace_id)


def new_trace_id() -> str:
    """Generate and set a fresh trace_id; return it."""
    tid = str(uuid.uuid4())
    _trace_id_var.set(tid)
    return tid


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    # Fields that are always present in the envelope
    _ENVELOPE_KEYS: frozenset[str] = frozenset(
        {"timestamp", "level", "logger", "message", "trace_id"}
    )

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": get_trace_id(),
        }

        # Attach any extra fields passed via `extra=` kwarg
        for key, value in record.__dict__.items():
            if (
                key not in logging.LogRecord.__dict__
                and key not in self._ENVELOPE_KEYS
                and not key.startswith("_")
            ):
                payload[key] = value

        # Exception info
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

_LEVEL_MAP: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def get_sre_logger(
    name: str,
    level: str = "INFO",
    stream: Optional[Any] = None,
) -> logging.Logger:
    """
    Return a logger that emits structured JSON to *stream* (default: stdout).

    Args:
        name:   Logger name (use __name__ in callers).
        level:  Severity threshold — one of DEBUG / INFO / WARNING / ERROR / CRITICAL.
        stream: IO stream to write to; defaults to sys.stdout.

    Returns:
        Configured :class:`logging.Logger`.

    Raises:
        ValueError: If *level* is not a recognised severity string.
    """
    level_upper = level.upper()
    if level_upper not in _LEVEL_MAP:
        raise ValueError(
            f"Unknown log level '{level}'. "
            f"Valid values: {sorted(_LEVEL_MAP)}"
        )

    numeric_level: int = _LEVEL_MAP[level_upper]
    logger = logging.getLogger(name)

    # Idempotent — skip if already configured at the same level
    if logger.handlers and logger.level == numeric_level:
        return logger

    logger.handlers.clear()
    logger.setLevel(numeric_level)
    logger.propagate = False

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)

    return logger
