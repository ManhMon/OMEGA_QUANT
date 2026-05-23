from datetime import datetime
import pandas as pd
import sys
sys.path.insert(0, 'OMEGA_QUANT/packages/quant/src')

# Patch to add debug output
import omega.quant.constraint_solver as cs

original_adjust = cs.ConstraintSolver.adjust_trades

def debug_adjust(self, trades, current, prices, industry_map, as_of):
    print(f"DEBUG: is_current_valid check...")
    result = original_adjust(self, trades, current, prices, industry_map, as_of)
    print(f"DEBUG: result = {result}")
    return result

cs.ConstraintSolver.adjust_trades = debug_adjust

from omega.quant.constraint_solver import ConstraintConfig, ConstraintSolver

config = ConstraintConfig(100000.0, 3.0, 0.5, 0.4, datetime(2026,5,15), datetime(2026,5,15,0,0,1))
solver = ConstraintSolver(config)

prices = pd.DataFrame({
    'asset': ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'],
    'price': [150.0, 2800.0, 300.0, 200.0, 3200.0],
    'as_of': [datetime(2026,5,15)] * 5
})

industry = {
    'AAPL': 'Technology',
    'GOOGL': 'Technology',
    'MSFT': 'Technology',
    'TSLA': 'Automotive',
    'AMZN': 'Retail'
}

current = pd.DataFrame({
    'asset': ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'],
    'quantity': [73, 97, -43, -120, -8]
})

trades = pd.DataFrame({
    'asset': ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'],
    'quantity': [-250, -272, -172, -77, 120]
})

as_of = datetime(2026,5,15,1)

adj = solver.adjust_trades(trades, current, prices, industry, as_of)
print('adjusted:')
print(adj)
