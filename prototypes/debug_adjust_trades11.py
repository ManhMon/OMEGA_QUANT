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

# Check 0.26 and 0.27
for s in [0.26, 0.27]:
    scaled_trades = trades.copy()
    scaled_trades['quantity'] = trades['quantity'] * s
    
    target = current.set_index('asset')['quantity'].add(
        scaled_trades.set_index('asset')['quantity'], fill_value=0
    ).reset_index()
    target.columns = ['asset', 'quantity']
    
    is_valid, _ = solver.validate_constraints(target, prices, industry, as_of)
    print(f"s={s}: valid={is_valid}")
