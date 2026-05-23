import pandas as pd

df = pd.read_csv('OMEGA_QUANT/data/sector_mapping_vci.csv', encoding='utf-8-sig')

print('=== SECTOR HIERARCHY ANALYSIS ===')
print(f'Total rows: {len(df)}')
print(f'Unique symbols: {len(df["symbol"].unique())}')
print(f'Unique sectors: {len(df["sector"].unique())}')

# Analyze hierarchy levels
print('\nAnalyzing sector hierarchy levels...')
symbol_sector_counts = df.groupby('symbol').size()
print(f'Symbols with 1 sector: {(symbol_sector_counts == 1).sum()}')
print(f'Symbols with 2 sectors: {(symbol_sector_counts == 2).sum()}')
print(f'Symbols with 3 sectors: {(symbol_sector_counts == 3).sum()}')
print(f'Symbols with 4 sectors: {(symbol_sector_counts == 4).sum()}')
print(f'Symbols with 5+ sectors: {(symbol_sector_counts >= 5).sum()}')

print(f'\nMax sectors per symbol: {symbol_sector_counts.max()}')
print(f'Avg sectors per symbol: {symbol_sector_counts.mean():.2f}')

# Show example
print('\nExample - Symbol AAA sectors:')
aaa_sectors = df[df['symbol'] == 'AAA']['sector'].tolist()
for i, sector in enumerate(aaa_sectors, 1):
    print(f'  Level {i}: {sector}')

print('\nExample - Symbol ABB sectors:')
abb_sectors = df[df['symbol'] == 'ABB']['sector'].tolist()
for i, sector in enumerate(abb_sectors, 1):
    print(f'  Level {i}: {sector}')
