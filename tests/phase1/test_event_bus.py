"""
Test suite for Event Bus (Pub/Sub with Versioning)

Tests cover:
- Event creation and serialization
- Basic pub/sub operations
- Wildcard subscriptions
- Thread safety
- Event versioning and schema validation
- Event history and replay

Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 3 (Event-Driven IPC Schema)
"""

import json
import pytest
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

from omega.core.event_bus import Event, EventBus


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / ".ly_state" / "session"


class TestEvent:
    """Test Event class functionality."""
    
    def test_event_creation_with_defaults(self):
        """Test creating an event with minimal fields."""
        event = Event(
            event_type="TASK_CREATED",
            payload={"task_id": "abc-123"}
        )
        
        assert event.event_type == "TASK_CREATED"
        assert event.payload == {"task_id": "abc-123"}
        assert event.event_version == "1.0"
        assert event.event_id is not None
        assert event.timestamp is not None
        assert event.severity == "INFO"
        assert event.schema_id is not None
        assert event.schema_id.startswith("sha256:")
    
    def test_event_creation_with_all_fields(self):
        """Test creating an event with all fields specified."""
        timestamp = datetime.utcnow()
        event = Event(
            event_type="MODEL_TRAINED",
            payload={"model_id": "model-001", "metrics": {"ic": 0.15}},
            event_version="2.0",
            event_id="evt-123",
            timestamp=timestamp,
            source="OpenCode",
            target="Codex",
            correlation_id="corr-456",
            causation_id="cause-789",
            trace_id="trace-abc",
            severity="WARN",
            schema_id="sha256:custom"
        )
        
        assert event.event_type == "MODEL_TRAINED"
        assert event.event_version == "2.0"
        assert event.event_id == "evt-123"
        assert event.timestamp == timestamp
        assert event.source == "OpenCode"
        assert event.target == "Codex"
        assert event.correlation_id == "corr-456"
        assert event.causation_id == "cause-789"
        assert event.trace_id == "trace-abc"
        assert event.severity == "WARN"
        assert event.schema_id == "sha256:custom"
    
    def test_event_to_dict(self):
        """Test event serialization to dictionary."""
        event = Event(
            event_type="TASK_COMPLETED",
            payload={"task_id": "task-001"},
            source="OpenCode"
        )
        
        event_dict = event.to_dict()
        
        assert event_dict["event_type"] == "TASK_COMPLETED"
        assert event_dict["payload"] == {"task_id": "task-001"}
        assert event_dict["source"] == "OpenCode"
        assert "event_id" in event_dict
        assert "timestamp" in event_dict
        assert "schema_id" in event_dict

    def test_event_timestamp_roundtrip_preserves_offset(self):
        """Test timezone-aware timestamp roundtrips without duplicate zone suffix."""
        timestamp = datetime(2026, 5, 9, 4, 22, 17, 123456, tzinfo=timezone(timedelta(hours=7)))
        event = Event(event_type="TASK_COMPLETED", payload={"task_id": "task-001"}, timestamp=timestamp)

        event_dict = event.to_dict()
        restored = Event.from_dict(event_dict)

        assert event_dict["timestamp"] == "2026-05-09T04:22:17.123456+07:00"
        assert restored.timestamp == timestamp
    
    def test_event_from_dict(self):
        """Test event deserialization from dictionary."""
        event_dict = {
            "event_id": "evt-123",
            "event_type": "TASK_FAILED",
            "event_version": "1.0",
            "timestamp": "2026-05-09T04:22:17Z",
            "source": "OpenCode",
            "payload": {"task_id": "task-001", "error": "timeout"},
            "severity": "ERROR",
            "schema_id": "sha256:abc123"
        }
        
        event = Event.from_dict(event_dict)
        
        assert event.event_id == "evt-123"
        assert event.event_type == "TASK_FAILED"
        assert event.event_version == "1.0"
        assert event.source == "OpenCode"
        assert event.payload == {"task_id": "task-001", "error": "timeout"}
        assert event.severity == "ERROR"
        assert event.schema_id == "sha256:abc123"
    
    def test_event_schema_hash_computation(self):
        """Test that schema hash is computed correctly."""
        event1 = Event(
            event_type="TASK_CREATED",
            payload={"task_id": "123", "priority": 5}
        )
        
        event2 = Event(
            event_type="TASK_CREATED",
            payload={"priority": 5, "task_id": "123"}  # Different order
        )
        
        # Same event type and payload keys should produce same hash
        assert event1.schema_id == event2.schema_id
        
        event3 = Event(
            event_type="TASK_CREATED",
            payload={"task_id": "123"}  # Different keys
        )
        
        # Different payload keys should produce different hash
        assert event1.schema_id != event3.schema_id


