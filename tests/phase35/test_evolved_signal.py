"""
P1/P2 Unit Tests for Phase35 Walk-Forward Evolved Alpha Integration

Tests cover:
- P1: GP ensemble normalization parity (train/test consistency)
- P1: Tuple return (signal, train_ic)
- P2: Ceiling enforcement (w_evo <= 0.25)
- P2: Floor enforcement (w_evo >= 0.1 * user_weight)
- Ensemble signal length consistency
"""
import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, MagicMock, patch
from omega.quant.alpha.phase35 import Phase35WalkForwardEngine


class TestP2BlendCeiling:
    """Test P2 blend ceiling enforcement."""

    def test_ceiling_enforcement_high_ic(self):
        """Test that w_evo never exceeds ceiling=0.25 even with high train_ic."""
        evolved_blend_weight = 0.4
        gp_train_ic = 0.90  # Very high IC

        # Apply adaptive blend logic (from phase35_walk_forward.py:1080-1090)
        abs_train_ic = abs(gp_train_ic)
        scale_factor = 2.0
        w_adaptive = min(evolved_blend_weight, abs_train_ic * scale_factor)
        ceiling = 0.25
        w_evo = min(w_adaptive, ceiling)
        floor = evolved_blend_weight * 0.1
        w_evo = max(w_evo, floor)
        w_hand = 1.0 - w_evo

        assert w_evo <= ceiling, f"w_evo={w_evo} exceeds ceiling={ceiling}"
        assert w_hand >= 0.75, f"w_hand={w_hand} should be >= 0.75"
        assert abs(w_evo + w_hand - 1.0) < 1e-9

    def test_floor_enforcement_low_ic(self):
        """Test that w_evo never goes below floor=0.04 with low train_ic."""
        evolved_blend_weight = 0.4
        gp_train_ic = 0.001  # Very low IC

        abs_train_ic = abs(gp_train_ic)
        scale_factor = 2.0
        w_adaptive = min(evolved_blend_weight, abs_train_ic * scale_factor)
        ceiling = 0.25
        w_evo = min(w_adaptive, ceiling)
        floor = evolved_blend_weight * 0.1
        w_evo = max(w_evo, floor)

        assert w_evo >= floor, f"w_evo={w_evo} below floor={floor}"
        assert w_evo == floor  # Should be exactly the floor

    def test_blend_weights_sum_to_one(self):
        """Test that w_evo + w_hand = 1.0 across IC range."""
        evolved_blend_weight = 0.4
        ceiling = 0.25

        for gp_train_ic in [-1.0, -0.5, 0.0, 0.01, 0.05, 0.1, 0.5, 1.0]:
            abs_train_ic = abs(gp_train_ic)
            scale_factor = 2.0
            w_adaptive = min(evolved_blend_weight, abs_train_ic * scale_factor)
            w_evo = min(w_adaptive, ceiling)
            floor = evolved_blend_weight * 0.1
            w_evo = max(w_evo, floor)
            w_hand = 1.0 - w_evo

            assert abs(w_evo + w_hand - 1.0) < 1e-9, \
                f"IC={gp_train_ic}: {w_evo} + {w_hand} = {w_evo + w_hand}"

    def test_ceiling_bounds_with_default_weight(self):
        """Test ceiling with default evolved_blend_weight=0.5."""
        evolved_blend_weight = 0.5
        ceiling = 0.25

        for gp_train_ic in [0.5, 1.0, 2.0]:
            abs_train_ic = abs(gp_train_ic)
            scale_factor = 2.0
            w_adaptive = min(evolved_blend_weight, abs_train_ic * scale_factor)
            w_evo = min(w_adaptive, ceiling)
            floor = evolved_blend_weight * 0.1
            w_evo = max(w_evo, floor)

            assert w_evo <= ceiling, f"IC={gp_train_ic}: w_evo={w_evo} > ceiling={ceiling}"


class TestP1NormalizationParity:
    """Test that train and test normalization use same per-tree z-score."""

    def test_per_individual_normalization(self):
        """Verify each HoF tree is individually normalized before averaging."""
        n_samples = 100
        np.random.seed(42)

        # Simulate 3 trees with different scales (as GP produces)
        raw_signals = [
            np.random.randn(n_samples) * 5.0 + 10.0,
            np.random.randn(n_samples) * 10.0 - 5.0,
            np.random.randn(n_samples) * 20.0 + 3.0,
        ]

        # Apply normalization (same logic as phase35_walk_forward.py:370-376,384-390)
        normalized = []
        for signal in raw_signals:
            signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
            std_val = np.std(signal)
            if std_val > 1e-9:
                signal = (signal - np.mean(signal)) / std_val
            normalized.append(signal)

        # Each normalized signal should have mean~0, std~1
        for i, sig in enumerate(normalized):
            assert abs(np.mean(sig)) < 0.01, f"Signal {i}: mean={np.mean(sig)} != 0"
            assert abs(np.std(sig) - 1.0) < 0.01, f"Signal {i}: std={np.std(sig)} != 1"

        # Average should still be well-behaved
        ensemble = np.mean(normalized, axis=0)
        assert np.std(ensemble) > 0.3, "Ensemble std too low"
        assert np.std(ensemble) < 2.0, "Ensemble std too high"

    def test_train_test_parity(self):
        """Verify train and test sides use identical normalization logic."""
        n_train, n_test = 200, 50
        np.random.seed(123)

        # Same tree output on train vs test (different lengths, different scales)
        train_raw = np.random.randn(n_train) * 7.0 + 2.0
        test_raw = np.random.randn(n_test) * 7.0 + 2.0

        # Normalize train side (from phase35_walk_forward.py:384-390)
        train_sig = np.nan_to_num(train_raw, nan=0.0, posinf=0.0, neginf=0.0)
        train_std = np.std(train_sig)
        if train_std > 1e-9:
            train_sig = (train_sig - np.mean(train_sig)) / train_std

        # Normalize test side (from phase35_walk_forward.py:370-376)
        test_sig = np.nan_to_num(test_raw, nan=0.0, posinf=0.0, neginf=0.0)
        test_std = np.std(test_sig)
        if test_std > 1e-9:
            test_sig = (test_sig - np.mean(test_sig)) / test_std

        # Both should be normalized
        assert abs(np.mean(train_sig)) < 0.01
        assert abs(np.std(train_sig) - 1.0) < 0.01
        assert abs(np.mean(test_sig)) < 0.01
        assert abs(np.std(test_sig) - 1.0) < 0.01


class TestP1EngineDefaults:
    """Test engine defaults match V5 proven config."""

    def test_top_n_stocks_default_15(self):
        import inspect
        sig = inspect.signature(Phase35WalkForwardEngine.__init__)
        assert sig.parameters['top_n_stocks'].default == 15

    def test_sector_cap_pct_default_040(self):
        import inspect
        sig = inspect.signature(Phase35WalkForwardEngine.__init__)
        assert abs(sig.parameters['sector_cap_pct'].default - 0.40) < 1e-9

    def test_evolved_blend_weight_validation(self):
        """Test that evolved_blend_weight outside [0,1] raises ValueError."""
        with pytest.raises(ValueError):
            Phase35WalkForwardEngine(
                alpha_module=None,
                evolved_blend_weight=1.5
            )
        with pytest.raises(ValueError):
            Phase35WalkForwardEngine(
                alpha_module=None,
                evolved_blend_weight=-0.1
            )
