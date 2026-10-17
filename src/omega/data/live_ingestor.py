"""
V21_QUANT: LIVE DATA INGESTOR (P0 Survival Priority)

Real-time price fetcher for HOSE/HNX with graceful error handling.
Normalizes prices to VND and matches warehouse schema.
"""

import pandas as pd
import logging
from typing import Optional, List

from omega.data.vci_direct import DirectVCIClient
from omega.data.vnstock_client import VnstockClient


class LiveDataIngestor:
    """Fetch real-time market data and normalize to warehouse format."""

    def __init__(self, source: str = "VCI", timeout: int = 10, max_retries: int = 3):
        """
        Args:
            source: Data source (VCI, TCBS, etc.)
            timeout: API timeout in seconds
            max_retries: Number of retry attempts on failure
        """
        self.client = VnstockClient(source=source, direct_vci_client=DirectVCIClient(
            timeout=timeout, max_attempts=max_retries))
        self.source = self.client.source
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)

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
        frame = self.fetch_live_batch([symbol], {symbol: exchange})
        return None if frame.empty else frame

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

        normalized = [DirectVCIClient._ticker(symbol) for symbol in symbols]
        exchanges = {DirectVCIClient._ticker(symbol): str(exchange).upper().replace('HSX', 'HOSE')
                     for symbol, exchange in symbol_exchange_map.items()}
        for offset in range(0, len(normalized), 100):
            try:
                frame = self.client.direct_vci_client.fetch_price_board(normalized[offset:offset + 100]).copy()
                if frame.empty:
                    continue
                if not frame['symbol'].isin(normalized[offset:offset + 100]).all():
                    raise ValueError("Unexpected live symbol")
                frame = frame[frame.apply(lambda row: row['symbol'] not in exchanges or
                                         row['exchange'] == exchanges[row['symbol']], axis=1)].copy()
                frame['date'] = pd.to_datetime(frame['date'], utc=True).dt.tz_convert('Asia/Ho_Chi_Minh').dt.tz_localize(None).dt.normalize()
                all_data.append(frame)
            except Exception as error:
                self.logger.warning("Live price board failed: %s", type(error).__name__)

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

        df_live = df_live.copy()
        df_warehouse = df_warehouse.copy()
        df_live['date'] = pd.to_datetime(df_live['date'])
        df_warehouse['date'] = pd.to_datetime(df_warehouse['date'])
        df_combined = pd.concat([df_warehouse, df_live], ignore_index=True)
        df_combined = df_combined.drop_duplicates(['symbol', 'date'], keep='last')
        df_combined = df_combined.sort_values(['symbol', 'date']).reset_index(drop=True)

        self.logger.info("Live data appended: %d rows", len(df_live))
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
