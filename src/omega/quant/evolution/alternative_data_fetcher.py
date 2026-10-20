"""
OMEGA_QUANT Alternative Data Fetcher
Fetches foreign flow, margin data from vnstock API.
Fallback: derives proxy signals from OHLCV when API unavailable.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - All data fetched with as_of constraint.
Memory Optimization: 2026-07-07 - Narrow copy calculation, vectorized date mapping.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from omega.data.macro_rates import OMO_NET_INJECTION_LIMIT, canonical_tenor
from omega.quant.strategy.macro_context import get_fx_omo_indicators
from omega.data.calendar import trading_session_open_utc
from omega.quant.sentiment.focal_point_detector import VNFocalPointDetector
from omega.quant.sentiment.vsi_engine import VSIPortfolioEngine, SentimentData

logger = logging.getLogger(__name__)


class AlternativeDataFetcher:
    """
    Fetch or derive alternative data signals.
    Primary: vnstock API (foreign flow, margin)
    Fallback: OHLCV-derived proxies
    """

    def __init__(self, use_api: bool = False, macro_rows=None, earnings_ledger=None):
        self.use_api = use_api
        self.macro_rows = macro_rows
        self.fp_detector = VNFocalPointDetector()
        self.vsi_engine = VSIPortfolioEngine()
        self.pead_engine = None
        if earnings_ledger is not None:
            from omega.quant.strategy.pead_drift import PEADDriftEngine

            self.pead_engine = PEADDriftEngine(earnings_ledger)

    @staticmethod
    def _utc_timestamp(value) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp) or timestamp.tzinfo is None:
            raise ValueError("macro timestamps must be timezone-aware")
        return timestamp.tz_convert("UTC")

    def get_macro_bitemporal_features(self, panel: pd.DataFrame, macro_rows=None, as_of=None) -> pd.DataFrame:
        """Tạo tín hiệu macro theo availability/vintage, không nhìn trước."""
        rows = list((self.macro_rows if macro_rows is None else macro_rows) or [])
        date_values = panel.index.get_level_values("date")
        dates = pd.DatetimeIndex(pd.to_datetime(pd.unique(date_values)))
        if dates.hasnans:
            raise ValueError("macro session dates must be valid")
        dates = dates.tz_localize(None).normalize().unique().sort_values()
        columns = ["interbank_on_spread", "term_structure_slope", "interbank_vol_5d", "macro_monetary_regime", "usd_vnd_zscore", "usd_vnd_vol_20d", "omo_net_injection_20d_sum", "macro_fx_liquidity_regime"]
        output = pd.DataFrame(np.nan, index=dates, columns=columns)
        if not rows or not len(dates):
            return output
        cutoff = self._utc_timestamp(as_of) if as_of is not None else None
        normalized = []
        for row in rows:
            item = row.as_dict() if hasattr(row, "as_dict") else dict(row)
            if not any(key in item for key in ("tenor", "maturity", "indicator")):
                continue
            available_raw = item["available_at"]
            vintage_raw = item.get("vintage_at", item.get("revision_at", available_raw))
            revision_raw = item.get("revision_at", item.get("vintage_at", available_raw))
            available = self._utc_timestamp(available_raw)
            vintage = self._utc_timestamp(vintage_raw)
            revision = self._utc_timestamp(revision_raw)
            tenor = canonical_tenor(item.get("tenor", item.get("maturity", item.get("indicator", ""))))
            value = float(item.get("rate", item.get("value")))
            if isinstance(item.get("rate", item.get("value")), (bool, np.bool_)) or not np.isfinite(value):
                raise ValueError("macro rate must be finite")
            normalized.append((tenor, value, available, vintage, revision, str(item.get("provider", ""))))
        for position, session in enumerate(dates):
            session_cutoff = self._utc_timestamp(trading_session_open_utc(session.date()))
            effective = session_cutoff if cutoff is None else min(session_cutoff, cutoff)
            latest = {}
            for tenor, value, available, vintage, revision, provider in normalized:
                candidate = (revision, vintage, available, provider, value)
                if available <= effective and vintage <= effective and revision <= effective and (tenor not in latest or candidate > latest[tenor][3]):
                    latest[tenor] = (value, available, vintage, candidate)
            ages = [position - max((i for i, day in enumerate(dates) if day.date() <= available.date()), default=position) for _, available, _, _ in latest.values()]
            if not latest or any(age > 5 for age in ages):
                continue
            on = latest.get("overnight")
            policy = latest.get("refinancing_rate") or latest.get("refinancing")
            long_rate = next((latest[tenor] for tenor in ("12m", "6m", "3m") if tenor in latest), None)
            if on is None:
                continue
            spread = on[0] - policy[0] if policy else np.nan
            slope = long_rate[0] - on[0] if long_rate else np.nan
            output.loc[session, "interbank_on_spread"] = spread if np.isfinite(spread) else np.nan
            output.loc[session, "term_structure_slope"] = slope if np.isfinite(slope) else np.nan
            output.loc[session, "interbank_vol_5d"] = output.loc[:session, "interbank_on_spread"].rolling(5, min_periods=2).std().iloc[-1]
            if not np.isfinite(spread):
                continue
            history = output.loc[:session, "interbank_on_spread"].dropna()
            delta = 0.0 if len(history) < 20 else history.iloc[-1] - history.iloc[-20]
            if np.isfinite(delta):
                output.loc[session, "macro_monetary_regime"] = 1 if delta > 0.05 else (-1 if delta < -0.05 else 0)
        fx_aliases = {
            "usd_vnd": ("usd_vnd", "usd_vnd_rate", "usdvnd"),
            "omo_net_injection": ("net_injection", "omo_net_injection", "sbv_omo_net"),
        }
        fx_candidates = []
        for row in rows:
            item = row.as_dict() if hasattr(row, "as_dict") else dict(row)
            if not any(key in item for aliases in fx_aliases.values() for key in aliases):
                continue
            available_raw = item["available_at"]
            vintage_raw = item.get("vintage_at", item.get("revision_at", available_raw))
            revision_raw = item.get("revision_at", item.get("vintage_at", available_raw))
            available = self._utc_timestamp(available_raw)
            vintage = self._utc_timestamp(vintage_raw)
            revision = self._utc_timestamp(revision_raw)
            date_value = item.get("date", item.get("rate_date", available_raw))
            session_date = pd.Timestamp(date_value)
            if pd.isna(session_date):
                raise ValueError("macro observation dates must be valid")
            session_date = session_date.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None) if session_date.tzinfo is not None else session_date
            session_date = session_date.normalize()
            for alias, aliases in fx_aliases.items():
                key = next((name for name in aliases if name in item), None)
                if key is None:
                    continue
                value = float(item[key])
                if isinstance(item[key], (bool, np.bool_)) or not np.isfinite(value):
                    raise ValueError("macro indicator must be finite")
                if alias == "usd_vnd" and value <= 0:
                    raise ValueError("USD/VND must be positive")
                fx_candidates.append((session_date.normalize(), available, vintage, revision, alias, value, str(item.get("provider", ""))))

        if fx_candidates:
            # Place observations on their declared ICT session, never before the session date.
            released = {}
            for session in dates:
                session_cutoff = self._utc_timestamp(trading_session_open_utc(session.date()))
                effective = session_cutoff if cutoff is None else min(session_cutoff, cutoff)
                for observed, available, vintage, revision, alias, value, provider in fx_candidates:
                    if observed > session or observed.date() > effective.tz_convert("Asia/Ho_Chi_Minh").date() or available > effective or vintage > effective or revision > effective:
                        continue
                    # Equal-provenance invalid OMO must not lose to a valid observation.
                    invalid_omo = alias == "omo_net_injection" and abs(value) > OMO_NET_INJECTION_LIMIT
                    candidate = (observed, revision, vintage, available, provider, invalid_omo, value)
                    key = (session, alias)
                    if key not in released or candidate > released[key][0]:
                        released[key] = (candidate, value)

            macro = pd.DataFrame(index=dates, columns=("usd_vnd", "omo_net_injection"), dtype=float)
            for (session, alias), (_, value) in released.items():
                macro.loc[session, alias] = value
            macro["omo_net_injection"] = macro["omo_net_injection"].where(
                macro["omo_net_injection"].abs() <= OMO_NET_INJECTION_LIMIT
            )
            indicators = get_fx_omo_indicators(macro)
            indicators = indicators.where(np.isfinite(indicators))
            if "macro_fx_liquidity_regime" in indicators:
                indicators["macro_fx_liquidity_regime"] = indicators["macro_fx_liquidity_regime"].where(
                    indicators["usd_vnd_zscore"].notna()
                    & indicators["omo_net_injection_20d_sum"].notna()
                )
            output.loc[:, indicators.columns] = indicators.reindex(dates).to_numpy()
        return output.where(np.isfinite(output))

    def get_foreign_flow_proxy(self, panel: pd.DataFrame) -> pd.Series:
        """
        Foreign flow proxy from OHLCV.
        Logic: Large volume + price up = foreign buying (institutional flow).
        Proxy: volume_zscore * sign(return) — captures unusual volume with direction.

        PIT Safety: Uses only past data (rolling stats).
        """
        vol = panel['volume']
        grouped_volume = vol.groupby(level='symbol')
        vol_ma = grouped_volume.rolling(20, min_periods=5).mean().droplevel(0)
        vol_std = grouped_volume.rolling(20, min_periods=5).std().droplevel(0)
        vol_zscore = (vol - vol_ma) / vol_std.replace(0, 1)

        ret_sign = panel.groupby(level='symbol')['close'].pct_change().map(np.sign)
        foreign_proxy = vol_zscore * ret_sign

        return foreign_proxy.fillna(0)

    def get_margin_proxy(self, panel: pd.DataFrame) -> pd.Series:
        """
        Margin outstanding proxy.
        Logic: Sustained buying on increasing volume = margin accumulation.
        Proxy: cumulative sum of (volume * return) over rolling window.

        PIT Safety: Rolling cumsum, no future data.
        """
        ret = panel.groupby(level='symbol')['close'].pct_change()
        flow = panel['volume'] * ret
        margin_proxy = flow.groupby(level='symbol').rolling(10, min_periods=3).sum().droplevel(0)

        return margin_proxy.fillna(0)

    def get_sector_rotation_proxy(self, panel: pd.DataFrame) -> pd.Series:
        """
        Sector rotation proxy.
        Logic: Relative strength vs market mean — stocks outperforming market = sector inflow.
        Proxy: symbol_return - cross_sectional_mean_return (rolling 10d).

        PIT Safety: Cross-sectional at each date, no future data.
        """
        ret_10d = panel.groupby(level='symbol')['close'].pct_change(10)
        market_mean = ret_10d.groupby(level='date').transform('mean')
        rotation_proxy = ret_10d - market_mean

        return rotation_proxy.fillna(0)

    def get_order_imbalance_proxy(self, panel: pd.DataFrame) -> pd.Series:
        """
        Order imbalance proxy from OHLCV.
        Logic: (close - open) / (high - low) indicates buying/selling pressure.
        Combined with volume for strength.

        PIT Safety: Same-bar data only, no future.
        """
        hl_range = (panel['high'] - panel['low']).replace(0, np.nan)
        pressure = (panel['close'] - panel['open']) / hl_range
        imbalance = pressure * np.log1p(panel['volume'])

        return imbalance.fillna(0)

    def get_liquidity_shock_proxy(self, panel: pd.DataFrame) -> pd.Series:
        """
        Liquidity shock detector.
        Logic: Sudden volume spike (>3x average) with large price move.

        PIT Safety: Rolling stats only.
        """
        vol = panel['volume']
        vol_ma = vol.groupby(level='symbol').rolling(20, min_periods=5).mean().droplevel(0)
        vol_spike = vol / vol_ma.replace(0, 1)

        abs_ret = panel.groupby(level='symbol')['close'].pct_change().abs()
        shock = vol_spike * abs_ret

        return shock.fillna(0)

    def _derive_sentiment_indicators(self, panel: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """
        Derives VSI and Focal Stress Score (FSS) in a PIT-safe manner.
        For each date T, uses market data from date T-1 to generate VSI and FSS.

        Memory optimization: Uses vectorized date mapping instead of boolean masking loop.
        Memory optimization 2 (GP_ALT_DATA_FETCHER_OPTIMIZATION): Pre-group by date once
        before loop to replace 12,782 slow .xs() MultiIndex slicing operations with fast
        dict lookups.

        Memory optimization 3 (GP_WEEKLY_EVOLUTION_ALT_CONCAT_OPTIMIZATION): Build a narrow
        copy panel_fp containing only ['foreign_flow', 'liquidity_shock', 'sector_rotation']
        (the columns actually consumed by focal_point_detector.analyze) and pre-group by date
        on that narrow copy. The original `panel` is left intact for daily_returns and
        daily_foreign computations downstream.
        """
        dates = sorted(panel.index.get_level_values('date').unique())

        # MEMORY OPTIMIZATION (GP_WEEKLY_EVOLUTION_ALT_CONCAT_OPTIMIZATION): narrow copy with
        # only the columns the focal-point detector actually needs. Original panel is kept
        # untouched for downstream daily_returns / daily_foreign calculations.
        fp_cols = ['foreign_flow', 'liquidity_shock', 'sector_rotation']
        panel_fp = panel[[c for c in fp_cols if c in panel.columns]].copy()

        # Memory optimization: Pre-group narrow panel by date once (replaces expensive .xs() calls in loop)
        market_by_date = {}
        for date_str, group in panel_fp.groupby(level='date'):
            market_by_date[date_str] = group.droplevel('date')
        
        # Build date -> score mappings (vectorized assignment at the end)
        vsi_map = {dates[0]: 50.0}  # Default for first date
        fss_map = {dates[0]: 20.0}
        sentiment_cache = {}
        
        # Calculate daily market returns and foreign flows
        daily_returns = panel.groupby(level='symbol')['close'].pct_change().groupby(level='date').mean()
        # Using margin_proxy as a proxy for physical market flow in the fallback calculation
        daily_foreign = panel['margin_proxy'].groupby(level='date').mean()
        
        # We loop from the second date to enforce T-1 lag
        for i in range(1, len(dates)):
            curr_date_str = dates[i]
            prev_date_str = dates[i-1]
            prev_datetime = pd.to_datetime(prev_date_str)
            
            # 1. Generate synthetic news based on T-1 market moves
            ret = daily_returns.get(prev_date_str, 0.0)
            flow = daily_foreign.get(prev_date_str, 0.0)
            
            news_items = []
            if ret < -0.015:
                news_items.append(SentimentData(text="Thị trường giảm mạnh bán tháo áp lực margin call", source="CAFEF", published_at=prev_datetime, as_of_time=prev_datetime))
                news_items.append(SentimentData(text="Nhiều cổ phiếu giảm sàn cắt lỗ hàng loạt", source="VIETSTOCK", published_at=prev_datetime, as_of_time=prev_datetime))
            elif ret > 0.015:
                news_items.append(SentimentData(text="Thị trường tăng trần bứt phá dòng tiền mạnh tích cực", source="CAFEF", published_at=prev_datetime, as_of_time=prev_datetime))
            else:
                news_items.append(SentimentData(text="Thị trường sideway ổn định giao dịch trầm lắng", source="VNEXPRESS", published_at=prev_datetime, as_of_time=prev_datetime))
                
            if flow < -1.0:
                news_items.append(SentimentData(text="Khối ngoại bán ròng mạnh rút vốn tiêu cực", source="VIETSTOCK", published_at=prev_datetime, as_of_time=prev_datetime))
                
            # If no items, add a neutral baseline
            if not news_items:
                news_items.append(SentimentData(text="Thị trường bình thường", source="VNEXPRESS", published_at=prev_datetime, as_of_time=prev_datetime))
                
            # 2. Compute VSI
            sentiment_key = tuple((item.text, item.source) for item in news_items)
            sentiment_scores = sentiment_cache.get(sentiment_key)
            if sentiment_scores is None:
                sentiment_scores = self.vsi_engine.calculate_sentiment(news_items)
                sentiment_cache[sentiment_key] = sentiment_scores
            else:
                sentiment_scores = [
                    replace(score, timestamp=prev_datetime, published_at=prev_datetime)
                    for score in sentiment_scores
                ]
            vsi_score_obj = self.vsi_engine.calculate_vsi(sentiment_scores, as_of_time=prev_datetime)
            vsi_val = vsi_score_obj.score
            
            # 3. Compute Focal Point Stress
            # Use pre-grouped single-index slice (memory optimization - avoids expensive .xs() call)
            prev_slice = market_by_date.get(prev_date_str, pd.DataFrame())
            fss_summary = self.fp_detector.analyze(sentiment_scores, prev_slice, prev_datetime)
            fss_val = fss_summary.aggregate_stress_score
            
            # Store in mapping for vectorized assignment later
            vsi_map[curr_date_str] = vsi_val
            fss_map[curr_date_str] = fss_val
            
        # Vectorized date mapping (eliminates O(T*N) boolean masking overhead)
        date_index = panel.index.get_level_values('date')
        vsi_series = pd.Series(date_index.map(vsi_map), index=panel.index).fillna(50.0)
        fss_series = pd.Series(date_index.map(fss_map), index=panel.index).fillna(20.0)
            
        return vsi_series, fss_series

    def get_pead_features(self, panel: pd.DataFrame, as_of=None) -> pd.DataFrame:
        """Issuer-specific, next-session PEAD; downstream execution lags stay intact."""
        if self.pead_engine is None:
            raise ValueError("PEAD requires an explicit earnings ledger")
        return self.pead_engine.features(panel, as_of=as_of)

    def generate_all(self, panel: pd.DataFrame) -> pd.DataFrame:
        """
        Generate all alternative data signals.
        
        Memory optimization: Calculate proxy signals on a narrow copy containing only
        essential OHLCV columns, then join back to original panel.
        
        Memory optimization 2 (GP_ALT_DATA_FETCHER_OPTIMIZATION): Reorder MultiIndex to 
        [symbol, date] and sort once to make groupby(level='symbol') operations contiguous.
        This prevents pandas from allocating expensive (n_groups, n_rows) alignment matrices.

        Args:
            panel: MultiIndex [date, symbol] with OHLCV

        Returns:
            Panel with additional alt data columns.
        """
        # Memory optimization: reorder MultiIndex to [symbol, date] and sort
        # This makes all subsequent groupby(level='symbol') operations contiguous
        pead = self.get_pead_features(panel) if self.pead_engine is not None else None
        if pead is not None and not panel.columns.intersection(pead.columns).empty:
            raise ValueError("panel already contains PEAD columns")
        if panel.empty and pead is not None:
            result = panel.copy()
            for name in self.get_feature_names() + list(self.get_macro_bitemporal_features(panel).columns):
                result[name] = pd.Series(index=panel.index, dtype="float64")
            result[pead.columns] = pead
            return result.reorder_levels(['date', 'symbol']).sort_index()

        panel = panel.reorder_levels(['symbol', 'date']).sort_index()
        
        # Memory optimization: work on narrow copy with only OHLCV columns
        essential_cols = ['open', 'high', 'low', 'close', 'volume']
        narrow = panel[essential_cols].copy()
        
        # Create a new DataFrame for features only
        features = pd.DataFrame(index=narrow.index)

        features['foreign_flow'] = self.get_foreign_flow_proxy(narrow)
        features['margin_proxy'] = self.get_margin_proxy(narrow)
        features['sector_rotation'] = self.get_sector_rotation_proxy(narrow)
        features['order_imbalance'] = self.get_order_imbalance_proxy(narrow)
        features['liquidity_shock'] = self.get_liquidity_shock_proxy(narrow)

        # Rolling aggregates for signal smoothing
        grouped_features = features.groupby(level='symbol')
        features['foreign_flow_ma5'] = grouped_features['foreign_flow'].rolling(5, min_periods=2).mean().droplevel(0)
        margin_rolling = grouped_features['margin_proxy'].rolling
        features['margin_trend'] = (
            margin_rolling(5).mean()
            / margin_rolling(20).mean().replace(0, 1)
        ).droplevel(0)
        features['rotation_momentum'] = grouped_features['sector_rotation'].rolling(5, min_periods=2).mean().droplevel(0)

        # Combine narrow panel with calculated features for sentiment indicators
        # (margin_proxy is required by _derive_sentiment_indicators)
        narrow_with_features = narrow.join(features)
        
        # Generate sentiment and focal point stress features
        vsi_s, fss_s = self._derive_sentiment_indicators(narrow_with_features)
        features['vsi_score'] = vsi_s
        features['focal_stress_score'] = fss_s

        # Align daily features on normalized temporary dates, keeping caller keys unchanged.
        session_dates = pd.DatetimeIndex(pd.to_datetime(
            panel.index.get_level_values('date')
        )).tz_localize(None).normalize()
        macro = self.get_macro_bitemporal_features(panel, self.macro_rows)
        features[macro.columns] = macro.reindex(session_dates).to_numpy()
        if pead is not None:
            features[pead.columns] = pead.reorder_levels(['symbol', 'date'])

        # Join all features back to original panel
        result = panel.join(features)

        # Restore index levels order to prevent silent column swap in unified_feature_adapter.py
        result = result.reorder_levels(['date', 'symbol']).sort_index()

        logger.info("Generated 10 alternative data signals")
        return result

    def get_feature_names(self) -> list:
        """Return list of alternative data feature names."""
        return [
            'foreign_flow', 'margin_proxy', 'sector_rotation',
            'order_imbalance', 'liquidity_shock',
            'foreign_flow_ma5', 'margin_trend', 'rotation_momentum',
            'vsi_score', 'focal_stress_score',
            'interbank_on_spread', 'term_structure_slope',
            'interbank_vol_5d', 'macro_monetary_regime',
        ] + ([
            'pead_sue', 'pead_sec', 'pead_sue_drift', 'pead_sec_drift',
            'pead_age_sessions',
        ] if self.pead_engine is not None else [])
