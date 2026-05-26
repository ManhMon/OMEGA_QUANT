"""
Policy Memory Layer - Decision and Policy Storage
Stores decisions/policies applied, query by context.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class PolicyEntry:
    """Single policy/decision entry."""
    policy_id: str
    policy_type: str  # decision, rule, constraint, guideline
    context: Dict[str, Any]  # Context in which policy applies
    action: str  # What action/decision was taken
    rationale: str  # Why this policy was applied
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    applied_count: int = 1
    success_count: int = 0
    failure_count: int = 0
    last_applied: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PolicyEntry':
        return cls(**data)


class PolicyMemory:
    """
    Policy Memory Layer - Stores decisions and policies.
    Query by context to find applicable policies.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("data/memory/policy")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.policies: List[PolicyEntry] = []
        self._load_policies()

    def _load_policies(self) -> None:
        """Load all policies from storage."""
        policy_file = self.storage_path / "policies.jsonl"
        if not policy_file.exists():
            return

        try:
            with open(policy_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        self.policies.append(PolicyEntry.from_dict(data))
            logger.info(f"Loaded {len(self.policies)} policies from storage")
        except Exception as e:
            logger.error(f"Failed to load policies: {e}")

    def _save_policy(self, policy: PolicyEntry) -> None:
        """Append policy to storage."""
        policy_file = self.storage_path / "policies.jsonl"
        try:
            with open(policy_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(policy.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to save policy {policy.policy_id}: {e}")

    def store_policy(self, policy: PolicyEntry) -> None:
        """Store a new policy."""
        self.policies.append(policy)
        self._save_policy(policy)
        logger.info(f"Stored policy {policy.policy_id} ({policy.policy_type})")

    def _context_matches(self, policy_context: Dict[str, Any], query_context: Dict[str, Any]) -> float:
        """
        Calculate context match score (0.0 to 1.0).
        Returns proportion of query context keys that match policy context.
        """
        if not query_context:
            return 0.0

        matches = 0
        total = len(query_context)

        for key, value in query_context.items():
            if key in policy_context:
                if policy_context[key] == value:
                    matches += 1
                elif isinstance(value, str) and isinstance(policy_context[key], str):
                    # Partial string match
                    if value.lower() in policy_context[key].lower() or \
                       policy_context[key].lower() in value.lower():
                        matches += 0.5

        return matches / total if total > 0 else 0.0

    def query_by_context(
        self,
        context: Dict[str, Any],
        min_match_score: float = 0.5,
        top_k: int = 10
    ) -> List[tuple[PolicyEntry, float]]:
        """Query policies by context similarity."""
        results = []

        for policy in self.policies:
            match_score = self._context_matches(policy.context, context)
            if match_score >= min_match_score:
                results.append((policy, match_score))

        # Sort by match score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def query_by_type(self, policy_type: str) -> List[PolicyEntry]:
        """Query policies by type."""
        return [policy for policy in self.policies if policy.policy_type == policy_type]

    def query_by_tags(self, tags: List[str]) -> List[PolicyEntry]:
        """Query policies by tags (any match)."""
        results = []
        tag_set = set(tags)
        for policy in self.policies:
            if tag_set & set(policy.tags):
                results.append(policy)
        return results

    def get_policy_by_id(self, policy_id: str) -> Optional[PolicyEntry]:
        """Get specific policy by ID."""
        for policy in self.policies:
            if policy.policy_id == policy_id:
                return policy
        return None

    def record_application(
        self,
        policy_id: str,
        success: bool,
        timestamp: Optional[str] = None
    ) -> bool:
        """Record that a policy was applied."""
        for policy in self.policies:
            if policy.policy_id == policy_id:
                policy.applied_count += 1
                if success:
                    policy.success_count += 1
                else:
                    policy.failure_count += 1
                policy.last_applied = timestamp or datetime.utcnow().isoformat()
                self._rewrite_storage()
                logger.info(f"Recorded application of policy {policy_id} (success={success})")
                return True
        return False

    def get_successful_policies(self, min_success_rate: float = 0.8) -> List[PolicyEntry]:
        """Get policies with high success rate."""
        results = []
        for policy in self.policies:
            if policy.applied_count > 0:
                success_rate = policy.success_count / policy.applied_count
                if success_rate >= min_success_rate:
                    results.append(policy)
        return results

    def get_frequently_applied(self, min_applications: int = 5) -> List[PolicyEntry]:
        """Get frequently applied policies."""
        return [
            policy for policy in self.policies
            if policy.applied_count >= min_applications
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about stored policies."""
        if not self.policies:
            return {
                "total_policies": 0,
                "by_type": {},
                "total_applications": 0,
                "avg_success_rate": 0.0
            }

        by_type: Dict[str, int] = {}
        total_applications = 0
        total_successes = 0

        for policy in self.policies:
            by_type[policy.policy_type] = by_type.get(policy.policy_type, 0) + 1
            total_applications += policy.applied_count
            total_successes += policy.success_count

        avg_success_rate = (
            total_successes / total_applications
            if total_applications > 0 else 0.0
        )

        return {
            "total_policies": len(self.policies),
            "by_type": by_type,
            "total_applications": total_applications,
            "avg_success_rate": avg_success_rate
        }

    def _rewrite_storage(self) -> None:
        """Rewrite entire policy storage."""
        policy_file = self.storage_path / "policies.jsonl"
        try:
            with open(policy_file, 'w', encoding='utf-8') as f:
                for policy in self.policies:
                    f.write(json.dumps(policy.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to rewrite policy storage: {e}")

    def prune_ineffective_policies(
        self,
        min_applications: int = 5,
        max_failure_rate: float = 0.5
    ) -> int:
        """Remove policies with high failure rate."""
        original_count = len(self.policies)
        
        def should_keep(policy: PolicyEntry) -> bool:
            if policy.applied_count < min_applications:
                return True  # Keep policies that haven't been tested enough
            failure_rate = policy.failure_count / policy.applied_count
            return failure_rate <= max_failure_rate

        self.policies = [policy for policy in self.policies if should_keep(policy)]
        removed_count = original_count - len(self.policies)

        if removed_count > 0:
            self._rewrite_storage()
            logger.info(f"Pruned {removed_count} ineffective policies")

        return removed_count

    def get_recent_policies(self, limit: int = 10) -> List[PolicyEntry]:
        """Get most recently created policies."""
        return sorted(self.policies, key=lambda p: p.timestamp, reverse=True)[:limit]

    def get_recently_applied(self, limit: int = 10) -> List[PolicyEntry]:
        """Get most recently applied policies."""
        return sorted(self.policies, key=lambda p: p.last_applied, reverse=True)[:limit]
