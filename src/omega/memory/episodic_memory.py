"""
Episodic Memory Layer - Task Execution History Storage
Stores episodes (task execution history) with query by time/task_type/outcome.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class Episode:
    """Single episode representing a task execution."""
    episode_id: str
    task_type: str
    outcome: str  # success, failure, partial, rollback
    timestamp: str
    duration_seconds: float
    context: Dict[str, Any] = field(default_factory=dict)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Episode':
        return cls(**data)


class EpisodicMemory:
    """
    Episodic Memory Layer - Stores task execution history.
    Query by time, task_type, outcome.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("data/memory/episodic")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.episodes: List[Episode] = []
        self._load_episodes()

    def _load_episodes(self) -> None:
        """Load all episodes from storage."""
        episode_file = self.storage_path / "episodes.jsonl"
        if not episode_file.exists():
            return

        try:
            with open(episode_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        self.episodes.append(Episode.from_dict(data))
            logger.info(f"Loaded {len(self.episodes)} episodes from storage")
        except Exception as e:
            logger.error(f"Failed to load episodes: {e}")

    def _save_episode(self, episode: Episode) -> None:
        """Append episode to storage."""
        episode_file = self.storage_path / "episodes.jsonl"
        try:
            with open(episode_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(episode.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to save episode {episode.episode_id}: {e}")

    def store_episode(self, episode: Episode) -> None:
        """Store a new episode."""
        self.episodes.append(episode)
        self._save_episode(episode)
        logger.info(f"Stored episode {episode.episode_id} ({episode.task_type}, {episode.outcome})")

    def query_by_time(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> List[Episode]:
        """Query episodes by time range."""
        results = []
        for episode in self.episodes:
            if start_time and episode.timestamp < start_time:
                continue
            if end_time and episode.timestamp > end_time:
                continue
            results.append(episode)
        return results

    def query_by_task_type(self, task_type: str) -> List[Episode]:
        """Query episodes by task type."""
        return [ep for ep in self.episodes if ep.task_type == task_type]

    def query_by_outcome(self, outcome: str) -> List[Episode]:
        """Query episodes by outcome."""
        return [ep for ep in self.episodes if ep.outcome == outcome]

    def query_combined(
        self,
        task_type: Optional[str] = None,
        outcome: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> List[Episode]:
        """Query episodes with multiple filters."""
        results = self.episodes

        if task_type:
            results = [ep for ep in results if ep.task_type == task_type]
        if outcome:
            results = [ep for ep in results if ep.outcome == outcome]
        if start_time:
            results = [ep for ep in results if ep.timestamp >= start_time]
        if end_time:
            results = [ep for ep in results if ep.timestamp <= end_time]

        return results

    def get_recent_episodes(self, limit: int = 10) -> List[Episode]:
        """Get most recent episodes."""
        return sorted(self.episodes, key=lambda ep: ep.timestamp, reverse=True)[:limit]

    def get_episode_by_id(self, episode_id: str) -> Optional[Episode]:
        """Get specific episode by ID."""
        for episode in self.episodes:
            if episode.episode_id == episode_id:
                return episode
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about stored episodes."""
        if not self.episodes:
            return {
                "total_episodes": 0,
                "by_task_type": {},
                "by_outcome": {},
                "avg_duration": 0.0
            }

        by_task_type: Dict[str, int] = {}
        by_outcome: Dict[str, int] = {}
        total_duration = 0.0

        for episode in self.episodes:
            by_task_type[episode.task_type] = by_task_type.get(episode.task_type, 0) + 1
            by_outcome[episode.outcome] = by_outcome.get(episode.outcome, 0) + 1
            total_duration += episode.duration_seconds

        return {
            "total_episodes": len(self.episodes),
            "by_task_type": by_task_type,
            "by_outcome": by_outcome,
            "avg_duration": total_duration / len(self.episodes)
        }

    def clear_old_episodes(self, before_timestamp: str) -> int:
        """Remove episodes older than specified timestamp."""
        original_count = len(self.episodes)
        self.episodes = [ep for ep in self.episodes if ep.timestamp >= before_timestamp]
        removed_count = original_count - len(self.episodes)

        # Rewrite storage
        episode_file = self.storage_path / "episodes.jsonl"
        try:
            with open(episode_file, 'w', encoding='utf-8') as f:
                for episode in self.episodes:
                    f.write(json.dumps(episode.to_dict()) + '\n')
            logger.info(f"Cleared {removed_count} old episodes")
        except Exception as e:
            logger.error(f"Failed to rewrite episodes: {e}")

        return removed_count
