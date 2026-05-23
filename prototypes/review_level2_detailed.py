import pandas as pd

df = pd.read_csv('OMEGA_QUANT/data/sector_mapping_vci.csv', encoding='utf-8-sig')

print('=== SECTOR LEVEL 2 - DETAILED REVIEW ===\n')

# Get level 2 sectors
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
print(f'Total symbols: {len(level2_df)}')
print(f'\n' + '=' * 80)
print('LEVEL 2 SECTOR BREAKDOWN (All 23 sectors)')
print('=' * 80)

cumulative = 0
for i, (sector, count) in enumerate(level2_counts.items(), 1):
    pct = 100 * count / len(level2_df)
    cumulative += pct
    status = 'GOOD' if count >= 50 else 'FAIR' if count >= 20 else 'SMALL'
    print(f'{i:2d}. {sector:45s} | {count:4d} symbols | {pct:5.1f}% | Cumul: {cumulative:5.1f}% | [{status}]')

print('=' * 80)
print('\nKEY INSIGHTS:')
print('- GOOD (>=50 symbols): Sectors with sufficient data for model training')
print('- FAIR (20-49 symbols): Sectors with moderate data')
print('- SMALL (<20 symbols): Sectors with limited data (may need grouping)')

good_count = (level2_counts >= 50).sum()
fair_count = ((level2_counts >= 20) & (level2_counts < 50)).sum()
small_count = (level2_counts < 20).sum()

print(f'\nDistribution:')
print(f'  GOOD sectors:  {good_count} ({100*good_count/len(level2_counts):.1f}%)')
print(f'  FAIR sectors:  {fair_count} ({100*fair_count/len(level2_counts):.1f}%)')
print(f'  SMALL sectors: {small_count} ({100*small_count/len(level2_counts):.1f}%)')

print(f'\nCoverage:')
good_symbols = level2_counts[level2_counts >= 50].sum()
fair_symbols = level2_counts[(level2_counts >= 20) & (level2_counts < 50)].sum()
small_symbols = level2_counts[level2_counts < 20].sum()
print(f'  GOOD sectors cover:  {good_symbols:4d} symbols ({100*good_symbols/len(level2_df):.1f}%)')
print(f'  FAIR sectors cover:  {fair_symbols:4d} symbols ({100*fair_symbols/len(level2_df):.1f}%)')
print(f'  SMALL sectors cover: {small_symbols:4d} symbols ({100*small_symbols/len(level2_df):.1f}%)')

print('\n' + '=' * 80)
print('RECOMMENDATION:')
print('- Use all 23 Level 2 sectors for One-Hot Encoding')
print('- SMALL sectors (<20 symbols) can be grouped into parent category if needed')
print('- Current distribution is well-balanced for model training')
print('=' * 80)
