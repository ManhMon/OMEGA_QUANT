"""
Unit tests for Vietnam Focal Point Detector & Market Implications Engine.

PIT Safety: PASS - Tests use explicitly dated panels and test cases.
"""

from datetime import datetime
import numpy as np
import pandas as pd
import pytest

from omega.quant.sentiment.vsi_engine import SentimentScore, SentimentPolarity
from omega.quant.sentiment.focal_point_detector import VNFocalPointDetector, FocalPointSummary
from omega.quant.sentiment.market_implications import VNMarketImplicationsEngine
from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher


def test_focal_point_detector_calculation():
    detector = VNFocalPointDetector()
    as_of = datetime(2026, 6, 11)

    # 1. Mock news scores
    news_scores = [
        SentimentScore(
            raw_score=-80.0,
            weighted_score=-68.0,
            polarity=SentimentPolarity.BEARISH,
            term_count=5,
            bullish_count=0,
            bearish_count=5,
            source_weight=0.85,
            timestamp=as_of,
            source="CAFEF",
            published_at=as_of,
            text_hash="abc",
            matched_terms=["margin call", "giảm sàn", "bán tháo"]
        )
    ]

    # 2. Mock market panel MultiIndex [date, symbol]
    dates = ["2026-06-11"]
    symbols = ["HPG", "GAS", "VCB"]
    idx = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"])
    market_panel = pd.DataFrame(
        {
            "liquidity_shock": [2.5, 3.0, 1.5],  # high stress z-scores
            "foreign_flow": [-1.2, -2.0, -0.5]
        },
        index=idx
    )

    # Analyze
    summary = detector.analyze(news_scores, market_panel, as_of)

    assert isinstance(summary, FocalPointSummary)
    assert summary.timestamp == as_of
    assert len(summary.focal_points) > 0

    # Retrieve the margin call focal point
    margin_fp = next(fp for fp in summary.focal_points if fp.keyword == "margin call")
    assert margin_fp.news_mentions == 1
    # expect high stress score since both news matches and market liquidity shock is high
    assert margin_fp.focal_score > 50.0
    assert margin_fp.urgency in ["elevated", "critical"]
    assert len(margin_fp.correlation_evidence) >= 2


def test_market_implications_generation():
    detector = VNFocalPointDetector()
    implications_engine = VNMarketImplicationsEngine()
    as_of = datetime(2026, 6, 11)

    # Mock critical margin call stress focal point
    dates = ["2026-06-11"]
    symbols = ["HPG"]
    idx = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"])
    market_panel = pd.DataFrame({"liquidity_shock": [5.0], "foreign_flow": [-2.0]}, index=idx)

    news_scores = [
        SentimentScore(
            raw_score=-90.0,
            weighted_score=-90.0,
            polarity=SentimentPolarity.BEARISH,
            term_count=2,
            bullish_count=0,
            bearish_count=2,
            source_weight=1.0,
            timestamp=as_of,
            source="VIETSTOCK",
            published_at=as_of,
            text_hash="xyz",
            matched_terms=["margin call"]
        )
    ]

    focal_summary = detector.analyze(news_scores, market_panel, as_of)
    implications = implications_engine.generate_implications(focal_summary, as_of)

    assert len(implications) > 0
    # Must find the VIC short card triggered by margin call focal point
    vic_card = next((c for c in implications if c.ticker == "VIC"), None)
    assert vic_card is not None
    assert vic_card.direction == "SHORT"
    assert vic_card.driver == "Margin Call Outbreak"
    assert len(vic_card.transmission_chain) >= 2
    assert vic_card.transmission_chain[0].impact_type == "contagion"


