import pandas as pd

df = pd.read_csv('OMEGA_QUANT/data/sector_mapping_vci.csv', encoding='utf-8-sig')

print('=== SECTOR LEVEL 3 (DETAILED LEVEL) - FULL LIST ===\n')

# Get level 3 sectors (third occurrence per symbol)
level3_sectors = []
for symbol in df['symbol'].unique():
    symbol_sectors = df[df['symbol'] == symbol]['sector'].tolist()
    if len(symbol_sectors) >= 3:
        level3_sectors.append(symbol_sectors[2])
    elif len(symbol_sectors) >= 2:
        level3_sectors.append(symbol_sectors[1])
    elif len(symbol_sectors) == 1:
        level3_sectors.append(symbol_sectors[0])

level3_df = pd.DataFrame({'sector': level3_sectors})
level3_counts = level3_df['sector'].value_counts().sort_values(ascending=False)

print(f'Total unique Level 3 sectors: {len(level3_counts)}')
print(f'Total symbols: {len(level3_df)}')
print(f'\nAll Level 3 sectors (sorted by frequency):')
print('=' * 70)

for i, (sector, count) in enumerate(level3_counts.items(), 1):
    pct = 100 * count / len(level3_df)
    print(f'{i:3d}. {sector:50s} ({count:4d} symbols, {pct:5.1f}%)')

print('\n' + '=' * 70)
print(f'Summary: {len(level3_counts)} unique Level 3 sectors')
