"""Distributed tracing for observability.

Implements distributed tracing with:
- TraceContext for trace propagation
- Span for operation tracking
- Tracer for span management
- Decorator for automatic tracing
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import logging
from datetime import datetime
import threading
import time
import uuid
from functools import wraps


logger = logging.getLogger(__name__)


class SpanKind(Enum):
    """Span kind classification."""
    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatus(Enum):
    """Span status."""
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class TraceContext:
    """Trace context for distributed tracing."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    trace_flags: int = 1  # 1 = sampled
    trace_state: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for propagation."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "trace_flags": self.trace_flags,
            "trace_state": self.trace_state
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TraceContext":
        """Create from dictionary."""
        return cls(
            trace_id=data["trace_id"],
            span_id=data["span_id"],
            parent_span_id=data.get("parent_span_id"),
            trace_flags=data.get("trace_flags", 1),
            trace_state=data.get("trace_state", {})
        )


@dataclass
class Span:
    """Span representing a traced operation."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    kind: SpanKind
    start_time: float
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    def duration_ms(self) -> Optional[float]:
        """Get span duration in milliseconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000
    
    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Add an event to the span."""
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {}
        })
    
    def set_attribute(self, key: str, value: Any):
        """Set a span attribute."""
        self.attributes[key] = value
    
    def set_status(self, status: SpanStatus, description: Optional[str] = None):
        """Set span status."""
        self.status = status
        if description:
            self.attributes["status.description"] = description
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert span to dictionary."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms(),
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events
        }


class Tracer:
    """Tracer for managing spans and traces."""
    
    def __init__(self, service_name: str = "omega_quant"):
        """Initialize tracer.
        
        Args:
            service_name: Name of the service
        """
        self.service_name = service_name
        
        # Thread-local storage for current span
        self._local = threading.local()
        
        # Completed spans storage
        self._spans: List[Span] = []
        self._spans_lock = threading.Lock()
        
        # Active spans by span_id
        self._active_spans: Dict[str, Span] = {}
        self._active_lock = threading.Lock()
        
        logger.info("Tracer initialized for service: %s", service_name)
    
    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None,
        parent_context: Optional[TraceContext] = None
    ) -> Span:
        """Start a new span.
        
        Args:
            name: Span name
            kind: Span kind
            attributes: Initial attributes
            parent_context: Parent trace context
            
        Returns:
            New Span instance
        """
        # Get or create trace context
        if parent_context:
            trace_id = parent_context.trace_id
            parent_span_id = parent_context.span_id
        else:
            current_span = self.get_current_span()
            if current_span:
                trace_id = current_span.trace_id
                parent_span_id = current_span.span_id
            else:
                trace_id = self._generate_trace_id()
                parent_span_id = None
        
        # Create span
        span = Span(
            trace_id=trace_id,
            span_id=self._generate_span_id(),
            parent_span_id=parent_span_id,
            name=name,
            kind=kind,
            start_time=time.time(),
            attributes=attributes or {}
        )
        
        # Add service name
        span.set_attribute("service.name", self.service_name)
        
        # Register as active span
        with self._active_lock:
            self._active_spans[span.span_id] = span
        
        # Set as current span in thread-local storage
        self._set_current_span(span)
        
        logger.debug("Started span: %s (trace_id=%s, span_id=%s)", name, trace_id, span.span_id)
        
        return span
    
    def end_span(self, span: Span):
        """End a span.
        
        Args:
            span: Span to end
        """
        if span.end_time is not None:
            logger.warning("Span %s already ended", span.span_id)
            return
        
        span.end_time = time.time()
        
        # Remove from active spans
        with self._active_lock:
            self._active_spans.pop(span.span_id, None)
        
        # Store completed span
        with self._spans_lock:
            self._spans.append(span)
            # Keep last 10000 spans
            if len(self._spans) > 10000:
                self._spans = self._spans[-10000:]
        
        logger.debug(
            "Ended span: %s (duration=%.2fms, status=%s)",
            span.name,
            span.duration_ms(),
            span.status.value
        )
        
        # Clear current span if it's this one
        current = self.get_current_span()
        if current and current.span_id == span.span_id:
            self._clear_current_span()
    
    def get_current_span(self) -> Optional[Span]:
        """Get current span from thread-local storage."""
        return getattr(self._local, "current_span", None)
    
    def _set_current_span(self, span: Span):
        """Set current span in thread-local storage."""
        self._local.current_span = span
    
    def _clear_current_span(self):
        """Clear current span from thread-local storage."""
        self._local.current_span = None
    
    def get_trace(self, trace_id: str) -> List[Span]:
        """Get all spans for a trace.
        
        Args:
            trace_id: Trace ID
            
        Returns:
            List of spans in the trace
        """
        with self._spans_lock:
            return [s for s in self._spans if s.trace_id == trace_id]
    
    def get_trace_context(self) -> Optional[TraceContext]:
        """Get current trace context.
        
        Returns:
            TraceContext or None if no active span
        """
        span = self.get_current_span()
        if not span:
            return None
        
        return TraceContext(
            trace_id=span.trace_id,
            span_id=span.span_id,
            parent_span_id=span.parent_span_id
        )
    
    def inject_context(self, carrier: Dict[str, str]):
        """Inject trace context into carrier (e.g., HTTP headers).
        
        Args:
            carrier: Dictionary to inject context into
        """
        context = self.get_trace_context()
        if not context:
            return
        
        carrier["traceparent"] = f"00-{context.trace_id}-{context.span_id}-{context.trace_flags:02x}"
        if context.trace_state:
            carrier["tracestate"] = ",".join(f"{k}={v}" for k, v in context.trace_state.items())
    
    def extract_context(self, carrier: Dict[str, str]) -> Optional[TraceContext]:
        """Extract trace context from carrier (e.g., HTTP headers).
        
        Args:
            carrier: Dictionary to extract context from
            
        Returns:
            TraceContext or None if not found
        """
        traceparent = carrier.get("traceparent")
        if not traceparent:
            return None
        
        try:
            parts = traceparent.split("-")
            if len(parts) != 4:
                return None
            
            version, trace_id, span_id, flags = parts
            
            trace_state = {}
            tracestate = carrier.get("tracestate")
            if tracestate:
                for item in tracestate.split(","):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        trace_state[k] = v
            
            return TraceContext(
                trace_id=trace_id,
                span_id=span_id,
                trace_flags=int(flags, 16),
                trace_state=trace_state
            )
        except Exception as e:
            logger.warning("Failed to extract trace context: %s", e)
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get tracer statistics."""
        with self._spans_lock:
            completed_count = len(self._spans)
            
            # Calculate average duration
            durations = [s.duration_ms() for s in self._spans if s.duration_ms() is not None]
            avg_duration = sum(durations) / len(durations) if durations else 0.0
            
            # Count by status
            status_counts = {}
            for span in self._spans:
                status_counts[span.status.value] = status_counts.get(span.status.value, 0) + 1
        
        with self._active_lock:
            active_count = len(self._active_spans)
        
        return {
            "service_name": self.service_name,
            "completed_spans": completed_count,
            "active_spans": active_count,
            "avg_duration_ms": avg_duration,
            "status_counts": status_counts
        }
    
    def _generate_trace_id(self) -> str:
        """Generate a new trace ID."""
        return uuid.uuid4().hex[:32]
    
    def _generate_span_id(self) -> str:
        """Generate a new span ID."""
        return uuid.uuid4().hex[:16]
    
    def clear_spans(self):
        """Clear all stored spans."""
        with self._spans_lock:
            self._spans.clear()
        logger.info("Cleared all spans")