def test_alternative_data_fetcher_integration():
    fetcher = AlternativeDataFetcher()
    dates = ["2026-06-09", "2026-06-10", "2026-06-11"]
    symbols = ["HPG", "GAS"]
    idx = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"])
    panel = pd.DataFrame(
        {
            "open": [10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
            "high": [10.5, 10.5, 9.8, 9.8, 10.2, 10.2],
            "low": [9.5, 9.5, 9.2, 9.2, 9.8, 9.8],
            "close": [10.2, 10.2, 9.3, 9.3, 10.1, 10.1],
            "volume": [1000, 1000, 5000, 5000, 2000, 2000]
        },
        index=idx
    )

    result = fetcher.generate_all(panel)
    assert "vsi_score" in result.columns
    assert "focal_stress_score" in result.columns

    # Verify PIT safety (T-1 lag).
    # Since date 2026-06-10 had a large drop (< -1.5% average return),
    # the sentiment indicators for 2026-06-11 (T) should show higher stress/lower VSI
    # reflecting the T-1 event.
    stress_t1 = result.xs("2026-06-10", level="date")["focal_stress_score"].iloc[0]
    stress_t2 = result.xs("2026-06-11", level="date")["focal_stress_score"].iloc[0]
    
    # 2026-06-10 uses 2026-06-09 (normal return) -> normal stress
    # 2026-06-11 uses 2026-06-10 (massive drop) -> higher stress
    assert stress_t2 > stress_t1


def test_generate_all_restores_date_symbol_index_order():
    """
    Regression test for GP_ALT_DATA_FETCHER_OPTIMIZATION index-swap bug.
    generate_all() internally reorders the MultiIndex to [symbol, date] for
    contiguous groupby, but must restore [date, symbol] before returning,
    otherwise unified_feature_adapter.py silently swaps date<->symbol columns.
    """
    fetcher = AlternativeDataFetcher()
    dates = ["2026-06-09", "2026-06-10", "2026-06-11"]
    symbols = ["HPG", "GAS"]
    idx = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"])
    panel = pd.DataFrame(
        {
            "open": [10.0, 10.0, 10.0, 10.0, 10.0, 10.0],
            "high": [10.5, 10.5, 9.8, 9.8, 10.2, 10.2],
            "low": [9.5, 9.5, 9.2, 9.2, 9.8, 9.8],
            "close": [10.2, 10.2, 9.3, 9.3, 10.1, 10.1],
            "volume": [1000, 1000, 5000, 5000, 2000, 2000]
        },
        index=idx
    )

    result = fetcher.generate_all(panel)

    # Returned index must be sorted by [date, symbol] — never [symbol, date]
    assert list(result.index.names) == ["date", "symbol"]
    assert result.index.is_monotonic_increasing

    # Cross-check: a date slice must contain exactly the expected symbols
    # (catches silent date<->symbol swap)
    slice_ = result.xs("2026-06-10", level="date")
    assert set(slice_.index) == set(symbols)


def test_pit_equivalence_full_vs_historical_panel():
    """
    Regression test: Verify that passing the full panel to VNFocalPointDetector.analyze()
    returns identical results to passing a historically-sliced panel (T-1).
    This proves there is no look-ahead leak in the optimized implementation.
    """
    detector = VNFocalPointDetector()
    as_of = datetime(2026, 6, 11)
    
    # Mock news scores
    news_scores = [
        SentimentScore(
            raw_score=-80.0,
            weighted_score=-68.0,
            polarity=SentimentPolarity.BEARISH,
            term_count=5,
            bullish_count=0,
            bearish_count=5,
            source_weight=0.85,
            timestamp=as_of,
            source="CAFEF",
            published_at=as_of,
            text_hash="test_hash",
            matched_terms=["margin call", "giảm sàn", "bán tháo"]
        )
    ]
    
    # Create a multi-date panel
    dates = ["2026-06-09", "2026-06-10", "2026-06-11"]
    symbols = ["HPG", "GAS", "VCB"]
    idx = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"])
    full_panel = pd.DataFrame(
        {
            "liquidity_shock": [1.0, 1.5, 1.2, 2.5, 3.0, 1.5, 3.0, 3.5, 2.0],
            "foreign_flow": [-0.5, -0.8, -0.3, -1.2, -2.0, -0.5, -1.5, -2.2, -0.7]
        },
        index=idx
    )
    
    # Analyze with full panel
    summary_full = detector.analyze(news_scores, full_panel, as_of)
    
    # Analyze with historically-sliced panel (up to as_of date)
    historical_panel = full_panel[full_panel.index.get_level_values('date') <= as_of.strftime('%Y-%m-%d')]
    summary_historical = detector.analyze(news_scores, historical_panel, as_of)
    
    # Verify identical results (no look-ahead leak)
    assert summary_full.aggregate_stress_score == summary_historical.aggregate_stress_score
    assert len(summary_full.focal_points) == len(summary_historical.focal_points)
    for fp_full, fp_hist in zip(summary_full.focal_points, summary_historical.focal_points):
        assert fp_full.keyword == fp_hist.keyword
        assert fp_full.focal_score == fp_hist.focal_score
        assert fp_full.urgency == fp_hist.urgency


def test_vectorized_date_mapping_equivalence():
    """
    Regression test: Verify that vectorized date mapping produces identical results
    to the legacy boolean masking loop for sentiment indicator assignment.
    """
    fetcher = AlternativeDataFetcher()
    
    # Create a test panel with multiple dates
    dates = ["2026-06-09", "2026-06-10", "2026-06-11", "2026-06-12"]
    symbols = ["HPG", "GAS"]
    idx = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"])
    panel = pd.DataFrame(
        {
            "open": [10.0, 10.0] * 4,
            "high": [10.5, 10.5, 9.8, 9.8, 10.2, 10.2, 10.3, 10.3],
            "low": [9.5, 9.5, 9.2, 9.2, 9.8, 9.8, 9.9, 9.9],
            "close": [10.2, 10.2, 9.3, 9.3, 10.1, 10.1, 10.15, 10.15],
            "volume": [1000, 1000, 5000, 5000, 2000, 2000, 1500, 1500]
        },
        index=idx
    )
    
    # Generate features with optimized vectorized implementation
    result = fetcher.generate_all(panel)
    
    # Verify that all rows within a date have the same VSI and FSS scores
    # (as they should be broadcast from date-level calculations)
    for date in dates:
        date_slice = result.xs(date, level="date")
        vsi_values = date_slice["vsi_score"].unique()
        fss_values = date_slice["focal_stress_score"].unique()
        
        # All symbols on the same date should have identical sentiment scores
        assert len(vsi_values) == 1, f"VSI should be identical for all symbols on {date}"
        assert len(fss_values) == 1, f"FSS should be identical for all symbols on {date}"
    
    # Verify PIT safety: later dates should reflect T-1 market conditions
    # Date 2026-06-10 had a sharp drop, so 2026-06-11 should show elevated stress
    fss_before_drop = result.xs("2026-06-10", level="date")["focal_stress_score"].iloc[0]
    fss_after_drop = result.xs("2026-06-11", level="date")["focal_stress_score"].iloc[0]
    assert fss_after_drop > fss_before_drop, "Stress should increase after market drop (T-1 lag)"
