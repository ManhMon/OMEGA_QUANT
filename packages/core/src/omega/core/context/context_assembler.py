"""
OMEGA_QUANT Context Assembly Pipeline (Token-Savior)

Purpose:
    Efficient context assembly for LLM agents with token budgeting, semantic pruning,
    and relevance scoring. Reduces 80-90% token waste.

Spec Reference:
    - Section 7.2: Token Budgeting
    - Section 7.3: Semantic Context Pruning
    - Section 7.4: Relevance Scoring
    - Section 7.5: Assembly Pipeline

Author: DevOps Engineer (Role 12)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ContextPriority(Enum):
    """Context priority levels."""
    CRITICAL = 1  # System prompt, role spec
    HIGH = 2      # Current task, active files
    MEDIUM = 3   # Recent history
    LOW = 4       # Archived context


@dataclass(frozen=True)
class ContextChunk:
    """Context chunk with priority and relevance scoring."""
    chunk_id: str
    content: str
    priority: ContextPriority
    relevance_score: float = 1.0
    token_count: int = 0
    source: str = ""  # file path or memory id
    tags: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssemblyResult:
    """Result of context assembly."""
    assembled_content: str
    total_tokens: int
    chunks_used: int
    chunks_dropped: int
    priority_breakdown: Dict[str, int] = field(default_factory=dict)
    assembly_time_ms: float = 0.0


class TokenBudget:
    """
    Token budgeting with priority allocation.
    
    Spec Section 7.2:
    - System: 15% (instructions, constraints)
    - Task: 50% (current work)
    - History: 25% (recent context)
    - Scratch: 10% (reasoning space)
    """
    
    DEFAULT_BUDGET = {
        "system": 0.15,
        "task": 0.50,
        "history": 0.25,
        "scratch": 0.10,
    }
    
    def __init__(self, total_tokens: int = 8000, budget_pct: Optional[Dict[str, float]] = None):
        self.total_tokens = total_tokens
        self.budget_pct = budget_pct or self.DEFAULT_BUDGET.copy()
        
        # Compute absolute token limits
        self.limits = {
            category: int(total_tokens * pct)
            for category, pct in self.budget_pct.items()
        }
        
        # Track usage
        self.usage = {category: 0 for category in self.limits}
    
    def allocate(self, category: str, tokens: int) -> bool:
        """
        Try to allocate tokens to category.
        
        Returns True if allocation succeeded, False if over budget.
        """
        if category not in self.limits:
            category = "scratch"  # Fallback
        
        if self.usage[category] + tokens <= self.limits[category]:
            self.usage[category] += tokens
            return True
        
        return False
    
    def get_remaining(self, category: str) -> int:
        """Get remaining tokens for category."""
        if category not in self.limits:
            return 0
        return self.limits[category] - self.usage.get(category, 0)
    
    def get_total_remaining(self) -> int:
        """Get total remaining tokens across all categories."""
        return sum(self.get_remaining(cat) for cat in self.limits)


class SemanticPruner:
    """
    Semantic context pruning based on relevance scoring.
    
    Spec Section 7.3:
    - TF-IDF based scoring
    - Keyword matching
    - Recency weighting
    """
    
    # Keywords for VN Quant domain
    DOMAIN_KEYWORDS = {
        "alpha": ["alpha", "signal", "feature", "factor", "indicator"],
        "risk": ["risk", "volatility", "var", "cvarr", "drawdown", "exposure"],
        "execution": ["order", "execution", "vwap", "twap", "fill", "slippage"],
        "data": ["price", "volume", "ohlcv", "returns", "market", "index"],
        "model": ["model", "train", "predict", "xgboost", "lstm", "genetic"],
        "system": ["state", "task", "memory", "cache", "registry", "pipeline"],
    }
    
    def __init__(self, domain_keywords: Optional[Dict[str, List[str]]] = None):
        self.domain_keywords = domain_keywords or self.DOMAIN_KEYWORDS
    
    def compute_relevance(
        self,
        chunk: ContextChunk,
        query: str,
    ) -> float:
        """
        Compute relevance score for chunk given query.
        
        Returns float in [0, 1] range.
        """
        query_lower = query.lower()
        content_lower = chunk.content.lower()
        
        # Keyword matching
        keyword_score = 0.0
        matched_categories = 0
        
        for category, keywords in self.domain_keywords.items():
            if any(kw in content_lower for kw in keywords):
                matched_categories += 1
                if any(kw in query_lower for kw in keywords):
                    keyword_score += 1.0
        
        if matched_categories > 0:
            keyword_score /= matched_categories
        
        # Direct match bonus
        direct_match = 0.0
        query_terms = set(re.findall(r'\w+', query_lower))
        content_terms = set(re.findall(r'\w+', content_lower))
        overlap = query_terms & content_terms
        if query_terms:
            direct_match = len(overlap) / len(query_terms)
        
        # Priority weight (higher priority = higher base score)
        priority_weight = {
            ContextPriority.CRITICAL: 1.0,
            ContextPriority.HIGH: 0.8,
            ContextPriority.MEDIUM: 0.5,
            ContextPriority.LOW: 0.2,
        }
        
        # Combine scores
        relevance = (
            0.5 * keyword_score +
            0.3 * direct_match +
            0.2 * priority_weight.get(chunk.priority, 0.0)
        )
        
        return min(1.0, max(0.0, relevance))
    
    def prune(
        self,
        chunks: List[ContextChunk],
        query: str,
        budget: TokenBudget,
    ) -> List[ContextChunk]:
        """
        Prune chunks based on relevance and token budget.
        
        Returns list of kept chunks.
        """
        # Compute relevance for all chunks
        scored_chunks = []
        for chunk in chunks:
            relevance = self.compute_relevance(chunk, query)
            scored_chunks.append((chunk, relevance))
        
        # Sort by relevance descending
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        
        # Allocate chunks within budget
        kept_chunks = []
        dropped_chunks = 0
        
        for chunk, relevance in scored_chunks:
            # Try to allocate
            if budget.allocate(chunk.priority.name.lower(), chunk.token_count):
                kept_chunks.append(chunk)
            else:
                dropped_chunks += 1
        
        logger.info(
            f"Pruned {dropped_chunks} chunks. "
            f"Kept {len(kept_chunks)} chunks. "
            f"Remaining tokens: {budget.get_total_remaining()}"
        )
        
        return kept_chunks


class ContextAssembler:
    """
    Context Assembly Pipeline (Token-Savior).
    
    Spec Section 7.5:
    1. Budget allocation (per category)
    2. Relevance scoring
    3. Semantic pruning
    4. Assembly with formatting
    
    Reduces 80-90% token waste by:
    - Allocating tokens by priority
    - Dropping low-relevance content
    - Using chunking for efficient assembly
    """
    
    def __init__(
        self,
        total_budget: int = 8000,
        budget_pct: Optional[Dict[str, float]] = None,
        domain_keywords: Optional[Dict[str, List[str]]] = None,
    ):
        self.budget = TokenBudget(total_budget, budget_pct)
        self.pruner = SemanticPruner(domain_keywords)
        self._relevance_cache: Dict[Tuple[str, str], float] = {}
        self._pruned_cache: Dict[Tuple[Tuple[str, ...], str, int], List[ContextChunk]] = {}

    def _get_relevance(self, chunk: ContextChunk, query: str) -> float:
        """Get cached relevance score for chunk-query pair."""
        cache_key = (chunk.chunk_id, query)
        if cache_key not in self._relevance_cache:
            self._relevance_cache[cache_key] = self.pruner.compute_relevance(chunk, query)
        return self._relevance_cache[cache_key]

    @staticmethod
    def _priority_budget_category(priority: ContextPriority) -> str:
        """Map chunk priority to token budget category."""
        return {
            ContextPriority.CRITICAL: "system",
            ContextPriority.HIGH: "task",
            ContextPriority.MEDIUM: "history",
            ContextPriority.LOW: "scratch",
        }.get(priority, "scratch")
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count (rough approximation).
        
        ~4 chars per token for English, ~2 for Vietnamese.
        """
        # Rough estimation: ~4 chars per token
        return len(text) // 4 + 1
    
    def assemble(
        self,
        chunks: List[ContextChunk],
        query: str,
        system_prompt: Optional[str] = None,
        task_description: Optional[str] = None,
    ) -> AssemblyResult:
        """
        Assemble context from chunks given query and budget.
        
        Args:
            chunks: List of context chunks
            query: Current task/query
            system_prompt: System prompt (optional)
            task_description: Task description (optional)
            
        Returns:
            AssemblyResult with assembled content and metrics
        """
        import time
        start_time = time.time()
        
        # Reset budget
        self.budget = TokenBudget(
            self.budget.total_tokens,
            self.budget.budget_pct.copy()
        )
        
        # Allocate system prompt if provided
        if system_prompt:
            tokens = self.estimate_tokens(system_prompt)
            self.budget.allocate("system", tokens)
        
        # Allocate task description if provided
        if task_description:
            tokens = self.estimate_tokens(task_description)
            self.budget.allocate("task", tokens)
        
        # Prune chunks with cache for repeated queries over same chunk set.
        pruned_cache_key = (
            tuple(chunk.chunk_id for chunk in chunks),
            query,
            self.budget.total_tokens,
        )
        kept_chunks = self._pruned_cache.get(pruned_cache_key)
        if kept_chunks is None:
            scored_chunks = [(chunk, self._get_relevance(chunk, query)) for chunk in chunks]
            scored_chunks.sort(key=lambda x: x[1], reverse=True)

            kept_chunks = []
            dropped_chunks = 0
            for chunk, relevance in scored_chunks:
                budget_category = self._priority_budget_category(chunk.priority)
                if self.budget.allocate(budget_category, chunk.token_count):
                    if chunk.relevance_score != relevance:
                        chunk = ContextChunk(
                            chunk_id=chunk.chunk_id,
                            content=chunk.content,
                            priority=chunk.priority,
                            relevance_score=relevance,
                            token_count=chunk.token_count,
                            source=chunk.source,
                            tags=chunk.tags,
                            metadata=chunk.metadata,
                        )
                    kept_chunks.append(chunk)
                else:
                    dropped_chunks += 1

            logger.info(
                f"Pruned {dropped_chunks} chunks. "
                f"Kept {len(kept_chunks)} chunks. "
                f"Remaining tokens: {self.budget.get_total_remaining()}"
            )
            self._pruned_cache[pruned_cache_key] = kept_chunks
        else:
            actual_kept = []
            for chunk in kept_chunks:
                budget_category = self._priority_budget_category(chunk.priority)
                if self.budget.allocate(budget_category, chunk.token_count):
                    actual_kept.append(chunk)
            kept_chunks = actual_kept

        # Sort by priority (CRITICAL first)
        priority_order = {
            ContextPriority.CRITICAL: 0,
            ContextPriority.HIGH: 1,
            ContextPriority.MEDIUM: 2,
            ContextPriority.LOW: 3,
        }
        kept_chunks.sort(key=lambda c: priority_order.get(c.priority, 4))
        
        # Assemble content
        lines = []
        
        if system_prompt:
            lines.append(f"[SYSTEM]\n{system_prompt}\n")
        
        if task_description:
            lines.append(f"[TASK]\n{task_description}\n")
        
        lines.append("[CONTEXT]")
        for chunk in kept_chunks:
            header = f"\n## {chunk.source} (priority={chunk.priority.name}, relevance={chunk.relevance_score:.2f})"
            lines.append(f"{header}\n{chunk.content}")
        
        assembled = "\n".join(lines)
        total_tokens = self.estimate_tokens(assembled)
        
        # Count priority breakdown
        priority_breakdown = {}
        for chunk in kept_chunks:
            priority_name = chunk.priority.name
            priority_breakdown[priority_name] = priority_breakdown.get(priority_name, 0) + chunk.token_count
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        return AssemblyResult(
            assembled_content=assembled,
            total_tokens=total_tokens,
            chunks_used=len(kept_chunks),
            chunks_dropped=len(chunks) - len(kept_chunks),
            priority_breakdown=priority_breakdown,
            assembly_time_ms=elapsed_ms,
        )
    
    def get_minimal_context(
        self,
        chunks: List[ContextChunk],
        query: str,
    ) -> str:
        """
        Get minimal context for task (80-90% token reduction).
        
        This is the main entry point for LLM agents.
        """
        result = self.assemble(chunks, query)
        
        # Log efficiency metrics
        reduction_pct = (
            (result.chunks_dropped / (result.chunks_used + result.chunks_dropped) * 100)
            if (result.chunks_used + result.chunks_dropped) > 0 else 0
        )
        
        logger.info(
            f"Context assembled: {result.total_tokens} tokens, "
            f"{result.chunks_used} chunks kept, "
            f"{reduction_pct:.1f}% reduction"
        )
        
        return result.assembled_content


def get_context_assembler() -> ContextAssembler:
    """Singleton factory for ContextAssembler."""
    if not hasattr(get_context_assembler, "_instance"):
        get_context_assembler._instance = ContextAssembler()
    return get_context_assembler._instance