class TestEventBusBasic:
    """Test basic EventBus functionality."""
    
    def test_subscribe_and_publish(self):
        """Test basic subscribe and publish."""
        bus = EventBus()
        received_events = []
        
        def callback(event: Event):
            received_events.append(event)
        
        bus.subscribe("TASK_CREATED", callback)
        
        event = Event(event_type="TASK_CREATED", payload={"task_id": "123"})
        count = bus.publish(event)
        
        assert count == 1
        assert len(received_events) == 1
        assert received_events[0].event_type == "TASK_CREATED"
    
    def test_multiple_subscribers(self):
        """Test multiple subscribers to same event type."""
        bus = EventBus()
        received_1 = []
        received_2 = []
        
        bus.subscribe("TASK_CREATED", lambda e: received_1.append(e))
        bus.subscribe("TASK_CREATED", lambda e: received_2.append(e))
        
        event = Event(event_type="TASK_CREATED", payload={"task_id": "123"})
        count = bus.publish(event)
        
        assert count == 2
        assert len(received_1) == 1
        assert len(received_2) == 1
    
    def test_unsubscribe(self):
        """Test unsubscribing from events."""
        bus = EventBus()
        received_events = []
        
        def callback(event: Event):
            received_events.append(event)
        
        bus.subscribe("TASK_CREATED", callback)
        
        # Publish first event
        event1 = Event(event_type="TASK_CREATED", payload={"task_id": "123"})
        bus.publish(event1)
        assert len(received_events) == 1
        
        # Unsubscribe
        result = bus.unsubscribe("TASK_CREATED", callback)
        assert result is True
        
        # Publish second event
        event2 = Event(event_type="TASK_CREATED", payload={"task_id": "456"})
        bus.publish(event2)
        assert len(received_events) == 1  # Should not receive second event
    
    def test_unsubscribe_nonexistent(self):
        """Test unsubscribing a callback that doesn't exist."""
        bus = EventBus()
        
        def callback(event: Event):
            pass
        
        result = bus.unsubscribe("TASK_CREATED", callback)
        assert result is False
    
    def test_no_subscribers(self):
        """Test publishing event with no subscribers."""
        bus = EventBus()
        
        event = Event(event_type="TASK_CREATED", payload={"task_id": "123"})
        count = bus.publish(event)
        
        assert count == 0

    def test_duplicate_event_rejected(self, state_dir: Path):
        """Test duplicate event_id is rejected and not redelivered."""
        bus = EventBus(state_dir=state_dir)
        received_events = []

        bus.subscribe("TASK_CREATED", lambda e: received_events.append(e))
        event = Event(event_type="TASK_CREATED", payload={"task_id": "123"}, event_id="evt-dup")

        assert bus.publish(event) == 1
        assert bus.publish(event) == 0
        assert len(received_events) == 1

        processed_events = (state_dir / "processed_events.json").read_text(encoding="utf-8")
        assert "evt-dup" in processed_events

    def test_retry_then_success(self, state_dir: Path):
        """Test at-least-once delivery retries failed event before success."""
        delays = []
        bus = EventBus(state_dir=state_dir, sleeper=delays.append)
        attempts = []

        def flaky_callback(event: Event):
            attempts.append(event.event_id)
            if len(attempts) < 3:
                raise RuntimeError("transient")

        bus.subscribe("TASK_CREATED", flaky_callback)

        count = bus.publish(Event(event_type="TASK_CREATED", payload={"task_id": "123"}, event_id="evt-retry"))

        assert count == 1
        assert len(attempts) == 3
        assert delays == [1, 2]
        retry_queue = (state_dir / "retry_queue.jsonl").read_text(encoding="utf-8")
        scheduled_queue = (state_dir / "scheduled_queue.jsonl").read_text(encoding="utf-8")
        assert "evt-retry" in retry_queue
        assert "evt-retry" in scheduled_queue

    def test_dead_letter_after_max_retries(self, state_dir: Path):
        """Test permanently failing event moves to dead-letter queue."""
        delays = []
        bus = EventBus(state_dir=state_dir, sleeper=delays.append)

        def failing_callback(event: Event):
            raise RuntimeError("permanent")

        bus.subscribe("TASK_CREATED", failing_callback)

        count = bus.publish(Event(event_type="TASK_CREATED", payload={"task_id": "123"}, event_id="evt-dead"))

        assert count == 0
        assert delays == [1, 2, 4, 8]
        dead_letter_queue = (state_dir / "dead_letter_queue.jsonl").read_text(encoding="utf-8")
        assert "evt-dead" in dead_letter_queue
        processed_events = json.loads((state_dir / "processed_events.json").read_text(encoding="utf-8"))
        assert "evt-dead" not in processed_events["event_ids"]

    def test_failed_subscriber_does_not_redeliver_successful_subscriber(self, state_dir: Path):
        """Test retry only redelivers to subscribers that have not succeeded yet."""
        delays = []
        bus = EventBus(state_dir=state_dir, sleeper=delays.append)
        successful_attempts = []
        flaky_attempts = []

        def stable_callback(event: Event):
            successful_attempts.append(event.event_id)

        def flaky_callback(event: Event):
            flaky_attempts.append(event.event_id)
            if len(flaky_attempts) < 3:
                raise RuntimeError("transient")

        bus.subscribe("TASK_CREATED", stable_callback)
        bus.subscribe("TASK_CREATED", flaky_callback)

        count = bus.publish(Event(event_type="TASK_CREATED", payload={"task_id": "123"}, event_id="evt-isolation"))

        assert count == 2
        assert successful_attempts == ["evt-isolation"]
        assert flaky_attempts == ["evt-isolation", "evt-isolation", "evt-isolation"]
        assert delays == [1, 2]

    def test_queue_files_created_and_consumed(self, state_dir: Path):
        """Test queue separation and due-item consumption."""
        bus = EventBus(state_dir=state_dir)
        event = Event(event_type="TASK_CREATED", payload={"task_id": "123"}, event_id="evt-queue")

        bus.publish(event)

        for name in ["task_queue.jsonl", "retry_queue.jsonl", "dead_letter_queue.jsonl", "scheduled_queue.jsonl"]:
            assert (state_dir / name).exists()

        future_record = {
            "event": event.to_dict(),
            "queue": "scheduled",
            "attempts": 1,
            "available_at": "2999-01-01T00:00:00+00:00",
            "error": "",
        }
        (state_dir / "scheduled_queue.jsonl").write_text(
            json.dumps(future_record) + "\n",
            encoding="utf-8",
        )

        assert bus.consume_queue("task") == 1
        assert bus.consume_queue("scheduled") == 0


