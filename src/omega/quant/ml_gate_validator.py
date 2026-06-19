# flake8: noqa
"""Backward compatibility shim for ml_gate_validator.

Redirects imports and mock patches to the canonical implementation in
omega.quant.ml.gate_validator.
"""
import warnings

warnings.simplefilter('always', DeprecationWarning)
warnings.warn(
    "omega.quant.ml_gate_validator is deprecated; import from omega.quant.ml.gate_validator instead.",
    DeprecationWarning,
    stacklevel=2
)

from omega.quant.ml.gate_validator import *
import omega.quant.ml.gate_validator as _module

# Expose all module-level variables/functions for patch/mock access
globals().update({k: v for k, v in _module.__dict__.items() if not k.startswith('_')})
