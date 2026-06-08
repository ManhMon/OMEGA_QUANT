"""
Structured Logger - OMEGA_QUANT Phase 7.
JSON logging with correlation IDs and trace IDs.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class StructuredLogger:
    """JSON logger with correlation/trace IDs for distributed tracing."""
    
    def __init__(self, name: str = "OmegaLogger", level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Console handler
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)
        
    def _build_log_entry(
        self,
        level: str,
        message: str,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Build structured log entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            "correlation_id": correlation_id or str(uuid.uuid4()),
            "trace_id": trace_id or str(uuid.uuid4())
        }
        entry.update(kwargs)
        return entry
    
    def info(self, message: str, **kwargs) -> str:
        """Log INFO level with structured data."""
        entry = self._build_log_entry("INFO", message, **kwargs)
        self.logger.info(json.dumps(entry, default=str))
        return entry["correlation_id"]
    
    def warning(self, message: str, **kwargs) -> str:
        """Log WARNING level with structured data."""
        entry = self._build_log_entry("WARNING", message, **kwargs)
        self.logger.warning(json.dumps(entry, default=str))
        return entry["correlation_id"]
    
    def error(self, message: str, **kwargs) -> str:
        """Log ERROR level with structured data."""
        entry = self._build_log_entry("ERROR", message, **kwargs)
        self.logger.error(json.dumps(entry, default=str))
        return entry["correlation_id"]
    
    def debug(self, message: str, **kwargs) -> str:
        """Log DEBUG level with structured data."""
        entry = self._build_log_entry("DEBUG", message, **kwargs)
        self.logger.debug(json.dumps(entry, default=str))
        return entry["correlation_id"]
    
    def get_errors(self) -> list:
        """Get all error log entries."""
        if not hasattr(self, '_error_log'):
            self._error_log = []
        return self._error_log
    
    def error(self, message: str, **kwargs) -> str:
        """Log ERROR level with structured data."""
        entry = self._build_log_entry("ERROR", message, **kwargs)
        self.logger.error(json.dumps(entry, default=str))
        
        # Store error for retrieval
        if not hasattr(self, '_error_log'):
            self._error_log = []
        self._error_log.append(entry)
        
        return entry["correlation_id"]
