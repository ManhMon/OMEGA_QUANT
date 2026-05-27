"""Unit tests for Country Instability Index (CII) Engine."""

import pytest
from datetime import datetime
from omega.quant.sentiment.cii_engine import (
    CountryData,
    CIILevel,
    CIITrend,
    CIIPortfolioEngine
)


def test_cii_baseline_and_level() -> None:
    engine = CIIPortfolioEngine()
    as_of = datetime(2026, 1, 1)
    
    # 1. Base stable country (default baseline 20 -> LOW level)
    data_stable = [
        CountryData(
            code="VN",
            as_of_time=as_of
        )
    ]
    scores = engine.calculate_cii(data_stable)
    assert len(scores) == 1
    assert scores[0].code == "VN"
    # Blended score: baseline 20 * 0.4 + event 0 * 0.6 = 8.0. UCDP/advisory floor = 0.
    # Total score = 8.0 -> level: LOW
    assert scores[0].score == 8.0
    assert scores[0].level == CIILevel.LOW
    
    # 2. Base unstable country (UA baseline 55 -> ELEVATED level)
    data_ua = [
        CountryData(
            code="UA",
            as_of_time=as_of
        )
    ]
    scores = engine.calculate_cii(data_ua)
    assert len(scores) == 1
    assert scores[0].code == "UA"
    # Blended score: 55 * 0.4 = 22.0 -> level: LOW
    assert scores[0].score == 22.0
    assert scores[0].level == CIILevel.LOW


def test_cii_component_boosts() -> None:
    engine = CIIPortfolioEngine()
    as_of = datetime(2026, 1, 1)
    
    # Country with active conflict & unrest signals
    data_active = [
        CountryData(
            code="VN",
            as_of_time=as_of,
            protest_count=10,
            protest_fatalities=2,
            conflict_battle_count=5,
            conflict_total_fatalities=16,
            military_flights=5,
            news_event_count=8,
            news_velocity_avg=4.0
        )
    ]
    
    scores = engine.calculate_cii(data_active)
    assert len(scores) == 1
    assert scores[0].score > 8.0  # Boosted from stable baseline
    assert scores[0].components.unrest > 0.0
    assert scores[0].components.conflict > 0.0


def test_cii_floor_triggers() -> None:
    engine = CIIPortfolioEngine()
    as_of = datetime(2026, 1, 1)
    
    # Trigger UCDP conflict floor 'war' (floor = 70.0 -> HIGH)
    data_war = [
        CountryData(
            code="VN",
            as_of_time=as_of,
            ucdp_intensity="war"
        )
    ]
    scores = engine.calculate_cii(data_war)
    assert len(scores) == 1
    assert scores[0].score == 70.0
    assert scores[0].level == CIILevel.HIGH
    
    # Trigger travel advisory floor 'do-not-travel' (floor = 60.0 -> ELEVATED)
    data_advisory = [
        CountryData(
            code="VN",
            as_of_time=as_of,
            advisory_max_level="do-not-travel"
        )
    ]
    scores = engine.calculate_cii(data_advisory)
    assert len(scores) == 1
    assert scores[0].score == 60.0
    assert scores[0].level == CIILevel.ELEVATED


def test_cii_trend_and_previous_scores() -> None:
    engine = CIIPortfolioEngine()
    as_of = datetime(2026, 1, 1)
    
    data = [
        CountryData(
            code="VN",
            as_of_time=as_of,
            ucdp_intensity="war"  # Score = 70.0
        )
    ]
    
    # Previous score 24h ago was 80.0 -> Change: -10.0 -> Trend: FALLING
    prev = {"VN": 80.0}
    scores = engine.calculate_cii(data, previous_scores=prev)
    assert len(scores) == 1
    assert scores[0].change_24h == -10.0
    assert scores[0].trend == CIITrend.FALLING
    
    # Previous score 24h ago was 60.0 -> Change: +10.0 -> Trend: RISING
    prev2 = {"VN": 60.0}
    scores2 = engine.calculate_cii(data, previous_scores=prev2)
    assert len(scores2) == 1
    assert scores2[0].change_24h == 10.0
    assert scores2[0].trend == CIITrend.RISING
