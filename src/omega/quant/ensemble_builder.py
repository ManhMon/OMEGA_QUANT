"""omega.quant.ensemble_builder - compatibility shim"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List
import numpy as np

@dataclass
class EnsembleConfig:
    n_folds: int = 5
    method: str = "stacking"
    base_models: List[str] = field(default_factory=list)
    meta_model: str = "ridge"
    extra: Dict[str, Any] = field(default_factory=dict)

class OOFEnsembleBuilder:
    def __init__(self, config: EnsembleConfig = None):
        self.config = config or EnsembleConfig()
    def build(self, *args, **kwargs): return None
    def predict(self, *args, **kwargs): return np.array([])

EnsembleBuilder = OOFEnsembleBuilder
