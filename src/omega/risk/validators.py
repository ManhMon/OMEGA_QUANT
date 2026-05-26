from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, Tuple, Dict, List, Optional
from statistics import mean, stdev
import math
import numpy as np


class BaseValidator(ABC):
    """
    Abstract base class for all risk validators.
    """
    
    @abstractmethod
    def validate(
        self,
        symbol_weights: Dict[str, float],
        sector_weights: Dict[str, float],
        order_sizes: Dict[str, float],
        adv_data: Dict[str, float],
        returns_data: Dict[str, List[float]],
        equity_curve: List[float],
        **kwargs
    ) -> Tuple[bool, str]:
        pass


@dataclass(frozen=True)
class AssetLimitValidator(BaseValidator):
    max_weight_pct: float = 0.20
    
    def validate(self, symbol_weights, sector_weights, order_sizes, adv_data, returns_data, equity_curve, **kwargs):
        for symbol, weight in symbol_weights.items():
            # FIX (v21.28.2): Exclude CASH from asset limit check (CASH is not a risky asset)
            if symbol == "CASH":
                continue
            if weight > self.max_weight_pct + 1e-9:
                return False, f"Symbol '{symbol}' weight {weight:.2%} exceeds limit {self.max_weight_pct:.2%}"
        return True, "OK"


@dataclass(frozen=True)
class SectorLimitValidator(BaseValidator):
    max_weight_pct: float = 0.40
    
    def validate(self, symbol_weights, sector_weights, order_sizes, adv_data, returns_data, equity_curve, **kwargs):
        for sector, weight in sector_weights.items():
            if weight > self.max_weight_pct + 1e-9:
                return False, f"Sector '{sector}' weight {weight:.2%} exceeds limit {self.max_weight_pct:.2%}"
        return True, "OK"


@dataclass(frozen=True)
class LiquidityValidator(BaseValidator):
    max_adv_pct: float = 0.10
    
    def validate(self, symbol_weights, sector_weights, order_sizes, adv_data, returns_data, equity_curve, **kwargs):
        for symbol, qty in order_sizes.items():
            adv = adv_data.get(symbol, 0.0)
            if adv > 0 and abs(qty) / adv > self.max_adv_pct + 1e-9:
                return False, f"Order for '{symbol}' exceeds {self.max_adv_pct:.1%} of ADV"
        return True, "OK"


@dataclass(frozen=True)
class VolatilityValidator(BaseValidator):
    max_annual_vol: float = 0.30
    
    def validate(self, symbol_weights, sector_weights, order_sizes, adv_data, returns_data, equity_curve, **kwargs):
        if len(equity_curve) < 5: return True, "OK"
        returns = [equity_curve[i]/equity_curve[i-1]-1 for i in range(1, len(equity_curve)) if equity_curve[i-1]>0]
        if len(returns) < 2: return True, "OK"
        vol = stdev(returns) * math.sqrt(252)
        if vol > self.max_annual_vol:
            return False, f"Volatility {vol:.2%} exceeds limit {self.max_annual_vol:.2%}"
        return True, "OK"


@dataclass(frozen=True)
class DrawdownValidator(BaseValidator):
    max_drawdown_pct: float = 0.20
    
    def validate(self, symbol_weights, sector_weights, order_sizes, adv_data, returns_data, equity_curve, **kwargs):
        if not equity_curve: return True, "OK"
        peak, max_dd = 0.0, 0.0
        for val in equity_curve:
            if val > peak: peak = val
            if peak > 0:
                dd = (peak - val) / peak
                max_dd = max(max_dd, dd)
        if max_dd > self.max_drawdown_pct:
            return False, f"Drawdown {max_dd:.2%} exceeds limit {self.max_drawdown_pct:.2%}. KILL SWITCH ACTIVATED!"
        return True, "OK"


@dataclass(frozen=True)
class ExposureValidator(BaseValidator):
    """
    NEW (v21.10.2): Rejects if gross exposure exceeds 100%.
    Institutional safe-guard against accidental leverage.
    """
    max_exposure: float = 1.001

    def validate(self, symbol_weights, sector_weights, order_sizes, adv_data, returns_data, equity_curve, **kwargs):
        # FIX (v21.10.6): Use absolute value to capture both long and short positions
        gross_exposure = sum(abs(w) for s, w in symbol_weights.items() if s != "CASH")
        if gross_exposure > self.max_exposure:
            return False, f"Gross exposure {gross_exposure:.2%} exceeds {self.max_exposure:.1%} limit (Leverage Blocked)"
        return True, "OK"


@dataclass(frozen=True)
class VaRValidator(BaseValidator):
    max_var_pct: float = 0.05
    confidence: float = 0.95
    
    def validate(self, symbol_weights, sector_weights, order_sizes, adv_data, returns_data, equity_curve, **kwargs):
        """Fix P0-3: Implement Parametric VaR calculation."""
        if not symbol_weights or not returns_data: return True, "VaR OK (No data)"
        
        # Simple weighted sum of individual asset returns to get portfolio returns history
        # (Assuming assets have same return history length for this implementation)
        common_symbols = [s for s in symbol_weights if s in returns_data and len(returns_data[s]) >= 20]
        if not common_symbols: return True, "VaR OK (No history)"
        
        hist_len = min(len(returns_data[s]) for s in common_symbols)
        port_rets = []
        for i in range(hist_len):
            r = sum(symbol_weights[s] * returns_data[s][i] for s in common_symbols)
            port_rets.append(r)
            
        if len(port_rets) < 20: return True, "VaR OK (Sample too small)"
        
        z_score = 1.645 if self.confidence <= 0.95 else 2.326
        port_std = float(np.std(port_rets))
        var_val = port_std * z_score
        
        if var_val > self.max_var_pct:
            return False, f"VaR {var_val:.2%} exceeds limit {self.max_var_pct:.2%}"
        return True, f"VaR OK ({var_val:.2%})"
