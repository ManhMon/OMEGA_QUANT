"""
Vietnam Focal Point Detector (VN-FPD) - OMEGA_QUANT Sentiment Module
Phase 25.5: Correlates macro-financial news keywords with physical market z-scores.

Author: System Architect & Backend Engineer
Date: 2026-06-11
PIT Safety: PASS - All calculations are anchored on explicit as_of_time, no look-ahead.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set
import numpy as np
import pandas as pd

from omega.quant.sentiment.vsi_engine import SentimentScore, SentimentPolarity

logger = logging.getLogger(__name__)


@dataclass
class FocalPoint:
    """Focal point containing text-market correlation details."""
    keyword: str
    display_name: str
    news_mentions: int
    news_velocity: float  # mentions per day
    market_zscore: float
    focal_score: float    # 0-100 composite score
    urgency: str          # "watch", "elevated", "critical"
    narrative: str
    correlation_evidence: List[str] = field(default_factory=list)


@dataclass
class FocalPointSummary:
    """Consolidated summary of all active focal points at a point in time."""
    timestamp: datetime
    focal_points: List[FocalPoint]
    aggregate_stress_score: float
    ai_context: str


class VNFocalPointDetector:
    """
    Correlates Vietnamese financial news keyword mention velocity
    with physical market indicators from AlternativeDataFetcher.
    """

    KEYWORD_MAPPINGS = {
        'tỷ giá': {
            'display': 'Exchange Rate Stress',
            'aliases': ['tỷ giá', 'usd/vnd', 'usd vnd', 'dola', 'mất giá'],
            'market_indicator': 'foreign_flow',
            'expected_direction': -1,  # Exchange rate stress usually correlates with foreign outflow (negative flow)
            'weight': 0.35
        },
        'margin call': {
            'display': 'Margin Liquidation Stress',
            'aliases': ['margin call', 'giảm sàn', 'bán giải chấp', 'giải chấp', 'call margin'],
            'market_indicator': 'liquidity_shock',
            'expected_direction': 1,  # Margin stress aligns with high liquidity shocks
            'weight': 0.30
        },
        'lãi suất': {
            'display': 'Interest Rate Tension',
            'aliases': ['lãi suất', 'ngân hàng trung ương', 'fed', 'thắt chặt', 'nới lỏng'],
            'market_indicator': 'sector_rotation',
            'expected_direction': -1,  # High rates correlate with defensive sector rotation
            'weight': 0.15
        },
        'khối ngoại bán': {
            'display': 'Foreign Net Selling Pressure',
            'aliases': ['khối ngoại bán', 'bán ròng', 'nước ngoài bán', 'rút vốn'],
            'market_indicator': 'foreign_flow',
            'expected_direction': -1,
            'weight': 0.20
        }
    }

    def __init__(self, urgency_critical_threshold: float = 70.0, urgency_elevated_threshold: float = 45.0):
        self.critical_threshold = urgency_critical_threshold
        self.elevated_threshold = urgency_elevated_threshold

    def analyze(
        self,
        news_scores: List[SentimentScore],
        market_panel: pd.DataFrame,
        as_of_time: datetime
    ) -> FocalPointSummary:
        """
        Correlates news headlines and content with physical market z-scores on as_of_time.
        
        Args:
            news_scores: List of SentimentScore from VSIEngine up to as_of_time.
            market_panel: MultiIndex DataFrame [date, symbol] containing alternative indicators.
            as_of_time: Point-in-time cutoff.
        """
        # Filter news up to as_of_time (PIT Safe)
        recent_news = [
            ns for ns in news_scores 
            if pd.to_datetime(ns.published_at) <= as_of_time
        ]
        
        # Get market indicators exactly at as_of_time
        date_str = as_of_time.strftime('%Y-%m-%d')
        try:
            market_slice = market_panel.xs(date_str, level='date')
        except KeyError:
            # Fallback if specific date is not found in historical panel
            dates = market_panel.index.get_level_values('date').unique()
            past_dates = [d for d in dates if pd.to_datetime(d) <= as_of_time]
            if past_dates:
                latest_past = max(past_dates)
                market_slice = market_panel.xs(latest_past, level='date')
            else:
                market_slice = pd.DataFrame()

        focal_points = []
        for kw, config in self.KEYWORD_MAPPINGS.items():
            # 1. Count news mentions
            mention_count = 0
            for news in recent_news:
                lower_text = (news.source + " " + ",".join(news.matched_terms)).lower()
                # Check for aliases
                if any(alias in lower_text for alias in config['aliases']):
                    mention_count += 1
            
            # Mention velocity (normalized to daily rate based on 24h window)
            news_velocity = mention_count / 1.0  # Assumes input represents a 24h slice

            # 2. Extract physical market indicator z-score
            indicator_col = config['market_indicator']
            if not market_slice.empty and indicator_col in market_slice.columns:
                # Average across all symbols to get market-wide index z-score
                avg_value = float(market_slice[indicator_col].mean())
                # Handle direction matching (e.g. negative flow * expected direction = positive stress score contribution)
                market_zscore = avg_value * config['expected_direction']
            else:
                market_zscore = 0.0

            # 3. Calculate Focal Score
            news_score = min(50.0, mention_count * 10.0)
            market_score = min(50.0, max(0.0, market_zscore * 15.0))
            
            # Correlation bonus: if BOTH news says it's happening AND market shows it
            correlation_bonus = 0.0
            if news_score >= 10.0 and market_score >= 10.0:
                correlation_bonus = 15.0
            
            focal_score = min(100.0, (news_score + market_score) * 0.8 + correlation_bonus)

            # Determine Urgency
            if focal_score >= self.critical_threshold:
                urgency = 'critical'
            elif focal_score >= self.elevated_threshold:
                urgency = 'elevated'
            else:
                urgency = 'watch'

            # Build narrative & evidence
            evidence = []
            if mention_count > 0:
                evidence.append(f"{mention_count} news mentions of related terms")
            if abs(market_zscore) > 0.5:
                evidence.append(f"Market indicator {indicator_col} shows aligned movement (z-score: {market_zscore:.2f})")
            if correlation_bonus > 0:
                evidence.append("News sentiment strongly correlates with market microstructure signals")

            narrative = f"{config['display']}: Stress score {focal_score:.1f}/100. Status: {urgency.upper()}."

            focal_points.append(
                FocalPoint(
                    keyword=kw,
                    display_name=config['display'],
                    news_mentions=mention_count,
                    news_velocity=news_velocity,
                    market_zscore=market_zscore,
                    focal_score=focal_score,
                    urgency=urgency,
                    narrative=narrative,
                    correlation_evidence=evidence
                )
            )

        # Aggregate stress score (weighted average of active focal points)
        total_weight = sum(config['weight'] for config in self.KEYWORD_MAPPINGS.values())
        weighted_stress = sum(
            fp.focal_score * self.KEYWORD_MAPPINGS[fp.keyword]['weight'] 
            for fp in focal_points
        )
        agg_stress = weighted_stress / total_weight if total_weight > 0 else 0.0

        # Build AI context
        ai_lines = ["[VIETNAM MARKET FOCAL POINT SYNTHESIS]"]
        for fp in focal_points:
            if fp.focal_score > 30.0:
                ai_lines.append(f"- {fp.display_name}: Score {fp.focal_score:.1f} [{fp.urgency.upper()}] -> {'; '.join(fp.correlation_evidence)}")

        return FocalPointSummary(
            timestamp=as_of_time,
            focal_points=sorted(focal_points, key=lambda x: x.focal_score, reverse=True),
            aggregate_stress_score=agg_stress,
            ai_context="\n".join(ai_lines)
        )
