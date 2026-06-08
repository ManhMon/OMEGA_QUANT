"""
OMEGA_QUANT Event Bus (IPC Engine)

Purpose:
    Provide event-driven communication between system components.
    - Pub/Sub architecture
    - Event contracts and schemas
    - Thread-safe event distribution
    - Event history and replay

Contract:
    - Input: Event name, payload (Dict)
    - Output: Distribution to all subscribed listeners

Reference:
    - Section 17: Event-Driven IPC architecture

Author: DevOps Engineer (Role 12)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional, Set
import fnmatch

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Standard system event with versioning and schema validation."""
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    event_version: str = "1.0"
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""
    target: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    trace_id: str = ""
    severity: str = "INFO"
    schema_id: str = field(default="")
    
    def __post_init__(self):
        """Compute schema_id if not provided."""
        if not self.schema_id:
            object.__setattr__(self, 'schema_id', self._compute_schema_hash())
    
    def _compute_schema_hash(self) -> str:
        """Compute deterministic hash of event schema."""
        # Sort payload keys for deterministic hashing
        schema_repr = f"{self.event_type}:{sorted(self.payload.keys())}"
        hash_digest = hashlib.sha256(schema_repr.encode()).hexdigest()[:16]
        return f"sha256:{hash_digest}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = asdict(self)
        # Convert datetime to ISO string
        if isinstance(data['timestamp'], datetime):
            timestamp = data['timestamp']
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            data['timestamp'] = timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Event:
        """Deserialize event from dictionary."""
        data = dict(data)
        # Parse timestamp if it's a string
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
        return cls(**data)


