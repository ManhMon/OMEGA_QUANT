"""GP Feature Adapter — wires existing alpha arsenals into GP evolution.

Purpose
-------
Loads 200+ existing alphas (ultimate_alpha_arsenal, phase34_microstructure)
plus base OHLCV + engineered features, returns a dict[name -> np.ndarray]
suitable as input features for genetic-program evolution.

Sources (best-effort, never hard-fail on missing module)
--------------------------------------------------------
- omega.quant.ultimate_alpha_arsenal.compute_ultimate_alphas (~132 alphas)
- omega.quant.phase34_microstructure_alphas.compute_phase34_microstructure_alphas (~17 alphas)
- Base OHLCV: open / high / low / close / volume
- Engineered: ret_1d, ret_5d, vol_ratio, hl_range, oc_range

PIT Safety
----------
This module is a thin orchestrator. PIT correctness is the responsibility of
each underlying alpha source (ultimate / phase34). We only forward the input
DataFrame and apply purely-pointwise / past-only transforms (rolling means,
pct_change) on the engineered base features.

Role
----
[L2-Impl][Phase2.1] — Backend Engineer (Role 9)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# sys.path bootstrap — make both alpha source trees importable.
# src  -> phase34_microstructure_alphas
# src/                 -> ultimate_alpha_arsenal
# --------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
# .../src/omega/quant/evolution/feature_adapter.py
_PKG_SRC = _THIS_FILE.parents[3]                # .../src
_REPO_ROOT = _PKG_SRC.parent                    # workspace root
_LEGACY_SRC = _PKG_SRC                          # .../src

# FIX v5: Guarantee _PKG_SRC at sys.path[0]
for _p in (_LEGACY_SRC, _PKG_SRC):
    _ps = str(_p)
    if _p.exists():
        if _ps in sys.path:
            sys.path.remove(_ps)
        sys.path.insert(0, _ps)

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class GPFeatureAdapter:
    """Wires existing alpha arsenals into GP evolution as input features."""

    def __init__(self) -> None:
        self.sources: Dict[str, Callable[..., pd.DataFrame]] = {}
        self._load_sources()

    # ---------------------------------------------------------------- loading
    def _load_sources(self) -> None:
        """Best-effort import of each alpha module. Never raise."""
        try:
            from omega.quant.ultimate_alpha_arsenal import compute_ultimate_alphas  # type: ignore
            self.sources["ultimate"] = compute_ultimate_alphas
            logger.info("Loaded ultimate_alpha_arsenal (132 alphas)")
        except ImportError as e:
            logger.warning(f"ultimate_alpha_arsenal not available: {e}")
        except Exception as e:  # noqa: BLE001 — defensive on import-time errors
            logger.warning(f"ultimate_alpha_arsenal import error: {e}")

        try:
            from omega.quant.phase34_microstructure_alphas import (  # type: ignore
                compute_phase34_microstructure_alphas,
            )
            self.sources["phase34"] = compute_phase34_microstructure_alphas
            logger.info("Loaded phase34_microstructure (17 alphas)")
        except ImportError as e:
            logger.warning(f"phase34 not available: {e}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"phase34 import error: {e}")

    # -------------------------------------------------------------- main API
    def compute_all(
        self,
        df: pd.DataFrame,
        top_n_features: int = 100,
    ) -> Dict[str, np.ndarray]:
        """Compute all available alphas; return dict[name -> np.ndarray] for GP.

        Parameters
        ----------
        df : DataFrame with at minimum (ticker, date, open, high, low, close, volume).
        top_n_features : keep only the top-N highest-variance features.
        """
        all_alphas: List[Tuple[str, np.ndarray]] = []

        # --- source: ultimate_alpha_arsenal ---
        if "ultimate" in self.sources:
            try:
                ult_df = self.sources["ultimate"](df, symbol_col="ticker")
                alpha_cols = [c for c in ult_df.columns if c.startswith("alpha_")]
                logger.info(f"ultimate_alpha_arsenal produced {len(alpha_cols)} alphas")
                for col in alpha_cols:
                    all_alphas.append((col, np.asarray(ult_df[col].values)))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"ultimate failed: {e}")

        # --- source: phase34 microstructure ---
        if "phase34" in self.sources:
            try:
                p34_df = self.sources["phase34"](df)
                alpha_cols = [c for c in p34_df.columns if c not in ("ticker", "date")]
                logger.info(f"phase34 produced {len(alpha_cols)} alphas")
                for col in alpha_cols:
                    all_alphas.append((col, np.asarray(p34_df[col].values)))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"phase34 failed: {e}")

        # --- base OHLCV (raw) ---
        base_features = ["open", "high", "low", "close", "volume"]
        for col in base_features:
            if col in df.columns:
                all_alphas.append((col, np.asarray(df[col].values)))

        # --- engineered base features (PIT-safe: past-only) ---
        eng = df.copy()
        eng = eng.sort_values(["ticker", "date"])
        eng["ret_1d"] = eng.groupby("ticker")["close"].pct_change(1)
        eng["ret_5d"] = eng.groupby("ticker")["close"].pct_change(5)
        eng["vol_ratio"] = eng["volume"] / (
            eng.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean()) + 1.0
        )
        eng["hl_range"] = (eng["high"] - eng["low"]) / (eng["close"] + 1e-9)
        eng["oc_range"] = (eng["close"] - eng["open"]) / (eng["close"] + 1e-9)
        for col in ["ret_1d", "ret_5d", "vol_ratio", "hl_range", "oc_range"]:
            all_alphas.append((col, np.asarray(eng[col].values)))

        logger.info(f"Total features: {len(all_alphas)}")

        # --- variance filter (strip constants / all-NaN columns) ---
        filtered: List[Tuple[str, np.ndarray]] = []
        for name, values in all_alphas:
            values = np.nan_to_num(
                np.asarray(values, dtype=np.float64),
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            )
            if np.std(values) > 1e-6:
                filtered.append((name, values))

        logger.info(f"After variance filter: {len(filtered)}")

        # --- top-N by variance (proxy for information content) ---
        if len(filtered) > top_n_features:
            filtered.sort(key=lambda x: -float(np.std(x[1])))
            filtered = filtered[:top_n_features]
            logger.info(f"Truncated to top {top_n_features} by std")

        return {name: values for name, values in filtered}

    # --------------------------------------------------------------- helpers
    def available_sources(self) -> List[str]:
        """Names of alpha sources successfully imported at init time."""
        return sorted(self.sources.keys())


__all__ = ["GPFeatureAdapter"]
