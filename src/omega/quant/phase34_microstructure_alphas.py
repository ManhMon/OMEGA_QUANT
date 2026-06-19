# flake8: noqa
"""Backward compatibility shim for phase34_microstructure_alphas.

Redirects imports and mock patches to the canonical implementation in
omega.quant.alpha.phase34.
"""
import warnings

warnings.simplefilter('always', DeprecationWarning)
warnings.warn(
    "omega.quant.phase34_microstructure_alphas is deprecated; import from omega.quant.alpha.phase34 instead.",
    DeprecationWarning,
    stacklevel=2
)

from omega.quant.alpha.phase34 import *
import omega.quant.alpha.phase34 as _module

# Expose all module-level variables/functions for patch/mock access
globals().update({k: v for k, v in _module.__dict__.items() if not k.startswith('_')})
