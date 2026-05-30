"""Create 2025 universe file in correct format."""
import json
import pandas as pd

df = pd.read_parquet("data/market_2015_now.parquet")
df["date"] = pd.to_datetime(df["date"])
y2024 = df[df["date"].dt.year == 2024].copy()
adv = y2024.groupby("ticker", group_keys=False).apply(
    lambda g: (g["volume"].astype(float) * g["close"].astype(float)).mean()
)
top50 = adv.nlargest(50)
universe_list = [{"ticker": t, "score": float(s)} for t, s in top50.items()]
out = {
    "date": "2025-01-02",
    "method": "adv_top50_from_2024",
    "n_eligible": int(len(adv)),
    "n_selected": 50,
    "filter": {"min_adv_vnd": 0, "min_price": 0, "min_listing_days": 0, "quality_lookback_days": 365},
    "universe": universe_list,
}
with open(".ly_state/session/universe/universe_2025-01-02.json", "w") as f:
    json.dump(out, f, indent=2)
print(f"Saved 2025 universe: {len(universe_list)} tickers")
print(f"Top 5: {[u['ticker'] for u in universe_list[:5]]}")