class TestEventBusWildcard:
    """Test wildcard subscription functionality."""
    
    def test_wildcard_star_subscription(self):
        """Test wildcard subscription with '*'."""
        bus = EventBus()
        received_events = []
        
        bus.subscribe("task.*", lambda e: received_events.append(e))
        
        # Should match
        bus.publish(Event(event_type="task.created", payload={}))
        bus.publish(Event(event_type="task.completed", payload={}))
        bus.publish(Event(event_type="task.failed", payload={}))
        
        # Should not match
        bus.publish(Event(event_type="model.trained", payload={}))
        
        assert len(received_events) == 3
        assert received_events[0].event_type == "task.created"
        assert received_events[1].event_type == "task.completed"
        assert received_events[2].event_type == "task.failed"
    
    def test_wildcard_all_events(self):
        """Test subscribing to all events with '*'."""
        bus = EventBus()
        received_events = []
        
        bus.subscribe("*", lambda e: received_events.append(e))
        
        bus.publish(Event(event_type="task.created", payload={}))
        bus.publish(Event(event_type="model.trained", payload={}))
        bus.publish(Event(event_type="deployment.started", payload={}))
        
        assert len(received_events) == 3
    
    def test_exact_and_wildcard_subscriptions(self):
        """Test mixing exact and wildcard subscriptions."""
        bus = EventBus()
        exact_events = []
        wildcard_events = []
        
        bus.subscribe("task.created", lambda e: exact_events.append(e))
        bus.subscribe("task.*", lambda e: wildcard_events.append(e))
        
        bus.publish(Event(event_type="task.created", payload={}))
        bus.publish(Event(event_type="task.completed", payload={}))
        
        assert len(exact_events) == 1  # Only task.created
        assert len(wildcard_events) == 2  # Both events


