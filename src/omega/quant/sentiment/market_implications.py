"""
Vietnam Market Implications Engine - OMEGA_QUANT Sentiment Module
Phase 25.6: Generates structured trade implication cards and transmission chains.

Author: System Architect & Backend Engineer
Date: 2026-06-11
PIT Safety: PASS - Rely on explicit as_of_time, no look-ahead.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from omega.quant.sentiment.focal_point_detector import FocalPointSummary

logger = logging.getLogger(__name__)


@dataclass
class TransmissionNode:
    """A causal step in the transmission chain."""
    node: str
    impact_type: str  # supply_disruption, demand_shift, capital_flow, sentiment_shift, contagion, etc.
    logic: str


@dataclass
class MarketImplicationCard:
    """Structured trade implication card."""
    ticker: str  # Ticker symbol or sector name (e.g., HPG, VNREAL, VCB)
    name: str
    direction: str  # LONG, SHORT, HEDGE
    timeframe: str  # 1W, 2W, 1M, 3M
    confidence: str  # HIGH, MEDIUM, LOW
    title: str
    narrative: str
    risk_caveat: str
    driver: str
    transmission_chain: List[TransmissionNode] = field(default_factory=list)


class VNMarketImplicationsEngine:
    """
    Generates causal trade-implication cards and transmission chains 
    for major Vietnamese sectors based on macro focal points.
    """

    ALLOWED_TICKERS = {
        'VN30': 'VN30 Index (Bluechips)',
        'HPG': 'Hoa Phat Group (Steel/Industrial)',
        'GAS': 'PV GAS (Energy/Commodity)',
        'VCB': 'Vietcombank (Financials)',
        'VIC': 'Vingroup (Real Estate/Conglomerate)',
        'VNM': 'Vinamilk (Defensive Consumer)',
        'REE': 'REE Corporation (Utilities/Infrastructure)',
    }

    def generate_implications(
        self,
        focal_summary: FocalPointSummary,
        as_of_time: datetime
    ) -> List[MarketImplicationCard]:
        """
        Generates implications based on focal points.
        Uses a high-performance deterministic mapping.
        """
        cards = []

        # Find critical/elevated focal points
        critical_fps = [fp for fp in focal_summary.focal_points if fp.urgency == 'critical']
        elevated_fps = [fp for fp in focal_summary.focal_points if fp.urgency == 'elevated']
        
        all_active = critical_fps + elevated_fps

        if not all_active:
            # Fallback default card under normal conditions
            cards.append(
                MarketImplicationCard(
                    ticker='VN30',
                    name=self.ALLOWED_TICKERS['VN30'],
                    direction='LONG',
                    timeframe='1M',
                    confidence='MEDIUM',
                    title='Stable Macro Conditions Support Accumulation',
                    narrative='Vietnam macro factors remain stable with normal sentiment and low focal stress. High-quality VN30 bluechips are prime accumulation targets.',
                    risk_caveat='Unexpected global macro shocks or exchange rate volatility.',
                    driver='Stable macro',
                    transmission_chain=[
                        TransmissionNode(
                            node='Low Geopolitical Stress',
                            impact_type='sentiment_shift',
                            logic='Increases local retail investor confidence'
                        ),
                        TransmissionNode(
                            node='Capital Inflows',
                            impact_type='capital_flow',
                            logic='Supports index valuation expansion'
                        )
                    ]
                )
            )
            return cards

        # Process active focal points
        for fp in all_active:
            if fp.keyword == 'tỷ giá':
                # Exchange rate stress leads to shorting exporters with foreign debt, or hedging
                cards.append(
                    MarketImplicationCard(
                        ticker='VCB',
                        name=self.ALLOWED_TICKERS['VCB'],
                        direction='HEDGE',
                        timeframe='2W',
                        confidence='HIGH' if fp.urgency == 'critical' else 'MEDIUM',
                        title='Exchange Rate Volatility Triggers Banking Sector Hedge',
                        narrative=f"High exchange rate pressure ({fp.focal_score:.1f}/100) forces SBV intervention. VCB serves as a defensive market anchor but remains exposed to foreign outflows.",
                        risk_caveat='Rapid cooling of USD/VND or unexpected rate cuts.',
                        driver='USD/VND Spike',
                        transmission_chain=[
                            TransmissionNode(
                                node='USD/VND rate appreciation',
                                impact_type='policy_shift',
                                logic='Triggers SBV liquidity contraction'
                            ),
                            TransmissionNode(
                                node='Foreign capital outflow',
                                impact_type='capital_flow',
                                logic='Applies selling pressure on bank bluechips'
                            )
                        ]
                    )
                )
            elif fp.keyword == 'margin call':
                # Margin liquidation stress implies shorting volatile index or hedging with defensive names
                cards.append(
                    MarketImplicationCard(
                        ticker='VIC',
                        name=self.ALLOWED_TICKERS['VIC'],
                        direction='SHORT',
                        timeframe='1W',
                        confidence='HIGH',
                        title='Margin Call Contagion in Real Estate Conglomerates',
                        narrative=f"Systemic margin liquidation tension ({fp.focal_score:.1f}/100) triggers forced selling of high-beta real estate names like VIC.",
                        risk_caveat='State-sponsored liquidity relief or rapid technical rebound.',
                        driver='Margin Call Outbreak',
                        transmission_chain=[
                            TransmissionNode(
                                node='Forced liquidation',
                                impact_type='contagion',
                                logic='Triggers cascading selling of collateral assets'
                            ),
                            TransmissionNode(
                                node='De-leveraging',
                                impact_type='capital_flow',
                                logic='Reduces sector aggregate purchasing power'
                            )
                        ]
                    )
                )
                cards.append(
                    MarketImplicationCard(
                        ticker='VNM',
                        name=self.ALLOWED_TICKERS['VNM'],
                        direction='LONG',
                        timeframe='1M',
                        confidence='MEDIUM',
                        title='Defensive Rotation to Consumer Staples during Liquidation',
                        narrative='As market-wide margin call cascades proceed, consumer staples (VNM) offer stable cashflows and dividend yield protection.',
                        risk_caveat='Incidental liquidation selling of VNM to cover other margin requirements.',
                        driver='Defensive flight',
                        transmission_chain=[
                            TransmissionNode(
                                node='Beta selloff',
                                impact_type='sentiment_shift',
                                logic='Forces flight from speculative growth sectors'
                            ),
                            TransmissionNode(
                                node='Defensive positioning',
                                impact_type='capital_flow',
                                logic='Inflows into low-beta dividend-yielding bluechips'
                            )
                        ]
                    )
                )
            elif fp.keyword == 'lãi suất':
                # Interest rate adjustments impact REE (utilities - capital intensive) and banks
                cards.append(
                    MarketImplicationCard(
                        ticker='REE',
                        name=self.ALLOWED_TICKERS['REE'],
                        direction='SHORT',
                        timeframe='3M',
                        confidence='MEDIUM',
                        title='Rising Rates Weigh on Capital-Intensive Utilities',
                        narrative=f"Interest rate hikes/tension ({fp.focal_score:.1f}/100) increases funding costs for utility infrastructure firms like REE.",
                        risk_caveat='Tariff increases offsetting financial cost spikes.',
                        driver='Interest Rate Hike',
                        transmission_chain=[
                            TransmissionNode(
                                node='Cost of debt increases',
                                impact_type='earnings_risk',
                                logic='Bridges to lower earnings margins on new projects'
                            ),
                            TransmissionNode(
                                node='Valuation adjustment',
                                impact_type='valuation_shift',
                                logic='Lowers net asset value calculations'
                            )
                        ]
                    )
                )

        return cards
