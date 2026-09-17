import sys
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Tuple

from omega.data.sanitizer import DataSanitizer, DataValidator, ValidationIssue
from omega.quant.feature.factory import FeatureFactory
from omega.quant.features.neutralization import HierarchicalNeutralizer
from omega.data.corporate_action import CorporateActionAdjuster, CorporateAction

warnings.filterwarnings('ignore')

class ProductionDataPipeline:
    def __init__(self, input_path: str, output_path: str, cache_dir: str = "V21_QUANT/data/cache", as_of_time: Optional[datetime] = None):
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT compliance in ProductionDataPipeline")
        self.input_path, self.output_path, self.cache_dir, self.as_of_time = Path(input_path), Path(output_path), Path(cache_dir), as_of_time
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sanitizer = DataSanitizer(as_of_time=as_of_time)
        self.validator = DataValidator()
        self.feature_module = FeatureFactory()
        self.neutralizer = HierarchicalNeutralizer()
        self.corp_action_adjuster = CorporateActionAdjuster()
        self.pipeline_stats, self.validation_issues = {}, []

    def _apply_corporate_actions(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.corp_action_adjuster.actions: return df
        as_of_iso = self.as_of_time.date().isoformat()
        filtered = [a for a in self.corp_action_adjuster.actions if a.ex_date <= as_of_iso]
        if not filtered: return df
        print(f"  Corporate Actions: Applying {len(filtered)} actions (ex_date <= {as_of_iso})")
        clean_data = {"type": "CleanDataFrame", "index": {"symbol": df['symbol'].unique().tolist(), "timestamp": sorted(df['timestamp'].dt.strftime('%Y-%m-%d').unique().tolist())}, "data": {}}
        for s in clean_data["index"]["symbol"]:
            clean_data["data"][s] = {c: df[df['symbol']==s].set_index('timestamp')[c].to_dict() for c in ['open','high','low','close','volume'] if c in df.columns}
        temp_adj = CorporateActionAdjuster()
        temp_adj.add_actions(filtered)
        adj_data = temp_adj.apply_adjustments(clean_data)
        rows = []
        for s in adj_data["index"]["symbol"]:
            s_df = pd.DataFrame(adj_data["data"][s])
            s_df['symbol'] = s
            rows.append(s_df.reset_index().rename(columns={'index':'timestamp'}))
        return pd.concat(rows).reset_index(drop=True)

    def run(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        print(f"Starting Production Data Pipeline (as_of={self.as_of_time.isoformat()})...")
        df = pd.read_parquet(self.input_path)
        self.pipeline_stats['l1_input_rows'] = len(df)
        df = self._apply_corporate_actions(df)
        self.sanitizer.fit(df, symbol_col='symbol')
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
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(self.output_path, index=False)
        with open(self.output_path.parent / f"{self.output_path.stem}_quality_report.json", 'w') as f: json.dump(report, f, indent=2)

def main():
    ProductionDataPipeline("V21_QUANT/data/market_2015_now.parquet", "V21_QUANT/data/market_2015_now_clean.parquet", as_of_time=datetime(2026, 5, 12, 17, 0, 0)).run()

if __name__ == "__main__": main()
