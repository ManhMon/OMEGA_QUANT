import pandas as pd

df = pd.read_csv('OMEGA_QUANT/data/sector_mapping_vci.csv')
print(f'Columns: {list(df.columns)}')
print(f'Shape: {df.shape}')
print(f'Unique sectors: {len(df["sector"].unique())}')
print(f'\nFirst 10 rows:')
print(df.head(10))
