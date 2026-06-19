"""
V21_QUANT: LIVE DATA INGESTOR (P0 Survival Priority)

Real-time price fetcher for HOSE/HNX with graceful error handling.
Normalizes prices to VND and matches warehouse schema.
"""

import pandas as pd
import logging
from typing import Optional, List
from datetime import datetime
import time

try:
    from vnstock import Quote
    VNSTOCK_AVAILABLE = True
except ImportError:
    VNSTOCK_AVAILABLE = False
    logging.warning("vnstock not available. Live data ingestion disabled.")


class LiveDataIngestor:
    """Fetch real-time market data and normalize to warehouse format."""

    def __init__(self, source: str = "VCI", timeout: int = 10, max_retries: int = 3):
        """
        Args:
            source: Data source (VCI, TCBS, etc.)
            timeout: API timeout in seconds
            max_retries: Number of retry attempts on failure
        """
        self.source = source
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)

        if not VNSTOCK_AVAILABLE:
            self.logger.error("vnstock library not installed. Install with: pip install vnstock")

    def _normalize_price_columns_to_vnd(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize price columns to VND_FULL using centralized guard."""
        from omega.data.vnd_price_contract import ensure_vnd_scale
        return ensure_vnd_scale(df, price_cols=["open", "high", "low", "close"])

    def fetch_live_price(self, symbol: str, exchange: str) -> Optional[pd.DataFrame]:
        """
        Fetch latest price snapshot for a single symbol.

        Args:
            symbol: Stock symbol (e.g., 'VCB')
            exchange: Exchange code ('HOSE' or 'HNX')

        Returns:
            DataFrame with single row matching warehouse schema, or None on failure
        """
        if not VNSTOCK_AVAILABLE:
            self.logger.error("Cannot fetch live data: vnstock not available")
            return None

        for attempt in range(self.max_retries):
            try:
                quote = Quote(source=self.source, symbol=symbol)

                # Fetch last 1 day to get most recent price
                df = quote.history(length="1D", interval="1D")

                if df is None or df.empty:
                    self.logger.warning(f"{symbol}: No data returned (attempt {attempt+1}/{self.max_retries})")
                    if attempt < self.max_retries - 1:
                        time.sleep(1)
                        continue
                    return None

                # Normalize column names
                if 'time' in df.columns:
                    df = df.rename(columns={'time': 'date'})
                elif 'timestamp' in df.columns:
                    df = df.rename(columns={'timestamp': 'date'})

                # Take most recent row
                df = df.tail(1).copy()

                # Add metadata
                df['symbol'] = symbol
                df['exchange'] = exchange

                # Ensure schema match
                required_cols = ['symbol', 'exchange', 'date', 'open', 'high', 'low', 'close', 'volume']
                df = df[required_cols]

                # VCI may return prices in thousand-VND units; normalize only then.
                df = self._normalize_price_columns_to_vnd(df)

                df['date'] = pd.to_datetime(df['date'])

                self.logger.info(f"{symbol}: Live price fetched successfully (close={df['close'].iloc[0]:.2f})")
                return df

            except Exception as e:
                self.logger.warning(f"{symbol}: Fetch failed (attempt {attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    self.logger.error(f"{symbol}: All retry attempts exhausted")
                    return None

        return None

    def fetch_live_batch(self, symbols: List[str], symbol_exchange_map: dict) -> pd.DataFrame:
        """
        Fetch live prices for multiple symbols.

        Args:
            symbols: List of stock symbols
            symbol_exchange_map: Dict mapping symbol -> exchange

        Returns:
            DataFrame with all successfully fetched prices
        """
        all_data = []

        for symbol in symbols:
            exchange = symbol_exchange_map.get(symbol, 'HOSE')
            df = self.fetch_live_price(symbol, exchange)

            if df is not None:
                all_data.append(df)

            # Rate limiting: 60 requests/min for VCI Community
            time.sleep(1.1)

        if all_data:
            combined = pd.concat(all_data, ignore_index=True)
            self.logger.info(f"Live batch fetch complete: {len(combined)} symbols")
            return combined
        else:
            self.logger.warning("Live batch fetch: No data retrieved")
            return pd.DataFrame()

    def append_live_to_warehouse(self, df_warehouse: pd.DataFrame, df_live: pd.DataFrame) -> pd.DataFrame:
        """
        Append live data to warehouse DataFrame.

        Args:
            df_warehouse: Historical warehouse data
            df_live: Live data snapshot

        Returns:
            Combined DataFrame with live data appended
        """
        if df_live.empty:
            self.logger.warning("No live data to append")
            return df_warehouse

        # Ensure date types match
        df_live['date'] = pd.to_datetime(df_live['date'])
        df_warehouse['date'] = pd.to_datetime(df_warehouse['date'])

        # Remove any duplicate dates for same symbols (keep warehouse data)
        live_date = df_live['date'].max()

        # Filter out any existing data for the live date
        df_warehouse_filtered = df_warehouse[df_warehouse['date'] < live_date]

        # Concatenate
        df_combined = pd.concat([df_warehouse_filtered, df_live], ignore_index=True)
        df_combined = df_combined.sort_values(['symbol', 'date']).reset_index(drop=True)

        self.logger.info(f"Live data appended: {len(df_live)} rows added (date={live_date})")
        return df_combined


if __name__ == "__main__":
    # Test the ingestor
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    ingestor = LiveDataIngestor(source="VCI")

    # Test single symbol
    test_symbol = "VCB"
    test_exchange = "HOSE"

    df = ingestor.fetch_live_price(test_symbol, test_exchange)

    if df is not None:
        print("\n" + "="*60)
        print("LIVE DATA INGESTOR TEST")
        print("="*60)
        print(df)
        print("\nColumns:", df.columns.tolist())
        print("Dtypes:", df.dtypes.to_dict())
        print("="*60)
    else:
        print("Failed to fetch live data")
