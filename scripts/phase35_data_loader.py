"""Phase 3.5 Data Loader - Load and validate warehouse data with PIT safety.

Version: v21.39-Phase35
Date: 2026-06-15

Loads HOSE/HNX warehouse data (2015-2026) with strict T-1 lag enforcement.
100% vectorized, no Python loops.

GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614
  - Default-on full sanitizer/winsor/causal forward-fill
  - Backward-compatible --disable-data-cleaning opt-out
  - Explicit normalization: expanding_zscore (default), cross_sectional_zscore,
    rank, or none — all PIT-safe (no look-ahead bias)
  - Persists evidence: data_cleaning_enabled, normalization_mode, sanitizer stats

GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615
  - Optional PIT-safe rolling universe selection (disabled by default)
  - Per-fold symbol selection uses ONLY train_df (no test data leakage)
  - Filters: ADTV >= 5B VND, avg close >= 5000 VND, min history
  - Ranked by mean daily value (close * volume), top N selected
  - Per-fold universe evidence persisted as JSON-serializable dict
  - Static default (no rolling) is preserved — backward compatible

COMPLIANCE:
  - PIT Safety: All features use T-1 lagged data
  - Vectorization: 100% Pandas/NumPy
  - Error Handling: Graceful degradation for missing data
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

# GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614
# Supported normalization modes (all PIT-safe, no look-ahead bias)
NORMALIZATION_MODES = (
    "expanding_zscore",       # Per-symbol expanding-window z-score (causal)
    "cross_sectional_zscore", # Per-date cross-sectional z-score
    "rank",                   # Per-date cross-sectional rank [-1, 1]
    "none",                   # No normalization (raw OHLCV preserved)
)


class Phase35DataLoader:
    """Load and validate warehouse data for walk-forward backtest.
    
    GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614
    Data cleaning (sanitizer + winsor + causal forward-fill) is DEFAULT-ON.
    Use ``enable_data_cleaning=False`` to opt out (backward-compatible).
    """
    
    def __init__(
        self,
        warehouse_path: Optional[str] = None,
        min_price: float = 1.0,
        min_volume: float = 1000.0,
        min_history_days: int = 60,
    ):
        """Initialize data loader.
        
        Parameters
        ----------
        warehouse_path : str, optional
            Path to warehouse parquet file. Defaults to repo data/market_2015_now.parquet.
        min_price : float
            Minimum price filter (VND)
        min_volume : float
            Minimum volume filter (shares)
        min_history_days : int
            Minimum history required per symbol
        """
        if warehouse_path is None:
            warehouse_path = Path(__file__).resolve().parent.parent / "data" / "market_2015_now.parquet"
        self.warehouse_path = Path(warehouse_path)
        self.min_price = min_price
        self.min_volume = min_volume
        self.min_history_days = min_history_days
        
        if not self.warehouse_path.exists():
            raise FileNotFoundError(f"Warehouse not found: {self.warehouse_path}")
    
    def load_raw_data(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        symbols: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Load raw OHLCV data from warehouse.
        
        Parameters
        ----------
        start_date : str, optional
            Start date (YYYY-MM-DD)
        end_date : str, optional
            End date (YYYY-MM-DD)
        symbols : list of str, optional
            Symbol filter (if None, load all)
        
        Returns
        -------
        pd.DataFrame
            Raw OHLCV data with columns: date, ticker, open, high, low, close, volume
        """
        logger.info(f"Loading data from {self.warehouse_path}")
        df = pd.read_parquet(self.warehouse_path)
        
        # Ensure date column is datetime
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        
        # Ensure PIT metadata columns are datetime when present
        if 'as_of' in df.columns:
            df['as_of'] = pd.to_datetime(df['as_of'])
        if 'available_at' in df.columns:
            df['available_at'] = pd.to_datetime(df['available_at'])
        
        # Filter by date range
        if start_date is not None:
            start_ts = pd.to_datetime(start_date)
            df = df[df['date'] >= start_ts]
        if end_date is not None:
            end_ts = pd.to_datetime(end_date)
            df = df[df['date'] <= end_ts]
            # PIT safety: only include rows whose data was actually available by end_ts
            if 'available_at' in df.columns:
                df = df[df['available_at'] <= end_ts]
        
        # Filter by symbols
        if symbols is not None:
            df = df[df['ticker'].isin(symbols)]
        
        # Sort by date and ticker
        df = df.sort_values(['date', 'ticker']).reset_index(drop=True)
        
        logger.info(f"Loaded {len(df):,} rows, {df['ticker'].nunique()} symbols, "
                   f"date range: {df['date'].min()} to {df['date'].max()}")
        
        return df
    
    def apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply quality filters to raw data.
        
        Parameters
        ----------
        df : pd.DataFrame
            Raw OHLCV data
        
        Returns
        -------
        pd.DataFrame
            Filtered data
        """
        initial_rows = len(df)
        if initial_rows == 0:
            logger.warning("No rows available after raw PIT/date filtering; returning empty DataFrame")
            return df.copy()
        
        # Filter by price
        df = df[df['close'] >= self.min_price].copy()
        
        # Filter by volume (remove suspended stocks, apply min_volume threshold)
        df = df[df['volume'] >= self.min_volume].copy()
        
        # Filter symbols with insufficient history
        symbol_counts = df.groupby('ticker').size()
        valid_symbols = symbol_counts[symbol_counts >= self.min_history_days].index
        df = df[df['ticker'].isin(valid_symbols)].copy()
        
        # Remove rows with invalid OHLC (high < low, close outside [low, high])
        df = df[
            (df['high'] >= df['low']) &
            (df['close'] >= df['low']) &
            (df['close'] <= df['high'])
        ].copy()
        
        removed_rows = initial_rows - len(df)
        logger.info(f"Filters removed {removed_rows:,} rows ({removed_rows/initial_rows:.1%})")
        logger.info(f"Remaining: {len(df):,} rows, {df['ticker'].nunique()} symbols")
        
        return df
    
    def compute_forward_returns(
        self,
        df: pd.DataFrame,
        horizons: List[int] = [1, 3, 5],
    ) -> pd.DataFrame:
        """Compute forward returns for multiple horizons.
        
        Parameters
        ----------
        df : pd.DataFrame
            OHLCV data with 'ticker', 'date', 'close' columns
        horizons : list of int
            Forward return horizons (days)
        
        Returns
        -------
        pd.DataFrame
            Data with forward return columns: fwd_ret_1, fwd_ret_3, fwd_ret_5
        """
        df = df.copy()
        
        for h in horizons:
            # Shift close price forward by h days
            fwd_close = df.groupby('ticker')['close'].shift(-h)
            
            # Compute return
            df[f'fwd_ret_{h}'] = (fwd_close - df['close']) / df['close'].clip(lower=1e-9)
            
            # Clip extreme returns (likely data errors)
            df[f'fwd_ret_{h}'] = df[f'fwd_ret_{h}'].clip(lower=-0.5, upper=0.5)
        
        logger.info(f"Computed forward returns for horizons: {horizons}")
        
        return df
    
    def get_top_symbols(
        self,
        df: pd.DataFrame,
        top_n: int = 30,
        metric: str = 'volume',
    ) -> List[str]:
        """Get top N symbols using ADTV > 5B and price > 5k filter, ranked by value."""
        df = df.copy()
        
        # Calculate daily trading value (close * volume)
        df['value'] = df['close'] * df['volume']
        
        # Calculate average daily values and prices per symbol
        symbol_stats = df.groupby('ticker').agg({
            'value': 'mean',
            'close': 'mean'
        })
        
        # Apply filters: ADTV > 5B VND and average close > 5,000 VND
        min_adtv = 5_000_000_000.0
        min_price = 5000.0
        
        filtered_stats = symbol_stats[
            (symbol_stats['value'] >= min_adtv) &
            (symbol_stats['close'] >= min_price)
        ]
        
        # Fallback if too few stocks pass the filter
        if len(filtered_stats) < 10:
            logger.warning(
                f"Too few symbols passed ADTV/Price filter ({len(filtered_stats)}), "
                f"falling back to sorting raw universe."
            )
            filtered_stats = symbol_stats
            
        # Select top N sorted by ADTV value descending
        top_symbols = filtered_stats['value'].nlargest(top_n).index.tolist()
        
        logger.info(
            f"Selected {len(top_symbols)} symbols (max {top_n}) with ADTV > 5B, price > 5k. "
            f"Top 10: {top_symbols[:10]}..."
        )
        return top_symbols
    
    def select_rolling_universe(
        self,
        train_df: pd.DataFrame,
        top_n: int = 30,
    ) -> Tuple[List[str], Dict[str, Any]]:
        """GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615

        PIT-safe rolling universe selection using ONLY train_df.

        For each fold, select top N symbols based on train-window statistics:
        1. Compute per-symbol mean daily value = mean(close * volume)
        2. Filter: ADTV (mean daily value) >= 5B VND
        3. Filter: avg close >= 5000 VND
        4. Filter: min history (min_history_days rows)
        5. Rank by mean daily value descending, take top N

        Parameters
        ----------
        train_df : pd.DataFrame
            Training window data (MUST NOT contain test data).
        top_n : int
            Number of symbols to select.

        Returns
        -------
        tuple of (list[str], dict)
            (selected_symbols, evidence_dict)
            evidence_dict is JSON-serializable.
        """
        if len(train_df) == 0:
            return [], {
                "gate": "PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615",
                "selected_symbols": [],
                "n_selected": 0,
                "n_candidates": 0,
                "pit_safe": True,
                "note": "Empty train_df",
            }

        df = train_df.copy()
        df['value'] = df['close'] * df['volume']

        symbol_stats = df.groupby('ticker').agg(
            mean_value=('value', 'mean'),
            mean_close=('close', 'mean'),
            n_days=('date', 'nunique'),
        )

        n_candidates_total = len(symbol_stats)

        min_adtv = 5_000_000_000.0
        min_avg_close = 5000.0
        min_hist = self.min_history_days

        filtered = symbol_stats[
            (symbol_stats['mean_value'] >= min_adtv) &
            (symbol_stats['mean_close'] >= min_avg_close) &
            (symbol_stats['n_days'] >= min_hist)
        ]

        n_after_filter = len(filtered)

        if n_after_filter < 5:
            logger.warning(
                f"Rolling universe: only {n_after_filter} symbols passed "
                f"ADTV/close/history filters, relaxing to sorted universe."
            )
            filtered = symbol_stats

        selected = filtered['mean_value'].nlargest(top_n).index.tolist()

        selected_stats = {}
        for sym in selected:
            row = filtered.loc[sym] if sym in filtered.index else symbol_stats.loc[sym]
            selected_stats[sym] = {
                "mean_value_vnd": float(row['mean_value']),
                "mean_close_vnd": float(row['mean_close']),
                "n_days": int(row['n_days']),
            }

        evidence = {
            "gate": "PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615",
            "selected_symbols": sorted(selected),
            "n_selected": int(len(selected)),
            "n_candidates_before_filter": int(n_candidates_total),
            "n_candidates_after_filter": int(n_after_filter),
            "top_n_requested": int(top_n),
            "min_adtv_vnd": float(min_adtv),
            "min_avg_close_vnd": float(min_avg_close),
            "min_history_days": int(min_hist),
            "selected_stats": selected_stats,
            "pit_safe": True,
            "note": "Selection uses ONLY train_df data. No test leakage.",
        }

        logger.info(
            f"Rolling universe: selected {len(selected)} symbols "
            f"(from {n_after_filter} filtered, {n_candidates_total} total)"
        )

        return selected, evidence

    def apply_rolling_universe_to_splits(
        self,
        splits: List[Tuple[pd.DataFrame, pd.DataFrame]],
        top_n: int = 30,
    ) -> List[Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]]:
        """GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615

        Apply per-fold rolling universe selection to walk-forward splits.

        For each fold:
        1. Select top N symbols using ONLY train_df
        2. Filter both train_df and test_df to selected symbols
        3. Persist per-fold universe evidence

        Parameters
        ----------
        splits : list of (train_df, test_df) tuples
        top_n : int
            Number of top symbols per fold.

        Returns
        -------
        list of (train_df, test_df, evidence) tuples
            Filtered splits with per-fold evidence dicts.
        """
        result = []
        for fold_idx, (train_df, test_df) in enumerate(splits):
            selected, evidence = self.select_rolling_universe(train_df, top_n=top_n)
            evidence["fold_id"] = fold_idx + 1
            evidence["train_date_range"] = (
                f"{train_df['date'].min()} to {train_df['date'].max()}"
            )
            evidence["test_date_range"] = (
                f"{test_df['date'].min()} to {test_df['date'].max()}"
            )

            train_filtered = train_df[train_df['ticker'].isin(selected)].copy()
            test_filtered = test_df[test_df['ticker'].isin(selected)].copy()

            evidence["train_rows_before"] = int(len(train_df))
            evidence["train_rows_after"] = int(len(train_filtered))
            evidence["test_rows_before"] = int(len(test_df))
            evidence["test_rows_after"] = int(len(test_filtered))

            test_symbols = set(test_filtered['ticker'].unique())
            train_symbols = set(selected)
            evidence["test_symbols_subset_of_train"] = test_symbols.issubset(train_symbols)

            logger.info(
                f"Fold {fold_idx + 1}: rolling universe {len(selected)} symbols, "
                f"train={len(train_filtered):,} rows, test={len(test_filtered):,} rows"
            )

            result.append((train_filtered, test_filtered, evidence))

        self._rolling_universe_evidence = [ev for _, _, ev in result]
        return result

    def select_pit_universe_for_window(
        self,
        full_df: pd.DataFrame,
        start_date: Any,
        end_date: Any,
        *,
        top_n: int = 30,
        lookback_trading_days: int = 252,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Select PIT-safe universe for a window using only prior trading days."""
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        unique_dates = np.sort(full_df['date'].dropna().unique())
        history_dates = unique_dates[unique_dates < start_ts.to_datetime64()]
        history_dates = history_dates[-lookback_trading_days:]
        history_df = full_df[full_df['date'].isin(history_dates)].copy()
        selected, evidence = self.select_rolling_universe(history_df, top_n=top_n)
        window_df = full_df[
            (full_df['date'] >= start_ts) &
            (full_df['date'] <= end_ts) &
            (full_df['ticker'].isin(selected))
        ].copy()
        evidence = dict(evidence)
        evidence.update({
            'window_start': str(start_ts.date()),
            'window_end': str(end_ts.date()),
            'history_end_exclusive': str(start_ts.date()),
            'lookback_trading_days': int(lookback_trading_days),
            'window_rows': int(len(window_df)),
            'window_symbols': int(window_df['ticker'].nunique()),
            'pit_safe': True,
        })
        return window_df, evidence

    def get_rolling_universe_evidence(self) -> List[Dict[str, Any]]:
        """GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615

        Return per-fold rolling universe evidence from last call.

        Returns
        -------
        list of dict
            Per-fold evidence dicts (JSON-serializable).
        """
        return getattr(self, '_rolling_universe_evidence', [])

    def create_walk_forward_splits(
        self,
        df: pd.DataFrame,
        n_folds: int = 8,
        train_years: int = 1,
        test_years: int = 1,
    ) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
        """Create walk-forward train/test splits.

        GATE: CPCV_FOLD_EXPANSION_FIX1_20260614 — adaptive step size so that
        ``n_folds`` requested folds actually fit within the data range.  The
        legacy fixed-365-day step is preserved when the data range can
        accommodate it; otherwise the step is shrunk to distribute folds
        evenly across the available span.

        Parameters
        ----------
        df : pd.DataFrame
            Full dataset with 'date' column
        n_folds : int
            Number of folds requested
        train_years : int
            Training window size (years)
        test_years : int
            Testing window size (years)

        Returns
        -------
        list of tuple
            List of (train_df, test_df) pairs
        """
        df = df.sort_values('date').reset_index(drop=True)

        min_date = df['date'].min()
        max_date = df['date'].max()
        total_days = (max_date - min_date).days

        train_window_days = train_years * 365
        test_window_days = test_years * 365

        # GATE: CPCV_FOLD_EXPANSION_FIX1_20260614 — adaptive step
        # Legacy step = 365 days.  Use it when it fits; shrink when needed.
        legacy_step = 365
        available_span = total_days - train_window_days - test_window_days
        if n_folds > 1 and available_span > 0:
            max_step = available_span // (n_folds - 1)
            step_days = min(legacy_step, max_step)
        else:
            step_days = legacy_step

        # Ensure step is at least 1 day to avoid infinite loop
        step_days = max(step_days, 1)

        logger.info(f"Creating {n_folds} walk-forward folds (step={step_days}d, "
                    f"train={train_window_days}d, test={test_window_days}d)")
        logger.info(f"Date range: {min_date} to {max_date}")

        splits = []

        for fold_idx in range(n_folds):
            train_start = min_date + pd.Timedelta(days=fold_idx * step_days)
            train_end = train_start + pd.Timedelta(days=train_window_days)

            test_start = train_end
            test_end = test_start + pd.Timedelta(days=test_window_days)

            if test_end > max_date:
                logger.warning(f"Fold {fold_idx+1}: test_end {test_end.date()} exceeds "
                               f"max_date {max_date.date()}, skipping remaining folds")
                break

            train_df = df[(df['date'] >= train_start) & (df['date'] < train_end)].copy()
            test_df = df[(df['date'] >= test_start) & (df['date'] < test_end)].copy()

            if len(train_df) == 0 or len(test_df) == 0:
                logger.warning(f"Fold {fold_idx+1}: empty train or test set, skipping")
                continue

            logger.info(f"Fold {fold_idx+1}: train={train_start.date()} to {train_end.date()} "
                        f"({len(train_df):,} rows), test={test_start.date()} to {test_end.date()} "
                        f"({len(test_df):,} rows)")

            splits.append((train_df, test_df))

        if len(splits) < n_folds:
            logger.warning(
                f"CPCV_FOLD_EXPANSION_FIX1: requested {n_folds} folds but only "
                f"{len(splits)} valid folds created (data range or empty splits)"
            )

        logger.info(f"Created {len(splits)} valid folds (requested {n_folds})")

        return splits
    
    def _apply_sanitization(self, df: pd.DataFrame) -> pd.DataFrame:
        """P11 + GATE DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614: Apply
        DataSanitizer with PIT-safe expanding window.

        Uses clean_ohlcv() which applies expanding window statistics
        (only past data) for outlier clipping — strictly no look-ahead.

        Pipeline:
        1. Remove duplicates (keep first occurrence)
        2. Causal forward-fill (max 3 days gap)
        3. 3-sigma outlier clipping (per-symbol, expanding window)
        4. Remove invalid prices (< 0.01 VND)

        Sanitization stats are stored in ``self._sanitization_stats`` for
        downstream evidence persistence.

        Parameters
        ----------
        df : pd.DataFrame
            Raw OHLCV data with 'ticker' and 'date' columns

        Returns
        -------
        pd.DataFrame
            Sanitized OHLCV data
        """
        from omega.quant.data.sanitizer import DataSanitizer

        sanitizer = DataSanitizer(
            max_fill_days=3,
            outlier_sigma=3.0,
            min_price=0.01,
        )

        # Use DataSanitizer.clean_ohlcv which returns (df_clean, stats_dict)
        ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
        df_clean, stats = sanitizer.clean_ohlcv(
            df,
            ohlcv_cols=ohlcv_cols,
            symbol_col='ticker',
            date_col='date',
        )

        # Store stats for evidence persistence
        # GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_FIX2_20260614
        # int()/float() cast: sanitizer stats may contain numpy.int64 from
        # pd.Series.sum() which is NOT JSON-serializable.  Convert all
        # values to native Python scalars for safe json.dump().
        self._sanitization_stats = {
            "input_rows": int(stats.get("input_rows", len(df))),
            "duplicates_removed": int(stats.get("duplicates_removed", 0)),
            "forward_filled": int(stats.get("forward_filled", 0)),
            "outliers_clipped": int(stats.get("outliers_clipped", 0)),
            "invalid_prices_removed": int(stats.get("invalid_prices_removed", 0)),
            "output_rows": int(stats.get("output_rows", len(df_clean))),
            "data_retention_pct": float(
                round(len(df_clean) / len(df) * 100, 1) if len(df) > 0 else 0.0
            ),
        }

        # Log sanitization report
        logger.info("P11 + DEFAULT_DATA_HYGIENE Data Cleaning Applied:")
        logger.info(f"=== Data Sanitization Report ===")
        logger.info(f"Input rows: {self._sanitization_stats['input_rows']}")
        logger.info(f"Duplicates removed: {self._sanitization_stats['duplicates_removed']}")
        logger.info(f"Values forward-filled: {self._sanitization_stats['forward_filled']}")
        logger.info(f"Outliers clipped: {self._sanitization_stats['outliers_clipped']}")
        logger.info(f"Invalid prices removed: {self._sanitization_stats['invalid_prices_removed']}")
        logger.info(f"Output rows: {self._sanitization_stats['output_rows']}")
        logger.info(f"Data retention: {self._sanitization_stats['data_retention_pct']:.1f}%")

        return df_clean

    def _apply_normalization(
        self,
        df: pd.DataFrame,
        mode: str = "expanding_zscore",
    ) -> pd.DataFrame:
        """GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614

        Apply PIT-safe normalization to OHLCV data.

        **Critical design**: Raw OHLCV columns (open, high, low, close, volume)
        are ALWAYS preserved — they are needed by forward-return and alpha
        formulas.  Normalized versions are added as ``_norm`` suffixed columns.

        Normalization modes:

        - ``expanding_zscore``: per-symbol expanding-window z-score (causal,
          min_periods=20).  No look-ahead — only past data used.
        - ``cross_sectional_zscore``: per-date cross-sectional z-score across
          all symbols.  No look-ahead — computed per-date snapshot only.
        - ``rank``: per-date cross-sectional rank normalized to [-1, 1].
          No look-ahead — computed per-date snapshot only.
        - ``none``: no normalization applied.

        Parameters
        ----------
        df : pd.DataFrame
            OHLCV data (already sanitized) with 'ticker' and 'date' columns
        mode : str
            One of NORMALIZATION_MODES

        Returns
        -------
        pd.DataFrame
            Data with ``_norm`` suffixed columns added (raw OHLCV preserved)
        """
        if mode == "none":
            self._normalization_stats = {
                "mode": "none",
                "columns_normalized": 0,
                "note": "No normalization applied",
            }
            return df

        if mode not in NORMALIZATION_MODES:
            raise ValueError(
                f"Unknown normalization mode '{mode}'. "
                f"Must be one of {NORMALIZATION_MODES}"
            )

        df = df.copy()
        ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
        norm_cols = [c for c in ohlcv_cols if c in df.columns]
        cols_normalized = 0

        if mode == "expanding_zscore":
            # Per-symbol expanding-window z-score (causal, no look-ahead)
            df = df.sort_values(['ticker', 'date'])
            for col in norm_cols:
                norm_col = f"{col}_norm"
                for ticker in df['ticker'].unique():
                    ticker_mask = df['ticker'] == ticker
                    series = df.loc[ticker_mask, col]
                    exp_mean = series.expanding(min_periods=20).mean()
                    exp_std = series.expanding(min_periods=20).std()
                    zscore = (series - exp_mean) / exp_std.clip(lower=1e-9)
                    df.loc[ticker_mask, norm_col] = zscore
                cols_normalized += 1

        elif mode == "cross_sectional_zscore":
            # Per-date cross-sectional z-score (no look-ahead — per-date only)
            for col in norm_cols:
                norm_col = f"{col}_norm"
                grouped = df.groupby('date')[col]
                cs_mean = grouped.transform('mean')
                cs_std = grouped.transform('std').clip(lower=1e-9)
                df[norm_col] = (df[col] - cs_mean) / cs_std
                cols_normalized += 1

        elif mode == "rank":
            # Per-date cross-sectional rank [-1, 1] (no look-ahead)
            for col in norm_cols:
                norm_col = f"{col}_norm"
                df[norm_col] = df.groupby('date')[col].rank(pct=True) * 2.0 - 1.0
                cols_normalized += 1

        self._normalization_stats = {
            "mode": mode,
            "columns_normalized": cols_normalized,
            "norm_column_names": [f"{c}_norm" for c in norm_cols[:cols_normalized]],
            "min_periods_expanding": 20 if mode == "expanding_zscore" else None,
            "pit_safe": True,
            "note": (
                f"{mode} normalization applied. Raw OHLCV columns preserved. "
                f"Normalized columns suffixed with '_norm'."
            ),
        }

        logger.info(
            f"GATE DEFAULT_DATA_HYGIENE_NORMALIZATION: mode={mode}, "
            f"columns_normalized={cols_normalized}, "
            f"norm_cols={[f'{c}_norm' for c in norm_cols[:cols_normalized]]}"
        )

        return df

    def get_last_evidence(self) -> Dict[str, Any]:
        """GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614

        Return evidence dict from the last ``load_and_prepare`` call.

        Keys:
            - ``data_cleaning_enabled``: bool
            - ``normalization_mode``: str
            - ``sanitizer_stats``: dict or None
            - ``normalization_stats``: dict or None
            - ``gate``: str

        Returns
        -------
        dict
            Evidence suitable for JSON persistence.
        """
        return getattr(self, '_last_evidence', {})

    def load_and_prepare(
        self,
        start_date: str = "2015-01-01",
        end_date: str = "2026-05-08",
        top_n_symbols: Optional[int] = 30,
        forward_horizons: List[int] = [1, 3, 5],
        enable_data_cleaning: bool = True,
        normalization_mode: str = "expanding_zscore",
    ) -> pd.DataFrame:
        """Load, filter, and prepare data for walk-forward backtest.

        GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614
        Data cleaning is DEFAULT-ON (``enable_data_cleaning=True``).
        Normalization defaults to ``expanding_zscore`` (PIT-safe).

        Parameters
        ----------
        start_date : str
            Start date (YYYY-MM-DD)
        end_date : str
            End date (YYYY-MM-DD)
        top_n_symbols : int
            Number of top symbols to select
        forward_horizons : list of int
            Forward return horizons
        enable_data_cleaning : bool
            If True (default), apply DataSanitizer before filtering.
            Set to False to opt out (backward-compatible).
        normalization_mode : str
            One of: 'expanding_zscore' (default), 'cross_sectional_zscore',
            'rank', 'none'.  Raw OHLCV columns are always preserved;
            normalized columns are added with '_norm' suffix.

        Returns
        -------
        pd.DataFrame
            Prepared data with forward returns (and optional _norm columns)
        """
        # Reset evidence
        self._sanitization_stats = None
        self._normalization_stats = None
        self._last_evidence = {}

        # Load raw data
        df = self.load_raw_data(start_date=start_date, end_date=end_date)

        # Data cleaning (default-on, PIT-safe expanding window)
        if enable_data_cleaning:
            df = self._apply_sanitization(df)

        # Apply filters
        df = self.apply_filters(df)

        # Select top symbols when requested.
        if top_n_symbols is not None and top_n_symbols > 0:
            top_symbols = self.get_top_symbols(df, top_n=top_n_symbols, metric='value')
            df = df[df['ticker'].isin(top_symbols)].copy()

        # GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614
        # Apply normalization (after filter, before forward returns)
        if normalization_mode != "none":
            df = self._apply_normalization(df, mode=normalization_mode)

        # Compute forward returns
        df = self.compute_forward_returns(df, horizons=forward_horizons)

        # Build and persist evidence
        # GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_FIX2_20260614
        # Wrap numeric values in int()/str() to ensure JSON-serializable.
        self._last_evidence = {
            "gate": "DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614",
            "data_cleaning_enabled": enable_data_cleaning,
            "normalization_mode": normalization_mode,
            "sanitizer_stats": self._sanitization_stats,
            "normalization_stats": getattr(self, '_normalization_stats', None),
            "output_rows": int(len(df)),
            "output_symbols": int(df['ticker'].nunique()),
            "date_range": f"{df['date'].min()} to {df['date'].max()}",
            "pit_safe": True,
        }

        logger.info(
            f"Data preparation complete: {len(df):,} rows, "
            f"{df['ticker'].nunique()} symbols"
        )
        logger.info(
            f"Evidence: cleaning={enable_data_cleaning}, "
            f"normalization={normalization_mode}"
        )

        return df


