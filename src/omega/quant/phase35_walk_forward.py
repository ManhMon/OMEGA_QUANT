# flake8: noqa
"""Backward compatibility shim for phase35_walk_forward.

Redirects imports and mock patches to the canonical implementation in
omega.quant.alpha.phase35.
"""
import warnings

warnings.simplefilter('always', DeprecationWarning)
warnings.warn(
    "omega.quant.phase35_walk_forward is deprecated; import from omega.quant.alpha.phase35 instead.",
    DeprecationWarning,
    stacklevel=2
)

from omega.quant.alpha.phase35 import *
import omega.quant.alpha.phase35 as _module

# Expose all module-level variables/functions for patch/mock access
globals().update({k: v for k, v in _module.__dict__.items() if not k.startswith('_')})
