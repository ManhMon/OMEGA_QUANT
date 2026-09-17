"""
VCI Full HSX/HNX Market Dataset - Comprehensive Validation
===========================================================
Role:   Data Engineer (Role 15, L2)
Gate:   VCI_FULL_HSX_HNX_2015_NOW_20260613
Date:   2026-06-13

Validates the downloaded parquet file against all requirements.

Compat: CANONICAL_VCI_UPDATER_LEGACY_TRACKING_20260613
  - Validation checks align with canonical schema and updater requirements.
  - price_scale="VND" accepted as compatible with VND_FULL values.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parents[1]
PARQUET_PATH = REPO / "data" / "market_vci_hsx_hnx_2015_now_20260613.parquet"
UNIVERSE_PATH = REPO / ".ly_state" / "session" / "vci_universe_hsx_hnx.json"
RESULTS_PATH = REPO / ".ly_state" / "session" / "vci_full_hsx_hnx_validation.json"

results = {}
all_pass = True

def check(name: str, condition: bool, detail: str = ""):
    global all_pass
    status = "PASS" if condition else "FAIL"
    if not condition:
        all_pass = False
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))
    results[name] = {"status": status, "detail": detail}
    return condition

print("=" * 70)
print("VALIDATION: VCI Full HSX/HNX Market Dataset")
print(f"File: {PARQUET_PATH}")
print("=" * 70)

# 1. File exists and loads
print("\n--- 1. File Exists and Loads ---")
file_exists = PARQUET_PATH.exists()
check("file_exists", file_exists, str(PARQUET_PATH))
if not file_exists:
    print("FATAL: File does not exist, cannot continue")
    sys.exit(1)

df = pd.read_parquet(PARQUET_PATH)
row_count = len(df)
col_count = df.shape[1]
check("file_loads", row_count > 0, f"{row_count} rows, {col_count} cols")
print(f"  Columns: {list(df.columns)}")
print(f"  Dtypes:\n{df.dtypes.to_string()}")

# 2. Schema compatibility
print("\n--- 2. Schema Compatibility ---")
expected_cols = [
    "ticker", "date", "exchange", "open", "high", "low", "close",
    "volume", "as_of", "available_at", "source", "price_scale",
    "adjusted", "rebuild_date",
]
present = [c for c in expected_cols if c in df.columns]
missing_cols = [c for c in expected_cols if c not in df.columns]
extra_cols = [c for c in df.columns if c not in expected_cols]
check("schema_all_expected_cols", len(missing_cols) == 0, f"Present: {len(present)}/{len(expected_cols)}")
if missing_cols:
    print(f"  MISSING columns: {missing_cols}")
if extra_cols:
    print(f"  Extra columns: {extra_cols}")
results["columns"] = list(df.columns)

# 3. Listing universe count and exchange split
print("\n--- 3. Universe Count and Exchange Split ---")
with open(UNIVERSE_PATH) as f:
    universe = json.load(f)
universe_total = universe["total"]
universe_hsx = universe["hsx_count"]
universe_hnx = universe["hnx_count"]

df_tickers = set(df["ticker"].unique())
universe_set = set(universe["hsx"]) | set(universe["hnx"])
coverage = len(df_tickers & universe_set)
missing_from_data = sorted(universe_set - df_tickers)
extra_in_data = sorted(df_tickers - universe_set)

check("universe_count_matches", len(df_tickers) == universe_total,
      f"Data tickers: {len(df_tickers)}, Universe: {universe_total}")
check("all_universe_tickers_in_data", len(missing_from_data) == 0,
      f"Missing: {len(missing_from_data)}" + (f" ({missing_from_data[:10]})" if missing_from_data else ""))
check("no_extra_tickers", len(extra_in_data) == 0,
      f"Extra: {len(extra_in_data)}")

exchange_counts = df["exchange"].value_counts()
print(f"  Exchange split:")
print(exchange_counts.to_string())

# 4. Fetched/empty/error counts
print("\n--- 4. Fetch Statistics ---")
stats_path = REPO / ".ly_state" / "session" / "vci_full_hsx_hnx_stats.json"
with open(stats_path) as f:
    download_stats = json.load(f)
fetch_stats = download_stats.get("stats", {})
print(f"  Fetched: {fetch_stats.get('fetched', 'N/A')}")
print(f"  Empty: {fetch_stats.get('empty', 'N/A')}")
print(f"  Errors: {fetch_stats.get('errors', 'N/A')}")
check("zero_errors", fetch_stats.get("errors", -1) == 0, f"errors={fetch_stats.get('errors')}")
check("zero_empty", fetch_stats.get("empty", -1) == 0, f"empty={fetch_stats.get('empty')}")
results["fetch_stats"] = fetch_stats

# 5. Exchange only HOSE/HNX
print("\n--- 5. Exchange Values ---")
exchanges = sorted(df["exchange"].unique().tolist())
print(f"  Exchanges: {exchanges}")
check("only_hose_hnx", set(exchanges).issubset({"HOSE", "HNX"}),
      f"Found: {exchanges}")

hose_count = int(exchange_counts.get("HOSE", 0))
hnx_count = int(exchange_counts.get("HNX", 0))
check("hose_has_data", hose_count > 0, f"HOSE rows: {hose_count}")
check("hnx_has_data", hnx_count > 0, f"HNX rows: {hnx_count}")

# 6. Row/ticker/date counts
print("\n--- 6. Row, Ticker, Date Counts ---")
ticker_count = df["ticker"].nunique()
date_count = df["date"].nunique()
print(f"  Total rows: {row_count}")
print(f"  Unique tickers: {ticker_count}")
print(f"  Unique dates: {date_count}")
check("row_count_positive", row_count > 0, f"{row_count}")
check("ticker_count_matches_universe", ticker_count == universe_total,
      f"{ticker_count} vs {universe_total}")
results["row_count"] = row_count
results["ticker_count"] = ticker_count
results["date_count"] = date_count

# 7. Date range
print("\n--- 7. Date Range ---")
date_min = df["date"].min()
date_max = df["date"].max()
today = pd.Timestamp.now().normalize()
print(f"  Min date: {date_min}")
print(f"  Max date: {date_max}")
print(f"  Today: {today}")
check("min_date_gte_2015", date_min >= pd.Timestamp("2015-01-01"),
      f"Min: {date_min} (must be >= 2015-01-01)")
pre_2015_count = int((df["date"] < pd.Timestamp("2015-01-01")).sum())
check("no_pre_2015_rows", pre_2015_count == 0,
      f"Pre-2015 rows: {pre_2015_count}")
check("max_date_current", date_max >= pd.Timestamp("2026-06-01"),
      f"Max: {date_max}")
check("no_future_dates", date_max <= today + pd.Timedelta(days=2),
      f"Max: {date_max} vs today: {today}")
results["date_min"] = str(date_min)
results["date_max"] = str(date_max)

# 8. Duplicate ticker-date
print("\n--- 8. Duplicate Ticker-Date ---")
dup_count = int(df.duplicated(subset=["ticker", "date"]).sum())
check("no_duplicate_ticker_date", dup_count == 0, f"Duplicates: {dup_count}")

# 9. Null OHLCV counts
print("\n--- 9. Null OHLCV Counts ---")
null_counts = {}
for col in ["open", "high", "low", "close", "volume"]:
    null_ct = int(df[col].isna().sum())
    pct = null_ct / row_count * 100
    print(f"  {col}: {null_ct} nulls ({pct:.4f}%)")
    null_counts[col] = null_ct
    check(f"no_null_{col}", null_ct == 0, f"{null_ct} nulls ({pct:.4f}%)")
results["null_ohlcv"] = null_counts

# 10. Non-positive OHLC and negative volume sanity
print("\n--- 10. Non-Positive OHLC & Negative Volume ---")
non_pos = {}
for col in ["open", "high", "low", "close"]:
    ct = int((df[col] <= 0).sum())
    pct = ct / row_count * 100
    print(f"  {col}: {ct} non-positive ({pct:.4f}%)")
    non_pos[col] = ct
    check(f"no_nonpositive_{col}", ct == 0, f"{ct} ({pct:.4f}%)")

vol_neg = int((df["volume"] < 0).sum())
vol_zero = int((df["volume"] == 0).sum())
print(f"  volume<0: {vol_neg}")
print(f"  volume=0: {vol_zero} ({vol_zero/row_count*100:.2f}%)")
check("no_negative_volume", vol_neg == 0, f"{vol_neg}")
non_pos["volume_negative"] = vol_neg
non_pos["volume_zero"] = vol_zero
results["non_positive"] = non_pos

# 11. OHLC invariant: high >= low, high >= open/close, low <= open/close
print("\n--- 11. OHLC Invariants ---")
invariant_violations = (
    (df["high"] < df["low"]).sum() +
    (df["high"] < df["open"]).sum() +
    (df["high"] < df["close"]).sum() +
    (df["low"] > df["open"]).sum() +
    (df["low"] > df["close"]).sum()
)
check("ohlc_invariants_hold", int(invariant_violations) == 0,
      f"Violations: {int(invariant_violations)}")

# 12. Price scale and source
print("\n--- 12. Price Scale and Source ---")
price_scales = df["price_scale"].unique().tolist()
sources = df["source"].unique().tolist()
adjusted_vals = df["adjusted"].unique().tolist()
print(f"  price_scale values: {price_scales}")
print(f"  source values: {sources}")
print(f"  adjusted values: {adjusted_vals}")
check("price_scale_vnd", set(price_scales) == {"VND"}, f"{price_scales}")
check("source_vnstock_vci", set(sources) == {"vnstock_vci"}, f"{sources}")
check("adjusted_backward", "backward_adjusted" in adjusted_vals, f"{adjusted_vals}")

# 13. VND_FULL price magnitude check
print("\n--- 13. Price Magnitude (VND_FULL) ---")
close_median = float(df["close"].median())
close_min = float(df["close"].min())
close_max = float(df["close"].max())
print(f"  Close median: {close_median:.0f}")
print(f"  Close min: {close_min:.0f}")
print(f"  Close max: {close_max:.0f}")
check("prices_in_vnd_range", close_median > 1000,
      f"Median close: {close_median:.0f} (should be > 1000 for VND_FULL)")

# 14. Coverage of VCI HSX/HNX symbols
print("\n--- 14. Coverage Analysis ---")
df_tickers_by_exchange = {}
for exch in ["HOSE", "HNX"]:
    exch_tickers = sorted(df[df["exchange"] == exch]["ticker"].unique().tolist())
    df_tickers_by_exchange[exch] = exch_tickers
    print(f"  {exch} tickers in data: {len(exch_tickers)}")

hose_in_data = set(df_tickers_by_exchange.get("HOSE", []))
hnx_in_data = set(df_tickers_by_exchange.get("HNX", []))
hsx_universe = set(universe["hsx"])
hnx_universe = set(universe["hnx"])

hose_missing = sorted(hsx_universe - hose_in_data)
hnx_missing = sorted(hnx_universe - hnx_in_data)
print(f"  HSX symbols missing from HOSE data: {len(hose_missing)}")
if hose_missing:
    print(f"    {hose_missing[:20]}")
print(f"  HNX symbols missing from HNX data: {len(hnx_missing)}")
if hnx_missing:
    print(f"    {hnx_missing[:20]}")
check("hose_full_coverage", len(hose_missing) == 0,
      f"Missing: {len(hose_missing)}")
check("hnx_full_coverage", len(hnx_missing) == 0,
      f"Missing: {len(hnx_missing)}")

# 15. Empty/error ticker listing
print("\n--- 15. Empty/Error Tickers ---")
empty_tickers = download_stats.get("empty_tickers", [])
error_list = download_stats.get("errors", [])
print(f"  Empty tickers: {len(empty_tickers)}")
print(f"  Error count: {len(error_list)}")
results["empty_tickers"] = empty_tickers
results["errors"] = error_list

# 16. Sample rows
print("\n--- 16. Sample Rows ---")
sample_cols = ["ticker", "date", "exchange", "open", "high", "low", "close", "volume"]
sample = df[sample_cols].head(5)
print(sample.to_string(index=False))
print()
sample_tail = df[sample_cols].tail(5)
print(sample_tail.to_string(index=False))
results["sample_head"] = sample.to_dict(orient="records")
results["sample_tail"] = sample_tail.to_dict(orient="records")

# 17. Date distribution by year
print("\n--- 17. Date Distribution by Year ---")
df["year"] = df["date"].dt.year
year_dist = df.groupby("year").size()
print(year_dist.to_string())
results["year_distribution"] = {str(k): int(v) for k, v in year_dist.items()}

# 18. File size
file_size_mb = PARQUET_PATH.stat().st_size / (1024 * 1024)
print(f"\n--- 18. File Size ---")
print(f"  File size: {file_size_mb:.1f} MB")
results["file_size_mb"] = round(file_size_mb, 1)

# Save results
results["timestamp"] = datetime.now().isoformat()
results["all_pass"] = all_pass
results["output_path"] = str(PARQUET_PATH)
RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(RESULTS_PATH, "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\n{'='*70}")
print(f"VALIDATION COMPLETE: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
print(f"Results saved to {RESULTS_PATH}")
print(f"{'='*70}")
