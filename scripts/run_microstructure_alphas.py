#!/usr/bin/env python3
"""run_microstructure_alphas.py - Compute microstructure features from intraday data."""
import sys, os, json, argparse, logging
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "packages" / "quant" / "src"))

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("microstructure")

compute_phase34 = None
SmartMoneyFeatures = None
get_structure_data = None

try:
    from omega.quant.phase34_microstructure_alphas import compute_phase34_microstructure_alphas, get_phase34_alpha_metadata
    compute_phase34 = compute_phase34_microstructure_alphas
    logger.info("phase34 imported")
except ImportError as e:
    logger.warning(f"phase34 not available: {e}")

try:
    from omega.quant.smart_money_features import SmartMoneyFeatures
    logger.info("SmartMoneyFeatures imported")
except ImportError as e:
    logger.warning(f"SmartMoneyFeatures not available: {e}")

try:
    from omega.quant.structure_features import get_structure_data
    logger.info("get_structure_data imported")
except ImportError as e:
    logger.warning(f"get_structure_data not available: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    intraday_path = WORKSPACE / "data" / "intraday" / f"{args.date}_all.parquet"
    
    if not intraday_path.exists():
        logger.warning(f"Intraday file not found: {intraday_path}, skipping")
        return 0
    
    logger.info(f"Loading intraday from {intraday_path}")
    df = pd.read_parquet(intraday_path)
    logger.info(f"Loaded {len(df)} rows, {df['ticker'].nunique() if 'ticker' in df.columns else 0} tickers")
    
    all_features = pd.DataFrame()
    feature_names = []
    
    # Step 1: Microstructure alphas
    if compute_phase34 is not None:
        try:
            micro_df = compute_phase34(df)
            if isinstance(micro_df, pd.DataFrame) and not micro_df.empty:
                all_features = micro_df
                feature_names.extend([c for c in micro_df.columns if c not in ("ticker", "date", "time")])
                logger.info(f"Microstructure: {len(feature_names)} alphas computed")
        except Exception as e:
            logger.warning(f"Microstructure compute failed: {e}")
    
    # Step 2: Smart money features
    if SmartMoneyFeatures is not None:
        try:
            smart = SmartMoneyFeatures()
            if hasattr(smart, "compute"):
                smart_df = smart.compute(df)
            elif hasattr(smart, "compute_features"):
                smart_df = smart.compute_features(df)
            else:
                smart_df = None
            if isinstance(smart_df, pd.DataFrame) and not smart_df.empty:
                if all_features.empty:
                    all_features = smart_df
                else:
                    all_features = pd.concat([all_features, smart_df], axis=1)
                feature_names.extend([c for c in smart_df.columns if c not in ("ticker", "date", "time")])
                logger.info(f"Smart money: added {len([c for c in smart_df.columns])} features")
        except Exception as e:
            logger.warning(f"Smart money compute failed: {e}")
    
    # Step 3: Structure data
    if get_structure_data is not None and "ticker" in df.columns:
        try:
            tickers = df["ticker"].unique().tolist()
            struct_df = get_structure_data(symbols=tickers)
            if isinstance(struct_df, pd.DataFrame) and not struct_df.empty:
                logger.info(f"Structure: {len(struct_df)} rows fetched")
        except Exception as e:
            logger.warning(f"Structure fetch failed: {e}")
    
    # Save
    out_parquet = WORKSPACE / ".ly_state" / "session" / f"microstructure_{args.date}.parquet"
    out_json = WORKSPACE / ".ly_state" / "session" / f"microstructure_{args.date}.json"
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    
    num_tickers = df["ticker"].nunique() if "ticker" in df.columns else 0
    
    if not all_features.empty:
        all_features.to_parquet(out_parquet)
        logger.info(f"Saved features to {out_parquet}")
    
    metadata = {
        "date": args.date,
        "num_tickers": int(num_tickers),
        "num_features": len(feature_names),
        "feature_names": feature_names[:50],  # Truncate for JSON size
        "intraday_source": str(intraday_path)
    }
    with open(out_json, "w") as f:
        json.dump(metadata, f, indent=2)
    
    print("="*60)
    print(f"MICROSTRUCTURE - {args.date}")
    print("="*60)
    print(f"  Tickers: {num_tickers}")
    print(f"  Features: {len(feature_names)}")
    print(f"  Saved: {out_json}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