# Global tracer instance
_global_tracer: Optional[Tracer] = None
_tracer_lock = threading.Lock()


def get_tracer(service_name: str = "omega_quant") -> Tracer:
    """Get or create global tracer instance.
    
    Args:
        service_name: Service name for tracer
        
    Returns:
        Global Tracer instance
    """
    global _global_tracer
    
    with _tracer_lock:
        if _global_tracer is None:
            _global_tracer = Tracer(service_name)
        return _global_tracer


def traced(
    name: Optional[str] = None,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None
) -> Callable:
    """Decorator to automatically trace a function.
    
    Args:
        name: Span name (defaults to function name)
        kind: Span kind
        attributes: Initial span attributes
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            span = tracer.start_span(span_name, kind=kind, attributes=attributes)
            
            try:
                # Add function info
                span.set_attribute("function.name", func.__name__)
                span.set_attribute("function.module", func.__module__)
                
                # Execute function
                result = func(*args, **kwargs)
                
                # Mark as successful
                span.set_status(SpanStatus.OK)
                
                return result
            
            except Exception as e:
                # Mark as error
                span.set_status(SpanStatus.ERROR, str(e))
                span.set_attribute("exception.type", type(e).__name__)
                span.set_attribute("exception.message", str(e))
                span.add_event("exception", {
                    "exception.type": type(e).__name__,
                    "exception.message": str(e)
                })
                raise
            
            finally:
                tracer.end_span(span)
        
        return wrapper
    
    return decorator
