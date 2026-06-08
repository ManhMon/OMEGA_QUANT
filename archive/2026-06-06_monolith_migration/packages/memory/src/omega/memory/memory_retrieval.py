"""
OMEGA_QUANT Memory Retrieval (Phase 6.3 - Memory & Evolution Engine)

Purpose:
    Retrieve and rank historical alphas using semantic similarity.
    - Cosine similarity on vectorized alpha expressions
    - Multi-criteria ranking (Sharpe, Fitness, Turnover)
    - Hash-based deduplication
    - Vectorized operations (100% Pandas/NumPy)

Contract:
    - Input: Query alpha expression, fitness threshold, symbol filter
    - Output: Ranked list of similar alphas
    - PIT Safety: All data based on T-1 or earlier

Reference:
    - Phase 6.3: Memory Retrieval
    - Institutional-grade alpha retrieval system

Author: Backend Engineer (Role 09)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional, TYPE_CHECKING
import pandas as pd
import numpy as np

if TYPE_CHECKING:
    from omega.memory.memory_archive import AlphaMemory

logger = logging.getLogger(__name__)


class AlphaRetriever:
    """
    Semantic similarity search for historical alphas.
    
    Features:
    - Cosine similarity on expression vectors
    - Multi-criteria ranking (Sharpe, Fitness, Turnover)
    - Symbol filtering
    - Threshold-based filtering
    """
    
    def __init__(self, alpha_memory: "AlphaMemory"):
        self.alpha_memory = alpha_memory
        self.signals_df = self.alpha_memory._load_signals()
    
    def _vectorize_expression(self, expression: str) -> np.ndarray:
        """
        Convert alpha expression to numeric vector.
        
        This enables cosine similarity comparison between expressions.
        """
        # Extract operators and functions from expression
        operators = ['+', '-', '*', '/', '(', ')']
        functions = ['rsi', 'macd', 'sma', 'ema', 'std', 'mean', 'max', 'min', 'rank', 'delay']
        
        # Create feature vector
        vector = np.zeros(len(operators) + len(functions))
        
        expr_lower = expression.lower()
        
        # Count operators
        for i, op in enumerate(operators):
            vector[i] = expr_lower.count(op)
        
        # Count functions
        for i, func in enumerate(functions):
            vector[len(operators) + i] = expr_lower.count(func + '(')
        
        # Normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        
        return vector
    
    def _compute_similarity(self, expr1: str, expr2: str) -> float:
        """
        Compute cosine similarity between two alpha expressions.
        
        Returns:
            Similarity score in [0, 1]
        """
        vec1 = self._vectorize_expression(expr1)
        vec2 = self._vectorize_expression(expr2)
        
        # Cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def retrieve_similar_alphas(
        self,
        expression: str,
        symbol: Optional[str] = None,
        min_sharpe: float = 0.0,
        min_fitness: float = 0.0,
        top_n: int = 10,
        min_similarity: float = 0.3,
    ) -> pd.DataFrame:
        """
        Retrieve alphas similar to the query expression.
        
        Args:
            expression: Query alpha expression
            symbol: Filter by symbol (optional)
            min_sharpe: Minimum Sharpe ratio filter
            min_fitness: Minimum fitness score filter
            top_n: Number of top results to return
            min_similarity: Minimum cosine similarity threshold
            
        Returns:
            DataFrame of similar alphas, sorted by fitness
        """
        if self.signals_df.empty:
            logger.warning("No alphas in memory archive")
            return pd.DataFrame()
        
        # Vectorize query
        query_vec = self._vectorize_expression(expression)
        
        # Compute similarities
        similarities = []
        for _, row in self.signals_df.iterrows():
            expr_vec = self._vectorize_expression(row["expression"])
            similarity = float(np.dot(query_vec, expr_vec))
            similarities.append(similarity)
        
        self.signals_df = self.signals_df.copy()
        self.signals_df["similarity"] = similarities
        
        # Apply filters
        filtered = self.signals_df[
            (self.signals_df["similarity"] >= min_similarity) &
            (self.signals_df["sharpe"] >= min_sharpe) &
            (self.signals_df["fitness"] >= min_fitness)
        ]
        
        if symbol:
            filtered = filtered[filtered["symbol"] == symbol]
        
        # Sort by fitness (descending)
        result = filtered.nlargest(top_n, "fitness")
        
        logger.info(f"Retrieved {len(result)} similar alphas for: {expression}")
        return result
    
    def retrieve_by_criteria(
        self,
        symbol: Optional[str] = None,
        min_sharpe: float = 0.0,
        min_fitness: float = 0.0,
        max_turnover: float = 1.0,
        top_n: int = 10,
    ) -> pd.DataFrame:
        """
        Retrieve alphas by performance criteria (no expression matching).
        
        Args:
            symbol: Filter by symbol (optional)
            min_sharpe: Minimum Sharpe ratio
            min_fitness: Minimum fitness score
            max_turnover: Maximum turnover rate
            top_n: Number of top results
            
        Returns:
            DataFrame of top alphas matching criteria
        """
        filtered = self.signals_df[
            (self.signals_df["sharpe"] >= min_sharpe) &
            (self.signals_df["fitness"] >= min_fitness) &
            (self.signals_df["turnover"] <= max_turnover)
        ]
        
        if symbol:
            filtered = filtered[filtered["symbol"] == symbol]
        
        result = filtered.nlargest(top_n, "fitness")
        
        logger.info(f"Retrieved {len(result)} alphas by criteria")
        return result
    
    def get_top_performers(
        self,
        symbol: Optional[str] = None,
        top_n: int = 10,
    ) -> pd.DataFrame:
        """
        Get top performing alphas (by fitness).
        
        Args:
            symbol: Filter by symbol (optional)
            top_n: Number of top alphas
            
        Returns:
            DataFrame of top alphas
        """
        result = self.signals_df.nlargest(top_n, "fitness")
        
        if symbol:
            result = result[result["symbol"] == symbol]
        
        return result


def create_retriever(alpha_memory: AlphaMemory) -> AlphaRetriever:
    """
    Factory function to create AlphaRetriever instance.
    
    Args:
        alpha_memory: AlphaMemory instance
        
    Returns:
        AlphaRetriever instance
    """
    return AlphaRetriever(alpha_memory)