class TestEventBusThreadSafety:
    """Test thread safety of EventBus."""
    
    def test_concurrent_publish(self):
        """Test publishing events from multiple threads."""
        bus = EventBus()
        received_events = []
        lock = threading.Lock()
        
        def callback(event: Event):
            with lock:
                received_events.append(event)
        
        bus.subscribe("task.*", callback)
        
        def publish_events(thread_id: int, count: int):
            for i in range(count):
                event = Event(
                    event_type="task.created",
                    payload={"thread_id": thread_id, "index": i}
                )
                bus.publish(event)
        
        threads = []
        num_threads = 10
        events_per_thread = 10
        
        for i in range(num_threads):
            thread = threading.Thread(target=publish_events, args=(i, events_per_thread))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        assert len(received_events) == num_threads * events_per_thread
    
    def test_concurrent_subscribe_unsubscribe(self):
        """Test subscribing and unsubscribing from multiple threads."""
        bus = EventBus()
        
        def callback(event: Event):
            pass
        
        def subscribe_unsubscribe(iterations: int):
            for _ in range(iterations):
                bus.subscribe("task.created", callback)
                time.sleep(0.001)
                bus.unsubscribe("task.created", callback)
        
        threads = []
        num_threads = 5
        iterations = 10
        
        for _ in range(num_threads):
            thread = threading.Thread(target=subscribe_unsubscribe, args=(iterations,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Should complete without deadlock or errors
        assert True


class TestEventBusHistory:
    """Test event history functionality."""
    
    def test_event_history_storage(self):
        """Test that events are stored in history."""
        bus = EventBus()
        
        event1 = Event(event_type="task.created", payload={"task_id": "1"})
        event2 = Event(event_type="task.completed", payload={"task_id": "2"})
        
        bus.publish(event1)
        bus.publish(event2)
        
        history = bus.get_event_history()
        
        assert len(history) == 2
        assert history[0].event_type == "task.completed"  # Most recent first
        assert history[1].event_type == "task.created"
    
    def test_event_history_filter_by_type(self):
        """Test filtering event history by type."""
        bus = EventBus()
        
        bus.publish(Event(event_type="task.created", payload={}))
        bus.publish(Event(event_type="model.trained", payload={}))
        bus.publish(Event(event_type="task.completed", payload={}))
        
        task_history = bus.get_event_history(event_type="task.created")
        
        assert len(task_history) == 1
        assert task_history[0].event_type == "task.created"
    
    def test_event_history_limit(self):
        """Test limiting event history results."""
        bus = EventBus()
        
        for i in range(10):
            bus.publish(Event(event_type="task.created", payload={"index": i}))
        
        history = bus.get_event_history(limit=5)
        
        assert len(history) == 5
        # Should get most recent 5 (indices 9, 8, 7, 6, 5)
        assert history[0].payload["index"] == 9
    
    def test_clear_history(self):
        """Test clearing event history."""
        bus = EventBus()
        
        bus.publish(Event(event_type="task.created", payload={}))
        bus.publish(Event(event_type="task.completed", payload={}))
        
        assert len(bus.get_event_history()) == 2
        
        bus.clear_history()
        
        assert len(bus.get_event_history()) == 0


class TestEventBusSchemaValidation:
    """Test event schema validation."""
    
    def test_validate_event_schema_valid(self):
        """Test validating a valid event against schema."""
        bus = EventBus()
        
        event = Event(
            event_type="TASK_CREATED",
            event_version="1.0",
            payload={
                "task_id": "abc-123",
                "task_type": "coding",
                "priority": 5
            }
        )
        
        schema = {
            "version": "1.0",
            "required_fields": ["task_id", "task_type"],
            "field_definitions": {
                "task_id": {"type": "string"},
                "task_type": {"type": "enum", "allowed_values": ["planning", "coding", "testing"]},
                "priority": {"type": "integer"}
            }
        }
        
        assert bus.validate_event_schema(event, schema) is True
    
    def test_validate_event_schema_missing_field(self):
        """Test validation fails when required field is missing."""
        bus = EventBus()
        
        event = Event(
            event_type="TASK_CREATED",
            event_version="1.0",
            payload={"task_id": "abc-123"}  # Missing task_type
        )
        
        schema = {
            "version": "1.0",
            "required_fields": ["task_id", "task_type"]
        }
        
        assert bus.validate_event_schema(event, schema) is False
    
    def test_validate_event_schema_wrong_version(self):
        """Test validation fails when version doesn't match."""
        bus = EventBus()
        
        event = Event(
            event_type="TASK_CREATED",
            event_version="1.0",
            payload={"task_id": "abc-123"}
        )
        
        schema = {
            "version": "2.0",
            "required_fields": ["task_id"]
        }
        
        assert bus.validate_event_schema(event, schema) is False
    
    def test_validate_event_schema_invalid_enum(self):
        """Test validation fails when enum value is invalid."""
        bus = EventBus()
        
        event = Event(
            event_type="TASK_CREATED",
            event_version="1.0",
            payload={
                "task_id": "abc-123",
                "task_type": "invalid_type"
            }
        )
        
        schema = {
            "version": "1.0",
            "required_fields": ["task_id", "task_type"],
            "field_definitions": {
                "task_type": {"type": "enum", "allowed_values": ["planning", "coding"]}
            }
        }
        
        assert bus.validate_event_schema(event, schema) is False


class TestEventBusUtilities:
    """Test utility methods of EventBus."""
    
    def test_get_subscribers(self):
        """Test getting subscriber counts."""
        bus = EventBus()
        
        bus.subscribe("task.created", lambda e: None)
        bus.subscribe("task.created", lambda e: None)
        bus.subscribe("model.trained", lambda e: None)
        
        subscribers = bus.get_subscribers()
        
        assert subscribers["task.created"] == 2
        assert subscribers["model.trained"] == 1
    
    def test_get_subscribers_for_specific_type(self):
        """Test getting subscriber count for specific event type."""
        bus = EventBus()
        
        bus.subscribe("task.created", lambda e: None)
        bus.subscribe("task.created", lambda e: None)
        
        subscribers = bus.get_subscribers("task.created")
        
        assert subscribers == {"task.created": 2}
    
    def test_clear_subscribers(self):
        """Test clearing all subscribers."""
        bus = EventBus()
        
        bus.subscribe("task.created", lambda e: None)
        bus.subscribe("model.trained", lambda e: None)
        
        assert len(bus.get_subscribers()) == 2
        
        bus.clear_subscribers()
        
        assert len(bus.get_subscribers()) == 0
    
    def test_duplicate_subscription_prevention(self):
        """Test that duplicate subscriptions are prevented."""
        bus = EventBus()
        
        def callback(event: Event):
            pass
        
        bus.subscribe("task.created", callback)
        bus.subscribe("task.created", callback)  # Duplicate
        
        subscribers = bus.get_subscribers("task.created")
        
        assert subscribers["task.created"] == 1  # Should only have 1
