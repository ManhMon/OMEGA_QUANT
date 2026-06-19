# flake8: noqa
"""OMEGA_QUANT Voting & Stacking Ensemble Module (Phase 15).

Shim wrapper preserving backward compatibility.
"""

from __future__ import annotations

import warnings


def _warn_deprecated() -> None:
    """Issue deprecation warning for this module."""
    warnings.warn(
        "omega.quant.ml.voting_stacking is deprecated; import from "
        "omega.quant.ml.ensemble_config, omega.quant.ml.voting, or "
        "omega.quant.ml.stacking instead.",
        DeprecationWarning,
        stacklevel=2,
    )


_warn_deprecated()

from omega.quant.ml.ensemble_config import (
    BaseModelPrediction,
    EnsembleConfig,
    EnsembleResult,
    MetaLearnerType,
    WeightingScheme,
)
from omega.quant.ml.stacking import (
    StackingEnsemble,
    create_stacking_ensemble,
)
from omega.quant.ml.voting import (
    VotingEnsemble,
    create_voting_ensemble,
)

__all__ = [
    "WeightingScheme",
    "MetaLearnerType",
    "EnsembleConfig",
    "BaseModelPrediction",
    "EnsembleResult",
    "VotingEnsemble",
    "create_voting_ensemble",
    "StackingEnsemble",
    "create_stacking_ensemble",
]
