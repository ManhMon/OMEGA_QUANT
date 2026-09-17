import pandas as pd
df = pd.read_csv('data/phase35_results/hybrid_fold9_Hybrid_eq.csv')
print("Columns:", list(df.columns))
print("First 5 rows:")
print(df.head())
print("\nTurnover summary:")
if 'turnover' in df.columns:
    print(df['turnover'].describe())
elif 'delta_w' in df.columns:
    print(df['delta_w'].describe())
else:
    # Look for weight columns or weight difference columns
    w_cols = [c for c in df.columns if c.startswith('w_') or c.startswith('weight_')]
    print("Weight columns found:", len(w_cols))
    if w_cols:
        print(df[w_cols].head())
        # Calculate daily turnover
        diffs = df[w_cols].diff().abs().sum(axis=1)
        print("Calculated turnover describe:")
        print(diffs.describe())
        print("Total turnover calculated:", diffs.sum())
