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

# Current is invalid (exceeds notional limit)
current = pd.DataFrame({'asset': ['GOOGL'], 'quantity': [1000]})
trades = pd.DataFrame({'asset': ['GOOGL'], 'quantity': [-990]})

as_of = datetime(2026, 5, 15, 1, 0, 0)

# Check current validity
is_valid_c, _ = solver.validate_constraints(current, prices, industry_map, as_of)
print(f"Current valid: {is_valid_c}")

# Check what scale works
for scale in [0.0, 0.1, 0.2, 0.5, 0.8, 0.9, 1.0]:
    target = pd.DataFrame({
        'asset': ['GOOGL'],
        'quantity': [1000 + (-990) * scale]
    })
    is_valid, violations = solver.validate_constraints(target, prices, industry_map, as_of)
    print(f"scale={scale}: target_qty={target['quantity'].values[0]}, valid={is_valid}")

# Test adjust_trades
adjusted = solver.adjust_trades(trades, current, prices, industry_map, as_of)
print(f"\nAdjusted: {adjusted}")
