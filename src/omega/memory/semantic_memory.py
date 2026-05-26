"""
Semantic Memory Layer - Knowledge Storage
Stores knowledge (facts, patterns, lessons learned) with similarity-based retrieval.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from pathlib import Path
import json
import logging
import math

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeEntry:
    """Single knowledge entry."""
    entry_id: str
    content: str
    category: str  # fact, pattern, lesson, principle
    tags: List[str] = field(default_factory=list)
    confidence: float = 1.0  # 0.0 to 1.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source: str = ""  # episode_id, manual, inferred
    metadata: Dict[str, Any] = field(default_factory=dict)
    references: List[str] = field(default_factory=list)  # Related episode IDs

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeEntry':
        return cls(**data)


class SemanticMemory:
    """
    Semantic Memory Layer - Stores knowledge with similarity retrieval.
    Uses simple term-based similarity (no external dependencies).
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("data/memory/semantic")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.knowledge: List[KnowledgeEntry] = []
        self._load_knowledge()

    def _load_knowledge(self) -> None:
        """Load all knowledge entries from storage."""
        knowledge_file = self.storage_path / "knowledge.jsonl"
        if not knowledge_file.exists():
            return

        try:
            with open(knowledge_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        self.knowledge.append(KnowledgeEntry.from_dict(data))
            logger.info(f"Loaded {len(self.knowledge)} knowledge entries from storage")
        except Exception as e:
            logger.error(f"Failed to load knowledge: {e}")

    def _save_entry(self, entry: KnowledgeEntry) -> None:
        """Append knowledge entry to storage."""
        knowledge_file = self.storage_path / "knowledge.jsonl"
        try:
            with open(knowledge_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to save knowledge entry {entry.entry_id}: {e}")

    def store_knowledge(self, entry: KnowledgeEntry) -> None:
        """Store a new knowledge entry."""
        self.knowledge.append(entry)
        self._save_entry(entry)
        logger.info(f"Stored knowledge {entry.entry_id} ({entry.category})")

    def _tokenize(self, text: str) -> Set[str]:
        """Simple tokenization for similarity calculation."""
        # Convert to lowercase, split on non-alphanumeric
        tokens = set()
        current_token = []
        for char in text.lower():
            if char.isalnum():
                current_token.append(char)
            else:
                if current_token:
                    tokens.add(''.join(current_token))
                    current_token = []
        if current_token:
            tokens.add(''.join(current_token))
        return tokens

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts."""
        tokens1 = self._tokenize(text1)
        tokens2 = self._tokenize(text2)

        if not tokens1 or not tokens2:
            return 0.0

        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        return intersection / union if union > 0 else 0.0

    def retrieve_by_similarity(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.1
    ) -> List[tuple[KnowledgeEntry, float]]:
        """Retrieve knowledge entries by similarity to query."""
        results = []

        for entry in self.knowledge:
            # Calculate similarity based on content and tags
            content_sim = self._calculate_similarity(query, entry.content)
            tag_sim = max(
                [self._calculate_similarity(query, tag) for tag in entry.tags],
                default=0.0
            )
            
            # Weighted combination
            similarity = 0.7 * content_sim + 0.3 * tag_sim
            
            # Apply confidence weighting
            similarity *= entry.confidence

            if similarity >= min_similarity:
                results.append((entry, similarity))

        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def query_by_category(self, category: str) -> List[KnowledgeEntry]:
        """Query knowledge by category."""
        return [entry for entry in self.knowledge if entry.category == category]

    def query_by_tags(self, tags: List[str]) -> List[KnowledgeEntry]:
        """Query knowledge by tags (any match)."""
        results = []
        tag_set = set(tags)
        for entry in self.knowledge:
            if tag_set & set(entry.tags):
                results.append(entry)
        return results

    def query_by_source(self, source: str) -> List[KnowledgeEntry]:
        """Query knowledge by source."""
        return [entry for entry in self.knowledge if entry.source == source]

    def get_entry_by_id(self, entry_id: str) -> Optional[KnowledgeEntry]:
        """Get specific knowledge entry by ID."""
        for entry in self.knowledge:
            if entry.entry_id == entry_id:
                return entry
        return None

    def update_confidence(self, entry_id: str, new_confidence: float) -> bool:
        """Update confidence score for a knowledge entry."""
        for entry in self.knowledge:
            if entry.entry_id == entry_id:
                entry.confidence = max(0.0, min(1.0, new_confidence))
                self._rewrite_storage()
                logger.info(f"Updated confidence for {entry_id} to {entry.confidence}")
                return True
        return False

    def get_high_confidence_knowledge(self, min_confidence: float = 0.8) -> List[KnowledgeEntry]:
        """Get knowledge entries with high confidence."""
        return [entry for entry in self.knowledge if entry.confidence >= min_confidence]

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about stored knowledge."""
        if not self.knowledge:
            return {
                "total_entries": 0,
                "by_category": {},
                "avg_confidence": 0.0,
                "total_tags": 0
            }

        by_category: Dict[str, int] = {}
        total_confidence = 0.0
        all_tags: Set[str] = set()

        for entry in self.knowledge:
            by_category[entry.category] = by_category.get(entry.category, 0) + 1
            total_confidence += entry.confidence
            all_tags.update(entry.tags)

        return {
            "total_entries": len(self.knowledge),
            "by_category": by_category,
            "avg_confidence": total_confidence / len(self.knowledge),
            "total_tags": len(all_tags)
        }

    def _rewrite_storage(self) -> None:
        """Rewrite entire knowledge storage."""
        knowledge_file = self.storage_path / "knowledge.jsonl"
        try:
            with open(knowledge_file, 'w', encoding='utf-8') as f:
                for entry in self.knowledge:
                    f.write(json.dumps(entry.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to rewrite knowledge storage: {e}")

    def prune_low_confidence(self, threshold: float = 0.3) -> int:
        """Remove knowledge entries below confidence threshold."""
        original_count = len(self.knowledge)
        self.knowledge = [entry for entry in self.knowledge if entry.confidence >= threshold]
        removed_count = original_count - len(self.knowledge)

        if removed_count > 0:
            self._rewrite_storage()
            logger.info(f"Pruned {removed_count} low-confidence entries")

        return removed_count
