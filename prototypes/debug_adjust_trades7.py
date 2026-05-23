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

def check(scale):
    t = trades.copy()
    t['quantity'] = t['quantity'] * scale
    tgt = current.set_index('asset')['quantity'].add(
        t.set_index('asset')['quantity'], fill_value=0
    ).reset_index()
    ok, v = solver.validate_constraints(tgt, prices, industry, as_of)
    return ok, v

for s in [0.25, 0.26, 0.27, 0.28, 0.29, 0.30]:
    ok, errs = check(s)
    print(f"scale={s:.2f}: valid={ok}")
    if not ok:
        for e in errs:
            print(f"  {e.constraint_type}: {e.current_value:.4f} (limit: {e.limit_value})")
