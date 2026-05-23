"""
Unit Tests for OMEGA_QUANT Memory Archive
Phase 6.2: Memory Archive

Author: MLEngine (Role 16)
Date: 2026-05-13
"""

import pytest
import pandas as pd
from datetime import datetime
from omega.memory.memory_archive import AlphaMemory, ErrorMemory

@pytest.fixture
def alpha_memory(tmp_path):
    # Use a temporary directory for testing
    archive_dir = tmp_path / "memory_archive"
    return AlphaMemory(archive_dir=str(archive_dir))

@pytest.fixture
def error_memory(tmp_path):
    # Use temporary directory and file
    audit_logs_dir = tmp_path / "logs"
    error_memory = ErrorMemory(audit_logs_dir=str(audit_logs_dir))
    # Override resolution log file for testing
    error_memory.resolution_log_file = tmp_path / "TEST_RESOLUTION_LOG.md"
    error_memory.error_db_file = tmp_path / "error_db.json"
    error_memory._initialize_resolution_log()
    return error_memory

def test_alpha_memory_store_and_retrieve(alpha_memory):
    """Test storing and retrieving alphas from memory."""
    as_of = datetime(2026, 5, 1)
    
    # Store first alpha
    h1 = alpha_memory.store_alpha(
        expression="close / open",
        params={"window": 5},
        fitness=0.8,
        sharpe=1.2,
        turnover=0.1,
        symbol="FPT",
        as_of_date=as_of
    )
    
    # Store second alpha
    h2 = alpha_memory.store_alpha(
        expression="rsi(close, 14)",
        params={"period": 14},
        fitness=0.95,
        sharpe=1.8,
        turnover=0.05,
        symbol="VNM",
        as_of_date=as_of
    )
    
    # Check index
    assert alpha_memory.index["total_alphas"] == 2
    assert h1 != h2
    
    # Get top alphas
    top = alpha_memory.get_top_alphas(n=1)
    assert len(top) == 1
    assert top.iloc[0]["alpha_hash"] == h2
    assert top.iloc[0]["fitness"] == 0.95

def test_alpha_memory_deduplication(alpha_memory):
    """Test that duplicate alphas are not stored twice."""
    as_of = datetime(2026, 5, 1)
    expr = "close / open"
    params = {"window": 5}
    
    h1 = alpha_memory.store_alpha(expr, params, 0.8, 1.2, 0.1, "FPT", as_of)
    h2 = alpha_memory.store_alpha(expr, params, 0.85, 1.3, 0.1, "FPT", as_of)
    
    assert h1 == h2
    assert alpha_memory.index["total_alphas"] == 1

def test_error_memory_logging(error_memory):
    """Test logging and retrieving errors."""
    h = error_memory.log_error(
        error_type="PIT_VIOLATION",
        component="data_loader",
        description="Look-ahead bias in price loading",
        root_cause="Used available_at instead of as_of",
        resolution="Added T-1 shift to available_at",
        prevention="Mandatory T-1 lag check in pipeline"
    )
    
    assert len(error_memory.error_db) == 1
    assert error_memory.error_db[0]["error_hash"] == h
    
    # Check resolution log file
    content = error_memory.resolution_log_file.read_text()
    assert h in content
    assert "PIT_VIOLATION" in content

def test_error_memory_similarity(error_memory):
    """Test finding similar errors."""
    desc = "Look-ahead bias in feature engineering"
    error_memory.log_error("PIT_VIOLATION", "features", desc, "root", "res", "prev")
    
    # Query for similar error
    similar = error_memory.get_similar_errors("PIT_VIOLATION", "features", desc)
    assert len(similar) == 1
    assert similar[0]["description"] == desc

