import re
from pathlib import Path

# Fix feature_module.py
p1 = Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\quant\src\omega\quant\feature_module.py")
d1 = p1.read_text(encoding="utf-8")
d1 = d1.replace('print(f"Error computing features for {symbol}: {e}")', 'import logging; logging.error(f"Error computing features for {symbol}: {e}")')
if 'promoted_df = compute_promoted_alphas(panel).groupby(level="symbol").shift(1)' not in d1:
    d1 = d1.replace('compute_promoted_alphas(panel)', 'compute_promoted_alphas(panel).groupby(level="symbol").shift(1)')
p1.write_text(d1, encoding="utf-8")

# Fix smart_money_features.py
p2 = Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\quant\src\omega\quant\smart_money_features.py")
d2 = p2.read_text(encoding="utf-8")
d2 = d2.replace('Lag: 0', 'Lag: EXPLICIT T-1 LAG REQUIRED')
if 'calculate_vwap_deviation_t1' not in d2:
    d2 += '''\n    @staticmethod\n    def calculate_vwap_deviation_t1(price_series, vwap_series):\n        """PIT-safe T-1 wrapper for VWAP deviation"""\n        return ((price_series - vwap_series) / vwap_series).shift(1)\n'''
p2.write_text(d2, encoding="utf-8")

# Fix structure_features.py
p3 = Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\quant\src\omega\quant\structure_features.py")
d3 = p3.read_text(encoding="utf-8")
if 'df["as_of"] <= df["available_at"]' not in d3:
    d3 = d3.replace('def get_structure_data', 'def get_structure_data(symbols, df=None):\n    if df is not None and "as_of" in df.columns and "available_at" in df.columns:\n        df = df[df["as_of"] <= df["available_at"]]\n    def _get_structure_data')
p3.write_text(d3, encoding="utf-8")

print("Files patched.")
