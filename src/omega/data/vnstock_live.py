"""
Stub for VnStock Live Data Provider.
Archived to archive/legacy_adapters/vnstock_live.py.

Fail-closed implementation: network data fetching is forbidden and raises ImportError.
In-memory calculation helpers (_compute_adv_vectorized, _compute_volatility_vectorized)
are preserved for downstream sector report and analytical compatibility.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

# Flag retained for backwards compatibility
VNSTOCK_AVAILABLE: bool = False


@dataclass
class VnStockLiveConfig:
    """Configuration container for legacy VnStock live provider (archived)."""

    pit_lag_days: int = 1
    board_lot_size: int = 100
    settlement_days: float = 2.5
    api_key: Optional[str] = None
    rate_limit_requests: int = 60
    rate_limit_period: float = 60.0

    def __repr__(self) -> str:
        return (
            f"VnStockLiveConfig(pit_lag_days={self.pit_lag_days}, "
            f"board_lot_size={self.board_lot_size}, "
            f"settlement_days={self.settlement_days}, "
            f"api_key='[REDACTED]', "
            f"rate_limit_requests={self.rate_limit_requests}, "
            f"rate_limit_period={self.rate_limit_period})"
        )


@dataclass
class VnStockLiveData:
    """Container for live market data (legacy container)."""

    prices: pd.DataFrame
    volumes: pd.DataFrame
    adv_data: pd.DataFrame
    volatility_data: pd.DataFrame
    metadata: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        return {
            "tickers_count": len(self.metadata.get("tickers", [])),
            "reference_date": str(self.metadata.get("reference_date", "")),
            "pit_date": str(self.metadata.get("pit_date", "")),
            "prices_shape": self.prices.shape if hasattr(self.prices, "shape") else None,
            "adv_shape": self.adv_data.shape if hasattr(self.adv_data, "shape") else None,
            "volatility_shape": self.volatility_data.shape if hasattr(self.volatility_data, "shape") else None,
        }


class VnStockLiveDataProvider:
    """
    Fail-closed stub for VnStockLiveDataProvider.
    Archived to archive/legacy_adapters/vnstock_live.py.
    """

    def __init__(self, config: Optional[VnStockLiveConfig] = None, *args: Any, **kwargs: Any) -> None:
        self.config = config or VnStockLiveConfig()

    def __repr__(self) -> str:
        return "VnStockLiveDataProvider(status='ARCHIVED', network='FAIL_CLOSED')"

    def __str__(self) -> str:
        return self.__repr__()

    # ----------------------------------------------------------------------
    # In-memory Vectorized Helpers (Preserved for Sector Report Compatibility)
    # ----------------------------------------------------------------------

    @staticmethod
    def _validate_numeric_input(
        price_data: pd.DataFrame, columns: List[str], window: int
    ) -> None:
        if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
            raise ValueError("window must be a positive integer")
        if not all(pd.api.types.is_numeric_dtype(price_data[col]) for col in columns):
            raise TypeError("numeric helper columns must be numeric")
        if not np.isfinite(price_data[columns].to_numpy(dtype=float)).all():
            raise ValueError("numeric helper columns must be finite")
        if (price_data[columns] < 0).any().any():
            raise ValueError("numeric helper columns cannot be negative")
        if price_data.duplicated(["ticker", "date"]).any():
            raise ValueError("duplicate ticker/date observations are not allowed")

    def _compute_adv_vectorized(
        self,
        price_data: pd.DataFrame,
        window: int = 20,
    ) -> pd.DataFrame:
        """
        Compute Average Daily Volume (ADV) using vectorized operations.

        Args:
            price_data: DataFrame with columns [ticker, date, volume, value]
            window: Rolling window for ADV calculation (default: 20 days)

        Returns:
            DataFrame with columns [ticker, adv_volume, adv_value]
        """
        if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
            raise ValueError("window must be a positive integer")
        if price_data.empty:
            return pd.DataFrame(columns=["ticker", "adv_volume", "adv_value"])

        if "ticker" not in price_data.columns or "date" not in price_data.columns:
            raise KeyError("price_data must contain 'ticker' and 'date' columns")
        if "volume" not in price_data.columns or "value" not in price_data.columns:
            raise KeyError("price_data must contain 'volume' and 'value' columns")
        self._validate_numeric_input(price_data, ["volume", "value"], window)

        # Vectorized: sort once, then groupby tail-mean via rank
        df = price_data.sort_values(["ticker", "date"])
        # Keep only last `window` rows per ticker
        df = df.groupby("ticker").tail(window)
        adv = (
            df.groupby("ticker")[["volume", "value"]]
            .mean()
            .rename(columns={"volume": "adv_volume", "value": "adv_value"})
            .reset_index()
        )
        return adv

    def _compute_volatility_vectorized(
        self,
        price_data: pd.DataFrame,
        window: int = 20,
    ) -> pd.DataFrame:
        """
        Compute historical volatility using vectorized operations.

        Args:
            price_data: DataFrame with columns [ticker, date, close]
            window: Rolling window for volatility calculation (default: 20 days)

        Returns:
            DataFrame with columns [ticker, volatility]
        """
        if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
            raise ValueError("window must be a positive integer")
        if price_data.empty:
            return pd.DataFrame(columns=["ticker", "volatility"])

        if "ticker" not in price_data.columns or "date" not in price_data.columns or "close" not in price_data.columns:
            raise KeyError("price_data must contain 'ticker', 'date', and 'close' columns")
        self._validate_numeric_input(price_data, ["close"], window)

        # Vectorized: pct_change per ticker, tail window, then std
        df = price_data.sort_values(["ticker", "date"]).copy()
        df["returns"] = df.groupby("ticker")["close"].pct_change()
        df = df.dropna(subset=["returns"])
        df = df.groupby("ticker").tail(window)
        vol = (
            df.groupby("ticker")["returns"]
            .std()
            .mul(np.sqrt(252))
            .rename("volatility")
            .reset_index()
        )
        return vol

    # ----------------------------------------------------------------------
    # Fail-Closed Network Data Ingestion Points (Archived / Access Forbidden)
    # ----------------------------------------------------------------------

    def fetch_live_data(self, *args: Any, **kwargs: Any) -> Any:
        """Archived entry point: network data fetch forbidden."""
        raise ImportError(
            "VnStockLiveDataProvider has been archived. Network data fetch is forbidden. "
            "See archive/legacy_adapters/vnstock_live.py."
        )

    def get_latest_prices(self, *args: Any, **kwargs: Any) -> Any:
        """Archived entry point: network data fetch forbidden."""
        raise ImportError(
            "VnStockLiveDataProvider has been archived. Network data fetch is forbidden. "
            "See archive/legacy_adapters/vnstock_live.py."
        )

    def get_market_data_for_risk_guard(self, *args: Any, **kwargs: Any) -> Any:
        """Archived entry point: network data fetch forbidden."""
        raise ImportError(
            "VnStockLiveDataProvider has been archived. Network data fetch is forbidden. "
            "See archive/legacy_adapters/vnstock_live.py."
        )

    def _fetch_price_data_single(self, *args: Any, **kwargs: Any) -> Any:
        """Archived entry point: network data fetch forbidden."""
        raise ImportError(
            "VnStockLiveDataProvider has been archived. Network data fetch is forbidden. "
            "See archive/legacy_adapters/vnstock_live.py."
        )
