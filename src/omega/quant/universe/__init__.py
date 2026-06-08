"""OMEGA_QUANT Universe Package - Phase 1.1 (Role 9)."""

# Auto-wired submodules and subpackages
try:
    from . import feature_computer
except ImportError:
    pass

try:
    from . import xgb_classifier
except ImportError:
    pass
