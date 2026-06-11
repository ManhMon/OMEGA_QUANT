"""
V21 Core Intelligence - Data Module
Version: v21.0
"""

from typing import Any, Dict, List, Optional, Union
import json
import hashlib
from pathlib import Path
from omega.data.corporate_action import CorporateActionAdjuster, CorporateAction
from omega.data.data_validator import DataValidator, ValidationIssue

class DataModule:
    """
    Responsible for ingesting, validating, and transforming raw price data.
    Enforces schema consistency and provides deterministic output.
    """

    CONTRACT_HASH = "6ed1762e6711df69477f37c32a42b13a12532cabc3f77f16cfc43ea90fdcc97a"

    def __init__(self, datasource=None, delisted_metadata_path: Optional[str] = None):
        self._schema = None
        self._cache = {}
        self._datasource = datasource
        self._corp_action_adjuster = CorporateActionAdjuster()
        self._data_validator = DataValidator()
        self._last_validation_issues: List[ValidationIssue] = []
        self._delisted_metadata = self._load_delisted_metadata(delisted_metadata_path)

    def set_datasource(self, datasource):
        """Attach a datasource (e.g., VnstockKBSDataSource)."""
        self._datasource = datasource

    def _load_delisted_metadata(self, path: Optional[str]) -> Dict[str, Any]:
        """Load delisted stock metadata for survivorship-bias-safe backtests."""
        if path:
            candidate_path = Path(path)
        else:
            candidate_path = Path(__file__).resolve().parents[3] / "state" / "delisted_stocks_metadata.json"

        if not candidate_path.exists():
            return {"version": "unknown", "delisted_stocks": []}

        try:
            with candidate_path.open("r", encoding="utf-8-sig") as f:
                payload = json.load(f)
        except Exception:
            return {"version": "unknown", "delisted_stocks": []}

        if not isinstance(payload, dict):
            return {"version": "unknown", "delisted_stocks": []}
        payload.setdefault("version", "unknown")
        payload.setdefault("delisted_stocks", [])
        return payload

    def get_universe_as_of(self, as_of_date: str) -> List[str]:
        """
        Return symbol universe available on as_of_date.
        Includes currently available datasource symbols and delisted symbols
        that were listed and not yet delisted on that date.
        """
        universe: set[str] = set()

        if self._datasource and hasattr(self._datasource, "get_all_symbols"):
            symbols = self._datasource.get_all_symbols()
            if isinstance(symbols, list):
                universe.update(str(sym) for sym in symbols)

        for stock in self._delisted_metadata.get("delisted_stocks", []):
            listing_date = str(stock.get("listing_date", ""))
            delist_date = str(stock.get("delist_date", ""))
            symbol = stock.get("symbol")
            if not symbol:
                continue
            if listing_date <= as_of_date < delist_date:
                universe.add(str(symbol))

        return sorted(universe)

    def is_delisted_on(self, symbol: str, check_date: str) -> bool:
        """True if symbol is delisted on or before check_date."""
        info = self.get_delisting_info(symbol)
        if not info:
            return False
        return check_date >= str(info.get("delist_date", ""))

    def get_delisting_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Return delisting metadata entry for a symbol, if available."""
        sym = symbol.upper()
        for stock in self._delisted_metadata.get("delisted_stocks", []):
            if str(stock.get("symbol", "")).upper() == sym:
                return stock
        return None

    def ingest_from_source(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        reject_corrupted: bool = True,
    ) -> List[Dict]:
        """Fetch raw data from attached datasource and run source-level validation."""
        if not self._datasource:
            raise ValueError("No datasource attached")
        all_rows = []
        for chunk in self._datasource.iter_chunks(symbol, start_date, end_date):
            all_rows.extend(chunk)
        self._last_validation_issues = self._data_validator.validate_rows(all_rows, symbol=symbol)
        if reject_corrupted and self._last_validation_issues:
            first_issue = self._last_validation_issues[0]
            raise ValueError(
                f"Corrupted source data rejected: {first_issue.rule} at {first_issue.timestamp} for {first_issue.symbol}"
            )
        return all_rows

    def get_last_validation_issues(self) -> List[ValidationIssue]:
        """Return validation issues from the latest source ingestion call."""
        return list(self._last_validation_issues)

    def load_schema(self, schema_path: str) -> bool:
        """Load and validate schema from file."""
        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                self._schema = json.load(f)
            return True
        except Exception:
            return False

    def add_corporate_action(self, action: CorporateAction):
        """Add a corporate action for price adjustment."""
        self._corp_action_adjuster.add_action(action)

    def add_corporate_actions(self, actions: List[CorporateAction]):
        """Add multiple corporate actions for price adjustment."""
        self._corp_action_adjuster.add_actions(actions)

    def clear_corporate_actions(self):
        """Clear all corporate actions."""
        self._corp_action_adjuster.clear_actions()

    def validate_input(self, raw_data: Union[List[Dict], str]) -> bool:
        """Validate raw input against loaded schema."""
        if not self._schema:
            return False
        if isinstance(raw_data, str):
            try:
                raw_data = json.loads(raw_data)
            except json.JSONDecodeError:
                return False
        if not isinstance(raw_data, list):
            return False

        required = self._schema.get("required", [])
        import math

        for item in raw_data:
            # Check required keys
            if not all(k in item for k in required):
                return False

            # Check bounds and valid values
            if "close" in item:
                val = item["close"]
                if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val) or val < 0.0001:
                    return False
            if "volume" in item:
                val = item["volume"]
                if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val) or val < 0.0:
                    return False
        return True

    def transform(self, raw_data: List[Dict]) -> Dict:
        """Transform raw data into standardized CleanDataFrame."""
        if not self.validate_input(raw_data):
            raise ValueError("Input validation failed: schema mismatch or invalid values (hard_stop)")

        timestamp_key = self._schema.get("timestamp_field", "timestamp")
        symbol_key = self._schema.get("symbol_field", "symbol")

        grouped = {}
        all_timestamps = set()

        for item in raw_data:
            sym = item.get(symbol_key)
            ts = item.get(timestamp_key)

            if sym not in grouped:
                grouped[sym] = {}

            # Reject duplicates
            if ts in grouped[sym]:
                raise ValueError(f"Non-monotonic or duplicate timestamp rejected. Symbol: {sym}, TS: {ts}")

            # Check monotonicity (timestamps must be increasing)
            if grouped[sym]:
                last_ts = max(grouped[sym].keys())
                if ts <= last_ts:
                    raise ValueError(f"Non-monotonic timestamp rejected. Symbol: {sym}, Last TS: {last_ts}, New TS: {ts}")

            grouped[sym][ts] = {
                k: v for k, v in item.items()
                if k not in (symbol_key, timestamp_key)
            }
            all_timestamps.add(ts)

        # Sort timestamps globally
        sorted_timestamps = sorted(list(all_timestamps))

        # Fix finding 4: Remove inferred forward-fill to strictly align observed rows.
        # Now we only keep rows where we have actual data, strictly enforcing no_inference.

        # Fix SECURE_ALIGNMENT_FIX: Support Dynamic Universe (mixed listing dates)
        # Use UNION of all timestamps, mark unavailable periods as None
        sorted_timestamps = sorted(list(all_timestamps))

        if not sorted_timestamps:
            raise ValueError("No timestamps found in input data")

        # Build final CleanDataFrame with explicit availability tracking
        final_grouped = {}
        for sym, sym_data in grouped.items():
            final_grouped[sym] = {}
            for ts in sorted_timestamps:
                if ts in sym_data:
                    # Symbol has data at this timestamp
                    final_grouped[sym][ts] = sym_data[ts]
                else:
                    # Symbol not yet listed or delisted - mark explicitly as None
                    final_grouped[sym][ts] = None

        clean_df = {
            "index": {
                "symbol": sorted(list(final_grouped.keys())),
                "timestamp": sorted_timestamps,
            },
            "type": "CleanDataFrame",
            "data": final_grouped,
        }

        # Apply corporate action adjustments if any
        adjusted_df = self._corp_action_adjuster.apply_adjustments(clean_df)
        return adjusted_df

    def get_hash(self) -> str:
        """Return deterministic hash of current state (for audit)."""
        h = hashlib.sha256()
        h.update(json.dumps(self._schema, sort_keys=True).encode())
        return h.hexdigest()
