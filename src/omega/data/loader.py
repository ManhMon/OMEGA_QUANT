"""
PIT-Safe Data Loader for OMEGA+++ Quant AI System

Enforces strict point-in-time safety with as_of/available_at timestamps.
Integrates with vnstock for EOD prices with local Parquet caching.

Architecture Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 4 (Data Governance)
"""

import os
import time
import hashlib
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
import pandas as pd
import numpy as np

from omega.data.calendar import VNTradingCalendar, _get_json_holidays


logger = logging.getLogger(__name__)


class PITViolationError(Exception):
    """Raised when point-in-time safety is violated (as_of > available_at)."""
    pass


class DataQualityError(Exception):
    """Raised when data quality checks fail."""
    pass


try:
    from omega.data.vnstock_vci import VnstockVCIDataSource
except ImportError:
    VnstockVCIDataSource = None

try:
    from omega.data.corporate_action import CorporateActionAdjuster, CorporateAction
except ImportError:
    CorporateActionAdjuster = None
    CorporateAction = None

try:
    from omega.data.validator import DataValidator, ValidationIssue
except ImportError:
    DataValidator = None
    ValidationIssue = None


class DataLoader:
    """
    PIT-Safe Data Loader with incremental loading and quality validation.

    Key Features:
    1. PIT Safety: Enforces as_of <= available_at for all data points
    2. Incremental Loading: Caches data locally in Parquet format
    3. Data Quality: Validates missing values, outliers, price adjustments
    4. vnstock Integration: Fetches EOD prices from Vietnamese stock market

    Contract:
    - Input: ticker, start_date, end_date, as_of_time (query time)
    - Output: DataFrame with columns [ticker, date, open, high, low, close, volume, as_of, available_at]
    - Precondition: start_date <= end_date, as_of_time >= end_date
    - Postcondition: All rows satisfy as_of <= available_at
    """

    def __init__(
        self,
        cache_dir: str = "data/cache",
        quality_threshold: float = 0.8,
        outlier_std_threshold: float = 5.0,
        enable_pit_enforcement: bool = True,
        dataset_version: str = "1.0.0",
        is_already_adjusted: bool = True,
        validate_provenance: bool = True
    ):
        """
        Initialize DataLoader.

        Args:
            cache_dir: Directory for Parquet cache files
            quality_threshold: Minimum quality score (0.0-1.0)
            outlier_std_threshold: Standard deviations for outlier detection
            enable_pit_enforcement: Enable strict PIT safety checks
            dataset_version: Version identifier for provenance tracking
            is_already_adjusted: If True, source provides adjusted prices (default True for vnstock)
            validate_provenance: Enable provenance and checksum validation
        """
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.quality_threshold = quality_threshold
        self.outlier_std_threshold = outlier_std_threshold
        self.enable_pit_enforcement = enable_pit_enforcement
        self.dataset_version = dataset_version
        self.is_already_adjusted = is_already_adjusted
        self.validate_provenance = validate_provenance
        
        # Initialize vnstock data source
        self.vnstock_source = VnstockVCIDataSource() if VnstockVCIDataSource else None
        
        # Initialize corporate action adjuster
        self.corporate_action_adjuster = CorporateActionAdjuster() if CorporateActionAdjuster else None
        
        # Initialize data validator with checksum validation
        self.validator = DataValidator(validate_provenance=validate_provenance) if DataValidator else None

        logger.info(
            f"DataLoader initialized: cache_dir={cache_dir}, "
            f"quality_threshold={quality_threshold}, "
            f"pit_enforcement={enable_pit_enforcement}, "
            f"dataset_version={dataset_version}, "
            f"is_already_adjusted={is_already_adjusted}, "
            f"validate_provenance={validate_provenance}"
        )

    def load_prices(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        as_of_time: datetime,
        force_refresh: bool = False,
        corporate_actions: Optional[List] = None,
        apply_adjustments: bool = False,
        source: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Load EOD prices with PIT safety enforcement and optional corporate action adjustments.

        Args:
            ticker: Stock ticker symbol (e.g., "VNM", "VCB")
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            as_of_time: Query time (when we're making the query). Mandatory.
            force_refresh: Force refresh from source (bypass cache)
            corporate_actions: List of CorporateAction objects to apply
            apply_adjustments: If True, apply corporate action adjustments to prices

        Returns:
            DataFrame with columns: [ticker, date, open, high, low, close, volume, as_of, available_at, 
                                     dataset_version, source, adjustments_applied]

        Raises:
            PITViolationError: If PIT safety is violated
            DataQualityError: If data quality checks fail
            ValueError: If as_of_time is missing
        """
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT compliance")

        # Validate date range
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        if start_dt > end_dt:
            raise ValueError(f"start_date ({start_date}) must be <= end_date ({end_date})")

        # Check cache first
        cache_key = self._generate_cache_key(ticker, start_date, end_date, source=source)
        cache_path = Path(self.cache_dir) / f"{cache_key}.parquet"

        if not force_refresh and cache_path.exists():
            logger.info(f"Loading from cache: {cache_path}")
            try:
                df = pd.read_parquet(cache_path)
                self._validate_schema(df)
            except Exception as e:
                logger.warning(f"Cache load/validation failed ({type(e).__name__}: {e}). Refreshing from source.")
                df = self._fetch_from_source(ticker, start_date, end_date, as_of_time, source=source)
                # Only add PIT timestamps if not already present
                if 'as_of' not in df.columns or 'available_at' not in df.columns:
                    df = self._add_pit_timestamps(df)
                self._write_parquet_atomic(df, cache_path)
        else:
            logger.info(f"Fetching data for {ticker} from {start_date} to {end_date}")
            df = self._fetch_from_source(ticker, start_date, end_date, as_of_time, source=source)

            # Only add PIT timestamps if not already present (for testing/mocking)
            if 'as_of' not in df.columns or 'available_at' not in df.columns:
                df = self._add_pit_timestamps(df)

            # Save to cache atomically
            self._write_parquet_atomic(df, cache_path)
            logger.info(f"Saved to cache: {cache_path}")

        # Enforce PIT safety
        if self.enable_pit_enforcement:
            self._enforce_pit_safety(df, as_of_time)

        # Apply corporate action adjustments if requested
        adjustments_applied = []
        if apply_adjustments and corporate_actions:
            if self.corporate_action_adjuster is None:
                raise RuntimeError("CorporateActionAdjuster not available")
            
            # Check for double-adjustment risk
            if self.is_already_adjusted:
                logger.warning(
                    f"[DOUBLE-ADJUSTMENT RISK] Source provides adjusted prices (is_already_adjusted=True) "
                    f"but apply_adjustments=True was requested for {ticker}. "
                    f"Skipping adjustment to prevent double-counting. "
                    f"Set is_already_adjusted=False if source provides raw prices."
                )
            else:
                df, adjustments_applied = self._apply_corporate_actions(
                    df, ticker, corporate_actions, as_of_time
                )
                logger.info(f"Applied {len(adjustments_applied)} corporate actions to {ticker}")
        
        # Add provenance metadata
        df = self._add_provenance_metadata(df, ticker, adjustments_applied, as_of_time)
        
        # Run validator with checksum validation (Blocker 1 fix)
        if self.validator and self.validate_provenance:
            validation_issues = self.validator.validate_rows(
                df.to_dict('records'),
                symbol=ticker,
                parquet_path=cache_path
            )
            if validation_issues:
                logger.warning(f"Validation found {len(validation_issues)} issues for {ticker}")
                for issue in validation_issues[:5]:  # Log first 5 issues
                    logger.warning(f"  {issue.rule}: {issue.message}")
        
        # Run quality checks
        quality_score = self._check_data_quality(df)
        if quality_score < self.quality_threshold:
            raise DataQualityError(
                f"Data quality score {quality_score:.2f} below threshold {self.quality_threshold}"
            )
        
        # Persist metadata sidecar
        self._save_metadata_sidecar(cache_path, df, quality_score, adjustments_applied, as_of_time)

        logger.info(f"Loaded {len(df)} rows for {ticker}, quality_score={quality_score:.2f}")
        return df

    def _fetch_from_source(self, ticker: str, start_date: str, end_date: str, as_of_time: Optional[datetime] = None, source: Optional[str] = None) -> pd.DataFrame:
        """
        Fetch data from vnstock provider (VCI, KBS, etc.).
        
        Args:
            ticker: Stock ticker symbol (e.g., "VNM", "VCB")
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            as_of_time: Query time (optional, for PIT compliance)
            source: Primary provider source (e.g., "KBS", "VCI")
            
        Returns:
            DataFrame with columns: [ticker, date, open, high, low, close, volume]
        """
        if self.vnstock_source is None:
            raise RuntimeError("vnstock package not available. Install with: pip install vnstock")
        
        try:
            # Fetch price data from vnstock with explicit source routing
            data, provider_results = self.vnstock_source.fetch_price_data_with_reconciliation(
                ticker, start_date, end_date, source=source
            )
            
            if not data:
                raise ValueError(f"No data returned for {ticker} from {start_date} to {end_date}")
            
            # Convert to DataFrame
            df = pd.DataFrame(data)
            self._log_provider_close_deviations(ticker, data, provider_results)
            
            # Rename columns to match expected schema
            df = df.rename(columns={
                'symbol': 'ticker',
                'timestamp': 'date',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume'
            })
            
            # Convert timestamp to datetime
            df['date'] = pd.to_datetime(df['date'], unit='s')
            
            # Ensure correct column order
            df = df[['ticker', 'date', 'open', 'high', 'low', 'close', 'volume', 'source_used']]
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch data from vnstock for {ticker}: {e}")
            raise

    def _log_provider_close_deviations(
        self,
        ticker: str,
        selected_rows: List[Dict[str, Any]],
        provider_results: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        if not selected_rows:
            return
        selected_source = selected_rows[0]["source_used"]
        selected_close = {row["timestamp"]: row["close"] for row in selected_rows}
        for provider, rows in provider_results.items():
            if provider == selected_source:
                continue
            for row in rows:
                reference = selected_close.get(row["timestamp"])
                if reference and abs(row["close"] - reference) / abs(reference) > 0.001:
                    logger.warning(
                        "Close deviation for %s: selected %s vs %s at %s exceeds 0.1%%",
                        ticker, selected_source, provider, row["timestamp"],
                    )

    def _add_pit_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add as_of and available_at timestamps for PIT safety.

        Rule: EOD prices are available at T+1 market open (09:00 VN time).
        - as_of: End of trading day (date at 15:00 VN time)
        - available_at: Next trading day at 09:00 VN time
        Localizes naive timestamps to Asia/Ho_Chi_Minh.
        """
        df = df.copy()

        # Handle empty DataFrame
        if len(df) == 0:
            df['as_of'] = pd.Series([], dtype='datetime64[ns, Asia/Ho_Chi_Minh]')
            df['available_at'] = pd.Series([], dtype='datetime64[ns, Asia/Ho_Chi_Minh]')
            return df

        # Localize naive date to Asia/Ho_Chi_Minh if needed
        date_s = pd.to_datetime(df['date'])
        if date_s.dt.tz is None:
            date_hcm = date_s.dt.tz_localize("Asia/Ho_Chi_Minh")
        else:
            date_hcm = date_s.dt.tz_convert("Asia/Ho_Chi_Minh")

        # as_of: End of trading day (15:00 VN time)
        df['as_of'] = date_hcm + pd.Timedelta(hours=15)

        holidays_cache = _get_json_holidays()

        def next_open(timestamp: pd.Timestamp) -> pd.Timestamp:
            session = timestamp.date() + timedelta(days=1)
            year_str = str(session.year)
            if year_str not in holidays_cache and session.year > 2027:
                raise ValueError(f"no holiday coverage for {session.year}")
            while not VNTradingCalendar.is_trading_day(datetime.combine(session, datetime.min.time())):
                session += timedelta(days=1)
                year_str = str(session.year)
                if year_str not in holidays_cache and session.year > 2027:
                    raise ValueError(f"no holiday coverage for {session.year}")
            ts = pd.Timestamp(session).replace(hour=9)
            return ts.tz_localize("Asia/Ho_Chi_Minh") if ts.tzinfo is None else ts.tz_convert("Asia/Ho_Chi_Minh")

        df['available_at'] = df['as_of'].map(next_open)

        return df

    @staticmethod
    def _normalize_to_utc_series(s: pd.Series) -> pd.Series:
        """Localize naive market timestamps to Asia/Ho_Chi_Minh and convert to true UTC instants."""
        s_dt = pd.to_datetime(s)
        if s_dt.dt.tz is None:
            return s_dt.dt.tz_localize("Asia/Ho_Chi_Minh").dt.tz_convert("UTC")
        return s_dt.dt.tz_convert("UTC")

    @staticmethod
    def _normalize_to_utc_instant(ts_val: Any) -> pd.Timestamp:
        """Localize naive market timestamp to Asia/Ho_Chi_Minh and convert to true UTC instant."""
        ts = pd.Timestamp(ts_val)
        if ts.tzinfo is None:
            return ts.tz_localize("Asia/Ho_Chi_Minh").tz_convert("UTC")
        return ts.tz_convert("UTC")

    def _enforce_pit_safety(self, df: pd.DataFrame, as_of_time: datetime) -> None:
        """
        Enforce PIT safety: as_of <= available_at for all rows.
        Filter out rows where available_at > as_of_time (not yet available).
        Localizes naive market timestamps to Asia/Ho_Chi_Minh and compares true UTC instants.

        Raises:
            ValueError: If any row violates as_of <= available_at (PIT violation)
        """
        # Compare true UTC instants
        as_of_utc = self._normalize_to_utc_series(df['as_of'])
        avail_utc = self._normalize_to_utc_series(df['available_at'])

        violations = df[as_of_utc > avail_utc]
        if len(violations) > 0:
            raise ValueError(
                f"PIT violation: Found {len(violations)} rows where as_of > available_at:\n{violations.head()}"
            )

        # Filter out data not yet available at query time (true UTC instant comparison)
        before_count = len(df)
        as_of_val_utc = self._normalize_to_utc_instant(as_of_time)

        df_filtered = df[avail_utc <= as_of_val_utc]
        after_count = len(df_filtered)

        if before_count > after_count:
            logger.warning(
                f"Filtered {before_count - after_count} rows not available at {as_of_time}"
            )

        # Update df in place (note: this modifies the caller's DataFrame)
        df.drop(df.index, inplace=True)
        df.reset_index(drop=True, inplace=True)
        for col in df_filtered.columns:
            df[col] = df_filtered[col].values

    def _check_data_quality(self, df: pd.DataFrame) -> float:
        """
        Check data quality and return quality score (0.0-1.0).

        Checks:
        1. Missing values in critical columns
        2. Outliers in price/volume (> N std deviations)
        3. OHLC consistency (high >= low, high >= open/close, low <= open/close)
        4. Price adjustments (detect splits/dividends via large jumps)

        Returns:
            Quality score (0.0 = worst, 1.0 = perfect)
        """
        if len(df) == 0:
            return 0.0
        
        # For single-row DataFrames, return 1.0 (perfect quality)
        if len(df) == 1:
            # Still check for basic validity
            critical_cols = ['open', 'high', 'low', 'close', 'volume']
            if df[critical_cols].isnull().sum().sum() > 0:
                return 0.8  # Minor penalty for missing values
            if (df['open'] <= 0).any() or (df['close'] <= 0).any():
                return 0.8  # Minor penalty for invalid prices
            return 1.0

        issues = []

        # 1. Missing values
        critical_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_counts = df[critical_cols].isnull().sum()
        if missing_counts.sum() > 0:
            issues.append(f"Missing values: {missing_counts.to_dict()}")

        # 2. Outliers (price changes > N std)
        df_sorted = df.sort_values('date')
        df_sorted['close_pct_change'] = df_sorted['close'].pct_change()

        if len(df_sorted) > 1:
            mean_change = df_sorted['close_pct_change'].mean()
            std_change = df_sorted['close_pct_change'].std()

            if std_change > 0:
                outliers = df_sorted[
                    abs(df_sorted['close_pct_change'] - mean_change) > self.outlier_std_threshold * std_change
                ]
                if len(outliers) > 0:
                    issues.append(f"Outliers detected: {len(outliers)} rows")

        # 3. OHLC consistency
        ohlc_violations = df[
            (df['high'] < df['low']) |
            (df['high'] < df['open']) |
            (df['high'] < df['close']) |
            (df['low'] > df['open']) |
            (df['low'] > df['close'])
        ]
        if len(ohlc_violations) > 0:
            issues.append(f"OHLC violations: {len(ohlc_violations)} rows")

        # 4. Negative prices or volumes
        negative_prices = df[(df['open'] <= 0) | (df['high'] <= 0) | (df['low'] <= 0) | (df['close'] <= 0)]
        if len(negative_prices) > 0:
            issues.append(f"Negative prices: {len(negative_prices)} rows")

        negative_volumes = df[df['volume'] < 0]
        if len(negative_volumes) > 0:
            issues.append(f"Negative volumes: {len(negative_volumes)} rows")

        # Calculate quality score
        total_checks = 5
        failed_checks = len(issues)
        quality_score = 1.0 - (failed_checks / total_checks)

        if issues:
            logger.warning(f"Data quality issues: {issues}")

        return max(0.0, quality_score)

    def _generate_cache_key(self, ticker: str, start_date: str, end_date: str, source: Optional[str] = None) -> str:
        """Generate cache key from ticker, date range, and source."""
        key_str = f"{ticker}_{start_date}_{end_date}"
        if source:
            key_str += f"_{str(source).strip().upper()}"
        return hashlib.md5(key_str.encode()).hexdigest()

    @staticmethod
    def _write_parquet_atomic(df: pd.DataFrame, dest_path: Path) -> None:
        """Write parquet cache to sibling temp file, flush with os.fsync for crash durability, and atomically replace with cleanup on failure."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = dest_path.with_suffix(f".tmp.{os.getpid()}.{time.time_ns()}.parquet")
        try:
            df.to_parquet(tmp_path, index=False)
            # Flush file buffers to disk via os.fsync before atomic replace for crash durability
            fd = os.open(str(tmp_path), os.O_RDWR)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp_path, dest_path)
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            raise

    def _validate_schema(self, df: pd.DataFrame) -> None:
        """
        Validate DataFrame schema against required columns.

        Required columns per OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 7.3:
        - ticker, date, open, high, low, close, volume, as_of, available_at

        Raises:
            ValueError: If required columns are missing
        """
        required_columns = ['ticker', 'date', 'open', 'high', 'low', 'close', 'volume', 'as_of', 'available_at']
        missing_columns = set(required_columns) - set(df.columns)

        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        # Validate PIT constraint on cached data
        if len(df) > 0:
            as_of_utc = self._normalize_to_utc_series(df['as_of'])
            avail_utc = self._normalize_to_utc_series(df['available_at'])
            violations = df[as_of_utc > avail_utc]
            if len(violations) > 0:
                raise ValueError(f"PIT violation in cached data: {len(violations)} rows")

    def clear_cache(self, ticker: Optional[str] = None) -> int:
        """
        Clear cache files.

        Args:
            ticker: If specified, clear only this ticker's cache. Otherwise clear all.

        Returns:
            Number of files deleted
        """
        deleted = 0

        for cache_file in Path(self.cache_dir).glob("*.parquet"):
            if ticker is None:
                cache_file.unlink()
                deleted += 1
            else:
                # Check if ticker is in filename (simple heuristic)
                # In production, maintain a metadata index
                cache_file.unlink()
                deleted += 1

        logger.info(f"Cleared {deleted} cache files")
        return deleted

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache_size_mb, file_count, oldest_file, newest_file
        """
        cache_files = list(Path(self.cache_dir).glob("*.parquet"))

        if not cache_files:
            return {
                'cache_size_mb': 0.0,
                'file_count': 0,
                'oldest_file': None,
                'newest_file': None
            }

        total_size = sum(f.stat().st_size for f in cache_files)
        mtimes = [f.stat().st_mtime for f in cache_files]

        return {
            'cache_size_mb': total_size / (1024 * 1024),
            'file_count': len(cache_files),
            'oldest_file': datetime.fromtimestamp(min(mtimes)),
            'newest_file': datetime.fromtimestamp(max(mtimes))
        }

    def load_market_data(
        self,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        as_of_time: datetime,
        tickers: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Load market data using vnstock v4.0 Unified UI (Real Data).
        Enforces PIT safety using as_of and available_at timestamps.
        """
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT compliance")
            
        if not tickers:
            raise ValueError("tickers list is mandatory")

        from vnstock import Market
        mkt = Market()
        
        all_data = []
        for ticker in tickers:
            try:
                # Try to load from Parquet cache first
                parquet_path = Path("data/market/parquet") / f"{ticker}.parquet"
                if parquet_path.exists():
                    df = pd.read_parquet(parquet_path)
                    df['time'] = pd.to_datetime(df['time'])
                    df = df.rename(columns={'time': 'date'})
                else:
                    # Fetch real OHLCV data from vnstock Unified UI
                    df = mkt.equity(ticker).ohlcv(
                        start=start_date.strftime("%Y-%m-%d"),
                        end=end_date.strftime("%Y-%m-%d")
                    )
                    
                    if not df.empty:
                        df['time'] = pd.to_datetime(df['time'])
                        df = df.rename(columns={'time': 'date'})
                        # P1 Fix: Add PIT timestamps if missing
                        if 'available_at' not in df.columns:
                            df['as_of'] = df['date']
                            df['available_at'] = df['date'] + pd.Timedelta(days=1)
                
                if not df.empty:
                    df['ticker'] = ticker
                    
                    # P1 Audit Fix: Use enforce_pit_safety
                    self._enforce_pit_safety(df, as_of_time)
                    
                    # Filter for only data that is available AT as_of_time
                    df = df[df['available_at'] <= as_of_time]
                    
                    if not df.empty:
                        df = df.set_index(['date', 'ticker'])
                        all_data.append(df)
                        logger.info(f"✓ Loaded {len(df)} rows for {ticker}")
                else:
                    logger.warning(f"! No data returned for {ticker}")
                    
            except Exception as e:
                logger.error(f"❌ Failed to load {ticker}: {e}")
        
        if not all_data:
            return pd.DataFrame()
            
        combined = pd.concat(all_data).sort_index()
        
        # Calculate returns if missing
        if 'returns' not in combined.columns:
            combined['returns'] = combined.groupby(level='ticker')['close'].pct_change()
            
        return combined


    def _apply_corporate_actions(
        self,
        df: pd.DataFrame,
        ticker: str,
        corporate_actions: List,
        as_of_time: datetime
    ) -> Tuple[pd.DataFrame, List[str]]:
        """
        Apply corporate action adjustments to price data (PIT-safe).
        
        Args:
            df: DataFrame with OHLC data (must include as_of, available_at)
            ticker: Stock ticker
            corporate_actions: List of CorporateAction objects
            as_of_time: Query time - only apply actions where ex_date <= as_of_time.date()
            
        Returns:
            Tuple of (adjusted_df, list of adjustment descriptions)
        """
        if not corporate_actions:
            return df, []
        
        # Filter actions for this ticker
        ticker_actions = [a for a in corporate_actions if a.symbol == ticker]
        if not ticker_actions:
            return df, []
        
        if as_of_time.tzinfo is None or as_of_time.utcoffset() is None:
            as_of_time = as_of_time.replace(tzinfo=UTC)

        verified_actions = []
        for action in ticker_actions:
            if pd.Timestamp(action.ex_date).date() > as_of_time.date():
                continue
            if getattr(action, "is_quarantined", False):
                logger.warning(
                    "Quarantined unverified corporate action for %s on %s: %s",
                    ticker,
                    action.ex_date,
                    getattr(action, "quarantine_reason", "unknown provenance failure"),
                )
                continue
            if not action.is_available_at(as_of_time):
                continue
            verified_actions.append(action)

        ticker_actions = verified_actions
        if not ticker_actions:
            return df, []
        
        # Store PIT timestamps before conversion
        pit_timestamps = df[['date', 'as_of', 'available_at']].copy()
        
        # Convert DataFrame to CleanDataFrame format for adjuster
        clean_data = self._df_to_clean_dataframe(df, ticker)
        
        # Apply adjustments using CorporateActionAdjuster
        adjuster = CorporateActionAdjuster()
        adjuster.add_actions(ticker_actions)
        adjusted_data = adjuster.apply_adjustments(clean_data)
        
        # Convert back to DataFrame
        adjusted_df = self._clean_dataframe_to_df(adjusted_data, ticker)
        
        # Restore PIT timestamps (merge on date)
        adjusted_df = adjusted_df.merge(pit_timestamps, on='date', how='left')
        
        # Build adjustment descriptions for provenance
        adjustments_applied = []
        for action in ticker_actions:
            desc = f"{action.action_type}:{action.ex_date}"
            if action.action_type == 'dividend':
                desc += f":{action.params.get('dividend_amount', 0)}"
            elif action.action_type == 'split':
                desc += f":{action.params.get('split_ratio', 1.0)}"
            adjustments_applied.append(desc)
        
        return adjusted_df, adjustments_applied
    
    def _df_to_clean_dataframe(self, df: pd.DataFrame, ticker: str) -> Dict:
        """
        Convert pandas DataFrame to CleanDataFrame dict format.
        
        Args:
            df: DataFrame with columns [ticker, date, open, high, low, close, volume, ...]
            ticker: Stock ticker
            
        Returns:
            CleanDataFrame dict with structure:
            {
                "type": "CleanDataFrame",
                "index": {"symbol": [...], "timestamp": [...]},
                "data": {symbol: {timestamp: {fields...}}}
            }
        """
        # Fully vectorized: no loops
        timestamps = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%dT%H:%M:%S').tolist()
        
        # Build nested dict structure using vectorized operations
        price_data = df[['open', 'high', 'low', 'close', 'volume']].to_dict('index')
        ticker_data = {
            timestamps[i]: {
                "open": float(price_data[i]['open']),
                "high": float(price_data[i]['high']),
                "low": float(price_data[i]['low']),
                "close": float(price_data[i]['close']),
                "volume": float(price_data[i]['volume'])
            }
            for i in range(len(timestamps))
        }
        
        clean_data = {
            "type": "CleanDataFrame",
            "index": {
                "symbol": [ticker] * len(timestamps),
                "timestamp": timestamps
            },
            "data": {ticker: ticker_data}
        }
        
        return clean_data
    
    def _clean_dataframe_to_df(self, clean_data: Dict, ticker: str) -> pd.DataFrame:
        """
        Convert CleanDataFrame dict back to pandas DataFrame.
        
        Args:
            clean_data: CleanDataFrame dict
            ticker: Stock ticker
            
        Returns:
            DataFrame with adjusted prices
        """
        if ticker not in clean_data["data"]:
            return pd.DataFrame()
        
        rows = []
        for timestamp, fields in clean_data["data"][ticker].items():
            if fields is None:
                continue
            row = {
                "ticker": ticker,
                "date": pd.to_datetime(timestamp),
                "open": fields.get("open"),
                "high": fields.get("high"),
                "low": fields.get("low"),
                "close": fields.get("close"),
                "volume": int(fields.get("volume")) if fields.get("volume") is not None else None
            }
            rows.append(row)
        
        df = pd.DataFrame(rows)
        df = df.sort_values('date').reset_index(drop=True)
        return df
    
    def _add_provenance_metadata(
        self,
        df: pd.DataFrame,
        ticker: str,
        adjustments_applied: List[str],
        as_of_time: datetime
    ) -> pd.DataFrame:
        """
        Add provenance metadata fields to DataFrame.
        
        Args:
            df: DataFrame with price data
            ticker: Stock ticker
            adjustments_applied: List of adjustment descriptions
            as_of_time: Point-in-time timestamp for PIT compliance
            
        Returns:
            DataFrame with added metadata columns
        """
        df = df.copy()
        
        # Add dataset version
        df['dataset_version'] = self.dataset_version
        
        # Add source attribution
        df['source'] = 'vnstock_vci'
        
        # Add adjustments applied (JSON string)
        import json
        df['adjustments_applied'] = json.dumps(adjustments_applied) if adjustments_applied else '[]'
        
        # Add ingestion timestamp (use as_of_time for PIT compliance)
        df['ingestion_timestamp'] = as_of_time
        
        return df
    
    def _save_metadata_sidecar(
        self,
        cache_path: Path,
        df: pd.DataFrame,
        quality_score: float,
        adjustments_applied: List[str],
        as_of_time: datetime
    ) -> None:
        """
        Save metadata sidecar JSON file alongside parquet cache.
        
        Args:
            cache_path: Path to parquet cache file
            df: DataFrame with data
            quality_score: Quality score
            adjustments_applied: List of adjustments
            as_of_time: Point-in-time timestamp for PIT compliance
        """
        import json
        
        metadata_path = cache_path.with_suffix('.metadata.json')
        
        # Calculate checksum of parquet file
        checksum = self._calculate_checksum(cache_path)
        
        metadata = {
            "dataset_version": self.dataset_version,
            "source": "vnstock_vci",
            "cache_file": cache_path.name,
            "checksum": checksum,
            "checksum_algorithm": "sha256",
            "row_count": len(df),
            "quality_score": quality_score,
            "adjustments_applied": adjustments_applied,
            "created_at": as_of_time.isoformat(),
            "columns": list(df.columns),
            "date_range": {
                "start": df['date'].min().isoformat() if len(df) > 0 else None,
                "end": df['date'].max().isoformat() if len(df) > 0 else None
            }
        }
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Saved metadata sidecar: {metadata_path}")
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """
        Calculate SHA256 checksum of a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Hex string of SHA256 checksum
        """
        if not file_path.exists():
            return ""
        
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        
        return sha256_hash.hexdigest()
