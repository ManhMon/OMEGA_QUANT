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

current = pd.DataFrame({'asset': ['AAPL'], 'quantity': [0]})
trades = pd.DataFrame({'asset': ['GOOGL'], 'quantity': [1000]})

# Test what scale works
print("Testing scales:")
for scale in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 1.0]:
    target = pd.DataFrame({
        'asset': ['GOOGL'],
        'quantity': [1000 * scale]
    })
    is_valid, violations = solver.validate_constraints(target, prices, industry_map, datetime(2026,5,15,1))
    print(f"scale={scale}: valid={is_valid}, violations={[(v.constraint_type, v.current_value) for v in violations]}")

# Now test adjust_trades
print("\nTesting adjust_trades:")
adjusted = solver.adjust_trades(trades, current, prices, industry_map, datetime(2026,5,15,1))
print(f"adjusted trades: {adjusted}")
target_adj = pd.DataFrame({'asset': ['GOOGL'], 'quantity': adjusted['quantity'].values})
is_valid_adj, viol_adj = solver.validate_constraints(target_adj, prices, industry_map, datetime(2026,5,15,1))
print(f"adjusted valid={is_valid_adj}, violations={[(v.constraint_type, v.current_value) for v in viol_adj]}")
