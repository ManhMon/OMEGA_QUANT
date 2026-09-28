from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from omega.quant.ensemble_optimizer import EnsembleOptimizer
from omega.quant.portfolio import regime_overlay


def test_weight_tilts_and_fallback(tmp_path, monkeypatch):
    from omega.core import llm_config

    now = datetime.now(timezone.utc)
    optimizer = EnsembleOptimizer()
    base = np.array([.5, .5])
    args = (base, ["momentum", "mean_reversion"], "BULL",
            {"momentum": .1, "mean_reversion": .2},
            {"momentum": .3, "mean_reversion": -.2}, now, now, tmp_path / "cache.db")
    options = {"influence": .6, "alpha_families": {"momentum": "momentum", "mean_reversion": "mean_reversion"}}
    for regime in ("momentum_heavy", "mean_reversion_heavy", "balanced", "defensive"):
        disagreement = "trend_supported" if regime == "momentum_heavy" else "reversal_supported" if regime == "mean_reversion_heavy" else "mixed"
        monkeypatch.setattr(llm_config, "classify_jev", lambda **kw: {"selected": {"weight_regime": regime} if kw["domain"] == "alpha_weight_regime" else {"outcome": disagreement}})
        result = optimizer.apply_jev_weight_tilt(*args, **options)
        assert np.isclose(result.sum(), 1)
        assert np.all(result <= .6)
        if regime == "momentum_heavy":
            assert result[0] > result[1]
        if regime == "mean_reversion_heavy":
            assert result[1] > result[0]
    monkeypatch.setattr(llm_config, "classify_jev", lambda **kw: (_ for _ in ()).throw(TimeoutError()))
    np.testing.assert_array_equal(optimizer.apply_jev_weight_tilt(*args, **options), base)
    with pytest.raises(ValueError):
        optimizer.apply_jev_weight_tilt(*(args[:5] + (now - timedelta(seconds=1), now) + args[7:]))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, "bad"])
def test_invalid_alpha_metrics_fail_closed(tmp_path, bad):
    now = datetime.now(timezone.utc)
    with pytest.raises((ValueError, TypeError)):
        EnsembleOptimizer().apply_jev_weight_tilt(
            np.array([.5, .5]), ["momentum", "mean_reversion"], "BULL",
            {"momentum": bad, "mean_reversion": 0}, {"momentum": 0, "mean_reversion": 0},
            now, now, tmp_path / "cache.db")


def test_regime_blend_pit_and_failure(tmp_path, monkeypatch):
    from omega.core import llm_config

    index = pd.date_range(end=datetime.now(timezone.utc) - timedelta(days=1), periods=263, freq="D")
    weights = pd.DataFrame({"VNM": np.full(263, .4)}, index=index)
    returns = np.linspace(-.01, .01, 263)
    source = pd.DataFrame({"value": ["BULL"], "as_of": [index[0]],
                           "available_at": [index[0]]}, index=index[:1])
    monkeypatch.setattr(regime_overlay, "_compute_hmm_regime_exposure", lambda *a, **kw: np.full(263, .8))
    class FakeHMM:
        def __init__(self, *a, **kw):
            self.is_fitted = False
            self.config = type("Config", (), {"features": ["returns", "volatility", "volume_change"]})()
            self.feature_means_ = np.zeros(3)
            self.feature_stds_ = np.ones(3)
            self.regime_map = {0: "Bull", 1: "Bear", 2: "Sideways"}
            self.model = type("Model", (), {"predict_proba": lambda self, x: np.array([[.5, .3, .2]])})()
        def fit(self, *a):
            self.is_fitted = True
    monkeypatch.setattr("omega.quant.strategy.regime_detector.RegimeDetectorHMM", FakeHMM)
    seen = []
    def classify(**kw):
        seen.append(kw)
        return {"selected": {"regime": "BULL"}}
    monkeypatch.setattr(llm_config, "classify_jev", classify)
    args = dict(strategy=regime_overlay.RegimeStrategy.JEV_ARBITRATED,
                 macro_llm=source, news_sentiment=source, jev_cache_path=tmp_path / "cache.db", jev_influence=.6)
    result = regime_overlay.apply_regime_overlay(weights, returns, **args)
    assert seen and all(call["available_at"] < call["as_of"] for call in seen)
    assert result.iloc[-1, 0] == pytest.approx(.4 * (.6 * 1.1 + .4 * .8))
    monkeypatch.setattr(llm_config, "classify_jev", lambda **kw: (_ for _ in ()).throw(TimeoutError()))
    fallback = regime_overlay.apply_regime_overlay(weights, returns, **args)
    assert fallback.iloc[-1, 0] == pytest.approx(.4 * .8)
    future = source.assign(available_at=index[-1] + timedelta(days=1))
    fallback = regime_overlay.apply_regime_overlay(weights, returns, **{**args, "news_sentiment": future})
    assert fallback.iloc[-1, 0] == pytest.approx(.4 * .8)


def test_four_state_schema_matches_stable_model():
    assert [regime_overlay.map_four_state_regime(i) for i in range(4)] == list(regime_overlay.REGIME_STATES)
    with pytest.raises(ValueError):
        regime_overlay.map_four_state_regime(4)


def test_disabled_alpha_never_calls_provider(tmp_path, monkeypatch):
    from omega.core import llm_config
    monkeypatch.setattr(llm_config, "classify_jev", lambda **kw: pytest.fail("disabled provider call"))
    now = datetime.now(timezone.utc)
    base = np.array([.5, .5])
    out = EnsembleOptimizer().apply_jev_weight_tilt(base, ["a", "b"], "BULL",
        {"a": 0., "b": 0.}, {"a": 0., "b": 0.}, now, now, tmp_path / "cache")
    np.testing.assert_array_equal(out, base)


