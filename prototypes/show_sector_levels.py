import pandas as pd

df = pd.read_csv('OMEGA_QUANT/data/sector_mapping_vci.csv', encoding='utf-8-sig')

print('=== SECTOR LEVELS ANALYSIS ===\n')

# Get unique sectors and count occurrences
sector_counts = df['sector'].value_counts().sort_values(ascending=False)

print(f'Total unique sectors: {len(sector_counts)}')
print(f'\nTop 30 sectors by frequency:')
print('=' * 60)

for i, (sector, count) in enumerate(sector_counts.head(30).items(), 1):
    print(f'{i:2d}. {sector:45s} ({count:4d} symbols)')

print('\n' + '=' * 60)
print(f'\nBottom 10 sectors (least frequent):')
print('=' * 60)

for i, (sector, count) in enumerate(sector_counts.tail(10).items(), 1):
    print(f'{i:2d}. {sector:45s} ({count:4d} symbols)')
