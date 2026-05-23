import pytest
import pandas as pd
from datetime import datetime, timedelta
from omega.core.promotion import PromotionGate

@pytest.fixture
def promotion_gate():
    return PromotionGate()

def test_embargo_calculation(promotion_gate):
    """Test required embargo calculation."""
    assert promotion_gate.calculate_required_embargo(3) == 4
    assert promotion_gate.calculate_required_embargo(5) == 6
    assert promotion_gate.calculate_required_embargo(1) == 2

def test_verify_embargo_t3_pass(promotion_gate):
    """Test T+3 embargo pass: exactly 4 days."""
    train_end = pd.to_datetime("2023-01-01")
    val_start = pd.to_datetime("2023-01-05")
    assert promotion_gate.verify_embargo(train_end, val_start, 3) is True

def test_verify_embargo_t3_fail(promotion_gate):
    """Test T+3 embargo fail: only 3 days."""
    train_end = pd.to_datetime("2023-01-01")
    val_start = pd.to_datetime("2023-01-04")
    assert promotion_gate.verify_embargo(train_end, val_start, 3) is False

def test_verify_embargo_t5_pass(promotion_gate):
    """Test T+5 embargo pass: exactly 6 days."""
    train_end = pd.to_datetime("2023-01-01")
    val_start = pd.to_datetime("2023-01-07")
    assert promotion_gate.verify_embargo(train_end, val_start, 5) is True

def test_verify_embargo_t5_fail(promotion_gate):
    """Test T+5 embargo fail: only 5 days."""
    train_end = pd.to_datetime("2023-01-01")
    val_start = pd.to_datetime("2023-01-06")
    assert promotion_gate.verify_embargo(train_end, val_start, 5) is False

def test_verify_embargo_nat_fail(promotion_gate):
    """Test embargo fail with NaT."""
    train_end = pd.to_datetime("NaT")
    val_start = pd.to_datetime("2023-01-07")
    assert promotion_gate.verify_embargo(train_end, val_start, 3) is False

def test_non_overlapping_windows_pass(promotion_gate):
    """Test valid non-overlapping validation windows."""
    windows = [
        ("2023-01-01", "2023-01-31"),
        ("2023-02-01", "2023-02-28"),
        ("2023-03-01", "2023-03-31")
    ]
    assert promotion_gate.verify_non_overlapping_windows(windows) is True

def test_non_overlapping_windows_fail(promotion_gate):
    """Test overlapping validation windows."""
    windows = [
        ("2023-01-01", "2023-01-31"),
        ("2023-01-15", "2023-02-28") # Overlaps with previous
    ]
    assert promotion_gate.verify_non_overlapping_windows(windows) is False

def test_windows_fail_closed_empty_or_invalid(promotion_gate):
    """Test windows fail on empty or invalid data."""
    assert promotion_gate.verify_non_overlapping_windows([]) is False
    assert promotion_gate.verify_non_overlapping_windows([("2023-01-31", "2023-01-01")]) is False # start > end
    assert promotion_gate.verify_non_overlapping_windows([("invalid_date", "2023-01-01")]) is False # parsing error

def test_verify_performance_pass(promotion_gate):
    """Test performance thresholds pass (IC > 0.1, Sharpe > 1.5)."""
    metrics = {'ic': 0.11, 'sharpe': 1.51}
    assert promotion_gate.verify_performance(metrics) is True

def test_verify_performance_fail_ic(promotion_gate):
    """Test performance thresholds fail on IC."""
    metrics = {'ic': 0.09, 'sharpe': 1.6}
    assert promotion_gate.verify_performance(metrics) is False

def test_verify_performance_fail_sharpe(promotion_gate):
    """Test performance thresholds fail on Sharpe."""
    metrics = {'ic': 0.15, 'sharpe': 1.49}
    assert promotion_gate.verify_performance(metrics) is False

def test_verify_performance_fail_missing_or_nan(promotion_gate):
    """Test performance thresholds fail on missing/NaN metrics."""
    assert promotion_gate.verify_performance({}) is False
    assert promotion_gate.verify_performance({'ic': float('nan'), 'sharpe': 1.6}) is False

def test_evaluate_promotion_pass(promotion_gate):
    """Test full evaluation pass."""
    metadata = {
        'max_horizon': 3,
        'train_end_date': '2023-01-01',
        'val_start_date': '2023-01-05',
        'metrics': {'ic': 0.12, 'sharpe': 1.6},
        'validation_windows': [('2023-01-05', '2023-02-05'), ('2023-02-06', '2023-03-06')]
    }
    assert promotion_gate.evaluate_promotion(metadata) is True

def test_evaluate_promotion_fail_missing_keys(promotion_gate):
    """Test full evaluation fail due to missing keys."""
    metadata = {
        'max_horizon': 3,
        'train_end_date': '2023-01-01'
        # Missing val_start_date and metrics
    }
    assert promotion_gate.evaluate_promotion(metadata) is False

def test_evaluate_promotion_fail_embargo(promotion_gate):
    """Test full evaluation fail due to embargo violation."""
    metadata = {
        'max_horizon': 5,
        'train_end_date': '2023-01-01',
        'val_start_date': '2023-01-06', # Only 5 days, needs 6
        'metrics': {'ic': 0.15, 'sharpe': 2.0}
    }
    assert promotion_gate.evaluate_promotion(metadata) is False

def test_evaluate_promotion_fail_performance(promotion_gate):
    """Test full evaluation fail due to bad metrics."""
    metadata = {
        'max_horizon': 3,
        'train_end_date': '2023-01-01',
        'val_start_date': '2023-01-10', # Safe embargo
        'metrics': {'ic': 0.05, 'sharpe': 2.0} # Bad IC
    }
    assert promotion_gate.evaluate_promotion(metadata) is False
