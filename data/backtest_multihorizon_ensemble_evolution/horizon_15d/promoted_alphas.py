"""
Automatically generated alpha features from Phase 2 Discovery.
DO NOT EDIT MANUALLY. USE AlphaPromoter TO UPDATE.
"""
import pandas as pd
import numpy as np

def compute_promoted_alphas(panel: pd.DataFrame) -> pd.DataFrame:
    """Compute all promoted alpha features on the input panel."""
    # Panel must be MultiIndex [timestamp, symbol]
    out = pd.DataFrame(index=panel.index)

    # Step 1: Create lagged environment to prevent leakage
    symbol_level = panel.index.names[1]
    lagged = panel.groupby(level=symbol_level).shift(1)

    # Primitives (safe, no eval needed)
    def rank(x): return x.groupby(level=0).rank(pct=True)
    def delay(x, n): return x.groupby(level=1).shift(n)
    def delta(x, n): return x - delay(x, n)
    def ma(x, n): return x.groupby(level=1).transform(lambda s: s.rolling(n).mean())
    def rsi(x, n):
        def _rsi(s, p):
            diff = s.diff()
            up = diff.where(diff > 0, 0)
            down = -diff.where(diff < 0, 0)
            ma_up = up.rolling(p).mean()
            ma_down = down.rolling(p).mean()
            rs = ma_up / (ma_down + 1e-9)
            return 100 - (100 / (1 + rs))
        return x.groupby(level=1).transform(lambda s: _rsi(s, n))

    # Safe function mapping for promoted alphas
    safe_funcs = {
        "rank": rank, "delay": delay, "delta": delta, "ma": ma, "rsi": rsi,
        "close": lagged["close"], "volume": lagged["volume"] if "volume" in lagged.columns else None
    }

    # IC: 0.3037, Category: evolved
    try:
        out["(min (mean (delay volume)))"] = eval("(min (mean (delay volume)))", {"__builtins__": {}}, safe_funcs)
    except Exception as e:
        print(f"Failed to compute promoted alpha (min (mean (delay volume))): {e}")

    return out