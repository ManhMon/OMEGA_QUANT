import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import pandas as pd
from omega.quant.validation.cpcv import CombinatorialPurgedKFold

# Simulated timestamps of length 2858
timestamps = pd.date_range('2015-01-01', periods=2858, freq='D')

cpcv = CombinatorialPurgedKFold(
    n_splits=10,
    n_test_splits=2,
    embargo_pct=0.01,
    label_horizon=5
)

folds = list(cpcv.split(timestamps))
print(f"Total folds generated: {len(folds)}")

for i, (train_idx, test_idx) in enumerate(folds):
    print(f"Fold {i+1:>2}: train_len={len(train_idx):>4}, test_len={len(test_idx):>4}, test_min={test_idx.min():>4}, test_max={test_idx.max():>4}")
