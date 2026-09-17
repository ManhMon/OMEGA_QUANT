import scripts.run_weekly_evolution as weekly

print("PROBE_NO_ALT:start", flush=True)
df = weekly.load_market_data(regime="all")
print(f"PROBE_NO_ALT:loaded rows={len(df)}", flush=True)
orig = getattr(weekly, "_generate_alternative_features")
weekly._generate_alternative_features = lambda df_in: df_in
try:
    df_prepared = weekly.prepare_features(df)
finally:
    weekly._generate_alternative_features = orig
print(f"PROBE_NO_ALT:prepared rows={len(df_prepared)}", flush=True)
available_alt = [c for c in weekly.ALTERNATIVE_FEATURE_COLUMNS if c in df_prepared.columns]
print(f"PROBE_NO_ALT:available_alt={len(available_alt)}", flush=True)
train_df, val_df, test_df = weekly.walk_forward_split(df_prepared, horizon=5, regime="all")
print(f"PROBE_NO_ALT:split train={len(train_df)} val={len(val_df)} test={len(test_df)}", flush=True)
