"""Point-in-time financial-statement loader."""

from pathlib import Path

import pandas as pd


class FinancialStatementLoader:
    """Load financial statements and align them to market dates safely."""

    def __init__(self, source: str | Path | pd.DataFrame):
        self.source = source
        self.raw: pd.DataFrame | None = None
        self.joined: pd.DataFrame | None = None

    def load_raw(self) -> pd.DataFrame:
        """Load and validate canonical long-form financial statements."""
        raw = self.source.copy() if isinstance(self.source, pd.DataFrame) else pd.read_parquet(self.source)
        required = {"symbol", "item_code", "item_value", "fiscal_period_end", "available_at"}
        missing = required.difference(raw.columns)
        if missing:
            raise ValueError(f"Missing financial statement columns: {sorted(missing)}")
        raw = raw.copy()
        raw["available_at"] = pd.to_datetime(raw["available_at"], utc=True)
        if raw["available_at"].isna().any():
            raise ValueError("available_at cannot be null")
        if raw["fiscal_period_end"].isna().any():
            raise ValueError("fiscal_period_end cannot be null")
        period_end = pd.to_datetime(raw["fiscal_period_end"], utc=True)
        if (period_end > raw["available_at"]).any():
            raise ValueError("PIT violation: fiscal_period_end exceeds available_at")
        self.raw = raw
        return raw.copy()

    def asof_join_market(self, market_df: pd.DataFrame) -> pd.DataFrame:
        """Join each factor using only statements available on each market date."""
        raw = self.raw if self.raw is not None else self.load_raw()
        required = {"symbol", "date"}
        missing = required.difference(market_df.columns)
        if missing:
            raise ValueError(f"Missing market columns: {sorted(missing)}")

        market = market_df.copy()
        if market["date"].isna().any():
            raise ValueError("market date cannot be null")
        market["date"] = pd.to_datetime(market["date"], utc=True)
        factors = raw[["symbol", "item_code", "item_value", "fiscal_period_end", "available_at"]].copy()
        factors = factors.sort_values("fiscal_period_end")
        factors = factors.drop_duplicates(["symbol", "item_code", "available_at"], keep="last")
        factors = factors.drop(columns="fiscal_period_end")
        market["_join"] = 1
        factor_codes = factors[["item_code"]].drop_duplicates()
        factor_codes["_join"] = 1
        left = market.merge(factor_codes, on="_join").drop(columns="_join")
        left = left.sort_values("date")
        right = factors.sort_values("available_at")
        self.joined = pd.merge_asof(
            left,
            right,
            left_on="date",
            right_on="available_at",
            by=["symbol", "item_code"],
            direction="backward",
        )
        return self.joined.copy()

    def get_factor_matrix(
        self, symbols: list[str], start_date: str | pd.Timestamp, end_date: str | pd.Timestamp
    ) -> pd.DataFrame:
        """Return date-symbol observations as a wide financial-factor matrix."""
        if self.joined is None:
            raise ValueError("Call asof_join_market before get_factor_matrix")
        start = pd.to_datetime(start_date, utc=True)
        end = pd.to_datetime(end_date, utc=True)
        if start > end:
            raise ValueError("start_date must be <= end_date")
        rows = self.joined[
            self.joined["symbol"].isin(symbols)
            & self.joined["date"].between(start, end)
        ]
        return rows.pivot(index=["date", "symbol"], columns="item_code", values="item_value").sort_index()
