"""
Load Sector Classification from VCI using vnstock
"""
import pandas as pd
from pathlib import Path
import sys

try:
    from vnstock import Listing
except ImportError:
    print("ERROR: vnstock not installed. Install with: pip install vnstock")
    sys.exit(1)

print("=" * 60)
print("LOADING SECTOR CLASSIFICATION FROM VCI")
print("=" * 60)

# Initialize Listing with VCI source
listing = Listing(source="vci")

# 1. Get ICB classification
print("\n[1] Loading ICB Classification...")
try:
    icb_df = listing.industries_icb()
    print(f"    SUCCESS: {len(icb_df)} ICB categories")
    print(f"    Columns: {list(icb_df.columns)}")
    # Skip printing dataframe if it has unicode
except Exception as e:
    print(f"    FAILED: {str(e)}")
    sys.exit(1)

# 2. Get symbols by industries
print("\n[2] Loading Symbols by Industries...")
try:
    industries_df = listing.symbols_by_industries(lang='vi', to_df=True)
    print(f"    SUCCESS: {len(industries_df)} symbols with industry info")
except Exception as e:
    print(f"    FAILED: {str(e)}")
    sys.exit(1)

# 3. Create sector mapping
print("\n[3] Creating Sector Mapping...")
try:
    # Use icb_name3 if exists, else icb_name2 or industry_name
    if 'icb_name3' in industries_df.columns:
        sector_col = 'icb_name3'
    elif 'icb_name2' in industries_df.columns:
        sector_col = 'icb_name2'
    else:
        sector_col = industries_df.columns[-1] # Fallback
        
    sector_map = industries_df[['symbol', sector_col]].drop_duplicates()
    sector_map = sector_map.rename(columns={sector_col: 'sector'})
    
    # Save with UTF-8 encoding
    output_path = Path('OMEGA_QUANT/data/sector_mapping_vci.csv')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sector_map.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"    Saved {len(sector_map)} symbols to: {output_path}")
    
except Exception as e:
    print(f"    FAILED: {str(e)}")
    sys.exit(1)

# 4. Summary
print("\n" + "=" * 60)
print("SECTOR MAPPING SUMMARY")
print("=" * 60)
print(f"Total symbols: {len(sector_map)}")
print(f"Total sectors: {sector_map['sector'].nunique()}")
print("\nSector distribution (top 10):")
print(sector_map['sector'].value_counts().head(10))
print("=" * 60)
