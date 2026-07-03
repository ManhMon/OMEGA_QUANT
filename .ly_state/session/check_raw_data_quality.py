"""Check raw data quality from vnstock API."""
from vnstock import Quote

q = Quote('VCB', source='vci')
df = q.history(period='1mo', interval='1d')

print("=== Sample Data ===")
print(df.head(10))

print("\n=== Data Types ===")
print(df.dtypes)

print("\n=== Missing Values ===")
print(df.isnull().sum())

print("\n=== Sample Statistics ===")
print(df.describe())

print("\n=== Check for zeros/negatives ===")
print(f"Zeros in close: {(df['close'] == 0).sum()}")
print(f"Negatives in close: {(df['close'] < 0).sum()}")
print(f"Zeros in volume: {(df['volume'] == 0).sum()}")
print(f"Nulls in close: {df['close'].isnull().sum()}")
print(f"Nulls in volume: {df['volume'].isnull().sum()}")

print("\n=== Check for outliers (IQR method) ===")
Q1 = df['close'].quantile(0.25)
Q3 = df['close'].quantile(0.75)
IQR = Q3 - Q1
lower_bound = Q1 - 1.5 * IQR
upper_bound = Q3 + 1.5 * IQR
outliers = df[(df['close'] < lower_bound) | (df['close'] > upper_bound)]
print(f"Outliers in close: {len(outliers)} rows")
if len(outliers) > 0:
    print(outliers[['time', 'close', 'volume']])
