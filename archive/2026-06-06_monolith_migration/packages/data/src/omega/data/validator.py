"""
OMEGA_QUANT Core Intelligence - Data validation rules for source ingestion.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from omega.data.calendar import VNTradingCalendar


@dataclass(frozen=True)
class ValidationIssue:
    rule: str
    message: str
    symbol: str
    timestamp: Any


class DataValidator:
    """Validate raw OHLCV rows before handing data to downstream modules.
    
    Now includes provenance metadata validation for dataset_version, checksum, and adjustments_applied.
    """

    def __init__(
        self,
        max_session_move: float = 0.20,
        adv_lookback: int = 20,
        liquid_adv_threshold: float = 100000.0,
        validate_provenance: bool = True,
    ) -> None:
        self.max_session_move = max_session_move
        self.adv_lookback = adv_lookback
        self.liquid_adv_threshold = liquid_adv_threshold
        self.validate_provenance = validate_provenance

    def validate(self, df: Any) -> Dict[str, Any]:
        """
        Validate DataFrame and return quality metrics.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Dictionary with validation results including missing_values counts
        """
        import pandas as pd
        
        if not isinstance(df, pd.DataFrame):
            return {"error": "Input must be a pandas DataFrame"}
        
        result = {
            "missing_values": {},
            "total_rows": len(df),
            "issues": []
        }
        
        # Count missing values per column
        for col in df.columns:
            missing_count = df[col].isna().sum()
            if missing_count > 0:
                result["missing_values"][col] = missing_count
        
        # Run full validation using validate_rows
        rows = df.to_dict('records')
        symbol = df['ticker'].iloc[0] if 'ticker' in df.columns and len(df) > 0 else "UNKNOWN"
        issues = self.validate_rows(rows, symbol=symbol)
        result["issues"] = [{"rule": issue.rule, "message": issue.message} for issue in issues]
        
        return result

    def validate_rows(self, rows: List[Dict[str, Any]], symbol: Optional[str] = None, parquet_path: Optional[Path] = None) -> List[ValidationIssue]:
        if not rows:
            return []

        # Handle timestamp sorting - filter out None values first
        sorted_rows = sorted([r for r in rows if r.get("timestamp") is not None], key=lambda r: r.get("timestamp"))
        if not sorted_rows:
            return []
        
        sym = symbol or str(sorted_rows[0].get("symbol", "UNKNOWN"))
        issues: List[ValidationIssue] = []

        issues.extend(self._validate_structural_ohlc(sorted_rows, sym))
        issues.extend(self._validate_price_moves(sorted_rows, sym))
        issues.extend(self._validate_zero_volume_liquidity(sorted_rows, sym))
        issues.extend(self._validate_data_gaps(sorted_rows, sym))
        
        # Validate provenance metadata if enabled
        if self.validate_provenance:
            issues.extend(self._validate_provenance_metadata(sorted_rows, sym))
            
            # NEW: Add checksum validation if parquet_path provided
            if parquet_path:
                issues.extend(self._validate_checksum_from_sidecar(parquet_path, sym))
        
        return issues

    def _validate_price_moves(self, rows: List[Dict[str, Any]], symbol: str) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for i in range(1, len(rows)):
            prev_close = rows[i - 1].get("close")
            close = rows[i].get("close")
            if not self._is_positive_number(prev_close) or not self._is_positive_number(close):
                continue
            move = abs((float(close) / float(prev_close)) - 1.0)
            if move > self.max_session_move:
                issues.append(
                    ValidationIssue(
                        rule="price_jump_gt_20pct",
                        message=f"Detected single-session move {move:.2%} > {self.max_session_move:.0%}",
                        symbol=symbol,
                        timestamp=rows[i].get("timestamp"),
                    )
                )
        
        # Validate price inconsistency (detect potential double-adjustment)
        issues.extend(self._validate_price_consistency(rows, symbol))
        return issues

    def _validate_zero_volume_liquidity(self, rows: List[Dict[str, Any]], symbol: str) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        vols = [float(r.get("volume", 0.0) or 0.0) for r in rows]
        for i in range(self.adv_lookback, len(rows)):
            trailing = vols[i - self.adv_lookback : i]
            if not trailing:
                continue
            adv = sum(trailing) / len(trailing)
            if adv >= self.liquid_adv_threshold and vols[i] == 0.0:
                issues.append(
                    ValidationIssue(
                        rule="zero_volume_liquid_stock",
                        message=f"Zero volume with trailing ADV={adv:.2f}",
                        symbol=symbol,
                        timestamp=rows[i].get("timestamp"),
                    )
                )
        return issues

    def _validate_data_gaps(self, rows: List[Dict[str, Any]], symbol: str) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        parsed_dates: List[date] = []
        for r in rows:
            d = self._to_date(r.get("timestamp"))
            if d is None:
                return issues
            parsed_dates.append(d)

        observed = set(parsed_dates)
        start = min(parsed_dates)
        end = max(parsed_dates)
        cur = start
        while cur <= end:
            cur_dt = datetime(cur.year, cur.month, cur.day)
            if VNTradingCalendar.is_trading_day(cur_dt) and cur not in observed:
                issues.append(
                    ValidationIssue(
                        rule="missing_trading_timestamp",
                        message=f"Missing trading day in observed data: {cur.isoformat()}",
                        symbol=symbol,
                        timestamp=cur.isoformat(),
                    )
                )
            cur += timedelta(days=1)
        return issues

    def _validate_structural_ohlc(self, rows: List[Dict[str, Any]], symbol: str) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for row in rows:
            if not all(k in row for k in ("open", "high", "low", "close")):
                continue
            o = row["open"]
            h = row["high"]
            l = row["low"]
            c = row["close"]
            if not all(self._is_number(x) for x in (o, h, l, c)):
                continue
            if float(h) < max(float(o), float(l), float(c)) or float(l) > min(float(o), float(h), float(c)):
                issues.append(
                    ValidationIssue(
                        rule="ohlc_structure_inconsistent",
                        message="OHLC violated: high must be max and low must be min",
                        symbol=symbol,
                        timestamp=row.get("timestamp"),
                    )
                )
        return issues

    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float))

    @staticmethod
    def _is_positive_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and value > 0

    @staticmethod
    def _to_date(ts: Any) -> Optional[date]:
        if isinstance(ts, datetime):
            return ts.date()
        if isinstance(ts, date):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts).date()
            except ValueError:
                return None
        if isinstance(ts, (int, float)):
            # Keep synthetic test timestamps untouched; only parse realistic epochs.
            if ts > 10**12:
                return datetime.fromtimestamp(ts / 1000.0).date()
            if ts > 10**9:
                return datetime.fromtimestamp(ts).date()
        return None

    def _validate_provenance_metadata(self, rows: List[Dict[str, Any]], symbol: str) -> List[ValidationIssue]:
        """
        Validate provenance metadata fields (dataset_version, source, adjustments_applied).
        
        Note: checksum validation is now handled by _validate_checksum_from_sidecar() 
        which reads from .metadata.json sidecar file instead of per-row fields.
        
        Args:
            rows: List of data rows
            symbol: Stock symbol
            
        Returns:
            List of validation issues
        """
        issues: List[ValidationIssue] = []
        
        for row in rows:
            # Check for dataset_version field
            if 'dataset_version' not in row:
                issues.append(
                    ValidationIssue(
                        rule="missing_dataset_version",
                        message="Missing dataset_version field in provenance metadata",
                        symbol=symbol,
                        timestamp=row.get("timestamp"),
                    )
                )
            
            # Check for source field
            if 'source' not in row:
                issues.append(
                    ValidationIssue(
                        rule="missing_source",
                        message="Missing source field in provenance metadata",
                        symbol=symbol,
                        timestamp=row.get("timestamp"),
                    )
                )
            
            # Validate adjustments_applied format (should be JSON string or list)
            if 'adjustments_applied' in row:
                adj = row['adjustments_applied']
                if adj is not None and not isinstance(adj, (str, list)):
                    issues.append(
                        ValidationIssue(
                            rule="invalid_adjustments_format",
                            message=f"adjustments_applied must be JSON string or list, got {type(adj)}",
                            symbol=symbol,
                            timestamp=row.get("timestamp"),
                        )
                    )
        
        return issues
    
    def _validate_price_consistency(self, rows: List[Dict[str, Any]], symbol: str) -> List[ValidationIssue]:
        """
        Validate price consistency to detect potential double-adjustment issues.
        
        Compares raw vs adjusted price expectations. If source claims to provide adjusted prices
        but we detect patterns suggesting raw prices (or vice versa), flag as inconsistency.
        
        Heuristic: Check for large price jumps that align with known corporate action patterns
        (e.g., 2:1 split = 50% drop, 10% dividend = ~10% drop).
        
        Args:
            rows: List of data rows
            symbol: Stock symbol
            
        Returns:
            List of validation issues
        """
        issues: List[ValidationIssue] = []
        
        # Check if source metadata claims adjusted prices
        if not rows:
            return issues
        
        first_row = rows[0]
        source = first_row.get('source', '')
        adjustments_applied = first_row.get('adjustments_applied', '[]')
        
        # Parse adjustments_applied
        import json
        if isinstance(adjustments_applied, str):
            try:
                adjustments_list = json.loads(adjustments_applied)
            except (json.JSONDecodeError, TypeError):
                adjustments_list = []
        else:
            adjustments_list = adjustments_applied if isinstance(adjustments_applied, list) else []
        
        # If source is vnstock and adjustments were applied, flag potential double-adjustment
        if 'vnstock' in source.lower() and len(adjustments_list) > 0:
            issues.append(
                ValidationIssue(
                    rule="potential_double_adjustment",
                    message=f"Source '{source}' provides adjusted prices by default, but adjustments_applied={adjustments_list}. "
                            f"This may indicate double-adjustment. Verify is_already_adjusted flag in DataLoader.",
                    symbol=symbol,
                    timestamp=first_row.get("timestamp"),
                )
            )
        
        # Check for suspicious price patterns that suggest unadjusted data when adjusted is expected
        for i in range(1, len(rows)):
            prev_close = rows[i - 1].get("close")
            close = rows[i].get("close")
            
            if not self._is_positive_number(prev_close) or not self._is_positive_number(close):
                continue
            
            ratio = float(close) / float(prev_close)
            
            # Detect common split ratios (2:1 = 0.5, 3:1 = 0.33, 1:2 = 2.0, etc.)
            common_split_ratios = [0.5, 0.33, 0.25, 2.0, 3.0, 4.0]
            for split_ratio in common_split_ratios:
                if abs(ratio - split_ratio) < 0.02:  # 2% tolerance
                    issues.append(
                        ValidationIssue(
                            rule="potential_unadjusted_split",
                            message=f"Detected price ratio {ratio:.3f} close to split ratio {split_ratio:.2f}. "
                                    f"If source provides adjusted prices, this may indicate raw data or missing adjustment.",
                            symbol=symbol,
                            timestamp=rows[i].get("timestamp"),
                        )
                    )
                    break
        
        return issues
    
    def _validate_checksum_from_sidecar(self, parquet_path: Path, symbol: str) -> List[ValidationIssue]:
        """
        Validate checksum from sidecar .metadata.json file.
        
        Reads the .metadata.json file adjacent to the parquet file and validates:
        1. Metadata file exists
        2. Checksum field exists in metadata
        3. Checksum algorithm is sha256
        4. Computed checksum of parquet file matches stored checksum
        
        Args:
            parquet_path: Path to the parquet file
            symbol: Stock symbol
            
        Returns:
            List of validation issues
        """
        issues: List[ValidationIssue] = []
        
        # Construct metadata file path
        metadata_path = parquet_path.parent / f"{parquet_path.stem}.metadata.json"
        
        # Check if metadata file exists
        if not metadata_path.exists():
            issues.append(
                ValidationIssue(
                    rule="missing_metadata_sidecar",
                    message=f"Missing .metadata.json sidecar file at {metadata_path}",
                    symbol=symbol,
                    timestamp=None,
                )
            )
            return issues
        
        # Read metadata file
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            issues.append(
                ValidationIssue(
                    rule="invalid_metadata_sidecar",
                    message=f"Failed to read .metadata.json: {e}",
                    symbol=symbol,
                    timestamp=None,
                )
            )
            return issues
        
        # Validate checksum field exists
        if 'checksum' not in metadata:
            issues.append(
                ValidationIssue(
                    rule="missing_checksum_in_sidecar",
                    message="Missing checksum field in .metadata.json",
                    symbol=symbol,
                    timestamp=None,
                )
            )
            return issues
        
        stored_checksum = metadata['checksum']
        
        # Validate checksum format (64-char hex for SHA256)
        if not isinstance(stored_checksum, str) or len(stored_checksum) != 64:
            issues.append(
                ValidationIssue(
                    rule="invalid_checksum_format",
                    message=f"checksum must be 64-char hex string, got {type(stored_checksum)} with length {len(stored_checksum) if isinstance(stored_checksum, str) else 'N/A'}",
                    symbol=symbol,
                    timestamp=None,
                )
            )
            return issues
        
        if not all(c in '0123456789abcdefABCDEF' for c in stored_checksum):
            issues.append(
                ValidationIssue(
                    rule="invalid_checksum_format",
                    message="checksum must contain only hexadecimal characters",
                    symbol=symbol,
                    timestamp=None,
                )
            )
            return issues
        
        # Validate checksum_algorithm
        checksum_algorithm = metadata.get('checksum_algorithm', 'sha256')
        if checksum_algorithm.lower() != 'sha256':
            issues.append(
                ValidationIssue(
                    rule="unsupported_checksum_algorithm",
                    message=f"Only sha256 is supported, got '{checksum_algorithm}'",
                    symbol=symbol,
                    timestamp=None,
                )
            )
            return issues
        
        # Compute actual checksum of parquet file
        try:
            sha256_hash = hashlib.sha256()
            with open(parquet_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256_hash.update(chunk)
            computed_checksum = sha256_hash.hexdigest()
        except IOError as e:
            issues.append(
                ValidationIssue(
                    rule="checksum_computation_failed",
                    message=f"Failed to compute checksum: {e}",
                    symbol=symbol,
                    timestamp=None,
                )
            )
            return issues
        
        # Compare checksums (case-insensitive)
        if computed_checksum.lower() != stored_checksum.lower():
            issues.append(
                ValidationIssue(
                    rule="checksum_mismatch",
                    message=f"Checksum mismatch: expected {stored_checksum}, got {computed_checksum}",
                    symbol=symbol,
                    timestamp=None,
                )
            )
        
        return issues
