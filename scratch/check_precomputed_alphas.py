import pandas as pd
import os

path = "data/precomputed_alpha_features.parquet"
df = pd.read_parquet(path)
alpha_cols = [c for c in df.columns if c.startswith("alpha_")]

print(f"Total alpha columns: {len(alpha_cols)}")

# Phân loại alpha theo tiền tố
categories = {
    "HR": [c for c in alpha_cols if c.startswith("alpha_hr_")],
    "GP": [c for c in alpha_cols if c.startswith("alpha_gp_")],
    "LLM": [c for c in alpha_cols if c.startswith("alpha_llm_")],
    "VN": [c for c in alpha_cols if any(c.startswith(p) for p in ["alpha_vn_", "alpha_stock_", "alpha_macro_"])],
    "Others": []
}

for c in alpha_cols:
    matched = False
    for cat, prefixes in [("HR", ["alpha_hr_"]), ("GP", ["alpha_gp_"]), ("LLM", ["alpha_llm_"]), ("VN", ["alpha_vn_", "alpha_stock_", "alpha_macro_"])]:
        if any(c.startswith(p) for p in prefixes):
            matched = True
            break
    if not matched:
        categories["Others"].append(c)

for cat, cols in categories.items():
    print(f"Category {cat}: {len(cols)} columns")
    if cols:
        print(f"  First 5: {cols[:5]}")

# Kiểm tra xem có alpha nào có giá trị không phải hằng số không
print("\nChecking for non-constant alphas in Others (first 10):")
non_const_count = 0
for c in alpha_cols[:20]:
    std = df[c].std()
    print(f"  {c}: std={std:.4f}, mean={df[c].mean():.4f}, min={df[c].min():.4f}, max={df[c].max():.4f}")
