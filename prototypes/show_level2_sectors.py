import pandas as pd

df = pd.read_csv('OMEGA_QUANT/data/sector_mapping_vci.csv', encoding='utf-8-sig')

print('=== SECTOR LEVEL 2 (INTERMEDIATE LEVEL) ===\n')

# Get level 2 sectors (second occurrence per symbol)
level2_sectors = []
for symbol in df['symbol'].unique():
    symbol_sectors = df[df['symbol'] == symbol]['sector'].tolist()
    if len(symbol_sectors) >= 2:
        level2_sectors.append(symbol_sectors[1])
    elif len(symbol_sectors) == 1:
        level2_sectors.append(symbol_sectors[0])

level2_df = pd.DataFrame({'sector': level2_sectors})
level2_counts = level2_df['sector'].value_counts().sort_values(ascending=False)

print(f'Total unique Level 2 sectors: {len(level2_counts)}')
print(f'\nTop 40 Level 2 sectors:')
print('=' * 60)

for i, (sector, count) in enumerate(level2_counts.head(40).items(), 1):
    pct = 100 * count / len(level2_df)
    print(f'{i:2d}. {sector:45s} ({count:4d} symbols, {pct:5.1f}%)')
