from scripts.run_weekly_evolution import load_market_data, prepare_features, walk_forward_split

print("PROBE:start", flush=True)
df = load_market_data(regime="all")
print(f"PROBE:loaded rows={len(df)}", flush=True)
df_prepared = prepare_features(df)
print(f"PROBE:prepared rows={len(df_prepared)}", flush=True)
train_df, val_df, test_df = walk_forward_split(df_prepared, horizon=5, regime="all")
print(f"PROBE:split train={len(train_df)} val={len(val_df)} test={len(test_df)}", flush=True)
