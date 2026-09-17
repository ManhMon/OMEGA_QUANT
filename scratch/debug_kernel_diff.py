import numpy as np
import sys
from pathlib import Path

REPO_ROOT = Path("c:/Users/GHC/repos/OMEGA_QUANT")
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import genetic_alpha_evolution_v4 as v4
from omega.quant.evolution.genetic_engine import GPConfig, GeneticEngine

def main():
    n_dates = 24
    per_date = 6
    n = n_dates * per_date
    x = np.linspace(-2.0, 2.0, n)
    dates = np.repeat(np.arange(n_dates), per_date)
    features = {
        'f1': x,
        'f2': x[::-1],
        '__date__': dates,
        '__log_market_cap__': np.tile(np.linspace(1.0, 3.0, per_date), n_dates),
        '__sector__': np.tile(np.array([0, 1, 2, 0, 1, 2]), n_dates),
    }
    
    # Setup context
    context = v4._build_vm_context(features)
    jit_payload = (
        context["design_matrix"],
        context["valid_mask"],
        context["date_flat_indices"],
        context["date_group_offsets"],
        int(np.max(np.diff(context["date_group_offsets"])))
    )
    
    # Mock alpha matrix (3 candidates)
    np.random.seed(42)
    alpha_matrix = np.random.randn(n, 3)
    
    # Run batch kernel
    res_batch = v4._numba_batch_ridge_neutralize(alpha_matrix, *jit_payload, 1e-6)
    
    # Run single kernel for each candidate
    res_single = np.empty_like(alpha_matrix)
    for c in range(3):
        res_single[:, c] = v4._numba_ridge_neutralize(alpha_matrix[:, c], *jit_payload, 1e-6)
        
    # Check difference
    diff = np.abs(res_batch - res_single)
    print("Max absolute difference:", np.max(diff))
    if np.max(diff) > 1e-10:
        for c in range(3):
            print(f"Candidate {c} diff:")
            print("Batch first 10 values:", res_batch[:10, c])
            print("Single first 10 values:", res_single[:10, c])

if __name__ == "__main__":
    main()
