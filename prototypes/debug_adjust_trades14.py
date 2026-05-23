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

# Second Codex stress case
current = pd.DataFrame({'asset': ['GOOGL', 'TSLA'], 'quantity': [100, -400]})
trades = pd.DataFrame({'asset': ['GOOGL', 'TSLA'], 'quantity': [-71, 537]})

as_of = datetime(2026,5,15,1)

# Check current validity
is_valid_c, _ = solver.validate_constraints(current, prices, industry, as_of)
print(f"current valid: {is_valid_c}")

# Find valid window
valid_s = []
for i in range(0, 1001):
    s = i / 1000
    st = trades.copy()
    st['quantity'] = st['quantity'] * s
    tgt = current.set_index('asset')['quantity'].add(
        st.set_index('asset')['quantity'], fill_value=0
    ).reset_index()
    ok, _ = solver.validate_constraints(tgt, prices, industry, as_of)
    if ok:
        valid_s.append(s)

if valid_s:
    print(f"valid window: {valid_s[0]} - {valid_s[-1]}, count={len(valid_s)}")
else:
    print("valid window: None")

# Test adjust_trades
adj = solver.adjust_trades(trades, current, prices, industry, as_of)
print(f"\nadjusted: {adj.to_dict('records')}")

# Check if adjusted is valid
tgt_adj = current.set_index('asset')['quantity'].add(
    adj.set_index('asset')['quantity'], fill_value=0
).reset_index()
ok_adj, viol = solver.validate_constraints(tgt_adj, prices, industry, as_of)
print(f"adj valid: {ok_adj}")
