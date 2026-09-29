"""
Sector Classification & Rotation Features for VN Market.
Tích hợp phân ngành ICB và sector-relative signals.

Version: v21.28-Elite (Institutional Grade)
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-04-26
Merge Surgery: Integrated structure_features.py logic for PIT-safe metadata and price bucketing

COMPLIANCE:
- PIT (Point-in-Time): Metadata fetched with as_of_date, price buckets use T-1 lagged prices
- Vectorization: pd.merge for metadata mapping, pd.cut for price buckets
- Schema: Outputs sector_code, exchange_code, price_bucket columns
"""

import logging
import json
import os
import tempfile
import stat
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta, timezone
from datetime import datetime as _datetime_type
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
# Direct vnstock import retained here for Vnstock().stock().company.profile() chain;
# higher-level callers should prefer omega.data.vnstock_client.VnstockClient.
from vnstock import Vnstock

# Configure logging
logger = logging.getLogger(__name__)

# Cache configuration - v21.28-Elite: [symbol][date] structure
CACHE_DIR = Path(__file__).parent.parent.parent.parent / 'data' / 'cache'
METADATA_CACHE_FILE = CACHE_DIR / 'structure_metadata_cache_v21.json'
CACHE_EXPIRY_DAYS = 7
MAX_METADATA_CACHE_BYTES = 8 * 1024 * 1024
MAX_METADATA_CACHE_WRITE_BYTES = MAX_METADATA_CACHE_BYTES // 2
MAX_METADATA_CACHE_ENTRIES = 10000


