"""VCI Candidate Market Dataset - Comprehensive Validation Script."""
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parents[1]
candidate_path = REPO / "data" / "market_vci_candidate_20260612.parquet"
canonical_path = REPO / "data" / "market_2015_now.parquet"
results = {}

print("=" * 70)
print("VALIDATION: VCI Candidate Market Dataset")
print("=" * 70)

# 1. File exists and loads
print("\n--- 1. File Exists and Loads ---")
assert candidate_path.exists(), "FAIL: file not found"
cand = pd.read_parquet(candidate_path)
print(f"  Loaded: {cand.shape[0]} rows, {cand.shape[1]} columns")
print(f"  Columns: {list(cand.columns)}")
results["file_exists"] = True
results["row_count"] = len(cand)
results["col_count"] = cand.shape[1]
results["columns"] = list(cand.columns)

# 2. Schema compatibility
print("\n--- 2. Schema Compatibility ---")
canon = pd.read_parquet(canonical_path)
canon_cols = set(canon.columns)
cand_cols = set(cand.columns)
missing = canon_cols - cand_cols
extra = cand_cols - canon_cols
print(f"  Canonical columns: {sorted(canon_cols)}")
print(f"  Candidate columns: {sorted(cand_cols)}")
if missing:
    print(f"  MISSING from candidate: {sorted(missing)}")
else:
    print("  All canonical columns present in candidate")
if extra:
    print(f"  Extra in candidate: {sorted(extra)}")
else:
    print("  No extra columns in candidate")
results["schema_compatible"] = len(missing) == 0
results["missing_cols"] = sorted(missing) if missing else []
results["extra_cols"] = sorted(extra) if extra else []

# 3. Exchanges only HOSE/HNX
print("\n--- 3. Exchange Filter ---")
exchanges = cand["exchange"].unique()
print(f"  Exchanges found: {sorted(exchanges)}")
only_hose_hnx = set(exchanges).issubset({"HOSE", "HNX"})
print(f"  Only HOSE/HNX: {only_hose_hnx}")
print(f"  Exchange counts:")
print(cand["exchange"].value_counts().to_string())
results["exchanges"] = sorted(exchanges.tolist())
results["only_hose_hnx"] = only_hose_hnx

# 4. Date range
print("\n--- 4. Date Range ---")
cand_min = cand["date"].min()
cand_max = cand["date"].max()
canon_min = canon["date"].min()
canon_max = canon["date"].max()
print(f"  Canonical: {canon_min} to {canon_max}")
print(f"  Candidate: {cand_min} to {cand_max}")
max_match = cand_max == canon_max
min_ok = cand_min <= canon_min
print(f"  Candidate max matches canonical max: {max_match}")
print(f"  Candidate min <= canonical min: {min_ok}")
results["date_range_cand"] = f"{cand_min} to {cand_max}"
results["date_range_canon"] = f"{canon_min} to {canon_max}"
results["max_date_match"] = bool(max_match)
results["min_date_covers"] = bool(min_ok)

# 5. Duplicate ticker-date
print("\n--- 5. Duplicate Ticker-Date ---")
dup_count = int(cand.duplicated(subset=["ticker", "date"]).sum())
print(f"  Duplicate (ticker,date) pairs: {dup_count}")
results["duplicate_count"] = dup_count

# 6. Null OHLCV counts
print("\n--- 6. Null OHLCV Counts ---")
null_counts = {}
for col in ["open", "high", "low", "close", "volume"]:
    null_ct = int(cand[col].isna().sum())
    pct = null_ct / len(cand) * 100
    print(f"  {col}: {null_ct} nulls ({pct:.4f}%)")
    null_counts[col] = null_ct
results["null_ohlcv"] = null_counts

# 7. Non-positive OHLCV sanity
print("\n--- 7. Non-Positive OHLCV Sanity ---")
non_pos = {}
for col in ["open", "high", "low", "close"]:
    ct = int((cand[col] <= 0).sum())
    pct = ct / len(cand) * 100
    print(f"  {col}: {ct} non-positive ({pct:.4f}%)")
    non_pos[col] = ct
vol_zero = int((cand["volume"] == 0).sum())
vol_neg = int((cand["volume"] < 0).sum())
print(f"  volume=0: {vol_zero} ({vol_zero/len(cand)*100:.2f}%)")
print(f"  volume<0: {vol_neg}")
non_pos["volume_zero"] = vol_zero
non_pos["volume_negative"] = vol_neg
results["non_positive"] = non_pos

