import pandas as pd
from pathlib import Path

# Load raw mapping
df = pd.read_csv('OMEGA_QUANT/data/sector_mapping_vci.csv', encoding='utf-8-sig')

# Extract Level 2 for each symbol
level2_data = []
for symbol in df['symbol'].unique():
    symbol_sectors = df[df['symbol'] == symbol]['sector'].tolist()
    if len(symbol_sectors) >= 2:
        sector = symbol_sectors[1]
    else:
        sector = symbol_sectors[0]
    level2_data.append({'symbol': symbol, 'sector': sector})

level2_df = pd.DataFrame(level2_data)

# Save to canonical path
output_path = Path('OMEGA_QUANT/data/sector_mapping_level2.csv')
level2_df.to_csv(output_path, index=False, encoding='utf-8-sig')
print(f"Created Level 2 mapping: {len(level2_df)} symbols, {level2_df['sector'].nunique()} sectors.")
