import glob
import json
import os
import re
import numpy as np
import pandas as pd

files = glob.glob('data/phase35_results/hybrid_fold*_Hybrid.json')
data = []
for f in files:
    bn = os.path.basename(f)
    match = re.search(r'hybrid_fold(\d+)_Hybrid\.json', bn)
    if not match:
        continue
    fid = int(match.group(1))
    with open(f) as fh:
        d = json.load(fh)
    data.append((fid, d))

data.sort(key=lambda x: x[0])
tcs = []
tos = []
n_days_list = []
for fid, d in data:
    cb = d.get("cost_breakdown", {})
    tcs.append(cb.get("total_cost", 0.0) * 100)
    tos.append(cb.get("total_turnover", 0.0))
    n_days_list.append(d.get("n_days", 1))

tcs = np.array(tcs)
tos = np.array(tos)
n_days_list = np.array(n_days_list)

print(f"Mean total_cost: {np.mean(tcs):.2f}%")
print(f"Median total_cost: {np.median(tcs):.2f}%")
print(f"Max total_cost: {np.max(tcs):.2f}%")
print(f"Min total_cost: {np.min(tcs):.2f}%")

high_mask = tcs > 100.0
print(f"\nFolds with cost > 100% ({np.sum(high_mask)} folds):")
for i, fid in enumerate(np.where(high_mask)[0] + 1):
    idx = fid - 1
    # Find the date range of this fold by checking its CSV or pipeline_state if available
    eq_csv = f'data/phase35_results/hybrid_fold{fid}_Hybrid_eq.csv'
    date_info = ""
    if os.path.exists(eq_csv):
        # The CSV might not have dates, but let's check its length
        eq_df = pd.read_csv(eq_csv)
        date_info = f"({len(eq_df)} bars)"
    
    print(f"  Fold {fid:>2}: cost={tcs[idx]:.2f}%, turnover={tos[idx]:.2f}, days={n_days_list[idx]} {date_info}")

print(f"\nMean of normal folds (cost <= 100%): {np.mean(tcs[~high_mask]):.2f}%")
print(f"Median of normal folds (cost <= 100%): {np.median(tcs[~high_mask]):.2f}%")
