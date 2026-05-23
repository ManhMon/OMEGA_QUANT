import pandas as pd
from pathlib import Path

parquet_path = Path("data/market/parquet/VCB.parquet")
if parquet_path.exists():
    df = pd.read_parquet(parquet_path)
    print("=" * 70)
    print(f"VCB PARQUET DATA (2015 to Present)")
    print("=" * 70)
    print(f"Rows: {len(df)}")
    print(f"Columns: {df.columns.tolist()}")
    print(f"Start date: {df['time'].min()}")
    print(f"End date: {df['time'].max()}")
    print("\nHead:")
    print(df.head())
else:
    print("File not found.")
