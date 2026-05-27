"""Unit tests for Global Contagion Detector."""

import pytest
import numpy as np
from datetime import datetime
from omega.quant.sentiment.contagion_detector import (
    GlobalIndexData,
    MarketStressLevel,
    GlobalContagionDetector,
    get_market_stress_signal
)


def test_contagion_detector_green_level() -> None:
    # 60 days of random returns (low correlation + low volatility)
    np.random.seed(42)
    vn_returns = np.random.normal(0.001, 0.005, 60)
    spx_returns = np.random.normal(0.0005, 0.004, 60)
    hsi_returns = np.random.normal(0.0003, 0.005, 60)
    sse_returns = np.random.normal(0.0002, 0.006, 60)
    
    now = datetime(2026, 4, 26, 18, 0, 0)
    
    global_indices = [
        GlobalIndexData('SPX', 'US', now, 5200.0, spx_returns),
        GlobalIndexData('HSI', 'HK', now, 18500.0, hsi_returns),
        GlobalIndexData('SSE', 'CN', now, 3100.0, sse_returns),
    ]
    
    cii_scores = {'US': 25.0, 'HK': 40.0, 'CN': 35.0}
    
    detector = GlobalContagionDetector()
    report = detector.detect_contagion(vn_returns, global_indices, cii_scores, now)
    
    # Under low correlation/volatility, SRI should be low (GREEN)
    assert report.sri.score < 30.0
    assert report.sri.level == MarketStressLevel.GREEN
    assert "No significant risk factors" in report.risk_narrative


def test_contagion_detector_yellow_level() -> None:
    # Yellow level: Inject correlation into HSI, keep volatility low
    np.random.seed(42)
    vn_returns = np.random.normal(0.001, 0.005, 60)
    spx_returns = np.random.normal(0.0005, 0.004, 60)
    
    # HSI correlated with VN-Index (copying returns), low volatility
    hsi_returns = vn_returns.copy()
    sse_returns = np.random.normal(0.0002, 0.006, 60)
    
    now = datetime(2026, 4, 26, 18, 0, 0)
    
    global_indices = [
        GlobalIndexData('SPX', 'US', now, 5200.0, spx_returns),
        GlobalIndexData('HSI', 'HK', now, 18500.0, hsi_returns),
        GlobalIndexData('SSE', 'CN', now, 3100.0, sse_returns),
    ]
    
    cii_scores = {'US': 25.0, 'HK': 40.0, 'CN': 35.0}
    
    detector = GlobalContagionDetector()
    report = detector.detect_contagion(vn_returns, global_indices, cii_scores, now)
    
    # SRI should be YELLOW
    assert report.sri.level == MarketStressLevel.YELLOW
    assert report.sri.correlation_component > 0
    assert "Primary risk source: HSI" in report.risk_narrative


def test_contagion_detector_red_level() -> None:
    # Red level: High correlation + High Volatility on HSI
    np.random.seed(42)
    vn_returns = np.random.normal(0.001, 0.015, 60)
    spx_returns = np.random.normal(0.0005, 0.012, 60)
    
    # HSI correlated + high standard deviation (volatility)
    hsi_returns = vn_returns.copy() * 3.0  # high vol
    sse_returns = np.random.normal(0.0002, 0.020, 60)
    
    now = datetime(2026, 4, 26, 18, 0, 0)
    
    global_indices = [
        GlobalIndexData('SPX', 'US', now, 5200.0, spx_returns),
        GlobalIndexData('HSI', 'HK', now, 18500.0, hsi_returns),
        GlobalIndexData('SSE', 'CN', now, 3100.0, sse_returns),
    ]
    
    # High country instability for HK (triggers additional cii component points)
    cii_scores = {'US': 25.0, 'HK': 65.0, 'CN': 35.0}
    
    detector = GlobalContagionDetector()
    report = detector.detect_contagion(vn_returns, global_indices, cii_scores, now)
    
    # SRI should be RED (> 60)
    assert report.sri.level == MarketStressLevel.RED
    assert report.sri.score >= 60.0


def test_convenience_function_mandatory_as_of() -> None:
    np.random.seed(42)
    vn_returns = np.random.normal(0.001, 0.015, 60)
    spx_returns = np.random.normal(0.0005, 0.012, 60)
    global_indices = [
        GlobalIndexData('SPX', 'US', datetime(2026, 1, 1), 5200.0, spx_returns),
    ]
    
    # Calling get_market_stress_signal with None as_of_time should raise ValueError
    with pytest.raises(ValueError, match="as_of_time is mandatory"):
        get_market_stress_signal(vn_returns, global_indices, as_of_time=None)
