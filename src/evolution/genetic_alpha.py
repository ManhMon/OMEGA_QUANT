"""
Genetic Programming Alpha Discovery - OMEGA_QUANT Phase 3.4
Strict PIT Safety, Vectorized Evaluation, Deterministic Genome Operations.
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Tuple
import random
from copy import deepcopy


def enforce_t_minus_1_lag(signal: pd.Series) -> pd.Series:
    """
    MANDATORY: Enforce T-1 lag for PIT safety.
    Ensures no look-ahead bias in evolved signals.
    """
    return signal.shift(1)


class Node:
    """Tree node for genetic program representation."""
    
    TERMINALS = ['close', 'open', 'high', 'low', 'volume', 'returns', 'rsi', 'macd']
    OPERATORS = ['add', 'sub', 'mul', 'div', 'std', 'mean', 'max', 'min', 'rank', 'delay']
    
    def __init__(self, value: str, children: Optional[List['Node']] = None):
        """
        Args:
            value: Terminal or Operator
            children: List of child nodes (for operators)
        """
        if value not in self.TERMINALS + self.OPERATORS:
            raise ValueError(f"Unknown node value: {value}")
        self.value = value
        self.children = children or []
        self._validate_arity()
    
    def _validate_arity(self):
        """Validate operator arity (number of children)."""
        if self.value in ['add', 'sub', 'mul', 'div']:
            if len(self.children) != 2:
                raise ValueError(f"Operator {self.value} requires exactly 2 children, got {len(self.children)}")
        elif self.value in ['std', 'mean', 'max', 'min', 'rank']:
            if len(self.children) != 1:
                raise ValueError(f"Operator {self.value} requires exactly 1 child, got {len(self.children)}")
        elif self.value == 'delay':
            if len(self.children) != 1:
                raise ValueError(f"Operator delay requires exactly 1 child, got {len(self.children)}")
    
    def evaluate(self, df: pd.DataFrame, window: int = 14) -> pd.Series:
        """
        Vectorized evaluation of node on DataFrame.
        
        Args:
            df: DataFrame with columns ['close', 'open', 'high', 'low', 'volume', 'returns', 'rsi', 'macd']
            window: Window size for rolling operations
        
        Returns:
            pd.Series: Evaluated signal
        """
        # Terminals
        if self.value == 'close':
            return df['close'].copy()
        if self.value == 'open':
            return df.get('open', pd.Series(0.0, index=df.index))
        if self.value == 'high':
            return df.get('high', pd.Series(0.0, index=df.index))
        if self.value == 'low':
            return df.get('low', pd.Series(0.0, index=df.index))
        if self.value == 'volume':
            return df['volume'].copy()
        if self.value == 'returns':
            return df.get('returns', df['close'].pct_change())
        if self.value == 'rsi':
            return df.get('rsi', pd.Series(0.0, index=df.index))
        if self.value == 'macd':
            return df.get('macd', pd.Series(0.0, index=df.index))
        
        # Unary operators
        if self.value in ['std', 'mean', 'max', 'min', 'rank', 'delay']:
            if len(self.children) < 1:
                raise ValueError(f"Operator {self.value} requires at least 1 child")
            child_signal = self.children[0].evaluate(df, window)
            
            if self.value == 'std':
                return child_signal.rolling(window=window, min_periods=1).std()
            if self.value == 'mean':
                return child_signal.rolling(window=window, min_periods=1).mean()
            if self.value == 'max':
                return child_signal.rolling(window=window, min_periods=1).max()
            if self.value == 'min':
                return child_signal.rolling(window=window, min_periods=1).min()
            if self.value == 'rank':
                return child_signal.rolling(window=window, min_periods=1).rank()
            if self.value == 'delay':
                return child_signal.shift(1)
        
        # Binary operators
        if len(self.children) < 2:
            raise ValueError(f"Operator {self.value} requires 2 children")
        
        left = self.children[0].evaluate(df, window)
        right = self.children[1].evaluate(df, window)
        
        if self.value == 'add':
            return left + right
        if self.value == 'sub':
            return left - right
        if self.value == 'mul':
            return left * right
        if self.value == 'div':
            return left / right.replace(0, np.nan)
        
        raise ValueError(f"Unknown operator: {self.value}")
    
    def get_depth(self) -> int:
        """Calculate tree depth."""
        if not self.children:
            return 0
        max_depth = 0
        for child in self.children:
            depth = child.get_depth()
            if depth > max_depth:
                max_depth = depth
        return 1 + max_depth
    
    def deepcopy(self) -> 'Node':
        """Create deep copy of subtree."""
        new_children = []
        for child in self.children:
            new_children.append(child.deepcopy())
        return Node(self.value, new_children)
    
    def __repr__(self) -> str:
        if not self.children:
            return self.value
        child_reprs = []
        for c in self.children:
            child_reprs.append(repr(c))
        return f"({self.value} {' '.join(child_reprs)})"


class Genome:
    """Genetic program (tree-based) for alpha discovery."""
    
    def __init__(self, tree: Optional[Node] = None, max_depth: int = 3, seed: Optional[int] = None):
        """
        Args:
            tree: Root node of expression tree. If None, generates random tree.
            max_depth: Maximum tree depth for random generation.
            seed: Random seed for reproducibility.
        """
        if seed is not None:
            random.seed(seed)
        self.tree = tree or self._random_tree(max_depth)
    
    def _random_tree(self, depth: int) -> Node:
        """Generate random expression tree."""
        if depth == 0 or random.random() < 0.3:
            # Terminal node
            return Node(random.choice(Node.TERMINALS))
        else:
            # Operator node
            op = random.choice(Node.OPERATORS)
            if op in ['add', 'sub', 'mul', 'div']:
                left = self._random_tree(depth - 1)
                right = self._random_tree(depth - 1)
                return Node(op, [left, right])
            else:  # Unary operators
                child = self._random_tree(depth - 1)
                return Node(op, [child])
    
    def evaluate_vectorized(self, df: pd.DataFrame) -> pd.Series:
        """
        Vectorized evaluation with mandatory T-1 lag enforcement.
        
        Args:
            df: DataFrame with OHLCV and indicator columns
        
        Returns:
            pd.Series: Signal with T-1 lag applied, NaN filled with 0
        """
        raw_signal = self.tree.evaluate(df)
        safe_signal = enforce_t_minus_1_lag(raw_signal)
        return safe_signal.fillna(0.0)
    
    def mutate(self) -> 'Genome':
        """
        Mutation: Replace random subtree with new random tree.
        
        Returns:
            Genome: New mutated genome
        """
        new_tree = self._random_tree(depth=3)
        return Genome(new_tree)
    
    @staticmethod
    def crossover(g1: 'Genome', g2: 'Genome') -> 'Genome':
        """
        Crossover: Combine two genomes by swapping subtrees with deep-copy.
        
        Args:
            g1: First parent genome
            g2: Second parent genome
        
        Returns:
            Genome: Offspring genome
        """
        # Deep copy to avoid shared references
        tree1_copy = g1.tree.deepcopy()
        tree2_copy = g2.tree.deepcopy()
        
        # Swap left child if both have children
        if tree1_copy.children and tree2_copy.children:
            tree1_copy.children[0] = tree2_copy.children[0].deepcopy()
        
        return Genome(tree1_copy)
    
    def get_depth(self) -> int:
        """Get tree depth."""
        return self.tree.get_depth()
    
    def __repr__(self) -> str:
        return repr(self.tree)
