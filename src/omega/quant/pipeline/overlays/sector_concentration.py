"""Sector concentration overlay - cap sector exposure at max threshold.

Gate: UNIFIED_SYSTEM_INTEGRATION_20260619

Reads sector mapping from CSV and enforces max sector exposure <= threshold
(default 30% NAV). Excess weight is redistributed proportionally across
other sectors in a PIT-safe manner.

PIT Safety: Uses only current weights and static sector mapping.
No forward-looking data required.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay

logger = logging.getLogger(__name__)


class SectorConcentrationOverlay(WeightOverlay):
    """Cap per-sector exposure at a configurable threshold (default 30%).

    Parameters
    ----------
    max_sector_exposure : float
        Maximum fraction of NAV allowed in any single sector (default 0.30).
    sector_mapping_file : str or Path or None
        Path to CSV with columns ``symbol`` and ``sector``.
        If None, uses repo-relative ``data/sector_mapping_level2.csv``.
    max_redistribution_iterations : int
        Max iterations for excess redistribution loop (default 10).
    """

    def __init__(
        self,
        max_sector_exposure: float = 0.30,
        sector_mapping_file: Optional[str] = None,
        max_redistribution_iterations: int = 10,
    ):
        self.max_sector_exposure = max_sector_exposure
        self.max_redistribution_iterations = max_redistribution_iterations
        self._sector_map: Optional[Dict[str, str]] = None

        if sector_mapping_file is not None:
            self._sector_mapping_path = Path(sector_mapping_file)
        else:
            repo_root = Path(__file__).resolve().parents[5]
            self._sector_mapping_path = repo_root / "data" / "sector_mapping_level2.csv"

    def _load_sector_map(self) -> Dict[str, str]:
        if self._sector_map is not None:
            return self._sector_map
        try:
            df = pd.read_csv(self._sector_mapping_path)
            self._sector_map = dict(zip(df["symbol"], df["sector"]))
            logger.info(
                "SectorConcentrationOverlay: loaded %d sector mappings from %s",
                len(self._sector_map),
                self._sector_mapping_path.name,
            )
        except Exception as e:
            logger.warning("Failed to load sector mapping: %s. Using empty map.", e)
            self._sector_map = {}
        return self._sector_map

    def apply(
        self,
        weights: pd.DataFrame,
        panel: pd.DataFrame,
        state: Dict[str, Any],
    ) -> pd.DataFrame:
        sector_map = self._load_sector_map()
        if not sector_map:
            logger.warning("SectorConcentrationOverlay: no sector mapping, returning weights unchanged.")
            return weights

        result = weights.copy()

        for dt in result.index:
            row = result.loc[dt]
            active_symbols = row[row.abs() > 1e-8].index.tolist()
            if not active_symbols:
                continue

            symbol_sectors = {sym: sector_map.get(sym, "Unknown") for sym in active_symbols}

            for _ in range(self.max_redistribution_iterations):
                sector_weights: Dict[str, float] = {}
                for sym in active_symbols:
                    sec = symbol_sectors[sym]
                    sector_weights[sec] = sector_weights.get(sec, 0.0) + abs(row[sym])

                capped = False
                for sec, sec_w in sector_weights.items():
                    if sec_w > self.max_sector_exposure:
                        excess_factor = self.max_sector_exposure / sec_w
                        for sym in active_symbols:
                            if symbol_sectors[sym] == sec:
                                row[sym] = row[sym] * excess_factor
                        capped = True

                if not capped:
                    break

                row_sum = row.abs().sum()
                if row_sum > 0 and abs(row_sum - 1.0) > 0.01:
                    uncapped_symbols = [
                        sym for sym in active_symbols
                        if symbol_sectors[sym] not in {
                            s for s, w in sector_weights.items()
                            if w > self.max_sector_exposure
                        }
                    ]
                    if uncapped_symbols:
                        deficit = 1.0 - row.abs().sum()
                        uncapped_sum = row[uncapped_symbols].abs().sum()
                        if uncapped_sum > 1e-8:
                            boost = deficit / uncapped_sum
                            for sym in uncapped_symbols:
                                row[sym] = row[sym] * (1.0 + boost)

            result.loc[dt] = row

        return result
