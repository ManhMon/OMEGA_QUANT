"""
Failure Memory Layer - Error and Rollback Storage
Stores failures/errors/rollbacks with pattern detection and recurrence checking.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from pathlib import Path
import json
import logging
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class FailureEntry:
    """Single failure/error entry."""
    failure_id: str
    failure_type: str  # error, rollback, timeout, validation_failure, constraint_violation
    error_message: str
    stack_trace: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    task_type: str = ""
    episode_id: str = ""
    recovery_action: str = ""
    resolved: bool = False
    recurrence_count: int = 1
    first_occurrence: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_occurrence: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FailureEntry':
        return cls(**data)


class FailureMemory:
    """
    Failure Memory Layer - Stores failures with pattern detection.
    Detects recurring failures and patterns.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("data/memory/failure")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.failures: List[FailureEntry] = []
        self._load_failures()

    def _load_failures(self) -> None:
        """Load all failures from storage."""
        failure_file = self.storage_path / "failures.jsonl"
        if not failure_file.exists():
            return

        try:
            with open(failure_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        self.failures.append(FailureEntry.from_dict(data))
            logger.info(f"Loaded {len(self.failures)} failures from storage")
        except Exception as e:
            logger.error(f"Failed to load failures: {e}")

    def _save_failure(self, failure: FailureEntry) -> None:
        """Append failure to storage."""
        failure_file = self.storage_path / "failures.jsonl"
        try:
            with open(failure_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(failure.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to save failure {failure.failure_id}: {e}")

    def _calculate_similarity(self, f1: FailureEntry, f2: FailureEntry) -> float:
        """Calculate similarity between two failures (0.0 to 1.0)."""
        score = 0.0
        
        # Type match (40%)
        if f1.failure_type == f2.failure_type:
            score += 0.4
        
        # Task type match (20%)
        if f1.task_type and f2.task_type and f1.task_type == f2.task_type:
            score += 0.2
        
        # Error message similarity (40%)
        if f1.error_message and f2.error_message:
            # Simple word-based similarity
            words1 = set(f1.error_message.lower().split())
            words2 = set(f2.error_message.lower().split())
            if words1 and words2:
                intersection = len(words1 & words2)
                union = len(words1 | words2)
                score += 0.4 * (intersection / union if union > 0 else 0.0)
        
        return score

    def store_failure(self, failure: FailureEntry) -> None:
        """Store a new failure, checking for recurrence."""
        # Check if this is a recurring failure
        similar_failures = self._find_similar_failures(failure, min_similarity=0.7)
        
        if similar_failures:
            # Update existing failure
            existing = similar_failures[0][0]
            existing.recurrence_count += 1
            existing.last_occurrence = failure.timestamp
            self._rewrite_storage()
            logger.warning(
                f"Recurring failure detected: {existing.failure_id} "
                f"(count={existing.recurrence_count})"
            )
        else:
            # New failure
            self.failures.append(failure)
            self._save_failure(failure)
            logger.info(f"Stored new failure {failure.failure_id} ({failure.failure_type})")

    def _find_similar_failures(
        self,
        failure: FailureEntry,
        min_similarity: float = 0.7
    ) -> List[tuple[FailureEntry, float]]:
        """Find similar failures."""
        results = []
        for existing in self.failures:
            if existing.resolved:
                continue
            similarity = self._calculate_similarity(failure, existing)
            if similarity >= min_similarity:
                results.append((existing, similarity))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def check_recurrence(self, failure: FailureEntry) -> Optional[FailureEntry]:
        """Check if a failure has occurred before."""
        similar = self._find_similar_failures(failure, min_similarity=0.7)
        return similar[0][0] if similar else None

    def query_by_type(self, failure_type: str) -> List[FailureEntry]:
        """Query failures by type."""
        return [f for f in self.failures if f.failure_type == failure_type]

    def query_by_task_type(self, task_type: str) -> List[FailureEntry]:
        """Query failures by task type."""
        return [f for f in self.failures if f.task_type == task_type]

    def query_unresolved(self) -> List[FailureEntry]:
        """Get all unresolved failures."""
        return [f for f in self.failures if not f.resolved]

    def query_recurring(self, min_count: int = 2) -> List[FailureEntry]:
        """Get recurring failures."""
        return [
            f for f in self.failures
            if f.recurrence_count >= min_count and not f.resolved
        ]

    def get_failure_by_id(self, failure_id: str) -> Optional[FailureEntry]:
        """Get specific failure by ID."""
        for failure in self.failures:
            if failure.failure_id == failure_id:
                return failure
        return None

    def mark_resolved(self, failure_id: str, recovery_action: str = "") -> bool:
        """Mark a failure as resolved."""
        for failure in self.failures:
            if failure.failure_id == failure_id:
                failure.resolved = True
                if recovery_action:
                    failure.recovery_action = recovery_action
                self._rewrite_storage()
                logger.info(f"Marked failure {failure_id} as resolved")
                return True
        return False

    def detect_patterns(self) -> Dict[str, Any]:
        """Detect patterns in failures."""
        if not self.failures:
            return {"patterns": []}

        patterns = []
        
        # Pattern 1: Most common failure types
        type_counts = Counter(f.failure_type for f in self.failures if not f.resolved)
        if type_counts:
            patterns.append({
                "pattern_type": "common_failure_types",
                "data": dict(type_counts.most_common(5))
            })
        
        # Pattern 2: Most common task types with failures
        task_counts = Counter(f.task_type for f in self.failures if f.task_type and not f.resolved)
        if task_counts:
            patterns.append({
                "pattern_type": "failure_prone_tasks",
                "data": dict(task_counts.most_common(5))
            })
        
        # Pattern 3: Recurring failures
        recurring = [
            {
                "failure_id": f.failure_id,
                "failure_type": f.failure_type,
                "recurrence_count": f.recurrence_count,
                "error_message": f.error_message[:100]
            }
            for f in self.failures
            if f.recurrence_count >= 3 and not f.resolved
        ]
        if recurring:
            patterns.append({
                "pattern_type": "highly_recurring",
                "data": recurring
            })
        
        # Pattern 4: Time-based clustering (failures in last 24h)
        recent_threshold = datetime.utcnow().isoformat()[:10]  # Today's date
        recent_failures = [
            f for f in self.failures
            if f.timestamp >= recent_threshold and not f.resolved
        ]
        if recent_failures:
            patterns.append({
                "pattern_type": "recent_spike",
                "data": {
                    "count": len(recent_failures),
                    "types": dict(Counter(f.failure_type for f in recent_failures))
                }
            })
        
        return {"patterns": patterns}

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about stored failures."""
        if not self.failures:
            return {
                "total_failures": 0,
                "unresolved": 0,
                "by_type": {},
                "recurring_count": 0,
                "avg_recurrence": 0.0
            }

        by_type: Dict[str, int] = {}
        unresolved = 0
        recurring_count = 0
        total_recurrence = 0

        for failure in self.failures:
            by_type[failure.failure_type] = by_type.get(failure.failure_type, 0) + 1
            if not failure.resolved:
                unresolved += 1
            if failure.recurrence_count > 1:
                recurring_count += 1
            total_recurrence += failure.recurrence_count

        return {
            "total_failures": len(self.failures),
            "unresolved": unresolved,
            "by_type": by_type,
            "recurring_count": recurring_count,
            "avg_recurrence": total_recurrence / len(self.failures)
        }

    def _rewrite_storage(self) -> None:
        """Rewrite entire failure storage."""
        failure_file = self.storage_path / "failures.jsonl"
        try:
            with open(failure_file, 'w', encoding='utf-8') as f:
                for failure in self.failures:
                    f.write(json.dumps(failure.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to rewrite failure storage: {e}")

    def clear_resolved(self) -> int:
        """Remove resolved failures from memory."""
        original_count = len(self.failures)
        self.failures = [f for f in self.failures if not f.resolved]
        removed_count = original_count - len(self.failures)

        if removed_count > 0:
            self._rewrite_storage()
            logger.info(f"Cleared {removed_count} resolved failures")

        return removed_count

    def get_recent_failures(self, limit: int = 10) -> List[FailureEntry]:
        """Get most recent failures."""
        return sorted(
            self.failures,
            key=lambda f: f.last_occurrence,
            reverse=True
        )[:limit]
