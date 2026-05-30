"""Check 2025 data availability for holdout validation."""
import pandas as pd

df = pd.read_parquet("data/market_2015_now.parquet")
df["date"] = pd.to_datetime(df["date"])
y2025 = df[df["date"].dt.year == 2025]
print(f"2025 data: {len(y2025)} rows, {y2025['ticker'].nunique()} tickers, {y2025['date'].nunique()} trading days")
print(f"Date range: {y2025['date'].min().date()} to {y2025['date'].max().date()}")
