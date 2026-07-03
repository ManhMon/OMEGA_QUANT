import os
import sys
import subprocess
import time
from pathlib import Path

# Set stdout encoding
sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = Path("C:/Users/GHC/repos/OMEGA_QUANT")

EXPERIMENTS = [
    {
        "name": "E5a_HighMinTrade",
        "args": [
            "--folds", "10",
            "--n-test-folds", "2",
            "--top-k", "7",
            "--cost-per-trade-bps", "15.0",
            "--dynamic-universe",
            "--symbol-count", "60",
            "--workers", "6",
            "--min-trade-threshold-bps", "350.0",
            "--rebalance-every-n-days", "15",
            "--output-tag", "p2_opt_e5a"
        ]
    },
    {
        "name": "E5b_LowFreqRebalance",
        "args": [
            "--folds", "10",
            "--n-test-folds", "2",
            "--top-k", "7",
            "--cost-per-trade-bps", "15.0",
            "--dynamic-universe",
            "--symbol-count", "60",
            "--workers", "6",
            "--min-trade-threshold-bps", "250.0",
            "--rebalance-every-n-days", "20",
            "--output-tag", "p2_opt_e5b"
        ]
    },
    {
        "name": "E5c_AggressiveBearDampening",
        "args": [
            "--folds", "10",
            "--n-test-folds", "2",
            "--top-k", "7",
            "--cost-per-trade-bps", "15.0",
            "--dynamic-universe",
            "--symbol-count", "60",
            "--workers", "6",
            "--risk-latent-gmm-bear-dampening", "0.20",
            "--output-tag", "p2_opt_e5c"
        ]
    },
    {
        "name": "E5d_CombinedOptCost",
        "args": [
            "--folds", "10",
            "--n-test-folds", "2",
            "--top-k", "10",
            "--cost-per-trade-bps", "15.0",
            "--dynamic-universe",
            "--symbol-count", "60",
            "--workers", "6",
            "--min-trade-threshold-bps", "350.0",
            "--rebalance-every-n-days", "20",
            "--output-tag", "p2_opt_e5d"
        ]
    }
]

def run_cmd(args):
    cmd = [sys.executable, str(REPO_ROOT / "scripts/backtest_hybrid_regime.py")] + args
    print(f"Executing: {' '.join(cmd)}")
    start = time.time()
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, encoding='utf-8')
    elapsed = time.time() - start
    print(f"Finished in {elapsed:.1f}s. Exit code: {res.returncode}")
    if res.returncode != 0:
        print("ERROR:")
        print(res.stderr[:2000])
    return res.returncode == 0

def main():
    print("Starting E5 Parameter Fine-Tuning Sweeps (p2full base)...")
    for exp in EXPERIMENTS:
        print(f"\n=== Running {exp['name']} ===")
        success = run_cmd(exp['args'])
        if not success:
            print(f"Experiment {exp['name']} failed! Aborting.")
            sys.exit(1)
    print("\nAll E5 optimization experiments completed successfully!")

if __name__ == "__main__":
    main()
