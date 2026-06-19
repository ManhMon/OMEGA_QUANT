"""Unsupervised Latent Representation Learner.

Trains a PyTorch-based Autoencoder on sequential feature inputs to extract
low-dimensional latent representations.
Point-in-Time safe: Trained strictly on historical fold data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

logger = logging.getLogger(__name__)


@dataclass
class LatentEncoderConfig:
    """Hyperparameters for the unsupervised latent encoder."""
    lookback: int = 60          # sequence length T
    n_features: int = 114       # feature dimension F
    latent_dim: int = 16        # output dimension D
    hidden_dim: int = 128
    dropout: float = 0.1
    lr: float = 1e-3
    weight_decay: float = 1e-5
    epochs: int = 5
    batch_size: int = 256
    seed: int = 42
    n_threads: int = 4


class _AutoencoderNet(nn.Module):
    """Simple MLP Autoencoder for robust sequence representation."""

    def __init__(
        self, input_dim: int, hidden_dim: int, latent_dim: int, dropout: float
    ):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, latent_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, input_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (N, input_dim)
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        # x: (N, input_dim)
        return self.encoder(x)


class UnsupervisedLatentEncoder:
    """
    Sklearn-like wrapper for unsupervised autoencoder training and transformation.
    """

    def __init__(self, cfg: Optional[LatentEncoderConfig] = None):
        self.cfg = cfg or LatentEncoderConfig()
        self.model: Optional[_AutoencoderNet] = None
        self._fitted: bool = False

    def _set_determinism(self) -> None:
        torch.manual_seed(self.cfg.seed)
        np.random.seed(self.cfg.seed)
        torch.set_num_threads(self.cfg.n_threads)
        try:
            torch.use_deterministic_algorithms(True, warn_only=True)
        except Exception:
            pass

    def fit(self, X_seq: np.ndarray) -> UnsupervisedLatentEncoder:
        """
        Train the autoencoder on 3D sequence array of shape (N, T, F).
        """
        if X_seq.ndim != 3:
            raise ValueError(f"X_seq must be 3D (N, T, F), got shape {X_seq.shape}")

        N, T, F = X_seq.shape
        if T != self.cfg.lookback or F != self.cfg.n_features:
            # Dynamically adapt config if not explicitly set
            self.cfg.lookback = T
            self.cfg.n_features = F

        self._set_determinism()
        input_dim = T * F

        # Flatten sequences to (N, T * F)
        X_flat = X_seq.reshape(N, input_dim).astype(np.float32)

        device = torch.device("cpu")
        self.model = _AutoencoderNet(
            input_dim=input_dim,
            hidden_dim=self.cfg.hidden_dim,
            latent_dim=self.cfg.latent_dim,
            dropout=self.cfg.dropout,
        ).to(device)

        X_tensor = torch.from_numpy(X_flat)
        ds = TensorDataset(X_tensor)
        gen = torch.Generator().manual_seed(self.cfg.seed)
        loader = DataLoader(
            ds, batch_size=self.cfg.batch_size, shuffle=True,
            generator=gen, num_workers=0, drop_last=False
        )

        opt = torch.optim.AdamW(
            self.model.parameters(), lr=self.cfg.lr,
            weight_decay=self.cfg.weight_decay
        )
        loss_fn = nn.MSELoss()

        for epoch in range(self.cfg.epochs):
            self.model.train()
            total_loss = 0.0
            for xb, in loader:
                opt.zero_grad()
                reconstructed = self.model(xb)
                loss = loss_fn(reconstructed, xb)
                loss.backward()
                opt.step()
                total_loss += loss.item() * len(xb)

            avg_loss = total_loss / len(X_flat)
            logger.debug(
                "Autoencoder Epoch %d/%d - Reconstruction Loss: %.6f",
                epoch + 1, self.cfg.epochs, avg_loss,
            )

        self._fitted = True
        return self

    def transform(self, X_seq: np.ndarray) -> np.ndarray:
        """
        Project 3D sequences (N, T, F) to 2D latent (N, latent_dim).
        """
        if not self._fitted or self.model is None:
            N = len(X_seq)
            return np.zeros((N, self.cfg.latent_dim), dtype=np.float32)

        if X_seq.ndim != 3:
            raise ValueError(f"X_seq must be 3D (N, T, F), got shape {X_seq.shape}")

        N, T, F = X_seq.shape
        input_dim = T * F
        X_flat = X_seq.reshape(N, input_dim).astype(np.float32)

        self.model.eval()
        with torch.no_grad():
            X_tensor = torch.from_numpy(X_flat)
            latent = self.model.encode(X_tensor)

        return latent.numpy().astype(np.float64)

    def fit_transform(self, X_seq: np.ndarray) -> np.ndarray:
        """Fit on sequences and return their latent representation."""
        return self.fit(X_seq).transform(X_seq)


# ===================================================================
# Deep Nonlinear Autoencoder — GATE: LATENT_ALPHA_MINING_64D_20260617
# ===================================================================


@dataclass
class DeepAutoencoderConfig:
    """Hyperparameters for the deep nonlinear autoencoder."""
    n_features: int = 64        # input feature dimension F
    latent_dim: int = 16        # bottleneck dimension D
    hidden_dims: tuple = (256, 128, 64)  # encoder hidden layers (decoder mirrors)
    activation: str = "gelu"    # 'relu', 'leaky_relu', or 'gelu'
    dropout: float = 0.1
    batch_norm: bool = True
    lr: float = 1e-3
    weight_decay: float = 1e-5
    epochs: int = 20
    batch_size: int = 256
    seed: int = 42
    n_threads: int = 4
    early_stop_patience: int = 5
    early_stop_min_delta: float = 1e-5


def _get_activation(name: str) -> nn.Module:
    """Return activation module by name."""
    if name == "relu":
        return nn.ReLU()
    elif name == "leaky_relu":
        return nn.LeakyReLU(0.1)
    elif name == "gelu":
        return nn.GELU()
    else:
        raise ValueError(f"Unknown activation: {name}. Use 'relu', 'leaky_relu', or 'gelu'.")


class _DeepNonlinearAutoencoderNet(nn.Module):
    """Deep MLP Autoencoder with multiple hidden layers and nonlinear activations.

    Architecture (encoder):
        input → [Linear → BN → Act → Dropout] × N → Linear → latent

    Architecture (decoder):
        latent → [Linear → BN → Act → Dropout] × N → Linear → output

    Supports both 2D input (N, F) and 3D input (N, T, F) — 3D is flattened
    internally to (N, T*F) before passing through the encoder.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dims: tuple,
        latent_dim: int,
        activation: str = "gelu",
        dropout: float = 0.1,
        batch_norm: bool = True,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim

        # Build encoder layers
        encoder_layers: list[nn.Module] = []
        prev_dim = input_dim
        for h_dim in hidden_dims:
            encoder_layers.append(nn.Linear(prev_dim, h_dim))
            if batch_norm:
                encoder_layers.append(nn.BatchNorm1d(h_dim))
            encoder_layers.append(_get_activation(activation))
            encoder_layers.append(nn.Dropout(dropout))
            prev_dim = h_dim
        # Final encoder projection to latent space
        encoder_layers.append(nn.Linear(prev_dim, latent_dim))
        self.encoder = nn.Sequential(*encoder_layers)

        # Build decoder layers (mirror of encoder)
        decoder_layers: list[nn.Module] = []
        prev_dim = latent_dim
        for h_dim in reversed(hidden_dims):
            decoder_layers.append(nn.Linear(prev_dim, h_dim))
            if batch_norm:
                decoder_layers.append(nn.BatchNorm1d(h_dim))
            decoder_layers.append(_get_activation(activation))
            decoder_layers.append(nn.Dropout(dropout))
            prev_dim = h_dim
        # Final decoder projection to input space
        decoder_layers.append(nn.Linear(prev_dim, input_dim))
        self.decoder = nn.Sequential(*decoder_layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass: encode then decode.

        Parameters
        ----------
        x : Tensor
            Shape (N, input_dim) for 2D or (N, T, F) for 3D.

        Returns
        -------
        Tensor
            Reconstructed input, same shape as input.
        """
        original_shape = x.shape
        if x.ndim == 3:
            x = x.reshape(x.size(0), -1)
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        if len(original_shape) == 3:
            reconstructed = reconstructed.reshape(original_shape)
        return reconstructed

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        """Encode input to latent representation.

        Parameters
        ----------
        x : Tensor
            Shape (N, input_dim) for 2D or (N, T, F) for 3D.

        Returns
        -------
        Tensor
            Latent representation, shape (N, latent_dim).
        """
        if x.ndim == 3:
            x = x.reshape(x.size(0), -1)
        return self.encoder(x)


class NonlinearDeepLatentEncoder:
    """Sklearn-like wrapper for deep nonlinear autoencoder training and transformation.

    Supports both 2D input (N, F) — cross-sectional features — and 3D input
    (N, T, F) — sequential features.  3D input is flattened internally.

    Output columns use the ``latent_ae_XX`` prefix convention.
    """

    def __init__(self, cfg: Optional[DeepAutoencoderConfig] = None):
        self.cfg = cfg or DeepAutoencoderConfig()
        self.model: Optional[_DeepNonlinearAutoencoderNet] = None
        self._fitted: bool = False
        self._input_dim: int = 0
        self._train_loss_history: list[float] = []

    def _set_determinism(self) -> None:
        torch.manual_seed(self.cfg.seed)
        np.random.seed(self.cfg.seed)
        torch.set_num_threads(self.cfg.n_threads)
        try:
            torch.use_deterministic_algorithms(True, warn_only=True)
        except Exception:
            pass

    def _prepare_input(self, X: np.ndarray) -> np.ndarray:
        """Validate and flatten input to 2D (N, D)."""
        if X.ndim == 3:
            N, T, F = X.shape
            return X.reshape(N, T * F).astype(np.float32)
        elif X.ndim == 2:
            return X.astype(np.float32)
        else:
            raise ValueError(
                f"X must be 2D (N, F) or 3D (N, T, F), got shape {X.shape}"
            )

    def fit(self, X: np.ndarray) -> "NonlinearDeepLatentEncoder":
        """Train the deep autoencoder on input data.

        Parameters
        ----------
        X : ndarray
            2D (N, F) or 3D (N, T, F) input array.

        Returns
        -------
        self
        """
        X_flat = self._prepare_input(X)
        N, D = X_flat.shape
        self._input_dim = D

        self._set_determinism()

        device = torch.device("cpu")
        self.model = _DeepNonlinearAutoencoderNet(
            input_dim=D,
            hidden_dims=self.cfg.hidden_dims,
            latent_dim=self.cfg.latent_dim,
            activation=self.cfg.activation,
            dropout=self.cfg.dropout,
            batch_norm=self.cfg.batch_norm,
        ).to(device)

        X_tensor = torch.from_numpy(X_flat)
        ds = TensorDataset(X_tensor)
        gen = torch.Generator().manual_seed(self.cfg.seed)
        loader = DataLoader(
            ds, batch_size=self.cfg.batch_size, shuffle=True,
            generator=gen, num_workers=0, drop_last=False,
        )

        opt = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.cfg.lr,
            weight_decay=self.cfg.weight_decay,
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            opt, mode="min", factor=0.5, patience=3,
        )
        loss_fn = nn.MSELoss()

        self._train_loss_history = []
        best_loss = float("inf")
        patience_counter = 0

        for epoch in range(self.cfg.epochs):
            self.model.train()
            total_loss = 0.0
            for (xb,) in loader:
                opt.zero_grad()
                reconstructed = self.model(xb)
                loss = loss_fn(reconstructed, xb)
                loss.backward()
                opt.step()
                total_loss += loss.item() * len(xb)

            avg_loss = total_loss / N
            scheduler.step(avg_loss)
            self._train_loss_history.append(avg_loss)

            logger.debug(
                "DeepAE Epoch %d/%d - Loss: %.6f (lr=%.2e)",
                epoch + 1, self.cfg.epochs, avg_loss,
                opt.param_groups[0]["lr"],
            )

            # Early stopping
            if avg_loss < best_loss - self.cfg.early_stop_min_delta:
                best_loss = avg_loss
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= self.cfg.early_stop_patience:
                    logger.debug(
                        "DeepAE early stopping at epoch %d (best_loss=%.6f)",
                        epoch + 1, best_loss,
                    )
                    break

        self._fitted = True
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Project input to latent representation.

        Parameters
        ----------
        X : ndarray
            2D (N, F) or 3D (N, T, F) input array.

        Returns
        -------
        ndarray (N, latent_dim)
            Latent representation with float64 dtype.
        """
        if not self._fitted or self.model is None:
            N = len(X)
            return np.zeros((N, self.cfg.latent_dim), dtype=np.float32)

        X_flat = self._prepare_input(X)

        self.model.eval()
        with torch.no_grad():
            X_tensor = torch.from_numpy(X_flat)
            latent = self.model.encode(X_tensor)

        return latent.numpy().astype(np.float64)

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        """Fit on data and return latent representation."""
        return self.fit(X).transform(X)

    def get_column_names(self) -> list[str]:
        """Return latent column names using ``latent_ae_XX`` convention."""
        return [f"latent_ae_{i:02d}" for i in range(self.cfg.latent_dim)]

    def get_reconstruction_loss(self, X: np.ndarray) -> float:
        """Compute mean reconstruction loss on input data.

        Parameters
        ----------
        X : ndarray
            2D (N, F) or 3D (N, T, F) input array.

        Returns
        -------
        float
            Mean MSE reconstruction loss.
        """
        if not self._fitted or self.model is None:
            return float("nan")

        X_flat = self._prepare_input(X)
        self.model.eval()
        with torch.no_grad():
            X_tensor = torch.from_numpy(X_flat)
            reconstructed = self.model(X_tensor)
            loss = nn.MSELoss()(reconstructed, X_tensor)

        return float(loss.item())
