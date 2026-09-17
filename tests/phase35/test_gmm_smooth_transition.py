import numpy as np
import pandas as pd
import pytest

from omega.quant.strategy.latent_gmm import LatentGMMConfig, LatentGMMRegime
from omega.quant.evolution.feature_adapter import GPFeatureAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cluster_df() -> pd.DataFrame:
    rng = np.random.RandomState(42)
    n_per = 80
    bear = np.column_stack([
        rng.normal(8.0, 0.15, n_per),
        rng.normal(0.0, 0.05, n_per),
        rng.normal(0.0, 0.05, n_per),
    ])
    sideways = np.column_stack([
        rng.normal(1.2, 0.10, n_per),
        rng.normal(1.2, 0.10, n_per),
        rng.normal(0.0, 0.05, n_per),
    ])
    bull = np.column_stack([
        rng.normal(0.15, 0.03, n_per),
        rng.normal(0.0, 0.03, n_per),
        rng.normal(0.0, 0.03, n_per),
    ])
    latent = np.vstack([bear, sideways, bull])
    df = pd.DataFrame(latent, columns=["latent_ae_00", "latent_ae_01", "latent_ae_11"])
    df["returns"] = np.concatenate([
        rng.normal(-0.02, 0.002, n_per),
        rng.normal(0.0005, 0.001, n_per),
        rng.normal(0.025, 0.002, n_per),
    ])
    return df


@pytest.fixture
def cluster_df() -> pd.DataFrame:
    return _make_cluster_df()


@pytest.fixture
def gmm_discrete(cluster_df: pd.DataFrame) -> LatentGMMRegime:
    cfg = LatentGMMConfig(
        n_components=3,
        latent_columns=["latent_ae_00", "latent_ae_01", "latent_ae_11"],
        min_training_samples=20,
        n_init=5,
        random_state=42,
        smooth_transition=False,
    )
    m = LatentGMMRegime(cfg)
    m.fit(cluster_df)
    assert m.is_fitted
    return m


@pytest.fixture
def gmm_smooth(cluster_df: pd.DataFrame) -> LatentGMMRegime:
    cfg = LatentGMMConfig(
        n_components=3,
        latent_columns=["latent_ae_00", "latent_ae_01", "latent_ae_11"],
        min_training_samples=20,
        n_init=5,
        random_state=42,
        smooth_transition=True,
        smooth_transition_temp=0.1,
    )
    m = LatentGMMRegime(cfg)
    m.fit(cluster_df)
    assert m.is_fitted
    return m


# ---------------------------------------------------------------------------
# Tests: Latent GMM smooth transition
# ---------------------------------------------------------------------------

def test_smooth_scale_in_bounds(gmm_smooth: LatentGMMRegime, cluster_df: pd.DataFrame) -> None:
    _, proba = gmm_smooth.predict_regime(cluster_df)
    scales = gmm_smooth.get_exposure_scale(proba)
    assert scales.shape == (len(cluster_df),)
    assert np.all(scales >= 0.1), f"Min scale {scales.min():.4f} < 0.1"
    assert np.all(scales <= 2.0), f"Max scale {scales.max():.4f} > 2.0"


def test_smooth_transition_false_is_discrete(gmm_discrete: LatentGMMRegime, cluster_df: pd.DataFrame) -> None:
    _, proba = gmm_discrete.predict_regime(cluster_df)
    scales = gmm_discrete.get_exposure_scale(proba)
    assert scales.shape == (len(cluster_df),)
    assert np.all(scales >= 0.1)
    assert np.all(scales <= 2.0)
    expected = np.zeros(len(proba))
    for sid, rname in gmm_discrete._regime_map.items():
        if rname == "Bear":
            expected += proba[:, sid] * gmm_discrete.config.bear_dampening
        elif rname == "Bull":
            expected += proba[:, sid] * gmm_discrete.config.bull_boost
        else:
            expected += proba[:, sid] * gmm_discrete.config.sideways_scale
    np.testing.assert_allclose(scales, expected, atol=1e-6)


def test_smooth_transition_differs_when_enabled(gmm_discrete: LatentGMMRegime, gmm_smooth: LatentGMMRegime, cluster_df: pd.DataFrame) -> None:
    _, proba = gmm_discrete.predict_regime(cluster_df)
    scales_disc = gmm_discrete.get_exposure_scale(proba)
    scales_smooth = gmm_smooth.get_exposure_scale(proba)
    assert not np.allclose(scales_disc, scales_smooth), "Smooth and discrete should differ for mixed-probability rows"


def _make_prob_by_regime(gmm: LatentGMMRegime, n: int, bull_w: float, bear_w: float, sideways_w: float) -> np.ndarray:
    proba = np.zeros((n, gmm.config.n_components))
    for sid, rname in gmm._regime_map.items():
        if rname == "Bull":
            proba[:, sid] = bull_w
        elif rname == "Bear":
            proba[:, sid] = bear_w
        elif rname == "Sideways":
            proba[:, sid] = sideways_w
    return proba


def test_smooth_high_bull_low_bear(gmm_smooth: LatentGMMRegime) -> None:
    n = 10
    proba = _make_prob_by_regime(gmm_smooth, n, bull_w=0.9, bear_w=0.05, sideways_w=0.05)
    scales = gmm_smooth.get_exposure_scale(proba)
    assert np.all(scales > 0.9), f"Expected bull-biased scales, got {scales}"
    assert np.all(scales <= 2.0)


def test_smooth_high_bear_low_bull(gmm_smooth: LatentGMMRegime) -> None:
    n = 10
    proba = _make_prob_by_regime(gmm_smooth, n, bull_w=0.05, bear_w=0.9, sideways_w=0.05)
    scales = gmm_smooth.get_exposure_scale(proba)
    assert np.all(scales < 0.6), f"Expected bear-biased scales, got {scales}"
    assert np.all(scales >= 0.1)


# ---------------------------------------------------------------------------
# Tests: Feature adapter loads vn_specific
# ---------------------------------------------------------------------------

@pytest.fixture
def feat_adapter() -> GPFeatureAdapter:
    return GPFeatureAdapter()


def test_feature_adapter_loads_vn_specific(feat_adapter: GPFeatureAdapter) -> None:
    sources = feat_adapter.available_sources()
    assert "vn_specific" in sources, f"Expected vn_specific in sources, got {sources}"


def test_vn_specific_produces_alpha_columns() -> None:
    rng = np.random.RandomState(42)
    n = 200
    tickers = ["A", "B"]
    dates = pd.date_range("2024-01-01", periods=n // 2, freq="B")
    rows = []
    for t in tickers:
        for d in dates[: n // 2]:
            rows.append({
                "ticker": t, "date": d,
                "open": rng.uniform(10, 50),
                "high": rng.uniform(10, 55),
                "low": rng.uniform(8, 50),
                "close": rng.uniform(10, 52),
                "volume": rng.randint(10000, 500000),
            })
    df = pd.DataFrame(rows).sort_values(["ticker", "date"]).reset_index(drop=True)
    adapter = GPFeatureAdapter()
    result = adapter.compute_all(df, top_n_features=200)
    vn_cols = [k for k in result if k.startswith("alpha_vnspec_")]
    assert len(vn_cols) > 0, f"Expected at least one vn_specific alpha, got {len(vn_cols)}"
    # Check a few known names
    known = ["alpha_vnspec_compute_vn_amihud_liquidity_reversal",
             "alpha_vnspec_alpha_vn_001_post_settlement_momentum"]
    for name in known:
        assert name in result, f"Missing expected alpha: {name}"