def _sync_cache_directory() -> None:
    if os.name == 'nt':
        # ponytail: Windows replace is atomic, not power-loss durable here; deploy persistent cache on POSIX.
        return
    fd = os.open(CACHE_DIR, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _load_metadata_cache() -> Dict[str, Dict[str, Dict[str, str]]]:
    """Load metadata cache with [symbol][date] structure.
    
    Historical entries require trusted availability provenance.
    """
    try:
        if not METADATA_CACHE_FILE.exists():
            return {}
        info = METADATA_CACHE_FILE.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_METADATA_CACHE_BYTES:
            raise ValueError("invalid metadata cache file")
        with open(METADATA_CACHE_FILE, 'rb') as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                raise ValueError("invalid metadata cache file")
            raw = f.read(MAX_METADATA_CACHE_BYTES + 1)
        if len(raw) > MAX_METADATA_CACHE_BYTES:
            raise ValueError("metadata cache too large")
        cache_data = json.loads(raw.decode('utf-8'))
        
        metadata = cache_data['metadata']
        if not isinstance(metadata, dict) or any(not isinstance(dates, dict) for dates in metadata.values()):
            raise ValueError("invalid metadata cache schema")
        return metadata
    except (OSError, ValueError, TypeError) as e:
        raise ValueError("Failed to load metadata cache") from e

def _save_metadata_cache(metadata: Dict[str, Dict[str, Dict[str, str]]]) -> None:
    """Save metadata cache to disk."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=CACHE_EXPIRY_DAYS)
    entries = []
    for symbol, dates in metadata.items():
        for key, value in dates.items():
            key = key.isoformat() if isinstance(key, _datetime_type) else str(key)
            try:
                observed = _datetime_type.fromisoformat(key)
            except ValueError:
                continue
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            observed = observed.astimezone(timezone.utc)
            if observed >= cutoff:
                entries.append((observed, symbol, key, value))
    entries.sort(key=lambda entry: entry[0], reverse=True)
    normalized = {}
    # ponytail: retain newest entries within half the reader ceiling; add streaming storage if the active universe grows beyond this budget.
    budget = MAX_METADATA_CACHE_WRITE_BYTES - 256
    for index, (_, symbol, key, value) in enumerate(entries):
        if index >= MAX_METADATA_CACHE_ENTRIES:
            break
        entry_bytes = len(json.dumps({symbol: {key: value}}, ensure_ascii=False).encode('utf-8')) + 8
        if entry_bytes > MAX_METADATA_CACHE_WRITE_BYTES - 256:
            raise ValueError("metadata cache entry exceeds write limit")
        if entry_bytes > budget:
            continue
        normalized.setdefault(symbol, {})[key] = value
        budget -= entry_bytes
    payload = json.dumps({'timestamp': now.isoformat(), 'metadata': normalized},
                         indent=2, ensure_ascii=False)
    if len(payload.encode('utf-8')) > MAX_METADATA_CACHE_WRITE_BYTES:
        raise ValueError("metadata cache exceeds write limit")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=CACHE_DIR, prefix=METADATA_CACHE_FILE.name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, METADATA_CACHE_FILE)
        try:
            _sync_cache_directory()
        except OSError:
            # The new cache is already visible; retry durability before reporting failure.
            _sync_cache_directory()
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise

def get_structure_metadata(
    symbols: List[str], 
    as_of_date: str | datetime,
    use_cache: bool = True,
    *,
    available_at: datetime | None = None,
) -> Dict[str, Dict[str, str]]:
    """
    Fetch structural metadata as of a specific date.
    
    PIT COMPLIANCE: Only fetch live data if as_of_date >= today.
    For historical dates without cache, return UNKNOWN to prevent look-ahead bias.
    
    Returns: {symbol: {sector_code, exchange_code}}
    """
    # Validate before cache access or network I/O.
    vn_tz = ZoneInfo("Asia/Ho_Chi_Minh")
    if isinstance(as_of_date, _datetime_type):
        if as_of_date.tzinfo is None or as_of_date.utcoffset() is None:
            raise ValueError("as_of_date datetime must be timezone-aware")
        as_of_ts = as_of_date.astimezone(timezone.utc)
        as_of_dt = as_of_ts.astimezone(vn_tz).date()
    elif type(as_of_date) is str and len(as_of_date) == 10:
        try:
            as_of_dt = _datetime_type.strptime(as_of_date, '%Y-%m-%d').date()
        except ValueError as exc:
            raise ValueError("invalid as_of_date") from exc
        if as_of_dt.isoformat() != as_of_date:
            raise ValueError("invalid as_of_date")
        as_of_ts = _datetime_type.combine(as_of_dt, _datetime_type.max.time(), tzinfo=vn_tz).astimezone(timezone.utc)
    else:
        raise ValueError("as_of_date must be YYYY-MM-DD or timezone-aware datetime")
    today = _datetime_type.now(vn_tz).date()
    is_historical = as_of_dt < today
    if not is_historical:
        if as_of_ts is None or not isinstance(available_at, _datetime_type) or available_at.tzinfo is None or available_at.utcoffset() is None:
            raise ValueError("same-day metadata requires timezone-aware as_of_date and available_at")
        if available_at.astimezone(timezone.utc) > as_of_ts:
            raise ValueError("metadata available_at is later than as_of_date")

    cache = _load_metadata_cache() if use_cache else {}
    metadata_snapshot = {}
    symbols_to_fetch = []

    cache_date = as_of_date.isoformat() if isinstance(as_of_date, _datetime_type) else as_of_date
    for symbol in symbols:
        cached = cache.get(symbol, {}).get(cache_date)
        if cached is not None:
            if (not isinstance(cached, dict) or
                    cached.get("availability_source") not in
                    (("historical_snapshot",) if is_historical else ("historical_snapshot", "observed"))):
                metadata_snapshot[symbol] = {'sector_code': 'UNKNOWN', 'exchange_code': 'UNKNOWN'}
                continue
            try:
                cached_available_at = _datetime_type.fromisoformat(cached.get("available_at"))
                if cached_available_at.tzinfo is None or cached_available_at.utcoffset() is None:
                    raise ValueError
            except (TypeError, ValueError):
                metadata_snapshot[symbol] = {'sector_code': 'UNKNOWN', 'exchange_code': 'UNKNOWN'}
                continue
            if cached_available_at.astimezone(timezone.utc) > as_of_ts or cached.get('sector_code') is None or cached.get('exchange_code') is None:
                metadata_snapshot[symbol] = {'sector_code': 'UNKNOWN', 'exchange_code': 'UNKNOWN'}
                continue
            metadata_snapshot[symbol] = {key: cached[key] for key in ('sector_code', 'exchange_code')}
        else:
            # PIT VIOLATION CHECK: Don't fetch live data for historical dates
            if is_historical:
                logger.warning(f"PIT VIOLATION PREVENTED: {symbol} on {as_of_date} not in cache, returning UNKNOWN")
                metadata_snapshot[symbol] = {'sector_code': 'UNKNOWN', 'exchange_code': 'UNKNOWN'}
            else:
                symbols_to_fetch.append(symbol)

    if not symbols_to_fetch:
        return metadata_snapshot

    # Only fetch if as_of_date >= today
    logger.info(f"Fetching live metadata for {len(symbols_to_fetch)} symbols as of {as_of_date}")
    if as_of_ts < _datetime_type.now(timezone.utc):
        raise ValueError("intraday replay unsupported: profile observed after as_of_date")
    stock = Vnstock()
    
    for symbol in symbols_to_fetch:
        symbol_data = {'sector_code': 'UNKNOWN', 'exchange_code': 'UNKNOWN'}
        try:
            if symbol and symbol != 'UNKNOWN' and not pd.isna(symbol):
                profile = stock.stock(symbol=symbol, source='VCI').company.profile()
                if profile is not None and not profile.empty:
                    observed_at = _datetime_type.now(timezone.utc)
                    if as_of_ts < observed_at:
                        raise ValueError("intraday replay unsupported: profile observed after as_of_date")
                    sector = profile.get('industryName', 'UNKNOWN')
                    exchange = profile.get('exchange', 'UNKNOWN')
                    if isinstance(sector, pd.Series): sector = sector.iloc[0] if not sector.empty else 'UNKNOWN'
                    if isinstance(exchange, pd.Series): exchange = exchange.iloc[0] if not exchange.empty else 'UNKNOWN'
                    
                    symbol_data = {
                        'sector_code': str(sector) if pd.notna(sector) else 'UNKNOWN',
                        'exchange_code': str(exchange) if pd.notna(exchange) else 'UNKNOWN',
                        'available_at': observed_at.isoformat(),
                        'availability_source': 'observed'
                    }
            
            metadata_snapshot[symbol] = symbol_data
            if symbol not in cache: cache[symbol] = {}
            cache[symbol][cache_date] = symbol_data
            
        except ValueError as e:
            if str(e).startswith("intraday replay unsupported"):
                raise
            logger.error("Error fetching metadata for %s: %s", symbol, e)
            metadata_snapshot[symbol] = symbol_data
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            metadata_snapshot[symbol] = symbol_data

    if use_cache:
        _save_metadata_cache(cache)
    
    return metadata_snapshot


@dataclass  
class SectorConfig:
    enable_sector_class: bool = True
    enable_sector_relative: bool = True
    enable_sector_rotation: bool = True
    icb_depth: int = 2  # 1=Sector, 2=Industry Group, 3=Sub-industry


class SectorClassifier:
    """
    Phân loại cổ phiếu theo ngành ICB và tính toán sector-relative features.
    """
    
    def __init__(self, config: SectorConfig = None):
        self.config = config or SectorConfig()
        self._sector_cache: Dict[str, str] = {}  # symbol -> sector_code
        self._symbol_list: List[str] = []
    
    def fetch_sector_mapping(self, symbols: List[str]) -> Dict[str, str]:
        """
        Lấy mapping từ symbol -> sector ICB.
        
        Returns:
            {symbol: sector_code} (e.g., "HPG": "C0612" for Steel)
        """
        requested = set(symbols)
        missing = requested.difference(self._sector_cache)
        if not missing:
            return {symbol: self._sector_cache[symbol] for symbol in symbols}
        
        # Try to fetch from vnstock (VCI source) — vnstock 4.x exposes Listing at top level
        try:
            from vnstock import Listing
            lst = Listing(source='VCI')
            # Lấy mapping symbols -> industries
            df_symbols = lst.symbols_by_industries()
            if df_symbols is not None:
                # Map symbol -> sector
                for _, row in df_symbols.iterrows():
                    symbol = row.get('symbol')
                    if symbol in missing:
                        # Get ICB code based on depth
                        if self.config.icb_depth == 1:
                            sector = row.get('industry_code_sector', row.get('industry_code', ''))
                        elif self.config.icb_depth == 2:
                            sector = row.get('industry_code_group', row.get('industry_code', ''))
                        else:
                            sector = row.get('industry_code', '')
                        
                        self._sector_cache[symbol] = sector
        except Exception as e:
            print(f"Could not fetch sector data from vnstock: {e}")
        
        return {symbol: self._sector_cache.get(symbol, 'UNKNOWN') for symbol in symbols}

    def get_sector_mapping_pit(
        self,
        as_of: Any,
        sector_history: Optional[pd.DataFrame] = None,
        symbol_col: str = "ticker",
        sector_col: str = "sector_code",
        effective_col: str = "effective_date",
    ) -> Dict[str, str]:
        """Return symbol->sector snapshot as of date using latest effective record <= as_of.

        Without history, no current cache classification is safe for a historical snapshot.
        """
        if sector_history is None:
            return {}

        if sector_history.empty:
            return {}

        as_of_ts = pd.Timestamp(as_of)
        history = sector_history.copy()
        history[effective_col] = pd.to_datetime(history[effective_col])
        history = history.loc[history[effective_col] <= as_of_ts]
        if history.empty:
            return {}

        history = history.sort_values([symbol_col, effective_col])
        latest = history.groupby(symbol_col, sort=False).tail(1)
        mapping = dict(zip(latest[symbol_col].astype(str), latest[sector_col].astype(str)))
        return mapping

    def compute_rs_ex_top3(
        self,
        panel: pd.DataFrame,
        as_of: Any,
        symbol_col: str = "ticker",
        date_col: str = "date",
        sector_col: str = "sector_code",
        return_col: str = "return_1",
        market_cap_col: str = "market_cap",
    ) -> pd.DataFrame:
        """Sector-relative return excluding top-3 mcap names per sector from t-1 cross-section."""
        required = {symbol_col, date_col, sector_col, return_col, market_cap_col}
        missing = required.difference(panel.columns)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")

        df = panel.copy()
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.sort_values([symbol_col, date_col])
        df["_mcap_lag1"] = df.groupby(symbol_col)[market_cap_col].shift(1)

        snapshot = df.loc[df[date_col] == pd.Timestamp(as_of)].copy()
        if snapshot.empty:
            return snapshot.assign(rs_ex_top3=pd.Series(dtype=float))

        snapshot["_rank"] = snapshot.groupby(sector_col)["_mcap_lag1"].rank(method="first", ascending=False)
        snapshot["_include_peer"] = snapshot["_rank"].gt(3) | snapshot["_rank"].isna()

        peer_means = (
            snapshot.loc[snapshot["_include_peer"]]
            .groupby(sector_col)[return_col]
            .mean()
            .rename("_peer_mean")
        )
        snapshot = snapshot.merge(peer_means, on=sector_col, how="left")
        snapshot["rs_ex_top3"] = snapshot[return_col] - snapshot["_peer_mean"].fillna(0.0)
        return snapshot.drop(columns=["_mcap_lag1", "_rank", "_include_peer", "_peer_mean"])
    
    def compute_sector_returns(self, clean_df: Dict[str, Any], 
                          sector_mapping: Dict[str, str]) -> Dict[str, List[float]]:
        """
        Tính return trung bình theo sector.
        
        Returns:
            {sector_code: [return_day0, return_day1, ...]}
        """
        symbols = clean_df['index']['symbol']
        timestamps = clean_df['index']['timestamp']
        
        # Aggregate returns by sector
        sector_returns: Dict[str, List[float]] = {}
        
        for sector in set(sector_mapping.values()):
            sector_returns[sector] = [0.0] * len(timestamps)
        
        for i, ts in enumerate(timestamps):
            # Sum returns by sector
            sector_return_sums: Dict[str, float] = {}
            sector_counts: Dict[str, int] = {}
            
            for sym in symbols:
                sector = sector_mapping.get(sym)
                if not sector:
                    continue
                
                sym_data = clean_df['data'][sym]
                if ts in sym_data:
                    ret = sym_data[ts].get('return_1', 0.0)
                    
                    if sector not in sector_return_sums:
                        sector_return_sums[sector] = 0.0
                        sector_counts[sector] = 0
                    
                    sector_return_sums[sector] += ret
                    sector_counts[sector] += 1
            
            # Average
            for sector in sector_returns:
                if sector_counts.get(sector, 0) > 0:
                    sector_returns[sector][i] = sector_return_sums[sector] / sector_counts[sector]
        
        return sector_returns
    
    def compute_relative_strength(self, clean_df: Dict[str, Any],
                                 sector_returns: Dict[str, List[float]],
                                 sector_mapping: Dict[str, str]) -> Dict[str, Dict[int, float]]:
        """
        Tính relative strength (symbol return - sector return).
        
        Returns:
            {symbol: {timestamp: relative_strength}}
        """
        symbols = clean_df['index']['symbol']
        timestamps = clean_df['index']['timestamp']
        
        result = {}
        
        for sym in symbols:
            sector = sector_mapping.get(sym)
            if not sector:
                continue
            
            result[sym] = {}
            sector_ret = sector_returns.get(sector, [0.0] * len(timestamps))
            
            sym_data = clean_df['data'][sym]
            for i, ts in enumerate(timestamps):
                if ts in sym_data:
                    sym_ret = sym_data[ts].get('return_1', 0.0)
                    # Relative = sym - sector
                    result[sym][ts] = sym_ret - sector_ret[i]
        
        return result
    
    def compute_sector_flow(self, foreign_flow_data: Dict[str, Dict[int, Dict]],
                           sector_mapping: Dict[str, str]) -> Dict[str, Dict[int, float]]:
        """
        Tính tổng flow theo sector.
        
        Returns:
            {sector_code: {timestamp: total_net_flow}}
        """
        symbols = set(foreign_flow_data.keys())
        timestamps = set()
        for sym_data in foreign_flow_data.values():
            timestamps.update(sym_data.keys())
        timestamps = sorted(timestamps)
        
        sector_flows: Dict[str, Dict[int, float]] = {}
        
        for sector in set(sector_mapping.values()):
            sector_flows[sector] = {ts: 0.0 for ts in timestamps}
        
        for sym, sector in sector_mapping.items():
            if sym not in foreign_flow_data:
                continue
            
            sym_flow = foreign_flow_data[sym]
            for ts, flow_data in sym_flow.items():
                if ts in sector_flows[sector]:
                    sector_flows[sector][ts] += flow_data.get('net_vol', 0.0)
        
        return sector_flows
    
    def detect_sector_rotation(self, sector_flows: Dict[str, Dict[int, float]],
                              lookback: int = 20) -> List[Dict[str, Any]]:
        """
        Phát hiện sector rotation (dòng tiền đang chảy vào ngành nào).
        
        Returns:
            List of {sector, momentum, signal} sorted by momentum descending
        """
        results = []
        
        for sector, flow_dict in sector_flows.items():
            timestamps = sorted(flow_dict.keys())
            
            if len(timestamps) < lookback:
                continue
            
            # Calculate momentum (sum of recent flow vs historical)
            recent_flow = sum(flow_dict.get(ts, 0.0) for ts in timestamps[-5:])
            historical_avg = sum(flow_dict.get(ts, 0.0) for ts in timestamps[:-5]) / max(len(timestamps) - 5, 1)
            
            momentum = recent_flow - historical_avg if historical_avg != 0 else 0.0
            
            # Signal
            if momentum > 0.3:
                signal = 'strong_inflow'
            elif momentum > 0.1:
                signal = 'moderate_inflow'
            elif momentum < -0.3:
                signal = 'strong_outflow'
            elif momentum < -0.1:
                signal = 'moderate_outflow'
            else:
                signal = 'neutral'
            
            results.append({
                'sector': sector,
                'momentum': momentum,
                'signal': signal,
                'recent_flow': recent_flow,
                'historical_avg': historical_avg
            })
        
        # Sort by momentum descending
        results.sort(key=lambda x: x['momentum'], reverse=True)
        
        return results
    
    def get_sector_symbols(self, sector_code: str) -> List[str]:
        """Lấy danh sách symbols theo sector."""
        return [sym for sym, sec in self._sector_cache.items() if sec == sector_code]
    
    def compute_structure_features(
        self,
        df: pd.DataFrame,
        metadata_map: Dict[str, Dict[str, str]],
        price_col: str = 'close',
        symbol_col: str = 'ticker',
        as_of_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Compute structural features with PIT safety and vectorization.
        
        MANDATORY: metadata_map must be provided for PIT safety. 
        Price buckets use T-1 lagged close prices.
        
        Supports both regular DataFrame and MultiIndex [date, ticker].
        
        MERGED FROM structure_features.py for unified sector classification.
        """
        df_out = df.copy()
        
        # Handle empty DataFrame - always create 3 required columns
        if df_out.empty:
            for col in ['sector_code', 'exchange_code', 'price_bucket']:
                df_out[col] = pd.Series(dtype='object')
            return df_out

        # Detect if MultiIndex [date, ticker]
        is_multiindex = isinstance(df_out.index, pd.MultiIndex)
        
        if is_multiindex:
            # Reset MultiIndex to columns for processing
            df_out = df_out.reset_index()
            if 'date' not in df_out.columns:
                raise ValueError("MultiIndex must have 'date' as first level")
            if symbol_col not in df_out.columns:
                raise ValueError(f"MultiIndex must have '{symbol_col}' as second level")
        
        # 1. PIT Price Bucket (Using T-1 Lagged Close)
        if 'date' in df_out.columns:
            df_out = df_out.sort_values(['date', symbol_col])
            if as_of_date is not None:
                cutoff = pd.Timestamp(as_of_date)
                cutoff = cutoff.tz_localize('UTC') if cutoff.tzinfo is None else cutoff.tz_convert('UTC')
                if (pd.to_datetime(df_out['date'], utc=True) > cutoff).any():
                    raise ValueError('feature date exceeds as_of_date')
            df_out['close_lag1'] = df_out.groupby(symbol_col)[price_col].shift(1)
        else:
            # No date column - cannot compute lag safely, must fail
            raise ValueError("ANTI-LEAKAGE: 'date' column required for T-1 lag computation. Cannot use current prices.")

        bins = [0, 10_000, 50_000, 100_000, np.inf]
        labels = ['0-10k', '10k-50k', '50k-100k', '100k+']
        
        df_out['price_bucket'] = pd.cut(
            df_out['close_lag1'],
            bins=bins,
            labels=labels,
            include_lowest=True,
            right=False
        ).astype(str)
        df_out.loc[df_out['close_lag1'].isna(), 'price_bucket'] = 'UNKNOWN'
        df_out.drop(columns=['close_lag1'], inplace=True)

        # 2. Only independently sourced historical snapshots may classify dated rows.
        if metadata_map:
            snapshots = []
            for symbol, entries in metadata_map.items():
                if not isinstance(entries, dict):
                    raise ValueError('historical metadata snapshot required')
                for observed, entry in entries.items():
                    if not isinstance(entry, dict) or entry.get('availability_source') != 'historical_snapshot':
                        continue
                    effective = pd.Timestamp(observed)
                    try:
                        available = pd.Timestamp(entry['available_at'])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise ValueError('metadata available_at required') from exc
                    if available.tzinfo is None:
                        raise ValueError('metadata available_at must be timezone-aware')
                    if effective.tzinfo is None:
                        effective = effective.tz_localize('UTC')
                    # Both the effective date and the source availability bound the first usable row.
                    usable_at = max(effective.tz_convert('UTC'), available.tz_convert('UTC'))
                    snapshots.append({symbol_col: symbol, 'available_at': usable_at.tz_localize(None),
                                       'sector_code': entry['sector_code'], 'exchange_code': entry['exchange_code']})
            if snapshots:
                meta_df = pd.DataFrame(snapshots).sort_values('available_at')
                dates = pd.to_datetime(df_out['date'], utc=True).dt.tz_localize(None)
                df_out['_row_time'] = dates
                df_out = pd.merge_asof(df_out.sort_values('_row_time'), meta_df,
                                       left_on='_row_time', right_on='available_at', by=symbol_col,
                                       direction='backward').drop(columns=['_row_time', 'available_at'])
            else:
                df_out['sector_code'] = 'UNKNOWN'
                df_out['exchange_code'] = 'UNKNOWN'
        else:
            # Empty metadata_map - create columns with UNKNOWN
            logger.warning("Empty metadata_map provided, filling with UNKNOWN")
            df_out['sector_code'] = 'UNKNOWN'
            df_out['exchange_code'] = 'UNKNOWN'
        
        # Fill UNKNOWN for missing matches
        df_out['sector_code'] = df_out['sector_code'].fillna('UNKNOWN')
        df_out['exchange_code'] = df_out['exchange_code'].fillna('UNKNOWN')
        
        # Restore MultiIndex if input was MultiIndex
        if is_multiindex:
            df_out = df_out.set_index(['date', symbol_col])

        return df_out


# Standalone feature generators (for use with FeatureFactory)
def generate_sector_features(clean_df: Dict[str, Any],
                           sector_mapping: Dict[str, str],
                           foreign_flow_data: Optional[Dict] = None) -> Dict[str, Dict[int, Dict[str, float]]]:
    """
    Generate all sector-related features for the FeatureMatrix.
    """
    sc = SectorClassifier()
    
    features = {}
    symbols = clean_df['index']['symbol']
    timestamps = clean_df['index']['timestamp']
    
    # Compute sector returns
    if not sc._sector_cache:
        sc._sector_cache = sector_mapping
    
    sector_returns = sc.compute_sector_returns(clean_df, sector_mapping)
    relative_strength = sc.compute_relative_strength(clean_df, sector_returns, sector_mapping)
    
    # Compute sector flows
    sector_flows = {}
    if foreign_flow_data:
        sector_flows = sc.compute_sector_flow(foreign_flow_data, sector_mapping)
    
    # Detect rotation
    rotation = sc.detect_sector_rotation(sector_flows)
    
    # Build feature matrix
    for sym in symbols:
        features[sym] = {}
        
        for i, ts in enumerate(timestamps):
            sector = sector_mapping.get(sym, '')
            
            feat = {
                'sector_code': sector,
                'rel_strength': relative_strength.get(sym, {}).get(ts, 0.0),
            }
            
            # Add sector flow if available
            if sector in sector_flows and ts in sector_flows[sector]:
                feat['sector_flow'] = sector_flows[sector][ts]
            
            # Add sector rotation signal if this is top sector
            if rotation and rotation[0].get('sector') == sector:
                feat['sector_rotation'] = 1.0
            else:
                feat['sector_rotation'] = 0.0
            
            features[sym][ts] = feat
    
    return features
