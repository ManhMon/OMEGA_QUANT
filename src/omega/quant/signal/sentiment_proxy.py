"""PIT-safe market-implied sentiment from daily OHLCV data."""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


class MarketImpliedSentimentProxy:
    """Build a bounded T-1 sentiment proxy without news coverage."""

    def __init__(self, window: int = 20) -> None:
        if window < 1:
            raise ValueError("window must be >= 1")
        self.window = window

    def compute(self, market_data: pd.DataFrame) -> pd.DataFrame:
        """Return market-implied sentiment components, shifted one observation per symbol."""
        required = {"high", "low", "close", "volume"}
        missing = required.difference(market_data.columns)
        if missing:
            raise ValueError(f"Missing market columns: {sorted(missing)}")

        data = market_data.copy()
        identifier = "symbol" if "symbol" in data else "ticker" if "ticker" in data else None
        groups = data.groupby(identifier, sort=False) if identifier else [(None, data)]
        outputs = []
        for _, group in groups:
            ordered = group.sort_values("date") if "date" in group else group
            previous_close = ordered["close"].shift()
            true_range = pd.concat(
                [
                    ordered["high"] - ordered["low"],
                    (ordered["high"] - previous_close).abs(),
                    (ordered["low"] - previous_close).abs(),
                ],
                axis=1,
            ).max(axis=1)
            atr = true_range.rolling(self.window, min_periods=1).mean()
            volume_average = ordered["volume"].rolling(self.window, min_periods=1).mean()
            volume_surge_ratio = ordered["volume"] / volume_average.replace(0, np.nan)
            return_jump_atr = (ordered["close"] - previous_close) / atr.replace(0, np.nan)
            buying_pressure_index = (
                (2 * ordered["close"] - ordered["high"] - ordered["low"])
                / (ordered["high"] - ordered["low"]).replace(0, np.nan)
            )
            sentiment = ((volume_surge_ratio - 1) * return_jump_atr + buying_pressure_index) / 2
            outputs.append(
                pd.DataFrame(
                    {
                        "volume_surge_ratio": volume_surge_ratio.shift(),
                        "return_jump_atr": return_jump_atr.shift(),
                        "buying_pressure_index": buying_pressure_index.shift(),
                        "market_implied_sentiment": sentiment.shift().clip(-1.0, 1.0),
                    },
                    index=ordered.index,
                )
            )
        return pd.concat(outputs).reindex(data.index)

    def compute_proxy(self, market_data: pd.DataFrame) -> pd.DataFrame:
        """Return the canonical PIT-safe sentiment proxy schema."""
        if "date" not in market_data:
            raise ValueError("Missing market columns: ['date']")
        identifier = "symbol" if "symbol" in market_data else "ticker" if "ticker" in market_data else None
        if identifier is None:
            raise ValueError("Missing market columns: ['symbol' or 'ticker']")

        result = self.compute(market_data)
        return pd.DataFrame(
            {
                "symbol": market_data[identifier],
                "date": market_data["date"],
                "market_implied_sentiment": result["market_implied_sentiment"],
                "available_at": market_data["date"],
            },
            index=market_data.index,
        )

    def update_incremental(
        self,
        canonical_path: str | Path,
        market_df: pd.DataFrame,
        checkpoint_path: str | Path,
    ) -> pd.DataFrame:
        """Upsert proxy rows and atomically persist per-symbol watermarks."""
        canonical_path = Path(canonical_path)
        checkpoint_path = Path(checkpoint_path)
        columns = ["symbol", "date", "market_implied_sentiment", "available_at"]
        existing = pd.read_parquet(canonical_path) if canonical_path.exists() else pd.DataFrame(columns=columns)
        candidate = self.compute_proxy(market_df).loc[:, columns]
        candidate = candidate.drop_duplicates(["symbol", "date"], keep="last")
        existing = existing.drop_duplicates(["symbol", "date"], keep="last")
        new_rows = candidate.merge(existing[["symbol", "date"]], on=["symbol", "date"], how="left", indicator=True)
        new_rows = new_rows.loc[new_rows["_merge"] == "left_only", columns]
        combined = (
            pd.concat([existing, candidate], ignore_index=True)
            .drop_duplicates(["symbol", "date"], keep="last")
            .sort_values(["symbol", "date"])
            .reset_index(drop=True)
        )
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        canonical_tmp = canonical_path.with_suffix(canonical_path.suffix + ".tmp")
        combined.to_parquet(canonical_tmp, index=False)
        canonical_tmp.replace(canonical_path)

        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.exists() else {}
        watermarks = {
            symbol: pd.Timestamp(group["date"].max()).isoformat()
            for symbol, group in combined.groupby("symbol", sort=True)
        }
        checkpoint["market_proxy"] = {
            "max_date": max(watermarks.values(), default=None),
            "symbol_watermarks": watermarks,
            "row_count": len(combined),
            "sha256": hashlib.sha256(canonical_path.read_bytes()).hexdigest(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_tmp = checkpoint_path.with_suffix(checkpoint_path.suffix + ".tmp")
        checkpoint_tmp.write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        checkpoint_tmp.replace(checkpoint_path)
        return new_rows.reset_index(drop=True)
