"""
Structure Features Module - Layer 01 Core Intelligence
Provides structural/categorical features for Vietnamese market.

100% vectorized (ZERO loops, ZERO comprehensions), PIT safe (T-1 lag applied per symbol).
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from pathlib import Path


# Dynamic metadata loading (loads once on import)
def _get_metadata_path() -> Path:
    """Helper to resolve metadata path relative to project root."""
    # Current file is OMEGA_QUANT/src/omega/core/structure_features.py
    # Root is OMEGA_QUANT (3 levels up)
    root = Path(__file__).resolve().parents[3]
    return root / 'data' / 'sector_mapping_level2.csv'

_METADATA_PATH = _get_metadata_path()

def _load_sector_map() -> Dict[str, str]:
    """Helper to load sector map from CSV."""
    if _METADATA_PATH.exists():
        try:
            mapping_df = pd.read_csv(_METADATA_PATH)
            return dict(zip(mapping_df['symbol'], mapping_df['sector']))
        except Exception:
            return {}
    return {}

SECTOR_MAP: Dict[str, str] = _load_sector_map()


EXCHANGE_MAP: Dict[str, str] = {
    'VNM': 'HOSE', 'VIC': 'HOSE', 'VHM': 'HOSE', 'VCB': 'HOSE',
    'BID': 'HOSE', 'CTG': 'HOSE', 'TCB': 'HOSE', 'MBB': 'HOSE',
    'HPG': 'HOSE', 'MSN': 'HOSE', 'VRE': 'HOSE', 'GAS': 'HOSE',
    'SAB': 'HOSE', 'MWG': 'HOSE', 'FPT': 'HOSE', 'VJC': 'HOSE',
    'SSI': 'HOSE', 'HDB': 'HOSE', 'ACB': 'HOSE', 'STB': 'HOSE',
    'PVS': 'HNX', 'SHB': 'HNX', 'PVX': 'HNX', 'CEO': 'HNX',
}

IPO_DATES: Dict[str, str] = {
    'VNM': '2017-01-19', 'VIC': '2007-07-20', 'VHM': '2018-05-17',
    'VCB': '2009-06-23', 'BID': '2009-01-08', 'CTG': '2009-09-04',
    'TCB': '2018-06-14', 'MBB': '2009-11-10', 'VPB': '2017-08-08',
    'HPG': '2007-11-28', 'MSN': '2009-12-08', 'VRE': '2019-01-18',
}


def get_sector_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get sector classification features (one-hot encoded).
    100% vectorized - ZERO loops, ZERO comprehensions.
    NOTE: Caller must apply shift(1) for T-1 lag if needed.
    """
    if isinstance(df.index, pd.MultiIndex):
        symbols = df.index.get_level_values('symbol')
    elif 'symbol' in df.columns:
        symbols = df['symbol']
    else:
        raise ValueError("DataFrame must have 'symbol' in index or columns")
    
    # Vectorized mapping using Series.map (NOT listcomp)
    symbol_series = pd.Series(symbols, index=df.index)
    # Normalize spaces to underscores to match one-hot col names
    sector_series = symbol_series.map(SECTOR_MAP).fillna('Other').str.replace(' ', '_', regex=False)
    
    # Vectorized one-hot encoding using pd.get_dummies
    result = pd.get_dummies(sector_series, prefix='sector').astype(np.int8)
    
    return result


