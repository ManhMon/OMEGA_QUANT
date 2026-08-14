"""Load PIT-stamped sentiment sources and align them to market observations."""

from pathlib import Path

import pandas as pd


class SentimentDataLoader:
    """Load canonical sentiment datasets and join only already-available values."""

    def __init__(
        self,
        market_proxy: str | Path | pd.DataFrame = "data/market_sentiment_proxy_2015_now.parquet",
        news_sentiment: str | Path | pd.DataFrame = "data/news_sentiment_2015_now.parquet",
    ) -> None:
        self.market_proxy = market_proxy
        self.news_sentiment = news_sentiment

    @staticmethod
    def _read(source: str | Path | pd.DataFrame) -> pd.DataFrame:
        return source.copy() if isinstance(source, pd.DataFrame) else pd.read_parquet(source)

    @staticmethod
    def _validate(data: pd.DataFrame, required: set[str], source_name: str) -> pd.DataFrame:
        missing = required.difference(data.columns)
        if missing:
            raise ValueError(f"Missing {source_name} columns: {sorted(missing)}")
        data = data.copy()
        for column in {"date", "publish_time", "available_at"}.intersection(data.columns):
            data[column] = pd.to_datetime(data[column], utc=True)
        if data[["symbol", "available_at"]].isna().any().any():
            raise ValueError(f"{source_name} provenance columns cannot be null")
        return data

    def load_market_proxy(self) -> pd.DataFrame:
        """Load market-implied sentiment with its availability timestamp."""
        data = self._validate(
            self._read(self.market_proxy),
            {"symbol", "date", "market_implied_sentiment", "available_at"},
            "market proxy",
        )
        if (data["date"] > data["available_at"]).any():
            raise ValueError("PIT violation: market proxy date exceeds available_at")
        return data

    def load_news_sentiment(self) -> pd.DataFrame:
        """Aggregate daily news sentiment without advancing availability."""
        data = self._validate(
            self._read(self.news_sentiment),
            {"symbol", "publish_time", "sentiment_score", "available_at"},
            "news sentiment",
        )
        if (data["publish_time"] > data["available_at"]).any():
            raise ValueError("PIT violation: news publish_time exceeds available_at")
        data["publish_date"] = data["publish_time"].dt.normalize()
        return (
            data.groupby(["symbol", "publish_date"], as_index=False)
            .agg(sentiment_score=("sentiment_score", "mean"), available_at=("available_at", "max"))
            .rename(columns={"publish_date": "publish_time"})
        )

    @staticmethod
    def _join(market: pd.DataFrame, sentiment: pd.DataFrame, value: str, factor: str) -> pd.DataFrame:
        right = sentiment[["symbol", "available_at", value]].sort_values(["available_at", "symbol"])
        joined = pd.merge_asof(
            market.sort_values(["date", "symbol"]),
            right,
            left_on="date",
            right_on="available_at",
            by="symbol",
            direction="backward",
        )
        return joined.rename(columns={value: factor, "available_at": f"{factor}_available_at"})

    def join_sentiment_to_market(self, market_data: pd.DataFrame) -> pd.DataFrame:
        """Attach the latest known proxy and news scores to each market row."""
        required = {"symbol", "date"}
        missing = required.difference(market_data.columns)
        if missing:
            raise ValueError(f"Missing market columns: {sorted(missing)}")
        market = market_data.copy()
        market["date"] = pd.to_datetime(market["date"], utc=True)
        if market[["symbol", "date"]].isna().any().any():
            raise ValueError("market provenance columns cannot be null")
        joined = self._join(market, self.load_market_proxy(), "market_implied_sentiment", "sentiment_proxy")
        return self._join(joined, self.load_news_sentiment(), "sentiment_score", "news_sentiment")
