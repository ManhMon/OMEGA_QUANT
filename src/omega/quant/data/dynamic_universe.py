"""
Dynamic Universe Selector - V21 Institutional
AI automatically selects potential stocks from the entire market.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
import numpy as np


@dataclass
class UniverseConfig:
    """Configuration for dynamic universe selection."""
    min_adv_value: float = 20e9        # Min avg daily value (20 billion VND)
    max_position_pct_adv: float = 0.02 # Max position as % of ADV (2%)
    top_n: int = 50                     # Max number of stocks to select
    sector_cap: float = 0.30            # Max sector weight (30%)
    min_hold_weeks: int = 2             # Cooldown before removing from universe
    score_threshold: float = 0.3        # Min score to be included


@dataclass
class SelectedUniverse:
    """Result of dynamic universe selection."""
    symbols: List[str]
    scores: Dict[str, float]
    liquidity: Dict[str, float]
    sector_weights: Dict[str, float]
    excluded_reason: Dict[str, str]


class DynamicUniverseSelector:
    """Selects potential stocks from the entire market dynamically.

    Pipeline:
    1. Pre-filter: Remove delisted/suspended/illiquid
    2. Scoring: Rank by ensemble AI score
    3. Top-N selection with sector cap
    4. Stability: Apply cooldown to reduce turnover
    """

    def __init__(self, config: Optional[UniverseConfig] = None):
        self.config = config or UniverseConfig()
        self._prev_universe: Set[str] = set()
        self._hold_counter: Dict[str, int] = {}  # weeks in current universe

    def pre_filter(
        self,
        symbols: List[str],
        adv_values: Dict[str, float],
        is_active: Dict[str, bool]
    ) -> Dict[str, str]:
        """Pre-filter: Remove delisted/suspended/illiquid stocks.

        Args:
            symbols: All available symbols
            adv_values: Average daily value (VND)
            is_active: Whether stock is actively trading

        Returns:
            Dictionary of excluded_symbol -> reason
        """
        excluded = {}
        for sym in symbols:
            if not is_active.get(sym, True):
                excluded[sym] = "delisted_or_suspended"
                continue
            adv = adv_values.get(sym, 0.0)
            if adv < self.config.min_adv_value:
                excluded[sym] = f"low_liquidity (ADV={adv/1e9:.1f}B)"
        return excluded

    def select(
        self,
        symbols: List[str],
        scores: Dict[str, float],
        adv_values: Dict[str, float],
        sectors: Dict[str, str],
        is_active: Optional[Dict[str, bool]] = None
    ) -> SelectedUniverse:
        """Run full universe selection pipeline.

        Args:
            symbols: All candidate symbols
            scores: AI ensemble scores per symbol
            adv_values: Average daily value (VND)
            sectors: Sector mapping (symbol -> sector)
            is_active: Whether stock is active

        Returns:
            SelectedUniverse
        """
        if is_active is None:
            is_active = {s: True for s in symbols}

        # 1. Pre-filter
        excluded = self.pre_filter(symbols, adv_values, is_active)
        valid_symbols = [s for s in symbols if s not in excluded]

        # 2. Score threshold filter
        for sym in list(valid_symbols):
            if scores.get(sym, 0.0) < self.config.score_threshold:
                excluded[sym] = "score_below_threshold"
                valid_symbols.remove(sym)

        # 3. Rank by score descending
        ranked = sorted(valid_symbols, key=lambda s: scores.get(s, 0.0), reverse=True)

        # 4. Top-N with sector cap
        selected = []
        sector_counts: Dict[str, int] = {}

        for sym in ranked:
            if len(selected) >= self.config.top_n:
                break
            sector = sectors.get(sym, "unknown")
            sector_ratio = sector_counts.get(sector, 0) / max(1, len(selected) + 1)
            if sector_ratio >= self.config.sector_cap:
                excluded[sym] = f"sector_cap_exceeded ({sector})"
                continue
            selected.append(sym)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

        # 5. Stability: Keep previous members a little longer (cooldown)
        # NOTE: ensure we still respect top_n by applying a final cap afterwards.
        for sym in self._prev_universe:
            if sym not in selected and sym not in excluded:
                weeks_held = self._hold_counter.get(sym, 0)
                if weeks_held < self.config.min_hold_weeks:
                    selected.append(sym)  # Keep in universe

        # Final cap to top_n with cooldown priority
        if len(selected) > self.config.top_n:
            def _priority_key(sym: str):
                # Higher priority for symbols still under cooldown
                weeks_held = self._hold_counter.get(sym, 0)
                under_cooldown = 1 if (sym in self._prev_universe and weeks_held < self.config.min_hold_weeks) else 0
                return (under_cooldown, scores.get(sym, 0.0))

            selected = sorted(selected, key=_priority_key, reverse=True)[: self.config.top_n]

        # 6. Update hold counter
        new_universe = set(selected)
        for sym in new_universe:
            if sym in self._prev_universe:
                self._hold_counter[sym] = self._hold_counter.get(sym, 0) + 1
            else:
                self._hold_counter[sym] = 1
        # Reset counter for removed symbols
        for sym in self._prev_universe - new_universe:
            self._hold_counter.pop(sym, None)

        self._prev_universe = new_universe

        # Build sector weights
        sector_weights: Dict[str, float] = {}
        for sym in selected:
            sec = sectors.get(sym, "unknown")
            sector_weights[sec] = sector_weights.get(sec, 0.0) + 1.0 / max(1, len(selected))

        return SelectedUniverse(
            symbols=selected,
            scores={s: scores.get(s, 0.0) for s in selected},
            liquidity={s: adv_values.get(s, 0.0) for s in selected},
            sector_weights=sector_weights,
            excluded_reason=excluded
        )