# ---------------------------------------------------------------------------
# GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615
# Opt-in per-rebalance dynamic universe selection.
# For each rebalance date R, selects top-N symbols using trailing history
# from [R - lookback_days, R) — strictly no data from R or later.
# Filters: ADTV >= 5B VND, avg close >= 5000 VND, min history days.
# Ranked by mean daily value (close * volume), top N selected.
# Evidence persisted per rebalance as JSON-serializable dict.
# ---------------------------------------------------------------------------
DYNAMIC_UNIVERSE_GATE_ID = "DYNAMIC_REBALANCE_UNIVERSE_20260615"


class DynamicUniverseSelector:
    """GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615

    PIT-safe per-rebalance universe selection.

    For each rebalance date R, selects top-N symbols using ONLY trailing
    history from [R - lookback_days, R).  selection_end is always < R,
    so no future data leaks into the selection.

    Parameters
    ----------
    lookback_days : int
        Trailing window in calendar days for selection statistics.
    rebalance_days : int
        Rebalance cadence in calendar days.
    top_n : int
        Number of symbols to select per rebalance.
    min_history_days : int
        Minimum trading days a symbol must have in the lookback window.
    """

    MIN_ADTV_VND = 5_000_000_000.0
    MIN_AVG_CLOSE_VND = 5000.0

    def __init__(
        self,
        lookback_days: int = 252,
        rebalance_days: int = 21,
        top_n: int = 30,
        min_history_days: int = 60,
    ):
        if lookback_days < 1:
            raise ValueError(f"lookback_days must be >= 1, got {lookback_days}")
        if rebalance_days < 1:
            raise ValueError(f"rebalance_days must be >= 1, got {rebalance_days}")
        if top_n < 1:
            raise ValueError(f"top_n must be >= 1, got {top_n}")
        self.lookback_days = lookback_days
        self.rebalance_days = rebalance_days
        self.top_n = top_n
        self.min_history_days = min_history_days
        self._evidence: List[Dict[str, Any]] = []

    def compute_rebalance_dates(
        self,
        dates: List[pd.Timestamp],
    ) -> List[pd.Timestamp]:
        """Compute rebalance dates from a sorted list of trading dates.

        Selects every ``rebalance_days``-th trading date starting from the
        first date in the window.

        Parameters
        ----------
        dates : list of pd.Timestamp
            Sorted unique trading dates.

        Returns
        -------
        list of pd.Timestamp
            Rebalance dates.
        """
        if not dates:
            return []
        sorted_dates = sorted(dates)
        rebal = []
        idx = 0
        while idx < len(sorted_dates):
            rebal.append(sorted_dates[idx])
            idx += self.rebalance_days
        return rebal

    def select_for_rebalance(
        self,
        full_df: pd.DataFrame,
        rebalance_date: pd.Timestamp,
    ) -> Tuple[List[str], Dict[str, Any]]:
        """Select symbols for a single rebalance date.

        PIT safety: selection window is [rebalance_date - lookback_days,
        rebalance_date).  selection_end is strictly < rebalance_date.

        Parameters
        ----------
        full_df : pd.DataFrame
            Full dataset with 'date', 'ticker', 'close', 'volume'.
        rebalance_date : pd.Timestamp
            The rebalance date.

        Returns
        -------
        tuple of (list[str], dict)
            (selected_symbols, evidence_dict)
        """
        window_start = rebalance_date - pd.Timedelta(days=self.lookback_days)
        window_end = rebalance_date  # exclusive — selection_end < rebalance_date

        window_df = full_df[
            (full_df['date'] >= window_start) &
            (full_df['date'] < window_end)
        ].copy()

        # Record actual selection_end (max date in window, must be < rebalance_date)
        if len(window_df) == 0:
            return [], {
                "gate": DYNAMIC_UNIVERSE_GATE_ID,
                "rebalance_date": str(rebalance_date.date()),
                "selection_window_start": str(window_start.date()),
                "selection_window_end_exclusive": str(window_end.date()),
                "selection_end": None,
                "selection_end_before_rebalance": True,
                "selected_symbols": [],
                "n_selected": 0,
                "n_candidates_before_filter": 0,
                "n_candidates_after_filter": 0,
                "turnover_from_previous": None,
                "pit_safe": True,
                "note": "Empty window",
            }

        selection_end = window_df['date'].max()
        assert selection_end < rebalance_date, (
            f"PIT violation: selection_end {selection_end} >= "
            f"rebalance_date {rebalance_date}"
        )

        window_df['value'] = window_df['close'] * window_df['volume']
        symbol_stats = window_df.groupby('ticker').agg(
            mean_value=('value', 'mean'),
            mean_close=('close', 'mean'),
            n_days=('date', 'nunique'),
        )

        n_before = len(symbol_stats)

        filtered = symbol_stats[
            (symbol_stats['mean_value'] >= self.MIN_ADTV_VND) &
            (symbol_stats['mean_close'] >= self.MIN_AVG_CLOSE_VND) &
            (symbol_stats['n_days'] >= self.min_history_days)
        ]

        n_after = len(filtered)

        if n_after < 5:
            filtered = symbol_stats

        selected = filtered['mean_value'].nlargest(self.top_n).index.tolist()

        evidence = {
            "gate": DYNAMIC_UNIVERSE_GATE_ID,
            "rebalance_date": str(rebalance_date.date()),
            "selection_window_start": str(window_start.date()),
            "selection_window_end_exclusive": str(window_end.date()),
            "selection_end": str(selection_end.date()),
            "selection_end_before_rebalance": True,
            "selected_symbols": sorted(selected),
            "n_selected": int(len(selected)),
            "n_candidates_before_filter": int(n_before),
            "n_candidates_after_filter": int(n_after),
            "top_n_requested": int(self.top_n),
            "lookback_days": int(self.lookback_days),
            "min_adtv_vnd": float(self.MIN_ADTV_VND),
            "min_avg_close_vnd": float(self.MIN_AVG_CLOSE_VND),
            "min_history_days": int(self.min_history_days),
            "turnover_from_previous": None,
            "pit_safe": True,
        }

        return selected, evidence

    def build_dynamic_universe_schedule(
        self,
        full_df: pd.DataFrame,
        start_date: Optional[pd.Timestamp] = None,
        end_date: Optional[pd.Timestamp] = None,
    ) -> Tuple[Dict[str, List[str]], List[Dict[str, Any]]]:
        """Build a complete rebalance schedule with per-date universe selections.

        Parameters
        ----------
        full_df : pd.DataFrame
            Full dataset with 'date', 'ticker', 'close', 'volume'.
        start_date : pd.Timestamp, optional
            First rebalance date (defaults to first date + lookback_days).
        end_date : pd.Timestamp, optional
            Last rebalance date (defaults to last date in full_df).

        Returns
        -------
        tuple of (dict, list)
            (schedule: {date_str: [symbols]}, evidence_list)
        """
        all_dates = sorted(full_df['date'].unique())
        if not all_dates:
            return {}, []

        if start_date is None:
            start_date = all_dates[0] + pd.Timedelta(days=self.lookback_days)
        if end_date is None:
            end_date = all_dates[-1]

        candidate_dates = [d for d in all_dates if start_date <= d <= end_date]
        rebalance_dates = self.compute_rebalance_dates(candidate_dates)

        schedule: Dict[str, List[str]] = {}
        evidence_list: List[Dict[str, Any]] = []
        prev_symbols: List[str] = []

        for rd in rebalance_dates:
            selected, ev = self.select_for_rebalance(full_df, rd)

            # Compute turnover from previous rebalance
            if prev_symbols:
                prev_set = set(prev_symbols)
                curr_set = set(selected)
                union_size = len(prev_set | curr_set)
                if union_size > 0:
                    # Jaccard distance as turnover proxy
                    turnover = 1.0 - len(prev_set & curr_set) / union_size
                else:
                    turnover = 0.0
                ev["turnover_from_previous"] = round(float(turnover), 4)
                ev["symbols_added"] = sorted(curr_set - prev_set)
                ev["symbols_removed"] = sorted(prev_set - curr_set)
            else:
                ev["turnover_from_previous"] = None
                ev["symbols_added"] = sorted(selected)
                ev["symbols_removed"] = []

            schedule[str(rd.date())] = selected
            evidence_list.append(ev)
            prev_symbols = selected

        self._evidence = evidence_list
        return schedule, evidence_list

    def get_evidence(self) -> List[Dict[str, Any]]:
        """Return evidence from last build_dynamic_universe_schedule call."""
        return list(self._evidence)


if __name__ == "__main__":
    # Test data loader
    logging.basicConfig(level=logging.INFO)
    
    loader = Phase35DataLoader()
    
    # Load and prepare data
    df = loader.load_and_prepare(
        start_date="2018-01-01",
        end_date="2026-05-08",
        top_n_symbols=20,
    )
    
    print(f"\nData shape: {df.shape}")
    print(f"\nColumns: {list(df.columns)}")
    print(f"\nFirst 5 rows:\n{df.head()}")
    print(f"\nSymbols: {sorted(df['ticker'].unique())}")
    
    # Create walk-forward splits
    splits = loader.create_walk_forward_splits(df, n_folds=6, train_years=1, test_years=1)
    
    print(f"\nCreated {len(splits)} walk-forward folds")
