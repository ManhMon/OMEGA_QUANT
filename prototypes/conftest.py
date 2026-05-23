"""
Pytest configuration for OMEGA_QUANT monorepo.
Ensures all package paths are available during test collection.
Handles namespace packages by extending __path__ for 'omega'.
"""

import sys
import os
import importlib

# Get root directory
root_dir = os.path.dirname(os.path.abspath(__file__))

# Add all package src directories to sys.path
packages = [
    "packages/core/src",
    "packages/data/src",
    "packages/quant/src",
    "packages/backtest/src",
    "packages/execution/src",
    "packages/risk/src",
    "packages/governance/src",
    "packages/security/src",
    "packages/observability/src",
    "packages/infra/src",
    "packages/contracts/src",
    "packages/memory/src",
]

# Ensure sys.path includes all src folders
for pkg in packages:
    pkg_path = os.path.join(root_dir, pkg)
    if os.path.exists(pkg_path) and pkg_path not in sys.path:
        sys.path.insert(0, pkg_path)

# Special handling for 'omega' namespace
def pytest_configure(config):
    # If omega is already imported, we extend its __path__
    # If not, we don't force it here to avoid early import side-effects,
    # but sys.path above should handle most cases if __init__.py files are correct.
    pass
