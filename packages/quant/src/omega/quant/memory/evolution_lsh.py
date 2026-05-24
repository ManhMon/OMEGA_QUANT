#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory Semantic Hashing (Locality-Sensitive Hashing - LSH)
For OMEGA_QUANT Memory & Evolution Engine.

Quickly compares current portfolio states with historical regimes
to find similar structural events without O(N) database scans.

Author: ML Engineer (Role 16)
Date: 2026-05-24
"""

import numpy as np
from typing import Dict, List, Set

class SemanticMemoryHasher:
    def __init__(self, num_permutations: int = 128):
        self.num_permutations = num_permutations
        self._permutations = self._generate_permutations()
        
    def _generate_permutations(self) -> np.ndarray:
        # Generate random projection vectors for MinHash/SimHash
        # Assume universe of top 100 stocks
        np.random.seed(42) 
        return np.random.randn(self.num_permutations, 100)
        
    def hash_portfolio(self, portfolio_weights: Dict[str, float], universe_index: Dict[str, int]) -> str:
        """
        Convert a portfolio weight dict into a 128-bit hex string via SimHash.
        Similar portfolios will have low Hamming distance between their hex strings.
        """
        vec = np.zeros(100)
        for sym, weight in portfolio_weights.items():
            if sym in universe_index:
                idx = universe_index[sym]
                vec[idx] = weight
                
        # SimHash projection
        projections = np.dot(self._permutations, vec)
        bits = (projections > 0).astype(int)
        
        # Convert bit array to hex string
        binary_str = "".join(str(b) for b in bits)
        return hex(int(binary_str, 2))[2:].zfill(self.num_permutations // 4)

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """Calculate Hamming distance between two hex hashes to gauge similarity."""
        val1 = int(hash1, 16)
        val2 = int(hash2, 16)
        xor_val = val1 ^ val2
        return bin(xor_val).count('1')