import pandas as pd
import numpy as np

# Load latent alpha components parquet
parquet_path = "data/latent_alphas_components.parquet"
df_la = pd.read_parquet(parquet_path)
print("--- Latent Alphas Parquet Info ---")
print(f"Shape: {df_la.shape}")
print(f"Columns: {df_la.columns.tolist()}")
print(f"Date range: {df_la['date'].min()} to {df_la['date'].max()}")
print(f"Unique tickers: {df_la['ticker'].nunique()}")
print(f"Non-zero counts for latent_ae_00: {np.count_nonzero(df_la['latent_ae_00'])}")
print(f"First 5 rows:")
print(df_la.head())

# Let's check a few rows of latent columns
for col in df_la.columns:
    if col.startswith("latent_"):
        print(f"{col}: mean={df_la[col].mean():.6f}, std={df_la[col].std():.6f}, unique={df_la[col].nunique()}")
