"""
Country Instability Index (CII) Engine - OMEGA_QUANT Sentiment Module
Phase 25.3: Centralized Geopolitical Instability Scoring

Calculates Country Instability Index (CII) using:
- Vectorized NumPy/Pandas operations
- Multiple components: Unrest, Conflict, Security, Information
- Base risks & country-specific volume dampening (US, CN, etc.)
- Strict Point-in-Time (PIT) safety (T-1 lag, shift-1 logic, time consistency)
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class CIILevel(Enum):
    """CII risk levels matching WorldMonitor thresholds."""
    LOW = "low"              # 0-30
    NORMAL = "normal"        # 31-50
    ELEVATED = "elevated"    # 51-65
    HIGH = "high"            # 66-80
    CRITICAL = "critical"    # 81-100


class CIITrend(Enum):
    """24-hour trend direction."""
    RISING = "rising"        # +5 or more
    STABLE = "stable"        # -5 to +5
    FALLING = "falling"      # -5 or less


@dataclass
class ComponentScores:
    """Four CII component scores (0-100 each)."""
    unrest: float
    conflict: float
    security: float
    information: float


@dataclass
class CountryScore:
    """Complete CII score for a single country at a point in time."""
    code: str
    name: str
    score: float
    level: CIILevel
    trend: CIITrend
    change_24h: float
    components: ComponentScores
    timestamp: datetime


@dataclass
class CountryData:
    """Raw signal counts for a country (input to CII calculation)."""
    code: str
    as_of_time: datetime
    
    # Unrest signals
    protest_count: int = 0
    protest_fatalities: int = 0
    protest_high_severity_count: int = 0
    internet_outage_total: int = 0
    internet_outage_major: int = 0
    internet_outage_partial: int = 0
    
    # Conflict signals
    conflict_battle_count: int = 0
    conflict_explosion_count: int = 0
    conflict_civilian_count: int = 0
    conflict_total_fatalities: int = 0
    strike_count_7d: int = 0
    strike_high_severity_count_7d: int = 0
    
    # Security signals
    military_flights: int = 0
    military_vessels: int = 0
    aviation_closure_count: int = 0
    aviation_severe_count: int = 0
    aviation_major_count: int = 0
    aviation_moderate_count: int = 0
    gps_jamming_high_count: int = 0
    gps_jamming_medium_count: int = 0
    
    # Information signals
    news_event_count: int = 0
    news_velocity_avg: float = 0.0
    news_has_alert: bool = False
    
    # Contextual signals
    displacement_outflow: int = 0
    climate_stress: float = 0.0
    advisory_max_level: Optional[str] = None
    advisory_source_count: int = 0
    ucdp_intensity: Optional[str] = None
    sanctions_entry_count: int = 0
    sanctions_new_entry_count: int = 0
    earthquake_severe_count: int = 0
    earthquake_major_count: int = 0
    earthquake_significant_count: int = 0
    
    # Supplemental signals
    ais_disruption_high: int = 0
    ais_disruption_elevated: int = 0
    ais_disruption_low: int = 0
    satellite_fire_count: int = 0
    satellite_fire_high_count: int = 0
    cyber_threat_critical: int = 0
    cyber_threat_high: int = 0
    cyber_threat_medium: int = 0
    temporal_anomaly_count: int = 0
    temporal_anomaly_critical: int = 0


class CIIPortfolioEngine:
    """Vectorized CII engine following WorldMonitor methodology."""
    
    EVENT_MULTIPLIERS = {
        'US': 0.3,
        'GB': 0.4,
        'FR': 0.4,
        'DE': 0.4,
        'IN': 0.5,
        'CN': 0.6,
    }
    
    BASELINE_RISK = {
        'UA': 55,
        'SY': 50,
        'YE': 50,
        'MM': 45,
        'IL': 45,
        'RU': 40,
        'IR': 40,
        'KP': 40,
    }
    
    def __init__(self):
        self.default_multiplier = 1.0
        self.default_baseline = 20.0
        
    def calculate_cii(
        self,
        country_data: List[CountryData],
        previous_scores: Optional[Dict[str, float]] = None
    ) -> List[CountryScore]:
        """Calculate CII scores for multiple countries (vectorized)."""
        if not country_data:
            return []
        
        timestamps = {cd.as_of_time for cd in country_data}
        if len(timestamps) > 1:
            raise ValueError(f"PIT violation: multiple timestamps in input data: {timestamps}")
            
        country_df = pd.DataFrame.from_records(map(vars, country_data))
        prev_series = pd.Series(previous_scores, dtype=float) if previous_scores else None
        scores_df = _calculate_cii_frame(country_df, prev_series)
        return scores_df.apply(_row_to_country_score, axis=1).tolist()


# Vectorized helpers
CII_BATCH_DEFAULTS = {
    'protest_count': 0,
    'protest_fatalities': 0,
    'protest_high_severity_count': 0,
    'internet_outage_total': 0,
    'internet_outage_major': 0,
    'internet_outage_partial': 0,
    'conflict_battle_count': 0,
    'conflict_explosion_count': 0,
    'conflict_civilian_count': 0,
    'conflict_total_fatalities': 0,
    'strike_count_7d': 0,
    'strike_high_severity_count_7d': 0,
    'military_flights': 0,
    'military_vessels': 0,
    'aviation_closure_count': 0,
    'aviation_severe_count': 0,
    'aviation_major_count': 0,
    'aviation_moderate_count': 0,
    'gps_jamming_high_count': 0,
    'gps_jamming_medium_count': 0,
    'news_event_count': 0,
    'news_velocity_avg': 0.0,
    'news_has_alert': False,
    'displacement_outflow': 0,
    'climate_stress': 0.0,
    'advisory_max_level': None,
    'advisory_source_count': 0,
    'ucdp_intensity': None,
    'sanctions_entry_count': 0,
    'sanctions_new_entry_count': 0,
    'earthquake_severe_count': 0,
    'earthquake_major_count': 0,
    'earthquake_significant_count': 0,
    'ais_disruption_high': 0,
    'ais_disruption_elevated': 0,
    'ais_disruption_low': 0,
    'satellite_fire_count': 0,
    'satellite_fire_high_count': 0,
    'cyber_threat_critical': 0,
    'cyber_threat_high': 0,
    'cyber_threat_medium': 0,
    'temporal_anomaly_count': 0,
    'temporal_anomaly_critical': 0,
}

_CII_EVENT_MULTIPLIERS = pd.Series(CIIPortfolioEngine.EVENT_MULTIPLIERS, dtype=float)
_CII_BASELINE_RISK = pd.Series(CIIPortfolioEngine.BASELINE_RISK, dtype=float)


def _prepare_cii_frame(
    country_data_df: pd.DataFrame,
    apply_pit_shift: bool = False
) -> pd.DataFrame:
    if country_data_df.empty:
        return country_data_df.copy()
        
    df = country_data_df.copy()
    for column, default_value in CII_BATCH_DEFAULTS.items():
        if column not in df.columns:
            df[column] = default_value
            
    if apply_pit_shift:
        if 'as_of_time' in df.columns and df['as_of_time'].nunique() == 1:
            group_sizes = df.groupby('code', sort=False).size()
            if (group_sizes == 1).all():
                return df
                
        shifted_columns = [column for column in CII_BATCH_DEFAULTS.keys() if column in df.columns]
        if shifted_columns:
            group_sizes = df.groupby('code', sort=False).size()
            multi_row_countries = group_sizes[group_sizes > 1].index
            if len(multi_row_countries) > 0:
                mask = df['code'].isin(multi_row_countries)
                shifted = df.loc[mask].groupby('code', sort=False)[shifted_columns].shift(1)
                fill_values = {column: CII_BATCH_DEFAULTS[column] for column in shifted_columns}
                df.loc[mask, shifted_columns] = shifted.fillna(fill_values)
    return df


def _calculate_cii_frame(
    country_data_df: pd.DataFrame,
    previous_scores: Optional[pd.Series] = None
) -> pd.DataFrame:
    if country_data_df.empty:
        return pd.DataFrame(
            columns=[
                'code', 'name', 'score', 'level', 'trend', 'change_24h',
                'unrest', 'conflict', 'security', 'information', 'timestamp'
            ]
        )
        
    if country_data_df['as_of_time'].nunique() > 1:
        timestamps = set(country_data_df['as_of_time'])
        raise ValueError(f"PIT violation: multiple timestamps in input data: {timestamps}")
        
    multiplier = country_data_df['code'].map(_CII_EVENT_MULTIPLIERS).fillna(1.0).to_numpy(dtype=float)
    baseline_risk = country_data_df['code'].map(_CII_BASELINE_RISK).fillna(20.0).to_numpy(dtype=float)
    is_high_volume = multiplier < 0.7
    
    protest_count = country_data_df['protest_count'].to_numpy(dtype=float)
    adjusted_protest = np.where(
        is_high_volume & (protest_count > 0),
        np.log2(protest_count + 1.0) * multiplier * 5.0,
        protest_count * multiplier
    )
    unrest = (
        np.minimum(50.0, adjusted_protest * 8.0) +
        np.minimum(30.0, country_data_df['protest_fatalities'].to_numpy(dtype=float) * 5.0 * multiplier) +
        np.minimum(20.0, country_data_df['protest_high_severity_count'].to_numpy(dtype=float) * 10.0 * multiplier) +
        np.minimum(
            50.0,
            country_data_df['internet_outage_total'].to_numpy(dtype=float) * 30.0 +
            country_data_df['internet_outage_major'].to_numpy(dtype=float) * 15.0 +
            country_data_df['internet_outage_partial'].to_numpy(dtype=float) * 5.0
        )
    )
    
    conflict_civilian = country_data_df['conflict_civilian_count'].to_numpy(dtype=float)
    conflict = (
        np.minimum(
            50.0,
            (
                country_data_df['conflict_battle_count'].to_numpy(dtype=float) * 3.0 +
                country_data_df['conflict_explosion_count'].to_numpy(dtype=float) * 4.0 +
                conflict_civilian * 5.0
            ) * multiplier
        ) +
        np.minimum(
            40.0,
            np.sqrt(country_data_df['conflict_total_fatalities'].to_numpy(dtype=float)) * 5.0 * multiplier
        ) +
        np.where(conflict_civilian > 0, np.minimum(10.0, conflict_civilian * 3.0), 0.0) +
        np.minimum(
            50.0,
            country_data_df['strike_count_7d'].to_numpy(dtype=float) * 3.0 +
            country_data_df['strike_high_severity_count_7d'].to_numpy(dtype=float) * 5.0
        )
    )
    
    security = (
        np.minimum(50.0, country_data_df['military_flights'].to_numpy(dtype=float) * 3.0) +
        np.minimum(30.0, country_data_df['military_vessels'].to_numpy(dtype=float) * 5.0) +
        np.minimum(
            40.0,
            country_data_df['aviation_closure_count'].to_numpy(dtype=float) * 20.0 +
            country_data_df['aviation_severe_count'].to_numpy(dtype=float) * 15.0 +
            country_data_df['aviation_major_count'].to_numpy(dtype=float) * 10.0 +
            country_data_df['aviation_moderate_count'].to_numpy(dtype=float) * 5.0
        ) +
        np.minimum(
            35.0,
            country_data_df['gps_jamming_high_count'].to_numpy(dtype=float) * 5.0 +
            country_data_df['gps_jamming_medium_count'].to_numpy(dtype=float) * 2.0
        )
    )
    
    news_event_count = country_data_df['news_event_count'].to_numpy(dtype=float)
    adjusted_news = np.where(
        is_high_volume,
        np.log2(news_event_count + 1.0) * multiplier * 3.0,
        news_event_count * multiplier
    )
    velocity = country_data_df['news_velocity_avg'].to_numpy(dtype=float)
    velocity_threshold = np.where(is_high_volume, 5.0, 2.0)
    information = np.where(
        news_event_count == 0,
        0.0,
        np.minimum(40.0, adjusted_news * 5.0) +
        np.where(
            velocity > velocity_threshold,
            np.minimum(40.0, (velocity - velocity_threshold) * 10.0 * multiplier),
            0.0
        ) +
        np.where(country_data_df['news_has_alert'].to_numpy(dtype=bool), 20.0 * multiplier, 0.0)
    )
    
    components = pd.DataFrame(
        {
            'unrest': np.clip(unrest, 0.0, 100.0),
            'conflict': np.clip(conflict, 0.0, 100.0),
            'security': np.clip(security, 0.0, 100.0),
            'information': np.clip(information, 0.0, 100.0),
        },
        index=country_data_df.index,
    )
    
    event_score = (
        components['unrest'].to_numpy(dtype=float) * 0.25 +
        components['conflict'].to_numpy(dtype=float) * 0.30 +
        components['security'].to_numpy(dtype=float) * 0.20 +
        components['information'].to_numpy(dtype=float) * 0.25
    )
    blended = baseline_risk * 0.4 + event_score * 0.6
    
    displacement = country_data_df['displacement_outflow'].to_numpy(dtype=float)
    displacement_boost = np.select(
        [displacement >= 1_000_000, displacement >= 100_000],
        [8.0, 4.0],
        default=0.0
    )
    
    advisory_level = country_data_df['advisory_max_level'].fillna('').to_numpy(dtype=str)
    advisory_boost = np.select(
        [
            advisory_level == 'do-not-travel',
            advisory_level == 'reconsider',
            advisory_level == 'caution',
        ],
        [15.0, 10.0, 5.0],
        default=0.0
    )
    advisory_sources = country_data_df['advisory_source_count'].to_numpy(dtype=float)
    advisory_boost += np.select(
        [advisory_sources >= 3, advisory_sources >= 2],
        [5.0, 3.0],
        default=0.0
    )
    
    ais_boost = np.minimum(
        10.0,
        country_data_df['ais_disruption_high'].to_numpy(dtype=float) * 2.5 +
        country_data_df['ais_disruption_elevated'].to_numpy(dtype=float) * 1.5 +
        country_data_df['ais_disruption_low'].to_numpy(dtype=float) * 0.5
    )
    fire_boost = np.minimum(
        8.0,
        country_data_df['satellite_fire_high_count'].to_numpy(dtype=float) * 1.5 +
        np.minimum(20.0, country_data_df['satellite_fire_count'].to_numpy(dtype=float)) * 0.25
    )
    cyber_boost = np.minimum(
        12.0,
        country_data_df['cyber_threat_critical'].to_numpy(dtype=float) * 3.0 +
        country_data_df['cyber_threat_high'].to_numpy(dtype=float) * 1.8 +
        country_data_df['cyber_threat_medium'].to_numpy(dtype=float) * 0.9
    )
    temporal_boost = np.minimum(
        6.0,
        country_data_df['temporal_anomaly_critical'].to_numpy(dtype=float) * 2.0 +
        country_data_df['temporal_anomaly_count'].to_numpy(dtype=float) * 0.75
    )
    supplemental_boost = ais_boost + fire_boost + cyber_boost + temporal_boost
    
    earthquake_boost = np.minimum(
        25.0,
        country_data_df['earthquake_severe_count'].to_numpy(dtype=float) * 10.0 +
        country_data_df['earthquake_major_count'].to_numpy(dtype=float) * 5.0 +
        country_data_df['earthquake_significant_count'].to_numpy(dtype=float) * 2.0
    )
    
    sanctions_entries = country_data_df['sanctions_entry_count'].to_numpy(dtype=float)
    sanctions_boost = np.select(
        [sanctions_entries >= 2000, sanctions_entries >= 501, sanctions_entries >= 101, sanctions_entries >= 1],
        [12.0, 8.0, 5.0, 3.0],
        default=0.0
    )
    sanctions_boost += np.where(country_data_df['sanctions_new_entry_count'].to_numpy(dtype=float) > 0, 2.0, 0.0)
    
    information_values = components['information'].to_numpy(dtype=float)
    news_urgency_boost = np.select(
        [information_values >= 70.0, information_values >= 50.0],
        [5.0, 3.0],
        default=0.0
    )
    
    total_score = (
        blended +
        displacement_boost +
        country_data_df['climate_stress'].to_numpy(dtype=float) +
        advisory_boost +
        supplemental_boost +
        earthquake_boost +
        sanctions_boost +
        news_urgency_boost
    )
    
    ucdp_intensity = country_data_df['ucdp_intensity'].fillna('').to_numpy(dtype=str)
    ucdp_floor = np.select(
        [ucdp_intensity == 'war', ucdp_intensity == 'minor'],
        [70.0, 50.0],
        default=0.0
    )
    advisory_floor = np.select(
        [advisory_level == 'do-not-travel', advisory_level == 'reconsider'],
        [60.0, 50.0],
        default=0.0
    )
    final_score = np.clip(np.maximum(np.maximum(ucdp_floor, advisory_floor), total_score), 0.0, 100.0)
    
    result = country_data_df[['code', 'as_of_time']].copy()
    result['name'] = result['code']
    result['score'] = final_score
    result['level'] = np.select(
        [final_score >= 81.0, final_score >= 66.0, final_score >= 51.0, final_score >= 31.0],
        [CIILevel.CRITICAL.value, CIILevel.HIGH.value, CIILevel.ELEVATED.value, CIILevel.NORMAL.value],
        default=CIILevel.LOW.value
    )
    
    prev_score = (
        result['code'].map(previous_scores).to_numpy(dtype=float)
        if previous_scores is not None
        else final_score.copy()
    )
    if previous_scores is not None:
        prev_score = np.where(np.isnan(prev_score), final_score, prev_score)
        
    change_24h = final_score - prev_score
    result['trend'] = np.select(
        [change_24h >= 5.0, change_24h <= -5.0],
        [CIITrend.RISING.value, CIITrend.FALLING.value],
        default=CIITrend.STABLE.value
    )
    result['change_24h'] = change_24h
    result[['unrest', 'conflict', 'security', 'information']] = components
    result['timestamp'] = result['as_of_time']
    
    return result.sort_values('score', ascending=False, kind='stable').reset_index(drop=True)[
        ['code', 'name', 'score', 'level', 'trend', 'change_24h', 'unrest', 'conflict', 'security', 'information', 'timestamp']
    ]


def _row_to_country_score(row: pd.Series) -> CountryScore:
    return CountryScore(
        code=row['code'],
        name=row['name'],
        score=float(row['score']),
        level=CIILevel(row['level']),
        trend=CIITrend(row['trend']),
        change_24h=float(row['change_24h']),
        components=ComponentScores(
            unrest=float(row['unrest']),
            conflict=float(row['conflict']),
            security=float(row['security']),
            information=float(row['information']),
        ),
        timestamp=row['timestamp'],
    )
