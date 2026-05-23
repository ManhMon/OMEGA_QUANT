from datetime import datetime
import pandas as pd
import sys
sys.path.insert(0, 'OMEGA_QUANT/packages/quant/src')
from omega.quant.constraint_solver import ConstraintConfig, ConstraintSolver

cfg = ConstraintConfig(
    max_notional_per_asset=100000.0,
    max_leverage=3.0,
    max_industry_concentration=0.5,
    max_asset_concentration=0.4,
    as_of=datetime(2026,5,15),
    available_at=datetime(2026,5,15,0,0,1),
)
solver = ConstraintSolver(cfg)

prices = pd.DataFrame({
    'asset': ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'],
    'price': [150.0, 2800.0, 300.0, 200.0, 3200.0],
    'as_of': [datetime(2026,5,15)] * 5
})

industry_map = {
    'AAPL': 'Technology',
    'GOOGL': 'Technology',
    'MSFT': 'Technology',
    'TSLA': 'Automotive',
    'AMZN': 'Retail'
}

# Current: AAPL=100, TSLA=100, MSFT=100
# Notional: 15k + 20k + 30k = 65k
# Gross: 65k, Net: 65k, Leverage: 1.0
# Concentrations: AAPL=23%, TSLA=31%, MSFT=46% - MSFT violates 40%!
# So current is already invalid!

current = pd.DataFrame({'asset': ['AAPL', 'TSLA', 'MSFT'], 'quantity': [100, 100, 100]})
is_valid, violations = solver.validate_constraints(current, prices, industry_map, datetime(2026,5,15,1))
print(f"Current portfolio valid={is_valid}")
for v in violations:
    print(f"  {v.constraint_type}: {v.current_value:.4f} (limit: {v.limit_value})")

# Let's use a valid current portfolio
current_valid = pd.DataFrame({'asset': ['AAPL', 'TSLA'], 'quantity': [100, 100]})
is_valid_v, viol_v = solver.validate_constraints(current_valid, prices, industry_map, datetime(2026,5,15,1))
print(f"\nValid current portfolio valid={is_valid_v}")
for v in viol_v:
    print(f"  {v.constraint_type}: {v.current_value:.4f} (limit: {v.limit_value})")

# Now test adjust_trades with valid current
trades = pd.DataFrame({'asset': ['GOOGL'], 'quantity': [1000]})
adjusted = solver.adjust_trades(trades, current_valid, prices, industry_map, datetime(2026,5,15,1))
print(f"\nAdjusted trades: {adjusted}")

# Check target
target = pd.concat([current_valid, adjusted]).groupby('asset')['quantity'].sum().reset_index()
print(f"Target positions: {target}")
is_valid_t, viol_t = solver.validate_constraints(target, prices, industry_map, datetime(2026,5,15,1))
print(f"Target valid={is_valid_t}")
for v in viol_t:
    print(f"  {v.constraint_type}: {v.current_value:.4f} (limit: {v.limit_value})")
