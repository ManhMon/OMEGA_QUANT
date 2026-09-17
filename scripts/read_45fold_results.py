"""Read and display the 45-fold CPCV results."""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "data/phase35_results/hybrid_regime_cpcv_comparison_optimized_45fold.json"
with open(path) as f:
    d = json.load(f)

perf = d["perf"]
print(f"Total elapsed: {perf['total_elapsed_sec']:.1f}s = {perf['total_elapsed_min']:.1f} min")
print(f"Workers: {d['config']['workers']}")
print(f"Folds: {d['config']['folds']} splits, {d['config']['n_test_folds']} test")
print(f"Symbols: {d['config']['symbol_count']}")
print()

for name, agg in d["aggregated"].items():
    if "error" not in agg:
        print(
            f"{name}: mean_sharpe={agg['mean_sharpe']:.4f}, "
            f"mean_return={agg['mean_return']*100:.2f}%, "
            f"mean_maxdd={agg['mean_max_dd']*100:.2f}%, "
            f"n_folds={agg['n_folds_completed']}, "
            f"n_errors={agg['n_folds_errored']}"
        )
    else:
        print(f"{name}: ERROR {agg}")

# Compute per-fold timing
per_fold_times = []
for name, agg in d["aggregated"].items():
    if "per_fold_return" in agg:
        n = len(agg["per_fold_return"])
        print(f"\n{name} per-fold returns: {[f'{r*100:.1f}%' for r in agg['per_fold_return'][:5]]}...")
