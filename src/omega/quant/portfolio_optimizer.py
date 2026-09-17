# flake8: noqa
"""Backward compatibility shim for portfolio_optimizer.

Redirects imports and mock patches to the canonical implementation in
omega.quant.portfolio.portfolio_optimizer.
"""
import warnings

warnings.simplefilter('always', DeprecationWarning)
warnings.warn(
    "omega.quant.portfolio_optimizer is deprecated; import from omega.quant.portfolio.portfolio_optimizer instead.",
    DeprecationWarning,
    stacklevel=2
)

from omega.quant.portfolio.portfolio_optimizer import *
import omega.quant.portfolio.portfolio_optimizer as _module

# Expose all module-level variables/functions for patch/mock access
globals().update({k: v for k, v in _module.__dict__.items() if not k.startswith('_')})