@pytest.mark.parametrize("disagreement", ["insufficient", "unknown", "mixed"])
def test_alpha_disagreement_fallback(tmp_path, monkeypatch, disagreement):
    from omega.core import llm_config
    monkeypatch.setattr(llm_config, "classify_jev", lambda **kw: {"selected": {
        "weight_regime": "momentum_heavy"} if kw["domain"] == "alpha_weight_regime" else {"outcome": disagreement}})
    now = datetime.now(timezone.utc)
    base = np.array([.5, .5])
    result = EnsembleOptimizer().apply_jev_weight_tilt(base, ["a", "b"], "BULL",
        {"a": 0., "b": 0.}, {"a": 0., "b": 0.}, now, now, tmp_path / "cache",
        influence=.5, alpha_families={"a": "momentum", "b": "mean_reversion"})
    np.testing.assert_array_equal(result, base)


def test_real_classifier_boundary_for_both_domains(tmp_path, monkeypatch):
    from omega.core import llm_config

    calls = []
    import sys
    import types

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def system_one(self, *, state, questions):
            calls.append(state["domain"])
            raise TimeoutError("injected provider failure")

    monkeypatch.setitem(sys.modules, "typesafe_sdk", types.SimpleNamespace(Choice=lambda **kw: kw, TypeSafeClient=Client))
    now = datetime.now(timezone.utc) + timedelta(seconds=5)
    base = np.array([.5, .5])
    tilted = EnsembleOptimizer().apply_jev_weight_tilt(
        base, ["a", "b"], "BULL", {"a": .1, "b": .2}, {"a": .3, "b": -.2},
        now, now, tmp_path / "cache", influence=.5,
        alpha_families={"a": "momentum", "b": "mean_reversion"})
    assert calls == ["alpha_weight_regime"]
    np.testing.assert_array_equal(tilted, base)


def test_historical_regime_classifier_cache_miss_disables_provider(tmp_path, monkeypatch):
    import sys
    import types
    from omega.core import llm_config

    class Client:
        def __init__(self, **kwargs):
            pytest.fail("historical cutoff called provider")

    monkeypatch.setitem(sys.modules, "typesafe_sdk", types.SimpleNamespace(TypeSafeClient=Client))
    real_classify = llm_config.classify_jev
    calls = []

    def classify(**kwargs):
        calls.append((kwargs["mode"], kwargs["as_of"]))
        return real_classify(**kwargs)

    monkeypatch.setattr(llm_config, "classify_jev", classify)
    monkeypatch.setattr(regime_overlay, "_compute_hmm_regime_exposure",
                        lambda *args, **kwargs: np.full(263, .8))

    class FakeHMM:
        def __init__(self, *args, **kwargs):
            self.is_fitted = False
            self.config = type("Config", (), {"features": ["returns", "volatility", "volume_change"]})()
            self.feature_means_ = np.zeros(3)
            self.feature_stds_ = np.ones(3)
            self.regime_map = {0: "Bull", 1: "Bear", 2: "Sideways"}
            self.model = type("Model", (), {"predict_proba": lambda self, x: np.array([[.5, .3, .2]])})()

        def fit(self, *args):
            self.is_fitted = True

    monkeypatch.setattr("omega.quant.strategy.regime_detector.RegimeDetectorHMM", FakeHMM)
    index = pd.date_range(end=datetime.now(timezone.utc) - timedelta(days=1), periods=263, freq="D")
    source = pd.DataFrame({"value": ["BULL"], "as_of": [index[0]],
                           "available_at": [index[0]]}, index=index[:1])
    weights = pd.DataFrame({"VNM": np.full(263, .4)}, index=index)
    result = regime_overlay.apply_regime_overlay(
        weights, np.zeros(263), strategy=regime_overlay.RegimeStrategy.JEV_ARBITRATED,
        macro_llm=source, news_sentiment=source, jev_cache_path=tmp_path / "missing.db",
        jev_influence=.6)
    assert result.iloc[-1, 0] == pytest.approx(.32)
    assert calls and all(mode == "cache_only" and cutoff < datetime.now(timezone.utc)
                         for mode, cutoff in calls)


def test_hmm_early_features_prefix_invariant(monkeypatch):
    observed = []

    class CapturingHMM:
        def __init__(self, config):
            self.is_fitted = False

        def fit(self, features, returns):
            observed.append(features.iloc[:20]["volatility"].to_numpy(copy=True))
            self.is_fitted = True

        def predict_regime(self, features):
            return "Sideways"

    monkeypatch.setattr("omega.quant.strategy.regime_detector.RegimeDetectorHMM", CapturingHMM)
    prefix = np.linspace(-.01, .01, 30)
    regime_overlay._compute_hmm_regime_exposure(np.r_[prefix, np.zeros(10)], min_train_samples=25)
    first = observed[0]
    observed.clear()
    regime_overlay._compute_hmm_regime_exposure(np.r_[prefix, np.full(10, .9)], min_train_samples=25)
    np.testing.assert_array_equal(observed[0], first)
    assert first[0] == 0 and first[1] > 0


def test_disabled_regime_preserves_hmm_baseline(monkeypatch):
    monkeypatch.setattr(regime_overlay, "_compute_hmm_regime_exposure", lambda *a, **kw: np.full(263, .8))
    index = pd.date_range(end=datetime.now(timezone.utc) - timedelta(days=1), periods=263, freq="D")
    weights = pd.DataFrame({"VNM": np.full(263, .4)}, index=index)
    result = regime_overlay.apply_regime_overlay(weights, np.zeros(263),
        strategy=regime_overlay.RegimeStrategy.JEV_ARBITRATED)
    np.testing.assert_allclose(result.to_numpy(), .32)
