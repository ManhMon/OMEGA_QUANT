from vnstock import Reference
ref = Reference()
m = ref.market()
print(f"Calling market.symbol()...")
try:
    df = m.symbol()
    print(f"Success! Got {len(df)} symbols.")
    print(df.head())
    print(f"Columns: {df.columns.tolist()}")
    
    # Filter for HOSE and HNX
    if 'exchange' in df.columns:
        hose_hnx = df[df['exchange'].isin(['HOSE', 'HNX'])]
        print(f"HOSE + HNX: {len(hose_hnx)} symbols")
        hose_hnx['symbol'].to_csv('all_symbols.txt', index=False, header=False)
except Exception as e:
    print(f"Error: {e}")
