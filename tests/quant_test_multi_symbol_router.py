import threading
import time

import numpy as np
import pandas as pd
import pytest

from omega.quant.execution.multi_symbol_router import MultiSymbolRouter, RouterConfig


class RecordingModel:
    def __init__(self, value: float, delay: float = 0.0):
        self.value = value
        self.delay = delay
        self.thread_names: list[str] = []

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        self.thread_names.append(threading.current_thread().name)
        if self.delay:
            time.sleep(self.delay)
        return np.asarray([self.value], dtype=float)


@pytest.fixture
def feature_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "AAA", "BBB"],
            "timestamp": pd.to_datetime(
                [
                    "2026-05-16T00:00:00Z",
                    "2026-05-16T00:00:00Z",
                    "2026-05-17T00:00:00Z",
                    "2026-05-17T00:00:00Z",
                ]
            ),
            "feature_1": [1.0, 2.0, 3.0, 4.0],
            "feature_2": [0.1, 0.2, 0.3, 0.4],
        }
    )


def test_get_model_registry_uses_default_registry_when_path_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    created_paths: list[object] = []

    class FakeRegistry:
        def __init__(self, registry_path: object = ".models") -> None:
            created_paths.append(registry_path)

    monkeypatch.setattr("omega.quant.multi_symbol_router.ModelRegistry", FakeRegistry)

    router = MultiSymbolRouter(RouterConfig(model_registry_path=None))

    assert router._get_model_registry() is router._get_model_registry()
    assert created_paths == [".models"]


def test_get_model_registry_uses_configured_registry_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    created_paths: list[object] = []

    class FakeRegistry:
        def __init__(self, registry_path: object = ".models") -> None:
            created_paths.append(registry_path)

    monkeypatch.setattr("omega.quant.multi_symbol_router.ModelRegistry", FakeRegistry)

    registry_path = tmp_path / "models"
    router = MultiSymbolRouter(RouterConfig(model_registry_path=str(registry_path)))

    assert router._get_model_registry() is router._get_model_registry()
    assert created_paths == [str(registry_path)]


def test_process_all_symbols_runs_real_inference_in_parallel(feature_frame: pd.DataFrame) -> None:
    router = MultiSymbolRouter(RouterConfig(max_workers=2, xgboost_weight=0.75, lstm_weight=0.25))
    xgb_model = RecordingModel(0.8, delay=0.05)
    lstm_model = RecordingModel(0.2, delay=0.05)
    router.set_models(xgb_model, lstm_model)

    result = router.process_all_symbols(
        ["AAA", "BBB"],
        feature_frame,
        pd.Timestamp("2026-05-18T00:00:00Z"),
    )

    assert result["symbol"].tolist() == ["AAA", "BBB"]
    assert result["xgboost_signal"].tolist() == [0.8, 0.8]
    assert result["lstm_signal"].tolist() == [0.2, 0.2]
    assert result["aggregated_signal"].tolist() == [pytest.approx(0.65), pytest.approx(0.65)]
    assert result["confidence"].tolist() == [pytest.approx(0.65), pytest.approx(0.65)]
    assert len(set(xgb_model.thread_names)) >= 2
    assert len(set(lstm_model.thread_names)) >= 2


def test_process_all_symbols_loads_models_from_registry(monkeypatch: pytest.MonkeyPatch, feature_frame: pd.DataFrame) -> None:
    router = MultiSymbolRouter(
        RouterConfig(
            max_workers=2,
            xgboost_model_name="xgb_prod",
            lstm_model_name="lstm_prod",
        )
    )
    registry_calls: list[tuple[str, str]] = []

    class FakeRegistry:
        def load_model(self, model_name: str, status: str = "PRODUCTION") -> RecordingModel:
            registry_calls.append(("load", model_name))
            return RecordingModel(0.4 if model_name == "xgb_prod" else 0.6)

        def get_active_model(self, model_name: str, status: str) -> dict[str, object]:
            registry_calls.append(("meta", model_name))
            return {
                "metadata": {
                    "trained_at": "2026-05-10T00:00:00Z",
                    "available_at": "2026-05-11T00:00:00Z",
                    "train_end_date": "2026-05-09T00:00:00Z",
                    "validation_start_date": "2026-05-10T00:00:00Z",
                }
            }

    monkeypatch.setattr(router, "_get_model_registry", lambda: FakeRegistry())

    result = router.process_all_symbols(
        ["AAA"],
        feature_frame[feature_frame["symbol"] == "AAA"],
        pd.Timestamp("2026-05-18T00:00:00Z"),
    )

    assert result["aggregated_signal"].tolist() == [pytest.approx(0.48)]
    assert registry_calls == [
        ("load", "xgb_prod"),
        ("load", "lstm_prod"),
        ("meta", "xgb_prod"),
        ("meta", "lstm_prod"),
    ]


def test_process_all_symbols_rejects_feature_lookahead(feature_frame: pd.DataFrame) -> None:
    router = MultiSymbolRouter()
    router.set_models(RecordingModel(0.1), RecordingModel(0.2))
    violating = feature_frame.copy()
    violating.loc[violating.index[-1], "timestamp"] = pd.Timestamp("2026-05-18T12:00:00Z")

    with pytest.raises(ValueError, match="PIT Safety violation"):
        router.process_all_symbols(["AAA", "BBB"], violating, pd.Timestamp("2026-05-18T00:00:00Z"))


def test_process_all_symbols_rejects_invalid_model_provenance(feature_frame: pd.DataFrame) -> None:
    router = MultiSymbolRouter(RouterConfig(xgboost_model_name="xgb_prod", lstm_model_name="lstm_prod"))
    router.set_models(RecordingModel(0.1), RecordingModel(0.2))
    router.xgboost_metadata = {
        "metadata": {
            "trained_at": "2026-05-10T00:00:00Z",
            "available_at": "2026-05-20T00:00:00Z",
            "train_end_date": "2026-05-12T00:00:00Z",
            "validation_start_date": "2026-05-11T00:00:00Z",
        }
    }
    router.lstm_metadata = {
        "metadata": {
            "trained_at": "2026-05-10T00:00:00Z",
            "available_at": "2026-05-11T00:00:00Z",
            "train_end_date": "2026-05-09T00:00:00Z",
            "validation_start_date": "2026-05-10T00:00:00Z",
        }
    }

    with pytest.raises(ValueError, match="PIT Safety violation|PIT Provenance check FAILED"):
        router.process_all_symbols(["AAA", "BBB"], feature_frame, pd.Timestamp("2026-05-18T00:00:00Z"))
