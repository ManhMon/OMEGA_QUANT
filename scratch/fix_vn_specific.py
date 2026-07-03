import re

with open("src/omega/quant/alpha/vn_specific.py", "r", encoding="utf-8") as f:
    content = f.read()

replacements = [
    (
        "    - Native Rolling API: Uses .groupby().rolling().mean().reset_index(level=0, drop=True)",
        "    - Native Rolling API: Uses .groupby().rolling().mean()\n      with reset_index(level=0, drop=True)"
    ),
    (
        "    Native Rolling API: Uses .groupby().rolling().mean/std().reset_index(level=0, drop=True)",
        "    Native Rolling API: Uses .groupby().rolling().mean/std()\n                        with reset_index(level=0, drop=True)"
    ),
    (
        "    VN ILLIQ Regime Penalty - Penalizes stocks in persistent illiquidity regimes.",
        "    VN ILLIQ Regime Penalty - Penalizes stocks in persistent\n    illiquidity regimes."
    ),
    (
        "             Hypothesis: Extreme BB positions (>1 or <-1) predict snapback to mean",
        "             Hypothesis: Extreme BB positions (>1 or <-1)\n                         predict snapback to mean"
    ),
    (
        "    VN Sector-Neutral Residual Reversion - Mean reversion of sector-adjusted returns.",
        "    VN Sector-Neutral Residual Reversion - Mean reversion\n    of sector-adjusted returns."
    ),
    (
        "    VN Close Location Reversion - Mean reversion based on Close Location Value (CLV).",
        "    VN Close Location Reversion - Mean reversion based on Close\n    Location Value (CLV)."
    ),
    (
        "             Hypothesis: Extreme foreign absorption (relative to volume) predicts reversal",
        "             Hypothesis: Extreme foreign absorption (relative to\n                         volume) predicts reversal"
    ),
    (
        "    VN Foreign Room Squeeze - Signal based on foreign room availability percentage.",
        "    VN Foreign Room Squeeze - Signal based on foreign room\n    availability percentage."
    ),
    (
        "    VN Limit Lock Continuation - Continuation signal after limit-lock (ceil/floor) events.",
        "    VN Limit Lock Continuation - Continuation signal after limit-lock\n    (ceil/floor) events."
    ),
    (
        "             Hypothesis: Limit locks persist in short term (momentum continuation)",
        "             Hypothesis: Limit locks persist in short term\n                         (momentum continuation)"
    ),
    (
        "    Formula: ret_2d - ret_3d (captures T+2 money settlement vs T+3 securities settlement differential)",
        "    Formula: ret_2d - ret_3d (captures T+2 money settlement vs\n             T+3 securities settlement differential)"
    ),
    (
        "             Hypothesis: T+2 (money) vs T+3 (securities) settlement creates momentum differential",
        "             Hypothesis: T+2 (money) vs T+3 (securities) settlement\n                         creates momentum differential"
    ),
    (
        "    Penny Trap Score - Low-price, low-liquidity manipulation risk (VN-specific).",
        "    Penny Trap Score - Low-price, low-liquidity manipulation risk\n    (VN-specific)."
    ),
    (
        "    Formula: Composite signal from Chaikin Money Flow (CMF) and volume-price correlation",
        "    Formula: Composite signal from Chaikin Money Flow (CMF) and\n             volume-price correlation"
    ),
    (
        "    VN Limit Unlock Exhaustion - Signal after limit unlock (momentum exhaustion).",
        "    VN Limit Unlock Exhaustion - Signal after limit unlock\n    (momentum exhaustion)."
    ),
    (
        "             Hypothesis: When price breaks limit-lock (ceiling/floor), momentum often exhausts",
        "             Hypothesis: When price breaks limit-lock (ceiling/floor),\n                         momentum often exhausts"
    ),
    (
        "    VN T+2 Settlement Supply Overhang - Supply pressure from T+2 settlement cycle.",
        "    VN T+2 Settlement Supply Overhang - Supply pressure from T+2\n    settlement cycle."
    ),
    (
        "             Hypothesis: Stocks sold at T are delivered at T+2 before 13:00 (money settlement),",
        "             Hypothesis: Stocks sold at T are delivered at T+2 before\n                         13:00 (money settlement),"
    ),
    (
        "    Native Rolling API: Uses .groupby().rolling().sum/mean/std().reset_index(level=0, drop=True)",
        "    Native Rolling API: Uses .groupby().rolling().sum/mean/std()\n                        with reset_index(level=0, drop=True)"
    ),
    (
        "    - T+2 before 13:00: Money settlement (cash from sales available) - both money & securities",
        "    - T+2 before 13:00: Money settlement (cash from sales available)\n      - both money & securities"
    ),
    (
        "        df: DataFrame with date, symbol, close, volume, and optional is_t2_settlement flag",
        "        df: DataFrame with date, symbol, close, volume, and optional\n            is_t2_settlement flag"
    ),
    (
        "    # T+2 Settlement Logic: Volume sold at T-1 creates settlement at T+2 (shift by 1 for T+2)",
        "    # T+2 Settlement Logic: Volume sold at T-1 creates settlement at T+2\n    # (shift by 1 for T+2)"
    ),
    (
        "             Hypothesis: Cash from sales at T returns at T+2 before 13:00 (money settlement),",
        "             Hypothesis: Cash from sales at T returns at T+2 before\n                         13:00 (money settlement),"
    ),
    (
        "    - T+2 before 13:00: Money settlement (cash from sales available for reinvestment) - both money & securities",
        "    - T+2 before 13:00: Money settlement (cash from sales available\n      for reinvestment) - both money & securities"
    ),
    (
        "    # T+2 Settlement Logic: Cash from sales at T-1 becomes available at T+2 (shift by 1 for T+2)",
        "    # T+2 Settlement Logic: Cash from sales at T-1 becomes available at T+2\n    # (shift by 1 for T+2)"
    ),
    (
        "    ALPHA_VN_001: Post-Settlement Momentum - Momentum continuation after T+2 settlement.",
        "    ALPHA_VN_001: Post-Settlement Momentum - Momentum continuation\n    after T+2 settlement."
    ),
    (
        "    Formula: sign(price_momentum_5d) * zscore(T2_cash_recycling) * price_momentum_5d",
        "    Formula: sign(price_momentum_5d) * zscore(T2_cash_recycling) *\n             price_momentum_5d"
    ),
    (
        "    Hypothesis: After T+2 settlement (cash available), momentum continues if",
        "    Hypothesis: After T+2 settlement (cash available), momentum continues\n    if"
    ),
    (
        "    cash recycling is strong (high volume at T-2 creates buying power at T).",
        "    cash recycling is strong (high volume at T-2 creates buying\n    power at T)."
    ),
    (
        "    Native Rolling API: Uses .groupby().rolling().mean/std().reset_index(level=0, drop=True)",
        "    Native Rolling API: Uses .groupby().rolling().mean/std()\n                        with reset_index(level=0, drop=True)"
    ),
    (
        "    - T+2 before 13:00: Money settlement (cash from sales available for reinvestment)",
        "    - T+2 before 13:00: Money settlement (cash from sales available\n      for reinvestment)"
    ),
    (
        "    # T+2 Settlement Logic: Cash from sales at T-2 becomes available at T (shift by 2 for T+2)",
        "    # T+2 Settlement Logic: Cash from sales at T-2 becomes available at T\n    # (shift by 2 for T+2)"
    ),
    (
        "    # Strong T+2 cash recycling + positive momentum -> positive signal (continuation)",
        "    # Strong T+2 cash recycling + positive momentum -> positive signal\n    # (continuation)"
    ),
    (
        "    Formula: -1 * sign(distance_to_limit) * |distance_to_limit|^2 * zscore(volume)",
        "    Formula: -1 * sign(distance_to_limit) * |distance_to_limit|^2 *\n             zscore(volume)"
    ),
    (
        "    where distance_to_limit = (price_change - limit_threshold) / limit_threshold",
        "    where distance_to_limit = (price_change - limit_threshold) /\n                              limit_threshold"
    ),
    (
        "    Hypothesis: Stocks near limit bands (?7% for HOSE) experience mean reversion,",
        "    Hypothesis: Stocks near limit bands (±7% for HOSE) experience\n    mean reversion,"
    ),
    (
        "    # Near ceiling (+) with high volume -> negative signal (expect reversal down)",
        "    # Near ceiling (+) with high volume -> negative signal\n    # (expect reversal down)"
    ),
    (
        "    ALPHA_VN_003: Foreign Flow Divergence - Divergence between foreign flow and price momentum.",
        "    ALPHA_VN_003: Foreign Flow Divergence - Divergence between foreign\n    flow and price momentum."
    ),
    (
        "    Formula: -sign(foreign_net_flow) * price_momentum * |zscore(foreign_net_flow)|",
        "    Formula: -sign(foreign_net_flow) * price_momentum *\n             |zscore(foreign_net_flow)|"
    ),
    (
        "    Hypothesis: When foreign flow diverges from price momentum (foreign selling",
        "    Hypothesis: When foreign flow diverges from price momentum\n    (foreign selling"
    ),
    (
        "    during price rise, or foreign buying during price fall), it signals",
        "    during price rise, or foreign buying during price fall), it\n    signals"
    ),
    (
        "    # Divergence signal: -sign(foreign_flow) * price_momentum * |zscore(foreign_flow)|",
        "    # Divergence signal: -sign(foreign_flow) * price_momentum *\n    # |zscore(foreign_flow)|"
    ),
    (
        "    # When foreign selling (negative flow) during price rise (positive momentum) -> positive signal (reversal expected)",
        "    # When foreign selling (negative flow) during price rise (positive\n    # momentum) -> positive signal (reversal expected)"
    ),
    (
        "    Hypothesis: Strong intraday moves with high volume persist into next day.",
        "    Hypothesis: Strong intraday moves with high volume persist\n    into next day."
    ),
    (
        "    # Persistence signal: sign(intraday_return) * zscore(intraday_return) * volume_ratio",
        "    # Persistence signal: sign(intraday_return) * zscore(intraday_return)\n    # * volume_ratio"
    ),
    (
        "    ALPHA_VN_005: Liquidity-Adjusted Reversal - Mean reversion adjusted by volume liquidity.",
        "    ALPHA_VN_005: Liquidity-Adjusted Reversal - Mean reversion adjusted\n    by volume liquidity."
    ),
    (
        "    normalized_spread = (high - low) / close (proxy for bid-ask spread)",
        "    normalized_spread = (high - low) / close (proxy for bid-ask spread)"
    ),
    (
        "    Hypothesis: Mean reversion is stronger in liquid stocks (low spread),",
        "    Hypothesis: Mean reversion is stronger in liquid stocks (low spread),"
    ),
    (
        "    # Extreme returns (high |zscore|) in liquid stocks (high penalty) -> strong reversal signal",
        "    # Extreme returns (high |zscore|) in liquid stocks (high penalty)\n    # -> strong reversal signal"
    ),
    (
        "    - This captures the 1-day differential between money and securities settlement",
        "    - This captures the 1-day differential between money and\n      securities settlement"
    ),
    (
        "    Logic: Combines volume consistency and price stability (lower = better quality)",
        "    Logic: Combines volume consistency and price stability\n           (lower = better quality)"
    ),
    (
        "    Formula: (volume_std / volume_mean) * (close_std / close_mean) over period",
        "    Formula: (volume_std / volume_mean) * (close_std / close_mean)\n             over period"
    ),
]

