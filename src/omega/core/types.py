"""
OMEGA_QUANT Core Types — shared dataclasses and protocols used across modules.

PipelineFrame: lightweight container for time-aligned feature/signal data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PipelineFrame:
    """
    Lightweight container for time-aligned columnar data.

    Used to pass features, signals, or targets between pipeline stages.

    Attributes:
        timestamps: Ordered list of Unix timestamps (int, seconds).
        values: Dict mapping column name -> list of values (parallel to timestamps).
        metadata: Optional arbitrary metadata dict.
    """

    timestamps: List[int]
    values: Dict[str, List[Any]] = field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = field(default=None)

    def __len__(self) -> int:
        return len(self.timestamps)

    def get_column(self, name: str) -> List[Any]:
        """Return column values by name, or empty list if not found."""
        return self.values.get(name, [])

    def columns(self) -> List[str]:
        """Return list of column names."""
        return list(self.values.keys())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to plain dict."""
        return {
            "timestamps": self.timestamps,
            "values": self.values,
            "metadata": self.metadata,
        }
