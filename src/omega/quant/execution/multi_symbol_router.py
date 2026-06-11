"""
MultiSymbolRouter Module (Institutional Grade - Phase 16)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
from enum import Enum

from omega.data.registry import ModelRegistry

logger = logging.getLogger(__name__)

class BrokerType(Enum):
    SSI = "SSI"
    VCI = "VCI"
    VND = "VND"
    MOCK = "MOCK"

@dataclass
class RouterConfig:
    """Configuration for MultiSymbolRouter."""
    max_workers: int = 10
    xgboost_weight: float = 0.6
    lstm_weight: float = 0.4
    min_confidence: float = 0.3
    lag_days: int = 1
    timeout_seconds: float = 30.0
    model_registry_path: Optional[str] = None
    xgboost_model_name: str = "xgboost_router"
    lstm_model_name: str = "lstm_router"
    model_status: str = "PRODUCTION"

@dataclass
class SignalResult:
    """Result from signal generation for a single symbol."""
    symbol: str
    timestamp: pd.Timestamp
    xgboost_signal: float
    lstm_signal: float
    aggregated_signal: float
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)

class MultiSymbolRouter:
    """
    Institutional Multi-Symbol Router (Phase 16).
    Dispatches tasks and routes orders to brokers.
    """
    def __init__(self, config: Optional[RouterConfig] = None):
        self.config = config or RouterConfig()
        self.xgboost_model = None
        self.lstm_model = None
        self.xgboost_metadata: Optional[Dict[str, Any]] = None
        self.lstm_metadata: Optional[Dict[str, Any]] = None
        self._routes: Dict[str, BrokerType] = {}
        self._model_registry: Optional[ModelRegistry] = None
        self._validate_config()

    def _validate_config(self) -> None:
        if not (0 <= self.config.xgboost_weight <= 1):
            raise ValueError("xgboost_weight must be in [0, 1]")
        if not (0 <= self.config.lstm_weight <= 1):
            raise ValueError("lstm_weight must be in [0, 1]")
        if not np.isclose(self.config.xgboost_weight + self.config.lstm_weight, 1.0):
            raise ValueError("Weights must sum to 1.0")

    def add_route(self, symbol: str, broker: BrokerType) -> None:
        """Add a routing rule for a symbol."""
        self._routes[symbol] = broker

    def get_broker_for_symbol(self, symbol: str) -> Optional[BrokerType]:
        """Get the routed broker for a given symbol."""
        return self._routes.get(symbol)

    def set_models(self, xgboost_model: Any, lstm_model: Any) -> None:
        self.xgboost_model = xgboost_model
        self.lstm_model = lstm_model

    def load_models_from_registry(self) -> None:
        registry = self._get_model_registry()
        self.xgboost_model = registry.load_model(
            self.config.xgboost_model_name,
            status=self.config.model_status,
        )
        self.lstm_model = registry.load_model(
            self.config.lstm_model_name,
            status=self.config.model_status,
        )
        self.xgboost_metadata = registry.get_active_model(self.config.xgboost_model_name, self.config.model_status)
        self.lstm_metadata = registry.get_active_model(self.config.lstm_model_name, self.config.model_status)

    def process_all_symbols(self, symbols: List[str], features: pd.DataFrame, timestamp: pd.Timestamp) -> pd.DataFrame:
        self._ensure_models_loaded()
        self._validate_features(features, timestamp, symbols)
        self._validate_model_metadata(timestamp)

        max_workers = min(max(len(symbols), 1), self.config.max_workers)
        results: List[SignalResult] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._score_symbol, symbol, features, timestamp): symbol
                for symbol in symbols
            }
            for future in as_completed(futures, timeout=self.config.timeout_seconds):
                results.append(future.result())

        return pd.DataFrame(
            {
                "symbol": result.symbol,
                "timestamp": result.timestamp,
                "xgboost_signal": result.xgboost_signal,
                "lstm_signal": result.lstm_signal,
                "aggregated_signal": result.aggregated_signal,
                "confidence": result.confidence,
                "metadata": result.metadata,
            }
            for result in sorted(results, key=lambda item: item.symbol)
        )

    def _get_model_registry(self) -> ModelRegistry:
        if self._model_registry is None:
            registry_path = self.config.model_registry_path
            if registry_path is not None:
                registry_path = str(Path(registry_path))
            self._model_registry = ModelRegistry(registry_path=registry_path)
        return self._model_registry

    def _ensure_models_loaded(self) -> None:
        if self.xgboost_model is None or self.lstm_model is None:
            self.load_models_from_registry()

    def _validate_features(self, features: pd.DataFrame, timestamp: pd.Timestamp, symbols: List[str]) -> None:
        if features.empty:
            raise ValueError("features must not be empty")
        if "symbol" not in features.columns:
            raise ValueError("features must contain 'symbol' column")
        if "timestamp" not in features.columns:
            raise ValueError("features must contain 'timestamp' column")

        feature_timestamps = pd.to_datetime(features["timestamp"], utc=True)
        inference_timestamp = pd.Timestamp(timestamp)
        if inference_timestamp.tzinfo is None:
            inference_timestamp = inference_timestamp.tz_localize("UTC")
        else:
            inference_timestamp = inference_timestamp.tz_convert("UTC")

        cutoff_timestamp = inference_timestamp - pd.Timedelta(days=self.config.lag_days)
        if (feature_timestamps > cutoff_timestamp).any():
            violating_ts = feature_timestamps[feature_timestamps > cutoff_timestamp].iloc[0]
            raise ValueError(
                "PIT Safety violation: feature timestamp "
                f"{violating_ts.isoformat()} exceeds T-{self.config.lag_days} cutoff {cutoff_timestamp.isoformat()}"
            )

        requested = set(symbols)
        available = set(features["symbol"].astype(str))
        missing = sorted(requested - available)
        if missing:
            raise ValueError(f"Missing features for symbols: {missing}")

    def _validate_model_metadata(self, timestamp: pd.Timestamp) -> None:
        inference_timestamp = pd.Timestamp(timestamp)
        if inference_timestamp.tzinfo is None:
            inference_timestamp = inference_timestamp.tz_localize("UTC")
        else:
            inference_timestamp = inference_timestamp.tz_convert("UTC")

        for model_name, metadata in (
            (self.config.xgboost_model_name, self.xgboost_metadata),
            (self.config.lstm_model_name, self.lstm_metadata),
        ):
            if metadata is None:
                continue
            self._validate_single_model_metadata(model_name, metadata, inference_timestamp)

    def _validate_single_model_metadata(
        self,
        model_name: str,
        metadata: Dict[str, Any],
        inference_timestamp: pd.Timestamp,
    ) -> None:
        pit_metadata = metadata.get("metadata", metadata)
        trained_at = pit_metadata.get("trained_at")
        available_at = pit_metadata.get("available_at")
        train_end_date = pit_metadata.get("train_end_date")
        validation_start_date = pit_metadata.get("validation_start_date")

        missing_fields = [
            field_name
            for field_name, field_value in (
                ("trained_at", trained_at),
                ("available_at", available_at),
                ("train_end_date", train_end_date),
                ("validation_start_date", validation_start_date),
            )
            if field_value is None
        ]
        if missing_fields:
            raise ValueError(f"PIT Provenance check FAILED: model '{model_name}' missing metadata {missing_fields}")

        available_at_ts = pd.Timestamp(available_at, tz="UTC")
        train_end_ts = pd.Timestamp(train_end_date, tz="UTC")
        validation_start_ts = pd.Timestamp(validation_start_date, tz="UTC")

        if available_at_ts > inference_timestamp:
            raise ValueError(
                f"PIT Safety violation: model '{model_name}' available_at {available_at_ts.isoformat()} "
                f"is in future relative to inference timestamp {inference_timestamp.isoformat()}"
            )
        if validation_start_ts <= train_end_ts:
            raise ValueError(
                f"PIT Provenance check FAILED: model '{model_name}' has invalid chronology "
                f"(validation_start_date: {validation_start_ts.isoformat()} <= train_end_date: {train_end_ts.isoformat()})"
            )

    def _score_symbol(self, symbol: str, features: pd.DataFrame, timestamp: pd.Timestamp) -> SignalResult:
        symbol_features = features.loc[features["symbol"].astype(str) == symbol].copy()
        if symbol_features.empty:
            raise ValueError(f"Missing features for symbol: {symbol}")

        symbol_features = symbol_features.sort_values("timestamp")
        latest_row = symbol_features.iloc[[-1]]
        model_input = latest_row.drop(columns=["symbol", "timestamp"], errors="ignore")
        model_input = model_input.replace([np.inf, -np.inf], np.nan).fillna(0.0)

        xgboost_signal = float(np.asarray(self.xgboost_model.predict(model_input)).reshape(-1)[-1])
        lstm_signal = float(np.asarray(self.lstm_model.predict(model_input)).reshape(-1)[-1])
        aggregated_signal = (
            (self.config.xgboost_weight * xgboost_signal)
            + (self.config.lstm_weight * lstm_signal)
        )
        confidence = max(abs(aggregated_signal), self.config.min_confidence)

        return SignalResult(
            symbol=symbol,
            timestamp=pd.Timestamp(timestamp),
            xgboost_signal=xgboost_signal,
            lstm_signal=lstm_signal,
            aggregated_signal=aggregated_signal,
            confidence=min(confidence, 1.0),
            metadata={
                "broker": self.get_broker_for_symbol(symbol).value if self.get_broker_for_symbol(symbol) else None,
                "feature_timestamp": pd.Timestamp(latest_row["timestamp"].iloc[0]).isoformat(),
            },
        )
