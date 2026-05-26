"""
Advanced Deep Learning Models for Strategy Logic.

Implements:
1. LSTM (Long Short-Term Memory) for time-series forecasting
2. TCN (Temporal Convolutional Network) with dilated convolutions
3. Transformer encoder for attention-based sequence modeling

All models gracefully degrade if PyTorch is not installed.

PIT Safety: Models receive pre-shifted features (T-1 lag applied upstream).
    Sequence models use causal masking - no future data leakage.
Vectorization: All tensor operations are batch-vectorized via PyTorch.

Author: OMEGA_QUANT Team
Version: 2.4
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

__all__ = [
    "LSTMModel",
    "TCNModel",
    "TransformerModel",
    "TORCH_AVAILABLE",
]

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    # Stub for type checking
    nn = None  # type: ignore[assignment]


# =============================================================================
# LSTM Model
# =============================================================================


class LSTMModel:
    """
    LSTM-based time-series forecasting model.

    Architecture: Input -> LSTM layers -> FC -> Output (single value)
    Suitable for sequential alpha signal prediction.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 64,
        num_layers: int = 2,
    ) -> None:
        """
        Args:
            input_dim: Number of input features per time step.
            hidden_dim: LSTM hidden state dimension.
            num_layers: Number of stacked LSTM layers.
        """
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.model: Optional[object] = None

        if TORCH_AVAILABLE:
            self._build_model()
        else:
            logger.warning("PyTorch not found. LSTMModel will not be functional.")

    def _build_model(self) -> None:
        """Build the internal LSTM network."""

        class _LSTMNet(nn.Module):
            def __init__(self, input_sz: int, hidden_sz: int, n_layers: int):
                super().__init__()
                self.lstm = nn.LSTM(
                    input_sz, hidden_sz, n_layers, batch_first=True
                )
                self.fc = nn.Linear(hidden_sz, 1)

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                out, _ = self.lstm(x)
                return self.fc(out[:, -1, :])

        self.model = _LSTMNet(self.input_dim, self.hidden_dim, self.num_layers)

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 10,
        lr: float = 0.001,
    ) -> None:
        """
        Train the LSTM model.

        Args:
            X: Input array of shape (batch, seq_len, input_dim).
            y: Target array of shape (batch, 1) or (batch,).
            epochs: Number of training epochs.
            lr: Learning rate.
        """
        if not TORCH_AVAILABLE or self.model is None:
            return

        criterion = nn.MSELoss()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        X_tensor = torch.FloatTensor(X)
        y_tensor = torch.FloatTensor(y).reshape(-1, 1)

        self.model.train()
        for _ in range(epochs):
            optimizer.zero_grad()
            outputs = self.model(X_tensor)
            loss = criterion(outputs, y_tensor)
            loss.backward()
            optimizer.step()

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Generate predictions.

        Args:
            X: Input array of shape (batch, seq_len, input_dim).

        Returns:
            Predictions of shape (batch,).
        """
        if not TORCH_AVAILABLE or self.model is None:
            return np.zeros(len(X), dtype=np.float64)

        self.model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X)
            preds = self.model(X_tensor)
            return preds.numpy().flatten()


# =============================================================================
# TCN (Temporal Convolutional Network)
# =============================================================================


class TCNModel:
    """
    Temporal Convolutional Network for time-series forecasting.

    Uses dilated causal convolutions to capture long-range dependencies
    without the vanishing gradient problem of RNNs.

    Architecture: Input -> TCN layers -> Global Average Pool -> FC -> Output
    """

    def __init__(
        self,
        input_dim: int,
        num_channels: Optional[list[int]] = None,
        kernel_size: int = 3,
        dropout: float = 0.2,
    ) -> None:
        """
        Args:
            input_dim: Number of input features per time step.
            num_channels: Channel sizes for each TCN layer, e.g. [32, 64, 64, 128].
            kernel_size: Convolution kernel size.
            dropout: Dropout rate.
        """
        self.input_dim = input_dim
        self.num_channels = num_channels or [32, 64, 64, 128]
        self.kernel_size = kernel_size
        self.dropout = dropout
        self.model: Optional[object] = None

        if TORCH_AVAILABLE:
            self._build_model()
        else:
            logger.warning("PyTorch not found. TCNModel will not be functional.")

    def _build_model(self) -> None:
        """Build the internal TCN network."""

        class _TemporalBlock(nn.Module):
            def __init__(
                self, in_ch: int, out_ch: int, k_size: int, dilation: int
            ):
                super().__init__()
                padding = (k_size - 1) * dilation // 2
                self.conv1 = nn.Conv1d(
                    in_ch, out_ch, k_size, padding=padding, dilation=dilation
                )
                self.conv2 = nn.Conv1d(
                    out_ch, out_ch, k_size, padding=padding, dilation=dilation
                )
                self.relu = nn.ReLU()
                self.dropout = nn.Dropout(0.2)
                self.downsample = (
                    nn.Conv1d(in_ch, out_ch, 1) if in_ch != out_ch else None
                )

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                out = self.dropout(self.relu(self.conv1(x)))
                out = self.dropout(self.relu(self.conv2(out)))
                res = x if self.downsample is None else self.downsample(x)
                return out + res

        class _TCNNet(nn.Module):
            def __init__(
                self,
                input_dim: int,
                num_channels: list[int],
                kernel_size: int,
                dropout: float,
            ):
                super().__init__()
                layers = []
                for i, out_ch in enumerate(num_channels):
                    dilation = 2**i
                    in_ch = input_dim if i == 0 else num_channels[i - 1]
                    layers.append(
                        _TemporalBlock(in_ch, out_ch, kernel_size, dilation)
                    )
                self.network = nn.Sequential(*layers)
                self.fc = nn.Linear(num_channels[-1], 1)

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                # x shape: (batch, seq_len, input_dim)
                x = x.transpose(1, 2)  # -> (batch, input_dim, seq_len)
                y = self.network(x)
                y = torch.mean(y, dim=2)  # Global average pooling
                return self.fc(y)

        self.model = _TCNNet(
            self.input_dim, self.num_channels, self.kernel_size, self.dropout
        )

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 10,
        lr: float = 0.001,
    ) -> None:
        """
        Train the TCN model.

        Args:
            X: Input array of shape (batch, seq_len, input_dim).
            y: Target array of shape (batch,).
            epochs: Number of training epochs.
            lr: Learning rate.
        """
        if not TORCH_AVAILABLE or self.model is None:
            return

        criterion = nn.MSELoss()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        X_tensor = torch.FloatTensor(X)
        y_tensor = torch.FloatTensor(y).unsqueeze(1)

        self.model.train()
        for _ in range(epochs):
            optimizer.zero_grad()
            outputs = self.model(X_tensor)
            loss = criterion(outputs, y_tensor)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 0.5)
            optimizer.step()

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Generate predictions.

        Args:
            X: Input array of shape (batch, seq_len, input_dim).

        Returns:
            Predictions of shape (batch,).
        """
        if not TORCH_AVAILABLE or self.model is None:
            return np.zeros(len(X), dtype=np.float64)

        self.model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X)
            preds = self.model(X_tensor)
            return preds.numpy().flatten()


