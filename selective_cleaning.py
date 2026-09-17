"""Selective data cleaning - only remove truly bad data."""
import pandas as pd
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SelectiveDataCleaner:
    """Only clean what's absolutely necessary."""
    
    def __init__(self):
        self.stats = {}
    
    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply selective cleaning - preserve as much data as possible."""
        initial_rows = len(df)
        
        # Step 1: Remove exact duplicates only
        df = df.drop_duplicates(subset=['date', 'ticker'], keep='first').copy()
        self.stats['duplicates_removed'] = initial_rows - len(df)
        
        # Step 2: Fix OHLC consistency issues only
        # Ensure high >= low
        df.loc[df['high'] < df['low'], 'high'] = df.loc[df['high'] < df['low'], 'low']
        # Ensure close is within [low, high]
        df.loc[df['close'] < df['low'], 'close'] = df.loc[df['close'] < df['low'], 'low']
        df.loc[df['close'] > df['high'], 'close'] = df.loc[df['close'] > df['high'], 'high']
        
        # Step 3: Remove truly invalid data only
        # Remove negative or zero prices
        invalid_mask = (df['close'] <= 0) | (df['open'] <= 0) | (df['high'] <= 0) | (df['low'] <= 0)
        df = df[~invalid_mask].copy()
        self.stats['invalid_prices_removed'] = initial_rows - len(df) - self.stats['duplicates_removed']
        
        # Step 4: Forward-fill small gaps (max 3 days) for continuity
        df = df.sort_values(['ticker', 'date'])
        ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
        forward_filled = 0
        
        for ticker in df['ticker'].unique():
            ticker_mask = df['ticker'] == ticker
            ticker_data = df.loc[ticker_mask].copy()
            ticker_data = ticker_data.set_index('date')
            
            for col in ohlcv_cols:
                if col in ticker_data.columns:
                    before_fill = ticker_data[col].isna().sum()
                    ticker_data[col] = ticker_data[col].ffill(limit=3)
                    after_fill = ticker_data[col].isna().sum()
                    forward_filled += (before_fill - after_fill)
            
            df.loc[ticker_mask, ohlcv_cols] = ticker_data[ohlcv_cols].values
        
        self.stats['forward_filled'] = forward_filled
        
        # IMPORTANT: Do NOT filter by min_volume here
        # Let the strategy decide what volume is acceptable
        
        final_rows = len(df)
        self.stats['total_removed'] = initial_rows - final_rows
        self.stats['retention_rate'] = final_rows / initial_rows * 100
        
        logger.info(f"Selective cleaning applied:")
        logger.info(f"  - Duplicates removed: {self.stats['duplicates_removed']:,}")
        logger.info(f"  - Invalid prices removed: {self.stats['invalid_prices_removed']:,}")
        logger.info(f"  - Values forward-filled: {self.stats['forward_filled']:,}")
        logger.info(f"  - Total removed: {self.stats['total_removed']:,} ({100 - self.stats['retention_rate']:.2f}%)")
        logger.info(f"  - Remaining: {final_rows:,} rows ({self.stats['retention_rate']:.2f}%)")
        
        return df
    
    def get_stats(self):
        return self.stats

if __name__ == "__main__":
    # Test the selective cleaner
    print("Testing selective data cleaner...")
    print()
    
    # Load data
    df = pd.read_parquet('data/market_2015_now.parquet')
    print(f"Loaded {len(df):,} rows")
    print()
    
    # Apply selective cleaning
    cleaner = SelectiveDataCleaner()
    df_clean = cleaner.clean(df)
    
    print()
    print("Stats:")
    for key, value in cleaner.get_stats().items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}%")
        else:
            print(f"  {key}: {value:,}")
