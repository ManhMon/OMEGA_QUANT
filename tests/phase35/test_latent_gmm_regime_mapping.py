import numpy as np
import pandas as pd

from omega.quant.strategy.latent_gmm import LatentGMMConfig, LatentGMMRegime


def _make_cluster_df(include_returns: bool = True) -> pd.DataFrame:
    rng = np.random.RandomState(42)
    n_per_cluster = 80

    bear_latent = np.column_stack(
        [
            rng.normal(8.0, 0.15, n_per_cluster),
            rng.normal(0.0, 0.05, n_per_cluster),
            rng.normal(0.0, 0.05, n_per_cluster),
        ]
    )
    sideways_latent = np.column_stack(
        [
            rng.normal(1.2, 0.10, n_per_cluster),
            rng.normal(1.2, 0.10, n_per_cluster),
            rng.normal(0.0, 0.05, n_per_cluster),
        ]
    )
    bull_latent = np.column_stack(
        [
            rng.normal(0.15, 0.03, n_per_cluster),
            rng.normal(0.0, 0.03, n_per_cluster),
            rng.normal(0.0, 0.03, n_per_cluster),
        ]
    )

    latent = np.vstack([bear_latent, sideways_latent, bull_latent])
    df = pd.DataFrame(
        latent,
        columns=["latent_ae_00", "latent_ae_01", "latent_ae_11"],
    )
    df["cluster"] = (
        ["bear_like"] * n_per_cluster
        + ["sideways_like"] * n_per_cluster
        + ["bull_like"] * n_per_cluster
    )

    if include_returns:
        df["returns"] = np.concatenate(
            [
                rng.normal(-0.02, 0.002, n_per_cluster),
                rng.normal(0.0005, 0.001, n_per_cluster),
                rng.normal(0.025, 0.002, n_per_cluster),
            ]
        )

    return df


def _fit_model(df: pd.DataFrame) -> LatentGMMRegime:
    model = LatentGMMRegime(
        LatentGMMConfig(
            n_components=3,
            latent_columns=["latent_ae_00", "latent_ae_01", "latent_ae_11"],
            min_training_samples=20,
            n_init=5,
            random_state=42,
        )
    )
    model.fit(df)
    assert model.is_fitted
    return model


def _dominant_label_per_cluster(model: LatentGMMRegime, df: pd.DataFrame) -> dict:
    labels, _ = model.predict_regime(df)
    result = {}
    for cluster_name, idx in df.groupby("cluster").groups.items():
        cluster_labels = pd.Series(labels[list(idx)])
        result[cluster_name] = cluster_labels.mode().iat[0]
    return result


def test_latent_gmm_maps_semantics_from_train_returns() -> None:
    df = _make_cluster_df(include_returns=True)
    model = _fit_model(df)

    dominant_labels = _dominant_label_per_cluster(model, df)

    assert dominant_labels["bull_like"] == "Bull"
    assert dominant_labels["sideways_like"] == "Sideways"
    assert dominant_labels["bear_like"] == "Bear"


def test_latent_gmm_falls_back_to_norm_heuristic_without_returns() -> None:
    df = _make_cluster_df(include_returns=False)
    model = _fit_model(df)

    dominant_labels = _dominant_label_per_cluster(model, df)

    assert dominant_labels["bear_like"] == "Bull"
    assert dominant_labels["bull_like"] == "Bear"
