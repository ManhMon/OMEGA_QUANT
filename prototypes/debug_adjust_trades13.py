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

# Exact Codex stress case
current = pd.DataFrame({
    'asset': ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'],
    'quantity': [73, 97, -43, -120, -8]
})

trades = pd.DataFrame({
    'asset': ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'],
    'quantity': [-250, -272, -172, -77, 120]
})

as_of = datetime(2026,5,15,1)

# Check current validity
is_valid_c, _ = solver.validate_constraints(current, prices, industry, as_of)
print(f"current valid: {is_valid_c}")

# Check full trade validity
tgt_full = current.set_index('asset')['quantity'].add(
    trades.set_index('asset')['quantity'], fill_value=0
).reset_index()
is_valid_full, _ = solver.validate_constraints(tgt_full, prices, industry, as_of)
print(f"full trade valid: {is_valid_full}")

# Find valid window
valid_s = []
for i in range(0, 101):
    s = i / 100
    st = trades.copy()
    st['quantity'] = st['quantity'] * s
    tgt = current.set_index('asset')['quantity'].add(
        st.set_index('asset')['quantity'], fill_value=0
    ).reset_index()
    ok, _ = solver.validate_constraints(tgt, prices, industry, as_of)
    if ok:
        valid_s.append(s)

print(f"valid window: {valid_s[0] if valid_s else None} - {valid_s[-1] if valid_s else None}, count={len(valid_s)}")

# Test adjust_trades
adj = solver.adjust_trades(trades, current, prices, industry, as_of)
print(f"\nadjusted: {adj.to_dict('records')}")

# Check if adjusted is valid
tgt_adj = current.set_index('asset')['quantity'].add(
    adj.set_index('asset')['quantity'], fill_value=0
).reset_index()
ok_adj, viol = solver.validate_constraints(tgt_adj, prices, industry, as_of)
print(f"adj valid: {ok_adj}")
if not ok_adj:
    print(f"violations: {[(v.constraint_type, v.asset, v.current_value, v.limit_value) for v in viol]}")