# 8. Row count and ticker count
print("\n--- 8. Row Count and Ticker Count ---")
cand_tickers_n = cand["ticker"].nunique()
canon_tickers_n = canon["ticker"].nunique()
print(f"  Candidate rows: {len(cand)}")
print(f"  Candidate tickers: {cand_tickers_n}")
print(f"  Canonical rows: {len(canon)}")
print(f"  Canonical tickers: {canon_tickers_n}")
results["cand_tickers"] = cand_tickers_n
results["canon_tickers"] = canon_tickers_n

# 9. Sample tickers from HOSE/HNX
print("\n--- 9. Sample Tickers ---")
hose_samples = sorted(cand[cand["exchange"] == "HOSE"]["ticker"].unique()[:10].tolist())
hnx_samples = sorted(cand[cand["exchange"] == "HNX"]["ticker"].unique()[:10].tolist())
print(f"  HOSE samples: {hose_samples}")
print(f"  HNX samples: {hnx_samples}")
results["hose_samples"] = hose_samples
results["hnx_samples"] = hnx_samples

# 10. Price scale check
print("\n--- 10. Price Scale (VND_FULL) ---")
close_median = float(cand["close"].median())
close_min = float(cand["close"].min())
close_max = float(cand["close"].max())
print(f"  Close median: {close_median:.0f}")
print(f"  Close range: {close_min:.0f} to {close_max:.0f}")
print(f"  Price scale values: {cand['price_scale'].unique().tolist()}")
print(f"  Source values: {cand['source'].unique().tolist()}")
results["close_median"] = close_median
results["price_scale_values"] = cand["price_scale"].unique().tolist()
results["source_values"] = cand["source"].unique().tolist()

# 11. Dtypes comparison
print("\n--- 11. Dtype Comparison ---")
dtype_diffs = []
for col in sorted(canon_cols & cand_cols):
    c_dtype = str(canon[col].dtype)
    v_dtype = str(cand[col].dtype)
    match = "OK" if c_dtype == v_dtype else "DIFF"
    print(f"  {col}: canonical={c_dtype} candidate={v_dtype} [{match}]")
    if match == "DIFF":
        dtype_diffs.append({"col": col, "canonical": c_dtype, "candidate": v_dtype})
results["dtype_diffs"] = dtype_diffs

# 12. Overlap analysis
print("\n--- 12. Overlap with Canonical Date Range ---")
in_range = cand[(cand["date"] >= canon_min) & (cand["date"] <= canon_max)]
print(f"  Candidate rows in canonical range: {len(in_range)}")
print(f"  Canonical rows: {len(canon)}")

canon_tickers_set = set(canon["ticker"].unique())
cand_tickers_set = set(cand["ticker"].unique())
only_canon = sorted(canon_tickers_set - cand_tickers_set)
only_cand = sorted(cand_tickers_set - canon_tickers_set)
print(f"  Tickers in canonical: {len(canon_tickers_set)}")
print(f"  Tickers in candidate: {len(cand_tickers_set)}")
print(f"  Tickers in both: {len(canon_tickers_set & cand_tickers_set)}")
print(f"  Tickers only in canonical ({len(only_canon)}): {only_canon}")
print(f"  Tickers only in candidate ({len(only_cand)}): {only_cand[:10]}")
results["tickers_only_canonical"] = only_canon
results["tickers_only_candidate"] = only_cand[:20]
results["rows_in_canonical_range"] = len(in_range)

# 13. Canonical not overwritten
print("\n--- 13. Canonical Integrity ---")
canon_check = pd.read_parquet(canonical_path)
canon_intact = len(canon_check) == 1687749
print(f"  Canonical still has 1687749 rows: {canon_intact}")
results["canonical_intact"] = canon_intact
del canon_check, in_range

# Save validation results
results["timestamp"] = datetime.now().isoformat()
results["output_path"] = str(candidate_path)
val_path = REPO / ".ly_state" / "session" / "vci_candidate_validation.json"
val_path.parent.mkdir(parents=True, exist_ok=True)
with open(val_path, "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nValidation results saved to {val_path}")

print("\n" + "=" * 70)
print("VALIDATION COMPLETE")
print("=" * 70)
