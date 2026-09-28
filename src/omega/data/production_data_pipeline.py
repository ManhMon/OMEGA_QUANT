import sys
import json
import os
import tempfile
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, date, UTC
from zoneinfo import ZoneInfo
from typing import Dict, List, Any, Optional, Tuple

from omega.data.sanitizer import DataSanitizer, DataValidator, ValidationIssue
from omega.quant.feature.factory import FeatureFactory
from omega.quant.features.neutralization import HierarchicalNeutralizer
from omega.data.corporate_action import CorporateActionAdjuster, CorporateAction
from omega.data.news_aggregator import NewsAggregator, DEFAULT_EVENT_HISTORY_PATH
from omega.data.pipeline.production_pipeline import _publish_output_pair

warnings.filterwarnings('ignore')

class ProductionDataPipeline:
    def __init__(self, input_path: str, output_path: str, cache_dir: str = "V21_QUANT/data/cache", as_of_time: Optional[datetime] = None):
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT compliance in ProductionDataPipeline")
        if not isinstance(as_of_time, datetime) or as_of_time.tzinfo is None or as_of_time.utcoffset() != UTC.utcoffset(None):
            raise ValueError("as_of_time must be timezone-aware UTC")
        self.input_path, self.output_path, self.cache_dir, self.as_of_time = Path(input_path), Path(output_path), Path(cache_dir), as_of_time
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sanitizer = DataSanitizer(as_of_time=as_of_time)
        self.validator = DataValidator()
        self.feature_module = FeatureFactory()
        self.neutralizer = HierarchicalNeutralizer()
        self.corp_action_adjuster = CorporateActionAdjuster()
        self.news_aggregator = NewsAggregator(event_history_path=DEFAULT_EVENT_HISTORY_PATH)
        self.pipeline_stats, self.validation_issues = {}, []

    def _apply_corporate_actions(self, df: pd.DataFrame) -> pd.DataFrame:
        if 'price_basis' not in df or df['price_basis'].isna().any() or not df['price_basis'].isin(['raw', 'adjusted']).all() or df['price_basis'].nunique() != 1:
            raise ValueError('price_basis must be uniformly raw or adjusted')
        if df['price_basis'].iloc[0] == 'adjusted': return df
        if not self.corp_action_adjuster.actions: return df
        as_of_iso = self.as_of_time.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
        filtered = [a for a in self.corp_action_adjuster.actions
                    if not a.is_quarantined and a.available_at is not None
                    and a.available_at <= self.as_of_time and a.ex_date <= as_of_iso]
        if not filtered: return df
        print(f"  Corporate Actions: Applying {len(filtered)} actions (ex_date <= {as_of_iso})")
        clean_data = {"type": "CleanDataFrame", "price_basis": "raw", "index": {"symbol": df['symbol'].unique().tolist(), "timestamp": sorted(df['timestamp'].dt.strftime('%Y-%m-%d').unique().tolist())}, "data": {}}
        records = df.assign(timestamp=df['timestamp'].dt.strftime('%Y-%m-%d'))
        available_cols = [c for c in ['open','high','low','close','volume'] if c in df.columns]
        for s, group in records.groupby('symbol'):
            clean_data["data"][s] = group.set_index('timestamp')[available_cols].to_dict('index')
        temp_adj = CorporateActionAdjuster()
        temp_adj.add_actions(filtered)
        adj_data = temp_adj.apply_adjustments(clean_data, as_of_time=self.as_of_time)
        rows = []
        for s in adj_data["index"]["symbol"]:
            s_df = pd.DataFrame.from_dict(adj_data["data"][s], orient='index')
            s_df['symbol'] = s
            rows.append(s_df.reset_index().rename(columns={'index':'timestamp'}))
        result = pd.concat(rows).reset_index(drop=True)
        result['timestamp'] = pd.to_datetime(result['timestamp'])
        result['price_basis'] = adj_data['price_basis']
        return result

    def run(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        print(f"Starting Production Data Pipeline (as_of={self.as_of_time.isoformat()})...")
        df = pd.read_parquet(self.input_path)
        self.pipeline_stats['l1_input_rows'] = len(df)
        if 'available_at' not in df:
            raise ValueError('available_at required for PIT-safe fitting')
        available = pd.to_datetime(df['available_at'], utc=True, errors='coerce')
        if available.isna().any():
            raise ValueError('invalid available_at')
        df = df.loc[available <= self.as_of_time].copy()
        if df.empty:
            raise ValueError('no rows available as of as_of_time')
        df = self._apply_corporate_actions(df)
        self.sanitizer.fit(df, symbol_col='symbol', date_col='timestamp')
        df = self.sanitizer.apply(df, symbol_col='symbol', date_col='timestamp')
        self.validation_issues = self.validator.validate_rows(df.to_dict('records'), symbol=None)
        self.pipeline_stats['l4_validation_issues'] = len(self.validation_issues)
        df = self.feature_module.generate(df, symbol_col='symbol')
        df_neutralized = df.copy()
        sector_map = {s: f"sector_{hash(s)%10}" for s in df['symbol'].unique()}
        df_neutralized['sector'] = df_neutralized['symbol'].map(sector_map)
        neut_values = {}
        for dt in df_neutralized['timestamp'].dt.date.unique():
            dt_mask = df_neutralized['timestamp'].dt.date == dt
            dt_df = df_neutralized[dt_mask]
            neut, _ = self.neutralizer.neutralize_cross_section(dt_df.set_index('symbol')['ret_1'], dt_df.set_index('symbol')['sector'])
            for s, v in neut.items(): neut_values[(s, dt)] = v
        df_neutralized['alpha_neutralized'] = df_neutralized.apply(lambda r: neut_values.get((r['symbol'], r['timestamp'].date()), np.nan), axis=1)
        report = self._l7_quality_report(df_neutralized)
        self._l8_save_output(df_neutralized, report)
        return df_neutralized, report

    def _l7_quality_report(self, df: pd.DataFrame) -> Dict[str, Any]:
        return {
            'pipeline_stats': self.pipeline_stats,
            'validation_issues': [issue.to_dict() if hasattr(issue, 'to_dict') else {'rule': issue.rule, 'symbol': issue.symbol, 'timestamp': issue.timestamp.isoformat() if isinstance(issue.timestamp, (datetime, date)) else str(issue.timestamp), 'severity': getattr(issue, 'severity', 'medium'), 'message': issue.message} for issue in self.validation_issues[:100]],
            'data_quality': {'total_rows': len(df), 'total_symbols': df['symbol'].nunique()}
        }

    def _l8_save_output(self, df: pd.DataFrame, report: Dict[str, Any]):
        _publish_output_pair(self.output_path, df, report)

def main():
    ProductionDataPipeline("V21_QUANT/data/market_2015_now.parquet", "V21_QUANT/data/market_2015_now_clean.parquet", as_of_time=datetime.now(UTC)).run()

if __name__ == "__main__": main()
