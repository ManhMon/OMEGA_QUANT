import sys
import os
from pathlib import Path
import pytest

# Get OMEGA root (omega/)
omega_root = Path(__file__).resolve().parent.parent

# 1. Dynamically find all package src directories and add them to sys.path
packages_dir = omega_root / "packages"
src_paths = []

if packages_dir.exists():
    for pkg in packages_dir.iterdir():
        if pkg.is_dir():
            src_dir = pkg / "src"
            if src_dir.exists():
                src_paths.append(str(src_dir))

# Add src paths to python path
for p in src_paths:
    if p not in sys.path:
        sys.path.insert(0, p)
        print(f"Added to sys.path: {p}")

# Add omega root itself (for absolute imports of packages.core etc. if any)
if str(omega_root) not in sys.path:
    sys.path.insert(0, str(omega_root))

# 2. Run pytest
print(f"Running pytest inside {omega_root}...")
os.chdir(str(omega_root))

# Standard arguments or custom ones passed via CLI
args = sys.argv[1:] if len(sys.argv) > 1 else ["packages/core/tests", "packages/quant/tests", "packages/risk/tests", "packages/execution/tests", "-q"]
sys.exit(pytest.main(args))
