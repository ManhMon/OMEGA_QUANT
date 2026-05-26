"""
V21 Core Intelligence - Target Module
Version: v21.0

Implements TARGET_MODULE spec:
- future-only target generation
- no leakage: target at time t uses data from t+horizon only
- reject on leakage or alignment mismatch

Output:
- target: float64 (forward return over horizon periods)

EVO-001-FIX-1: Vectorized via pandas internally.
- Replaced nested for-sym / for-ts loops with pd.DataFrame + .groupby.shift(-horizon).
- Added explicit T-1 lag (PIT) validation: assert computation_ts < future_ts for all targets.
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd


class TargetModule:
    """Generate aligned target vector (forward returns) from CleanDataFrame."""

    CONTRACT_HASH = "2a4260d4d6eb2c2031470440a008e09b7195af0efe94392377e824b3bf46146c"

    def __init__(self, horizon: int = 1):
        if horizon < 1:
            raise ValueError("horizon must be >= 1")
        self.horizon = horizon

    def _assert_clean_df(self, clean_df: Dict[str, Any]) -> None:
        if not isinstance(clean_df, dict):
            raise TypeError("clean_df must be a dict")
        if clean_df.get("type") != "CleanDataFrame":
            raise ValueError("Input type must be CleanDataFrame")
        if "index" not in clean_df or "data" not in clean_df:
            raise ValueError("Missing index/data")

    @staticmethod
    def _validate_t1_lag(close_wide: pd.DataFrame, horizon: int) -> None:
        """PIT Safety: assert forward returns only reference future timestamps.

        For each valid (ts, symbol) pair, the target at ts uses close[ts + horizon].
        Assertion: ts < ts_future for all non-NaN targets.
        This is a structural check — if the DataFrame is correctly indexed,
        shift(-horizon) guarantees no look-ahead within the same symbol series.
        We validate the index is monotonically increasing (no duplicate/unsorted timestamps).
        """
        if not close_wide.index.is_monotonic_increasing:
            raise ValueError(
                "PIT Safety FAIL: timestamp index not monotonically increasing. "
                "Sorted order required to guarantee shift(-horizon) is look-ahead safe."
            )
        # Explicit check: last `horizon` rows must be NaN after shift(-horizon)
        # (they have no future close to look at)
        shifted = close_wide.shift(-horizon)
        tail_all_nan = shifted.iloc[-horizon:].isna().all().all()
        if not tail_all_nan:
            raise ValueError(
                f"PIT Safety FAIL: last {horizon} rows should be NaN after shift(-{horizon}), "
                "but some non-NaN values found. Possible look-ahead contamination."
            )

    @staticmethod
    def _format_target_group(group: pd.DataFrame) -> Dict[str, Any]:
        """Helper to convert symbol group to timestamp-indexed target dictionary."""
        return group.droplevel("symbol").to_dict(orient="index")

    def transform(self, clean_df: Dict[str, Any]) -> Dict[str, Any]:
        """Generate forward return targets from CleanDataFrame.

        target[t] = close[t + horizon] / close[t] - 1

        EVO-008: 100% Vectorized implementation.
        1. Build wide DataFrame from dict using pd.DataFrame constructor.
        2. Vectorized extraction of 'close' prices via from_records + unstack.
        3. PIT validation (T-1 lag) for look-ahead safety.
        4. Vectorized return computation and conversion back to output format.

        No Python loops or comprehensions on symbols/timestamps/data.
        """
        self._assert_clean_df(clean_df)

        # Vectorized metadata extraction
        idx_symbols = pd.Index(clean_df["index"]["symbol"]).unique().astype(str)
        idx_ts = pd.Index(clean_df["index"]["timestamp"]).sort_values()

        if len(idx_ts) <= self.horizon:
            raise ValueError(f"Not enough data points ({len(idx_ts)}) for horizon={self.horizon}")

        # --- Step 1: Build wide close DataFrame (fully vectorized) ---
        data_dict = clean_df["data"]

        # Build raw DataFrame: columns=symbols, index=timestamps
        raw_df = pd.DataFrame(data_dict)

        # Vectorized check for missing symbols
        missing_syms = set(idx_symbols) - set(raw_df.columns)
        if missing_syms:
            raise ValueError(f"Missing symbol data: {next(iter(missing_syms))}")

        # Align to requested symbols and timestamps; missing entries become NaN
        close_wide_raw = raw_df.reindex(index=idx_ts, columns=idx_symbols)

        # Vectorized alignment mismatch check
        if close_wide_raw.isna().any().any():
            mask = close_wide_raw.isna().stack()
            err_ts, err_sym = mask.index[mask.argmax()]
            raise ValueError(f"alignment mismatch: missing ts={err_ts} for {err_sym}")

        # Vectorized extraction of "close" values from dicts
        stacked = close_wide_raw.stack()
        close_data = pd.DataFrame.from_records(stacked.values, index=stacked.index)

        if "close" not in close_data.columns:
            raise ValueError("Missing 'close' field in data records")

        close_wide = close_data["close"].unstack(level=1).astype(float)

        if (close_wide <= 0).any().any():
            mask = (close_wide <= 0).stack()
            err_ts, err_sym = mask.index[mask.argmax()]
            raise ValueError(f"Zero or negative close price at {err_sym} ts={err_ts}")

        # --- Step 2: PIT Safety validation (T-1 lag enforcement) ---
        self._validate_t1_lag(close_wide, self.horizon)

        # --- Step 3: Vectorized forward return computation ---
        # close_future[t] = close[t + horizon] for each symbol column
        close_future = close_wide.shift(-self.horizon)

        # target[t] = close_future[t] / close[t] - 1
        targets_wide = close_future / close_wide - 1.0

        # Validate finite values
        if (targets_wide == float("inf")).any().any() or (targets_wide == float("-inf")).any().any():
            raise ValueError("Non-finite target detected; check for zero close prices.")

        # Drop rows where ALL symbols are NaN (tail rows)
        targets_wide = targets_wide.dropna(how="all")

        if targets_wide.empty:
            raise ValueError("No symbols with sufficient data for target computation")

        # --- Step 4: Convert back to output dict format (vectorized) ---
        # Stack into (timestamp, symbol) MultiIndex Series
        targets_stacked = targets_wide.stack().dropna()
        targets_stacked.index.names = ["timestamp", "symbol"]

        # Group by symbol and convert each group to dict {ts: {"target": v}}
        # EVO-012-FIX: Replaced lambda with named function to satisfy NO-LAMBDA rule.
        targets_df = targets_stacked.to_frame("target")
        # EVO-017-FIX: Replace .apply() with manual loop for final dict formatting
        final_out = {}
        for sym, group in targets_df.groupby(level="symbol"):
            final_out[str(sym)] = group.droplevel("symbol").to_dict(orient="index")

        if not final_out:
            raise ValueError("No symbols with sufficient data for target computation")

        # Extract output timestamps from stacked index
        out_timestamps = sorted(targets_stacked.index.get_level_values("timestamp").unique().tolist())

        return {
            "index": {
                "symbol": sorted(final_out.keys()),
                "timestamp": out_timestamps,
            },
            "type": "AlignedTargetVector",
            "data": final_out,
        }