def get_exchange_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get exchange classification features (one-hot encoded).
    100% vectorized - ZERO loops, ZERO comprehensions.
    NOTE: Caller must apply shift(1) for T-1 lag if needed.
    """
    if isinstance(df.index, pd.MultiIndex):
        symbols = df.index.get_level_values('symbol')
    elif 'symbol' in df.columns:
        symbols = df['symbol']
    else:
        raise ValueError("DataFrame must have 'symbol' in index or columns")
    
    # Vectorized mapping using Series.map (NOT listcomp)
    symbol_series = pd.Series(symbols, index=df.index)
    exchange_series = symbol_series.map(EXCHANGE_MAP).fillna('UPCOM')
    
    # Vectorized one-hot encoding using pd.get_dummies
    result = pd.get_dummies(exchange_series, prefix='exchange').astype(np.int8)
    
    # Ensure all exchanges exist
    all_exchanges = ['exchange_HOSE', 'exchange_HNX', 'exchange_UPCOM']
    result = result.reindex(columns=all_exchanges, fill_value=0)
    
    return result


def get_price_level_features(df: pd.DataFrame, price_col: str = 'close') -> pd.DataFrame:
    """
    Get price-level bucket features (Penny/Mid/Large).
    100% vectorized - ZERO loops.
    """
    if price_col not in df.columns:
        raise ValueError(f"Column '{price_col}' not found in DataFrame")
    
    prices = df[price_col]
    
    result = pd.DataFrame(index=df.index)
    result['price_bucket_penny'] = (prices < 10000).astype(np.int8)
    result['price_bucket_mid'] = ((prices >= 10000) & (prices <= 50000)).astype(np.int8)
    result['price_bucket_large'] = (prices > 50000).astype(np.int8)
    
    return result


def get_market_cap_features(
    df: pd.DataFrame, 
    price_col: str = 'close',
    volume_col: str = 'volume'
) -> pd.DataFrame:
    """
    Get market cap proxy features (log-transformed).
    100% vectorized - ZERO loops.
    """
    if price_col not in df.columns or volume_col not in df.columns:
        raise ValueError(f"Columns '{price_col}' and '{volume_col}' required")
    
    prices = df[price_col]
    volumes = df[volume_col]
    
    market_cap = prices * volumes
    log_market_cap = np.log1p(market_cap)
    
    result = pd.DataFrame({
        'log_market_cap': log_market_cap
    }, index=df.index)
    
    return result


def get_listing_age_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get listing age features (days since IPO).
    100% vectorized - ZERO loops, ZERO comprehensions.
    """
    if isinstance(df.index, pd.MultiIndex):
        symbols = df.index.get_level_values('symbol')
        dates = df.index.get_level_values('date')
    elif 'symbol' in df.columns:
        symbols = df['symbol']
        # If no MultiIndex, prefer 'date' column over index
        dates = df['date'] if 'date' in df.columns else df.index
    else:
        raise ValueError("DataFrame must have 'symbol' in index or columns")
    
    # Vectorized date conversion
    dates = pd.to_datetime(dates)
    
    # Vectorized mapping (NOT listcomp)
    symbol_series = pd.Series(symbols, index=df.index)
    ipo_series = symbol_series.map(IPO_DATES).fillna('2000-01-01')
    ipo_dates = pd.to_datetime(ipo_series)
    
    # Vectorized subtraction
    listing_age = (dates - ipo_dates).dt.days
    
    result = pd.DataFrame({
        'listing_age_days': listing_age
    }, index=df.index)
    
    return result


def get_structure_data(
    df: pd.DataFrame,
    price_col: str = 'close',
    volume_col: str = 'volume'
) -> pd.DataFrame:
    """
    Get all structure features combined with T-1 lag applied per symbol.
    100% vectorized - ZERO loops.
    """
    # 0. Ensure chronological order for position-based shift
    # Backup original index to restore later
    original_idx = df.index
    
    if isinstance(df.index, pd.MultiIndex):
        # Sort by level names if possible, else by level positions
        # Replaced ListComp with vectorized Index operations for compliance
        names = pd.Series(df.index.names)
        sort_levels = names[names.isin(['symbol', 'date'])].tolist()
        
        if not sort_levels:
            sort_levels = [0, 1]
        df_sorted = df.sort_index(level=sort_levels)
    elif 'symbol' in df.columns and 'date' in df.columns:
        df_sorted = df.sort_values(['symbol', 'date'])
    elif 'symbol' in df.columns:
        # If only symbol, sort by symbol then by original index (assumed date)
        df_sorted = df.sort_values('symbol')
    else:
        df_sorted = df
        
    # 1. Generate all features (current bar) on sorted data
    raw_features = pd.concat([
        get_sector_features(df_sorted),
        get_exchange_features(df_sorted),
        get_price_level_features(df_sorted, price_col),
        get_market_cap_features(df_sorted, price_col, volume_col),
        get_listing_age_features(df_sorted)
    ], axis=1)
    
    # 2. Apply T-1 lag per symbol to prevent cross-ticker pollution
    if isinstance(df_sorted.index, pd.MultiIndex):
        features_sorted = raw_features.groupby(level='symbol', group_keys=False).shift(1)
    elif 'symbol' in df_sorted.columns:
        symbol_col = df_sorted['symbol']
        features_sorted = raw_features.groupby(symbol_col, group_keys=False).shift(1)
    else:
        features_sorted = raw_features.shift(1)
    
    # 3. Restore original order (vectorized reindex)
    return features_sorted.reindex(original_idx)


def get_neutralization_buckets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get neutralization buckets (sector + price-level combination).
    100% vectorized - ZERO loops, ZERO comprehensions.
    """
    # Extract sector name (vectorized idxmax)
    sector_cols = df.columns[df.columns.str.startswith('sector_')]
    price_cols = df.columns[df.columns.str.startswith('price_bucket_')]
    
    result = pd.DataFrame(index=df.index)
    
    # Filter only rows with data to avoid idxmax error on NaN
    valid_mask = df[sector_cols].sum(axis=1) > 0
    
    if len(sector_cols) > 0:
        sector_idx = df.loc[valid_mask, sector_cols].idxmax(axis=1)
        result.loc[valid_mask, 'sector'] = sector_idx.str.replace('sector_', '', regex=False)
    
    if len(price_cols) > 0:
        price_idx = df.loc[valid_mask, price_cols].idxmax(axis=1)
        result.loc[valid_mask, 'price_bucket'] = price_idx.str.replace('price_bucket_', '', regex=False)
    
    # Combine sector + price bucket (vectorized string concat)
    if 'sector' in result.columns and 'price_bucket' in result.columns:
        result['neutralization_bucket'] = (
            result['sector'].fillna('') + '_' + result['price_bucket'].fillna('')
        )
    
    return result
