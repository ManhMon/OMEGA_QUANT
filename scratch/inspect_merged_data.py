import pandas as pd
import numpy as np

# Load original market data to get the list of columns and dates
df_market = pd.read_parquet("data/market_2015_now.parquet")
print("Market data dates:", df_market['date'].min(), "to", df_market['date'].max())

# Let's inspect the saved components
df_la = pd.read_parquet("data/latent_alphas_components.parquet")
print("Latent alphas components dates:", df_la['date'].min(), "to", df_la['date'].max())

# Let's simulate the merge in backtest
df_merged = df_market.merge(df_la, on=["ticker", "date"], how="left")
df_merged['latent_ae_00'] = df_merged['latent_ae_00'].fillna(0.0)
non_zero_dates = df_merged[df_merged['latent_ae_00'] != 0.0]['date'].unique()
print(f"Number of non-zero dates in merged data: {len(non_zero_dates)}")
if len(non_zero_dates) > 0:
    print(f"Non-zero date range: {min(non_zero_dates)} to {max(non_zero_dates)}")
else:
    print("No non-zero dates!")