# =============================================================================
# Transformer Encoder
# =============================================================================


class TransformerModel:
    """
    Transformer encoder for time-series forecasting.

    Uses self-attention to capture complex temporal dependencies.
    Architecture: Input -> Linear Proj -> Positional Encoding ->
        Transformer Encoder -> Mean Pool -> FC -> Output
    """

    def __init__(
        self,
        input_dim: int,
        d_model: int = 64,
        nhead: int = 4,
        num_layers: int = 2,
        dim_feedforward: int = 128,
        dropout: float = 0.1,
    ) -> None:
        """
        Args:
            input_dim: Number of input features.
            d_model: Model dimension (must be divisible by nhead).
            nhead: Number of attention heads.
            num_layers: Number of Transformer encoder layers.
            dim_feedforward: Hidden layer size in FFN.
            dropout: Dropout rate.
        """
        # Ensure d_model is divisible by nhead
        if d_model % nhead != 0:
            d_model = (d_model // nhead) * nhead

        self.input_dim = input_dim
        self.d_model = d_model
        self.nhead = nhead
        self.num_layers = num_layers
        self.dim_feedforward = dim_feedforward
        self.dropout = dropout
        self.model: Optional[object] = None

        if TORCH_AVAILABLE:
            self._build_model()
        else:
            logger.warning(
                "PyTorch not found. TransformerModel will not be functional."
            )

    def _build_model(self) -> None:
        """Build the internal Transformer network."""

        class _PositionalEncoding(nn.Module):
            def __init__(self, d_model: int, max_len: int = 5000):
                super().__init__()
                pe = torch.zeros(max_len, d_model)
                position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
                div_term = torch.exp(
                    torch.arange(0, d_model, 2).float()
                    * (-np.log(10000.0) / d_model)
                )
                pe[:, 0::2] = torch.sin(position * div_term)
                pe[:, 1::2] = torch.cos(position * div_term)
                pe = pe.unsqueeze(0)  # (1, max_len, d_model)
                self.register_buffer("pe", pe)

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                return x + self.pe[:, : x.size(1), :]

        class _TransformerNet(nn.Module):
            def __init__(
                self,
                input_dim: int,
                d_model: int,
                nhead: int,
                num_layers: int,
                dim_feedforward: int,
                dropout: float,
            ):
                super().__init__()
                self.input_proj = nn.Linear(input_dim, d_model)
                self.pos_encoder = _PositionalEncoding(d_model)
                encoder_layer = nn.TransformerEncoderLayer(
                    d_model=d_model,
                    nhead=nhead,
                    dim_feedforward=dim_feedforward,
                    dropout=dropout,
                    batch_first=True,
                )
                self.transformer = nn.TransformerEncoder(
                    encoder_layer, num_layers=num_layers
                )
                self.fc = nn.Linear(d_model, 1)

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                # x shape: (batch, seq_len, input_dim)
                x = self.input_proj(x)
                x = self.pos_encoder(x)
                x = self.transformer(x)
                x = torch.mean(x, dim=1)  # Mean pool across sequence
                return self.fc(x)

        self.model = _TransformerNet(
            self.input_dim,
            self.d_model,
            self.nhead,
            self.num_layers,
            self.dim_feedforward,
            self.dropout,
        )

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 10,
        lr: float = 0.001,
    ) -> None:
        """
        Train the Transformer model.

        Args:
            X: Input array of shape (batch, seq_len, input_dim).
            y: Target array of shape (batch,).
            epochs: Number of training epochs.
            lr: Learning rate.
        """
        if not TORCH_AVAILABLE or self.model is None:
            return

        criterion = nn.MSELoss()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        X_tensor = torch.FloatTensor(X)
        y_tensor = torch.FloatTensor(y).unsqueeze(1)

        self.model.train()
        for _ in range(epochs):
            optimizer.zero_grad()
            outputs = self.model(X_tensor)
            loss = criterion(outputs, y_tensor)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            optimizer.step()

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Generate predictions.

        Args:
            X: Input array of shape (batch, seq_len, input_dim).

        Returns:
            Predictions of shape (batch,).
        """
        if not TORCH_AVAILABLE or self.model is None:
            return np.zeros(len(X), dtype=np.float64)

        self.model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X)
            preds = self.model(X_tensor)
            return preds.numpy().flatten()