class EventBus:
    """
    Central event distribution hub (IPC Engine).
    Supports wildcards, history, and schema validation.
    """
    
    def __init__(
        self,
        state_dir: Optional[Path | str] = None,
        max_retries: int = 5,
        retry_delays: Optional[List[int]] = None,
        sleeper: Optional[Callable[[float], None]] = None,
    ):
        """Initialize event bus state."""
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._bus_lock = threading.Lock()
        self._history: deque = deque(maxlen=1000)
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._max_retries = max_retries
        self._retry_delays = retry_delays or [1, 2, 4, 8, 16]
        self._sleep = sleeper or time.sleep
        self._state_dir = self._resolve_state_dir(state_dir)
        self._processed_events_path = self._state_dir / "processed_events.json"
        self._task_queue_path = self._state_dir / "task_queue.jsonl"
        self._retry_queue_path = self._state_dir / "retry_queue.jsonl"
        self._dead_letter_queue_path = self._state_dir / "dead_letter_queue.jsonl"
        self._scheduled_queue_path = self._state_dir / "scheduled_queue.jsonl"
        self._initialize_state_files()

    def _resolve_state_dir(self, state_dir: Optional[Path | str]) -> Path:
        """Resolve .ly_state/session path, defaulting from current working tree."""
        if state_dir is not None:
            return Path(state_dir)

        current = Path.cwd().resolve()
        for candidate in (current, *current.parents):
            session_dir = candidate / ".ly_state" / "session"
            if session_dir.exists():
                return session_dir
        return current / ".ly_state" / "session"

    def _initialize_state_files(self) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        if not self._processed_events_path.exists():
            self._write_json(self._processed_events_path, {"event_ids": []})

        for queue_path in (
            self._task_queue_path,
            self._retry_queue_path,
            self._dead_letter_queue_path,
            self._scheduled_queue_path,
        ):
            queue_path.touch(exist_ok=True)

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists() or path.stat().st_size == 0:
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, data: Dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)

    def _append_jsonl(self, path: Path, data: Dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True) + os.linesep)

    def _read_jsonl(self, path: Path) -> List[Dict[str, Any]]:
        if not path.exists() or path.stat().st_size == 0:
            return []
        with path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def _write_jsonl(self, path: Path, records: List[Dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + os.linesep)

    def _is_duplicate_event(self, event: Event) -> bool:
        processed_events = self._read_json(self._processed_events_path).get("event_ids", [])
        return event.event_id in processed_events

    def _mark_event_processed(self, event: Event) -> None:
        processed = self._read_json(self._processed_events_path)
        event_ids = processed.get("event_ids", [])
        if event.event_id not in event_ids:
            event_ids.append(event.event_id)
            self._write_json(self._processed_events_path, {"event_ids": event_ids})

    def _queue_record(
        self,
        event: Event,
        queue_name: str,
        attempts: int = 0,
        available_at: Optional[str] = None,
        error: str = "",
    ) -> Dict[str, Any]:
        return {
            "event": event.to_dict(),
            "queue": queue_name,
            "attempts": attempts,
            "available_at": available_at,
            "error": error,
        }

    def _deliver_event(self, event: Event, completed_callbacks: Optional[Set[int]] = None) -> int:
        matching_callbacks = []
        with self._bus_lock:
            for pattern, callbacks in self.subscribers.items():
                if self._matches_pattern(event.event_type, pattern):
                    matching_callbacks.extend(callbacks)

        if completed_callbacks is None:
            completed_callbacks = set()
        count = 0
        last_error = None
        for cb in matching_callbacks:
            callback_id = id(cb)
            if callback_id in completed_callbacks:
                continue
            try:
                cb(event)
                count += 1
                completed_callbacks.add(callback_id)
            except Exception as exc:
                last_error = exc
                logger.error(f"Event callback error: {event.event_type} - {exc}")

        if last_error is not None:
            raise RuntimeError(str(last_error))

        return count

    def _publish_with_retry(self, event: Event) -> tuple[int, bool]:
        last_error = ""
        completed_callbacks: Set[int] = set()
        for attempt in range(1, self._max_retries + 1):
            try:
                delivered = self._deliver_event(event, completed_callbacks=completed_callbacks)
                return (len(completed_callbacks) if delivered >= 0 else 0, True)
            except Exception as exc:
                last_error = str(exc)
                if attempt == self._max_retries:
                    break

                delay = self._retry_delays[min(attempt - 1, len(self._retry_delays) - 1)]
                available_at = datetime.now(timezone.utc).timestamp() + delay
                self._append_jsonl(
                    self._retry_queue_path,
                    self._queue_record(
                        event,
                        queue_name="retry",
                        attempts=attempt,
                        available_at=datetime.fromtimestamp(available_at, tz=timezone.utc).isoformat(),
                        error=last_error,
                    ),
                )
                self._append_jsonl(
                    self._scheduled_queue_path,
                    self._queue_record(
                        event,
                        queue_name="scheduled",
                        attempts=attempt,
                        available_at=datetime.fromtimestamp(available_at, tz=timezone.utc).isoformat(),
                        error=last_error,
                    ),
                )
                self._sleep(delay)

        self._append_jsonl(
            self._dead_letter_queue_path,
            self._queue_record(event, queue_name="dead_letter", attempts=self._max_retries, error=last_error),
        )
        return 0, False
    
    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to a specific event type (supports wildcards)."""
        with self._bus_lock:
            if callback not in self.subscribers[event_type]:
                self.subscribers[event_type].append(callback)
                logger.debug(f"Subscribed callback to event: {event_type}")
    
    def unsubscribe(self, event_type: str, callback: Callable) -> bool:
        """Unsubscribe from an event type."""
        with self._bus_lock:
            if event_type in self.subscribers and callback in self.subscribers[event_type]:
                self.subscribers[event_type].remove(callback)
                logger.debug(f"Unsubscribed callback from event: {event_type}")
                return True
            return False
    
    def publish(self, event: Event) -> int:
        """Publish an event to all matching subscribers. Returns count of notified subscribers."""
        logger.debug(f"Publishing event: {event.event_type}")

        with self._bus_lock:
            if self._is_duplicate_event(event):
                logger.warning(f"Duplicate event rejected: {event.event_id}")
                return 0

            self._append_jsonl(self._task_queue_path, self._queue_record(event, queue_name="task"))

        # Store in history
        with self._bus_lock:
            self._history.append(event)

        count, success = self._publish_with_retry(event)
        if success:
            with self._bus_lock:
                self._mark_event_processed(event)

        return count

    def consume_queue(self, queue_name: str, now: Optional[datetime] = None) -> int:
        """Consume due records from task, retry, or scheduled queues."""
        queue_map = {
            "task": self._task_queue_path,
            "retry": self._retry_queue_path,
            "scheduled": self._scheduled_queue_path,
            "dead_letter": self._dead_letter_queue_path,
        }
        if queue_name not in queue_map:
            raise ValueError(f"Unsupported queue: {queue_name}")

        current_time = now or datetime.now(timezone.utc)
        records = self._read_jsonl(queue_map[queue_name])
        remaining = []
        consumed = 0

        for record in records:
            available_at = record.get("available_at")
            if available_at:
                available_dt = datetime.fromisoformat(available_at.replace("Z", "+00:00"))
                if available_dt > current_time:
                    remaining.append(record)
                    continue

            consumed += 1

        self._write_jsonl(queue_map[queue_name], remaining)
        return consumed
    
    def _matches_pattern(self, event_type: str, pattern: str) -> bool:
        """Check if event_type matches subscription pattern."""
        if pattern == "*":
            return True
        return fnmatch.fnmatch(event_type, pattern)
    
    def get_history(self, event_type: Optional[str] = None, limit: Optional[int] = None) -> List[Event]:
        """Get event history, optionally filtered by type."""
        with self._bus_lock:
            history = list(self._history)
        
        if event_type:
            history = [e for e in history if e.event_type == event_type]
        
        # Reverse to get most recent first
        history = list(reversed(history))
        
        if limit:
            history = history[:limit]
        
        return history
    
    def get_event_history(self, event_type: Optional[str] = None, limit: Optional[int] = None) -> List[Event]:
        """Alias for get_history() for backward compatibility."""
        return self.get_history(event_type=event_type, limit=limit)
    
    def clear_history(self):
        """Clear event history."""
        with self._bus_lock:
            self._history.clear()
    
    def get_subscribers(self, event_type: Optional[str] = None) -> Dict[str, int]:
        """Get subscriber counts by event type."""
        with self._bus_lock:
            if event_type:
                return {event_type: len(self.subscribers.get(event_type, []))}
            return {k: len(v) for k, v in self.subscribers.items()}
    
    def clear_subscribers(self):
        """Clear all subscribers."""
        with self._bus_lock:
            self.subscribers.clear()
    
    def register_schema(self, event_type: str, schema: Dict[str, Any]):
        """Register event schema for validation."""
        with self._bus_lock:
            self._schemas[event_type] = schema
    
    def validate_event_schema(self, event: Event, schema: Optional[Dict[str, Any]] = None) -> bool:
        """Validate event against provided schema or registered schema."""
        # Use provided schema or look up registered schema
        if schema is None:
            with self._bus_lock:
                schema = self._schemas.get(event.event_type)
        
        if not schema:
            return True  # No schema provided/registered, pass validation
        
        # Check required fields
        required_fields = schema.get('required_fields', [])
        for field in required_fields:
            if field not in event.payload:
                return False
        
        # Check event version
        if 'version' in schema and schema['version'] != event.event_version:
            return False
        
        # Check enum values in field_definitions
        field_defs = schema.get('field_definitions', {})
        for field, definition in field_defs.items():
            if field in event.payload and definition.get('type') == 'enum':
                allowed_values = definition.get('allowed_values', [])
                if event.payload[field] not in allowed_values:
                    return False
        
        # Check enum values (legacy format)
        enums = schema.get('enums', {})
        for field, allowed_values in enums.items():
            if field in event.payload and event.payload[field] not in allowed_values:
                return False
        
        return True


def get_event_bus() -> EventBus:
    """Factory for EventBus."""
    return EventBus()
