from datetime import datetime
import pandas as pd
import sys
sys.path.insert(0, 'OMEGA_QUANT/packages/quant/src')
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

def check(scale):
    t = trades.copy()
    t['quantity'] = t['quantity'] * scale
    tgt = current.set_index('asset')['quantity'].add(
        t.set_index('asset')['quantity'], fill_value=0
    ).reset_index()
    ok, v = solver.validate_constraints(tgt, prices, industry, as_of)
    return ok, [x.constraint_type for x in v]

print(f"\nvalid@0.0:  {check(0.0)[0]}")
print(f"valid@0.26: {check(0.26)[0]}")
print(f"valid@0.27: {check(0.27)[0]}")
print(f"valid@1.0:  {check(1.0)[0]}")

# infer scale from first nonzero trade
scale = adj.loc[adj.asset == 'AAPL', 'quantity'].iloc[0] / trades.loc[trades.asset == 'AAPL', 'quantity'].iloc[0]
print(f"\nchosen_scale: {scale}")
print(f"chosen_valid: {check(scale)[0]}")
