"""Forensic Filter Module - JEV Deep Integration Shadow.

Counterfactual forensics tracking audit qualifications, report revisions,
and label validity without hard production vetoes.
"""
from datetime import datetime, timezone
from typing import Dict, Any


class ForensicFilter:
    """Forensic filter for counterfactual event and report shadow."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def evaluate_counterfactual(self, events=None, as_of=None) -> Dict[str, Any]:
        """Evaluate forensic exclusions counterfactually."""
        if as_of is None:
            as_of = datetime.now(timezone.utc)
        if not isinstance(as_of, datetime):
            raise ValueError("as_of must be datetime")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if events is None:
            events = []
        if not isinstance(events, (list, tuple)):
            raise ValueError("events must be a sequence of mappings")
        qualifying = []
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("event must be a mapping")
            available = event.get("available_at")
            if not isinstance(available, datetime) or available.tzinfo is None or available.utcoffset() is None:
                raise ValueError("event available_at must be timezone-aware")
            novelty = event.get("novelty")
            if not isinstance(novelty, str) or novelty not in ("new", "revision", "duplicate"):
                raise ValueError("event novelty must be new, revision, or duplicate")
            if available <= as_of and novelty != "duplicate":
                qualifying.append({"event_id": event.get("event_id"), "reason": novelty})
        return {"action": "shadow", "excluded": False, "counterfactual": True,
                "qualified_events": qualifying, "counterfactual_excluded": bool(qualifying)}
