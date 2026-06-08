import sys
import os
from pathlib import Path

# Phase 6 fix: PREPEND packages/*/src so canonical (omega.quant.portfolio
# package, omega.data, etc.) take precedence over the legacy src/ tree
# at the repo root. Without this, `src/omega/quant/portfolio.py` (a flat
# legacy module) shadows the canonical package directory and tests for
# omega.quant.portfolio.portfolio_optimizer fail to collect.
repo_root = Path(__file__).parent.parent.parent.parent
packages_dir = repo_root / "packages"

for p in packages_dir.iterdir():
    if p.is_dir():
        src_dir = p / "src"
        if src_dir.exists():
            sp = str(src_dir)
            if sp in sys.path:
                sys.path.remove(sp)
            sys.path.insert(0, sp)

