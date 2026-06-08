"""
Unit Tests for OMEGA_QUANT Memory Retrieval
Phase 6.3: Memory Retrieval

Author: MLEngine (Role 16)
Date: 2026-05-13
"""

import pytest
import pandas as pd
from datetime import datetime
from omega.memory.memory_archive import AlphaMemory
from omega.memory.memory_retrieval import AlphaRetriever

@pytest.fixture
def retriever(tmp_path):
    # Setup AlphaMemory with some data
    archive_dir = tmp_path / "memory_archive"
    memory = AlphaMemory(archive_dir=str(archive_dir))
    
    as_of = datetime(2026, 5, 1)
    
    # Store some Alphas
    memory.store_alpha(
        expression="close / open",
        params={"window": 1},
        fitness=0.8,
        sharpe=1.2,
        turnover=0.1,
        symbol="FPT",
        as_of_date=as_of
    )
    
    memory.store_alpha(
        expression="rsi(close, 14)",
        params={"period": 14},
        fitness=0.95,
        sharpe=1.8,
        turnover=0.05,
        symbol="VNM",
        as_of_date=as_of
    )
    
    memory.store_alpha(
        expression="macd(close, 12, 26, 9)",
        params={},
        fitness=0.7,
        sharpe=1.0,
        turnover=0.15,
        symbol="VIC",
        as_of_date=as_of
    )
    
    return AlphaRetriever(memory)

def test_retrieval_similarity(retriever):
    """Test retrieving similar alphas by expression."""
    # Query with a similar expression to "rsi(close, 14)"
    query_expr = "rsi(close, 21)"
    
    results = retriever.retrieve_similar_alphas(
        expression=query_expr,
        min_similarity=0.5,
        top_n=5
    )
    
    assert len(results) >= 1
    # RSI expression should be the most similar
    assert "rsi" in results.iloc[0]["expression"].lower()

def test_retrieval_by_criteria(retriever):
    """Test retrieving alphas by performance criteria."""
    results = retriever.retrieve_by_criteria(
        min_sharpe=1.5,
        min_fitness=0.9
    )
    
    assert len(results) == 1
    assert results.iloc[0]["symbol"] == "VNM"
    assert results.iloc[0]["sharpe"] == 1.8

def test_retrieval_empty_memory(tmp_path):
    """Test retrieval behavior with empty memory."""
    archive_dir = tmp_path / "empty_archive"
    memory = AlphaMemory(archive_dir=str(archive_dir))
    retriever = AlphaRetriever(memory)
    
    results = retriever.retrieve_similar_alphas("close/open")
    assert results.empty

def test_top_performers(retriever):
    """Test getting top performing alphas."""
    results = retriever.get_top_performers(top_n=2)
    assert len(results) == 2
    assert results.iloc[0]["fitness"] == 0.95
    assert results.iloc[1]["fitness"] == 0.8

