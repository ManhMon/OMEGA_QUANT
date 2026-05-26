"""
De-correlation Engine - Alpha Factory V2.0 (v21.7.2)
Institutional Grade Diversity Management.

Logic:
1. Hierarchical Clustering: Group alphas by correlation (Threshold: 0.7).
2. Greedy Selection: Pick one best alpha from each cluster.
3. Final Check: Ensure all selected alphas have mutual correlation < 0.3.
"""

import pandas as pd
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from typing import List, Dict, Any

class DecorrelationEngine:
    def __init__(self, rho_threshold: float = 0.3, cluster_threshold: float = 0.7):
        self.rho_threshold = rho_threshold
        self.cluster_threshold = cluster_threshold

    def filter_alphas(self, alpha_pool: List[Any], data: pd.DataFrame) -> List[Any]:
        """
        Filters a pool of alphas using 2-stage de-correlation.
        """
        if len(alpha_pool) < 2:
            return alpha_pool

        # 1. Compute Correlation Matrix
        alpha_matrix = {}
        for i, ind in enumerate(alpha_pool):
            series = ind.evaluate(data)
            alpha_matrix[f"alpha_{i}"] = series
        
        corr_df = pd.DataFrame(alpha_matrix).corr().fillna(0.0)
        
        # 2. Stage 1: Hierarchical Clustering (rho > 0.7)
        # CRITICAL FIX: Use .copy() to ensure array is writable
        dist_matrix_values = (1 - corr_df.abs()).values.copy()
        np.fill_diagonal(dist_matrix_values, 0)
        
        # Ensure values are clipped to [0, 1] to avoid float precision issues with squareform
        dist_matrix_values = np.clip(dist_matrix_values, 0, 1)
        
        condensed_dist = squareform(dist_matrix_values)
        linkage_matrix = linkage(condensed_dist, method='complete')
        clusters = fcluster(linkage_matrix, t=1 - self.cluster_threshold, criterion='distance')
        
        # 3. Stage 2: Greedy Selection within Clusters
        cluster_groups = {}
        for i, cluster_id in enumerate(clusters):
            if cluster_id not in cluster_groups:
                cluster_groups[cluster_id] = []
            cluster_groups[cluster_id].append(alpha_pool[i])
            
        # Pick the one with best fitness from each cluster
        cluster_champions = []
        for cluster_id in cluster_groups:
            # Sort by fitness descending
            sorted_group = sorted(cluster_groups[cluster_id], key=lambda x: x.fitness, reverse=True)
            cluster_champions.append(sorted_group[0])
            
        # 4. Final Greedy Pruning (rho < 0.3)
        golden_alphas = []
        for candidate in cluster_champions:
            if not golden_alphas:
                golden_alphas.append(candidate)
                continue
            
            is_diverse = True
            c_series = candidate.evaluate(data)
            for selected in golden_alphas:
                s_series = selected.evaluate(data)
                corr = abs(c_series.corr(s_series))
                if not pd.isna(corr) and corr > self.rho_threshold:
                    is_diverse = False
                    break
            
            if is_diverse:
                golden_alphas.append(candidate)
                
        return golden_alphas

if __name__ == "__main__":
    # Small test logic
    print("DecorrelationEngine Module Loaded Successfully.")
