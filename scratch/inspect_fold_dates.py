import sys
sys.path.extend([".", "scripts", "src"])
import pandas as pd
import numpy as np
from phase35_data_loader import Phase35DataLoader

# Initialize loader
loader = Phase35DataLoader()
df = loader.load_and_prepare(
    start_date="2015-01-05",
    end_date="2026-06-12",
    top_n_symbols=30,
)

# Merge pre-computed latent alpha components
df_la = pd.read_parquet("data/latent_alphas_components.parquet")
df = df.merge(df_la[["ticker", "date", "latent_ae_00", "latent_ae_01", "latent_ae_11"]], on=["ticker", "date"], how="left")
df[["latent_ae_00", "latent_ae_01", "latent_ae_11"]] = df[["latent_ae_00", "latent_ae_01", "latent_ae_11"]].fillna(0.0)

# Create splits
splits = loader.create_walk_forward_splits(df, n_folds=8, train_years=3, test_years=1)
print(f"Created {len(splits)} splits.")

for idx, (train_df, test_df) in enumerate(splits):
    fold_id = idx + 1
    # Check date range of train_df
    train_dates = sorted(train_df['date'].unique())
    print(f"Fold {fold_id} train dates: {train_dates[0]} to {train_dates[-1]} ({len(train_dates)} dates)")
    # Check count of non-zero rows in train_df for latent_ae_00
    non_zero = np.count_nonzero(train_df['latent_ae_00'])
    print(f"  Non-zero rows for latent_ae_00 in train: {non_zero} out of {len(train_df)}")
    
    test_dates = sorted(test_df['date'].unique())
    print(f"Fold {fold_id} test dates: {test_dates[0]} to {test_dates[-1]} ({len(test_dates)} dates)")
    non_zero_test = np.count_nonzero(test_df['latent_ae_00'])
    print(f"  Non-zero rows for latent_ae_00 in test: {non_zero_test} out of {len(test_df)}")
