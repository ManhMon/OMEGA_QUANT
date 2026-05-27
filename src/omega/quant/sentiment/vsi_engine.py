"""
Vietnam Sentiment Index (VSI) Engine - OMEGA_QUANT Sentiment Module
Phase 25.1: Centralized Vietnamese Financial Sentiment Analysis

Calculates a VN-market specific sentiment index (0-100) using:
- Vectorized NumPy/Pandas operations
- Vietnam specific finance sentiment dictionary (Ceiling/Floor, Margin Call, etc.)
- Source credibility weights (CafeF, Vietstock, VnExpress...)
- Strict Point-in-Time (PIT) safety (T-1 lag, shift-1 logic, future dates validation)
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import re

from omega.core.vn_market_rules import VnMarketRules


class SentimentPolarity(Enum):
    """Sentiment polarity classification."""
    BULLISH = "bullish"      # Positive sentiment
    BEARISH = "bearish"      # Negative sentiment
    NEUTRAL = "neutral"      # Neutral sentiment


class VSILevel(Enum):
    """VSI sentiment levels."""
    EXTREME_FEAR = "extreme_fear"      # 0-20
    FEAR = "fear"                      # 21-40
    NEUTRAL = "neutral"                # 41-60
    GREED = "greed"                    # 61-80
    EXTREME_GREED = "extreme_greed"    # 81-100


@dataclass
class SentimentDictionary:
    """Vietnam market-specific sentiment dictionary."""
    BULLISH_STRONG: Dict[str, float] = None
    BULLISH_MODERATE: Dict[str, float] = None
    BULLISH_WEAK: Dict[str, float] = None
    BEARISH_STRONG: Dict[str, float] = None
    BEARISH_MODERATE: Dict[str, float] = None
    BEARISH_WEAK: Dict[str, float] = None
    
    def __post_init__(self):
        self.BULLISH_STRONG = {
            'tăng trần': 1.0,
            'bứt phá': 1.0,
            'tích cực': 1.0,
            'tăng mạnh': 1.0,
            'đột phá': 1.0,
            'bùng nổ': 1.0,
            'tăng vọt': 1.0,
            'tăng nóng': 1.0,
            'dòng tiền mạnh': 1.0,
            'bluechip tăng': 1.0,
            'vn30 tăng': 1.0,
            'khối ngoại mua': 1.0,
            'thanh khoản cao': 1.0,
            'đáy': 1.0,
            'hồi phục mạnh': 1.0,
        }
        self.BULLISH_MODERATE = {
            'tăng nhẹ': 0.6,
            'tích lũy': 0.6,
            'hồi phục': 0.6,
            'cải thiện': 0.6,
            'lạc quan': 0.6,
            'tăng trưởng': 0.6,
            'khả quan': 0.6,
            'tăng điểm': 0.6,
            'xanh nhẹ': 0.6,
            'mua vào': 0.6,
            'nâng đỡ': 0.6,
            'kháng cự vượt': 0.6,
        }
        self.BULLISH_WEAK = {
            'ổn định': 0.3,
            'duy trì': 0.3,
            'giữ vững': 0.3,
            'cân bằng': 0.3,
            'sideway tích cực': 0.3,
        }
        self.BEARISH_STRONG = {
            'giảm sàn': -1.0,
            'sụp đổ': -1.0,
            'bán tháo': -1.0,
            'giảm mạnh': -1.0,
            'lao dốc': -1.0,
            'rớt giá': -1.0,
            'margin call': -1.0,
            'cắt lỗ': -1.0,
            'thoái vốn': -1.0,
            'khối ngoại bán': -1.0,
            'thanh khoản thấp': -1.0,
            'đỉnh': -1.0,
            'sụt giảm': -1.0,
            'tiêu cực': -1.0,
            'penny giảm': -1.0,
        }
        self.BEARISH_MODERATE = {
            'giảm nhẹ': -0.6,
            'điều chỉnh': -0.6,
            'suy yếu': -0.6,
            'bi quan': -0.6,
            'giảm điểm': -0.6,
            'đỏ nhẹ': -0.6,
            'bán ra': -0.6,
            'áp lực': -0.6,
            'kháng cự': -0.6,
            'rủi ro': -0.6,
        }
        self.BEARISH_WEAK = {
            'trầm lắng': -0.3,
            'thận trọng': -0.3,
            'chờ đợi': -0.3,
            'sideway tiêu cực': -0.3,
        }
    
    def get_all_terms(self) -> Dict[str, float]:
        all_terms = {}
        all_terms.update(self.BULLISH_STRONG)
        all_terms.update(self.BULLISH_MODERATE)
        all_terms.update(self.BULLISH_WEAK)
        all_terms.update(self.BEARISH_STRONG)
        all_terms.update(self.BEARISH_MODERATE)
        all_terms.update(self.BEARISH_WEAK)
        return all_terms


@dataclass
class SourceCredibility:
    """Source credibility weights for Vietnam financial news sources."""
    VNEXPRESS: float = 0.90
    CAFEF: float = 0.85
    STOCKBIZ: float = 0.85
    VIETSTOCK: float = 0.85
    VNECONOMY: float = 0.80
    DANTRI: float = 0.75
    THANHNIEN: float = 0.75
    TUOITRE: float = 0.75
    NDH: float = 0.65
    FINHAY: float = 0.65
    TIMO: float = 0.60
    FACEBOOK: float = 0.50
    ZALO: float = 0.50
    TELEGRAM: float = 0.45
    REDDIT: float = 0.45
    UNKNOWN: float = 0.30
    
    @classmethod
    def get_weight(cls, source: str) -> float:
        source_upper = source.upper().replace(' ', '').replace('-', '')
        if hasattr(cls, source_upper):
            return getattr(cls, source_upper)
        
        if 'VNEXPRESS' in source_upper or 'VNE' in source_upper:
            return cls.VNEXPRESS
        elif 'CAFEF' in source_upper or 'CAFE' in source_upper:
            return cls.CAFEF
        elif 'STOCKBIZ' in source_upper or 'SBIZ' in source_upper:
            return cls.STOCKBIZ
        elif 'VIETSTOCK' in source_upper:
            return cls.VIETSTOCK
        elif 'FACEBOOK' in source_upper or 'FB' in source_upper:
            return cls.FACEBOOK
        elif 'ZALO' in source_upper:
            return cls.ZALO
        elif 'TELEGRAM' in source_upper or 'TG' in source_upper:
            return cls.TELEGRAM
        return cls.UNKNOWN


@dataclass
class SentimentData:
    """Raw sentiment data for a single article/post (PIT safe)."""
    text: str
    source: str
    published_at: datetime
    as_of_time: datetime
    ticker: Optional[str] = None
    author_credibility: Optional[float] = None


@dataclass
class SentimentScore:
    """Sentiment score for a single article/post."""
    raw_score: float
    weighted_score: float
    polarity: SentimentPolarity
    term_count: int
    bullish_count: int
    bearish_count: int
    source_weight: float
    timestamp: datetime
    source: str
    published_at: datetime
    text_hash: str
    matched_terms: List[str]


@dataclass
class VSIScore:
    """Vietnam Sentiment Index score."""
    score: float
    level: VSILevel
    article_count: int
    avg_sentiment: float
    bullish_ratio: float
    bearish_ratio: float
    neutral_ratio: float
    timestamp: datetime


class VSIPortfolioEngine:
    """Vectorized VSI calculator for Vietnam market sentiment analysis."""
    
    def __init__(self):
        self.dictionary = SentimentDictionary()
        self.sentiment_terms = self.dictionary.get_all_terms()
    
    def calculate_sentiment(
        self,
        sentiment_data: List[SentimentData]
    ) -> List[SentimentScore]:
        """Calculate sentiment scores for multiple articles (vectorized)."""
        if not sentiment_data:
            return []
        
        sentiment_df = pd.DataFrame.from_records(map(vars, sentiment_data))
        scores_df = _calculate_sentiment_frame(sentiment_df, self.sentiment_terms)
        return scores_df.apply(_row_to_sentiment_score, axis=1).tolist()
    
    def calculate_vsi(
        self,
        sentiment_scores: List[SentimentScore],
        as_of_time: Optional[datetime] = None
    ) -> VSIScore:
        """Aggregate sentiment scores into VSI index (0-100)."""
        if not sentiment_scores:
            if as_of_time is None:
                raise ValueError("as_of_time is required when sentiment_scores is empty.")
            return VSIScore(
                score=50.0,
                level=VSILevel.NEUTRAL,
                article_count=0,
                avg_sentiment=0.0,
                bullish_ratio=0.0,
                bearish_ratio=0.0,
                neutral_ratio=0.0,
                timestamp=as_of_time
            )
        
        scores_df = pd.DataFrame.from_records(map(_sentiment_score_to_record, sentiment_scores))
        return _aggregate_vsi_from_frame(scores_df, as_of_time)


# Vectorized helpers
VSI_BATCH_DEFAULTS = {
    'text': '',
    'source': 'UNKNOWN',
    'published_at': pd.NaT,
    'ticker': None,
    'author_credibility': np.nan,
}

_VSI_EXACT_SOURCE_WEIGHTS = {
    'VNEXPRESS': SourceCredibility.VNEXPRESS,
    'CAFEF': SourceCredibility.CAFEF,
    'STOCKBIZ': SourceCredibility.STOCKBIZ,
    'VIETSTOCK': SourceCredibility.VIETSTOCK,
    'VNECONOMY': SourceCredibility.VNECONOMY,
    'DANTRI': SourceCredibility.DANTRI,
    'THANHNIEN': SourceCredibility.THANHNIEN,
    'TUOITRE': SourceCredibility.TUOITRE,
    'NDH': SourceCredibility.NDH,
    'FINHAY': SourceCredibility.FINHAY,
    'TIMO': SourceCredibility.TIMO,
    'FACEBOOK': SourceCredibility.FACEBOOK,
    'ZALO': SourceCredibility.ZALO,
    'TELEGRAM': SourceCredibility.TELEGRAM,
    'REDDIT': SourceCredibility.REDDIT,
    'UNKNOWN': SourceCredibility.UNKNOWN,
}


def _resolve_source_weights(source_series: pd.Series, author_credibility: pd.Series) -> np.ndarray:
    normalized = (
        source_series.fillna('UNKNOWN')
        .astype(str)
        .str.upper()
        .str.replace(' ', '', regex=False)
        .str.replace('-', '', regex=False)
    )
    exact_weights = normalized.map(_VSI_EXACT_SOURCE_WEIGHTS)
    fuzzy_weights = np.select(
        [
            normalized.str.contains('VNEXPRESS') | normalized.str.contains('VNE'),
            normalized.str.contains('CAFEF') | normalized.str.contains('CAFE'),
            normalized.str.contains('STOCKBIZ') | normalized.str.contains('SBIZ'),
            normalized.str.contains('VIETSTOCK'),
            normalized.str.contains('FACEBOOK') | normalized.str.contains('FB'),
            normalized.str.contains('ZALO'),
            normalized.str.contains('TELEGRAM') | normalized.str.contains('TG'),
        ],
        [
            SourceCredibility.VNEXPRESS,
            SourceCredibility.CAFEF,
            SourceCredibility.STOCKBIZ,
            SourceCredibility.VIETSTOCK,
            SourceCredibility.FACEBOOK,
            SourceCredibility.ZALO,
            SourceCredibility.TELEGRAM,
        ],
        default=SourceCredibility.UNKNOWN,
    )
    resolved = exact_weights.fillna(pd.Series(fuzzy_weights, index=source_series.index))
    return np.where(author_credibility.notna(), author_credibility.to_numpy(dtype=float), resolved.to_numpy(dtype=float))


def _calculate_sentiment_frame(
    sentiment_data_df: pd.DataFrame,
    sentiment_terms: Dict[str, float]
) -> pd.DataFrame:
    if sentiment_data_df.empty:
        return pd.DataFrame(
            columns=[
                'raw_score', 'weighted_score', 'polarity', 'term_count', 'bullish_count',
                'bearish_count', 'source_weight', 'timestamp', 'source', 'published_at',
                'text_hash', 'matched_terms'
            ]
        )
    
    if sentiment_data_df['as_of_time'].nunique() > 1:
        timestamps = set(sentiment_data_df['as_of_time'])
        raise ValueError(f"PIT violation: multiple timestamps in input data: {timestamps}")
        
    as_of_time = sentiment_data_df['as_of_time'].iloc[0]
    published_at = pd.to_datetime(sentiment_data_df['published_at'], errors='coerce')
    future_mask = published_at.notna() & (published_at > as_of_time)
    if future_mask.any():
        offending_ts = published_at[future_mask].iloc[0]
        raise ValueError(
            f"PIT violation: published_at ({offending_ts.isoformat()}) "
            f"is after as_of_time ({as_of_time.isoformat()})."
        )
        
    texts = sentiment_data_df['text'].fillna('').astype(str).str.lower().to_numpy(dtype=str)
    terms = np.array(list(sentiment_terms.keys()), dtype=str)
    weights = np.array(list(sentiment_terms.values()), dtype=float)
    counts = np.char.count(texts[:, None], terms[None, :])
    
    weighted_counts = counts * weights
    bullish_mask = weights > 0
    bearish_mask = weights < 0
    
    bullish_count = counts[:, bullish_mask].sum(axis=1).astype(int)
    bearish_count = counts[:, bearish_mask].sum(axis=1).astype(int)
    term_count = bullish_count + bearish_count
    total_score = weighted_counts.sum(axis=1)
    avg_score = np.divide(
        total_score,
        term_count,
        out=np.zeros_like(total_score, dtype=float),
        where=term_count > 0
    )
    raw_score = np.clip(avg_score * 100.0, -100.0, 100.0)
    
    source_weight = _resolve_source_weights(
        sentiment_data_df['source'],
        pd.to_numeric(sentiment_data_df['author_credibility'], errors='coerce')
    )
    weighted_score = raw_score * source_weight
    
    polarity = np.select(
        [raw_score > 10.0, raw_score < -10.0],
        [SentimentPolarity.BULLISH.value, SentimentPolarity.BEARISH.value],
        default=SentimentPolarity.NEUTRAL.value
    )
    
    matched_terms = pd.Series(
        map(
            lambda mask: ','.join(terms[mask].tolist()),
            counts > 0
        ),
        index=sentiment_data_df.index,
        dtype='object',
    )
    text_hash = sentiment_data_df['text'].fillna('').map(
        lambda text: hashlib.sha256(str(text).encode('utf-8')).hexdigest()[:16]
    )
    
    return pd.DataFrame(
        {
            'raw_score': raw_score.astype(float),
            'weighted_score': weighted_score.astype(float),
            'polarity': polarity,
            'term_count': term_count.astype(int),
            'bullish_count': bullish_count.astype(int),
            'bearish_count': bearish_count.astype(int),
            'source_weight': source_weight.astype(float),
            'timestamp': sentiment_data_df['as_of_time'],
            'source': sentiment_data_df['source'],
            'published_at': published_at,
            'text_hash': text_hash,
            'matched_terms': matched_terms,
        },
        index=sentiment_data_df.index,
    )


def _aggregate_vsi_from_frame(
    sentiment_scores_df: pd.DataFrame,
    as_of_time: Optional[datetime] = None
) -> VSIScore:
    if sentiment_scores_df.empty:
        if as_of_time is None:
            raise ValueError("as_of_time is required when sentiment_scores is empty.")
        return VSIScore(
            score=50.0,
            level=VSILevel.NEUTRAL,
            article_count=0,
            avg_sentiment=0.0,
            bullish_ratio=0.0,
            bearish_ratio=0.0,
            neutral_ratio=0.0,
            timestamp=as_of_time
        )
        
    if sentiment_scores_df['timestamp'].nunique() > 1:
        timestamps = set(sentiment_scores_df['timestamp'])
        raise ValueError(f"PIT violation: multiple timestamps in sentiment scores: {timestamps}")
        
    timestamp = sentiment_scores_df['timestamp'].iloc[0]
    weighted_scores = sentiment_scores_df['weighted_score'].to_numpy(dtype=float)
    avg_sentiment = float(np.mean(weighted_scores))
    total_count = len(sentiment_scores_df)
    
    polarity_values = sentiment_scores_df['polarity'].to_numpy(dtype=str)
    bullish_ratio = float(np.mean(polarity_values == SentimentPolarity.BULLISH.value))
    bearish_ratio = float(np.mean(polarity_values == SentimentPolarity.BEARISH.value))
    neutral_ratio = float(np.mean(polarity_values == SentimentPolarity.NEUTRAL.value))
    
    base_score = (avg_sentiment + 100.0) / 2.0
    polarity_amplifier = 1.0 + (max(bullish_ratio, bearish_ratio) - 0.5) * 0.2
    vsi_score = float(np.clip(base_score * polarity_amplifier, 0.0, 100.0))
    
    if vsi_score >= 81.0:
        level = VSILevel.EXTREME_GREED
    elif vsi_score >= 61.0:
        level = VSILevel.GREED
    elif vsi_score >= 41.0:
        level = VSILevel.NEUTRAL
    elif vsi_score >= 21.0:
        level = VSILevel.FEAR
    else:
        level = VSILevel.EXTREME_FEAR
        
    return VSIScore(
        score=vsi_score,
        level=level,
        article_count=total_count,
        avg_sentiment=avg_sentiment,
        bullish_ratio=bullish_ratio,
        bearish_ratio=bearish_ratio,
        neutral_ratio=neutral_ratio,
        timestamp=timestamp
    )


def _row_to_sentiment_score(row: pd.Series) -> SentimentScore:
    matched_terms = [term for term in str(row['matched_terms']).split(',') if term] if row['matched_terms'] else []
    return SentimentScore(
        raw_score=float(row['raw_score']),
        weighted_score=float(row['weighted_score']),
        polarity=SentimentPolarity(row['polarity']),
        term_count=int(row['term_count']),
        bullish_count=int(row['bullish_count']),
        bearish_count=int(row['bearish_count']),
        source_weight=float(row['source_weight']),
        timestamp=row['timestamp'],
        source=row['source'],
        published_at=row['published_at'],
        text_hash=row['text_hash'],
        matched_terms=matched_terms
    )


def _sentiment_score_to_record(score: SentimentScore) -> Dict[str, object]:
    return {
        'weighted_score': score.weighted_score,
        'polarity': score.polarity.value,
        'timestamp': score.timestamp,
    }