for orig, repl in replacements:
    if orig not in content:
        print(f"Warning: original text not found: {orig[:40]}...")
    content = content.replace(orig, repl)

# Let's fix line 1768 which says:
# "    Logic: Combines volume consistency and price stability (lower = better quality)"
# Wait, this is same as L1768 and we already replaced it in the list!

# Let's also replace any other lingering rolling mean or std lines if any:
# E.g.:
# Native Rolling API: Uses .groupby().rolling().mean().reset_index(level=0, drop=True)
# Native Rolling API: Uses .groupby().rolling().std/mean().reset_index(level=0, drop=True)

# Replace all forms of:
# Native Rolling API: Uses .groupby().rolling().std/mean().reset_index(level=0, drop=True)
content = re.sub(
    r"Native Rolling API: Uses \.groupby\(\)\.rolling\(\)\.std/mean\(\)\.reset_index\(level=0, drop=True\)",
    "Native Rolling API: Uses .groupby().rolling().std/mean()\n                        with reset_index(level=0, drop=True)",
    content
)

# And:
content = re.sub(
    r"Native Rolling API: Uses \.groupby\(\)\.rolling\(\)\.mean\(\)\.reset_index\(level=0, drop=True\)",
    "Native Rolling API: Uses .groupby().rolling().mean()\n                        with reset_index(level=0, drop=True)",
    content
)

# Write back
with open("src/omega/quant/alpha/vn_specific.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
