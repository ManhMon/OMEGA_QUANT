"""
V21 Core Intelligence - Data validation rules for source ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from .vn_trading_calendar import VNTradingCalendar


@dataclass(frozen=True)
class ValidationIssue:
    rule: str
    message: str
    symbol: str
    timestamp: Any
    severity: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        """Convert issue to JSON-serializable dict."""
        ts = self.timestamp
        if hasattr(ts, "isoformat"):
            ts_str = ts.isoformat()
        else:
            ts_str = str(ts)
            
        return {
            "rule": self.rule,
            "message": self.message,
            "symbol": self.symbol,
            "timestamp": ts_str,
            "severity": self.severity
        }


class DataValidator:
    """Validate raw OHLCV rows before handing data to downstream modules."""

    def __init__(
        self,
        max_session_move: float = 0.20,
        adv_lookback: int = 20,
        liquid_adv_threshold: float = 100000.0,
    ) -> None:
        self.max_session_move = max_session_move
        self.adv_lookback = adv_lookback
        self.liquid_adv_threshold = liquid_adv_threshold

    def validate_rows(self, rows: List[Dict[str, Any]], symbol: Optional[str] = None) -> List[ValidationIssue]:
        if not rows:
            return []

        sorted_rows = sorted(rows, key=lambda r: r.get("timestamp"))
        sym = symbol or str(sorted_rows[0].get("symbol", "UNKNOWN"))
        issues: List[ValidationIssue] = []

        issues.extend(self._validate_structural_ohlc(sorted_rows, sym))
        issues.extend(self._validate_price_moves(sorted_rows, sym))
        issues.extend(self._validate_zero_volume_liquidity(sorted_rows, sym))
        issues.extend(self._validate_data_gaps(sorted_rows, sym))
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
