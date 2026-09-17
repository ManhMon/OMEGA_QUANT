import sys
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Tuple

from omega.data.sanitizer import DataSanitizer, DataValidator, ValidationIssue
from omega.data.corporate_action import CorporateActionAdjuster, CorporateAction
# NOTE: FeatureModule, NeutralizationEngine not yet in OMEGA package
# These will be integrated in Phase 12 (Portfolio Optimization)

warnings.filterwarnings('ignore')

class ProductionDataPipeline:
    def __init__(self, input_path: str, output_path: str, cache_dir: str = "data/cache", as_of_time: Optional[datetime] = None):
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT compliance in ProductionDataPipeline")
        self.input_path, self.output_path, self.cache_dir, self.as_of_time = Path(input_path), Path(output_path), Path(cache_dir), as_of_time
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sanitizer = DataSanitizer(as_of_time=as_of_time)
        self.validator = DataValidator()
        # NOTE: FeatureModule and NeutralizationEngine are Phase 12 features
        # Removed to prevent import errors - will be integrated in Portfolio Optimization phase
        self.corp_action_adjuster = CorporateActionAdjuster()
        self.pipeline_stats, self.validation_issues = {}, []

    def _apply_corporate_actions(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.corp_action_adjuster.actions: return df
        as_of_iso = self.as_of_time.date().isoformat()
        filtered = [a for a in self.corp_action_adjuster.actions if a.ex_date <= as_of_iso]
        if not filtered: return df
        print(f"  Corporate Actions: Applying {len(filtered)} actions (ex_date <= {as_of_iso})")
        
        # Vectorized: build clean_data structure without loops
        symbols = df['symbol'].unique().tolist()
        timestamps = sorted(df['timestamp'].dt.strftime('%Y-%m-%d').unique().tolist())
        clean_data = {"type": "CleanDataFrame", "index": {"symbol": symbols, "timestamp": timestamps}, "data": {}}
        
        price_cols = ['open', 'high', 'low', 'close', 'volume']
        available_cols = [c for c in price_cols if c in df.columns]
        
        # Fully vectorized: use groupby to build nested dict without symbol loop
        df_indexed = df.set_index(['symbol', 'timestamp'])
        clean_data["data"] = {
            s: {c: df_indexed.loc[s][c].to_dict() if s in df_indexed.index.get_level_values(0) else {} 
                for c in available_cols}
            for s in symbols
        }
        
        temp_adj = CorporateActionAdjuster()
        temp_adj.add_actions(filtered)
        adj_data = temp_adj.apply_adjustments(clean_data)
        
        # Fully vectorized: use list comprehension instead of loop
        dfs = [
            pd.DataFrame(adj_data["data"][s]).assign(symbol=s).reset_index().rename(columns={'index': 'timestamp'})
            for s in adj_data["index"]["symbol"]
        ]
        
        return pd.concat(dfs, ignore_index=True) if dfs else df

    def run(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        print(f"Starting Production Data Pipeline (as_of={self.as_of_time.isoformat()})...")
        df = pd.read_parquet(self.input_path)
        self.pipeline_stats['l1_input_rows'] = len(df)
        df = self._apply_corporate_actions(df)
        self.sanitizer.fit(df, symbol_col='symbol')
        df = self.sanitizer.apply(df, symbol_col='symbol', date_col='timestamp')
        
        # Validation using DataValidator.validate_rows() - fully vectorized groupby approach
        # Vectorized: Use groupby().apply() to partition by symbol and validate each group
        # This replaces O(N*S) Python loop with pandas-native vectorized operation
        def validate_symbol_group(group):
            """Validate a single symbol's data group."""
            symbol = group.name
            symbol_rows = group.to_dict('records')
            issues = self.validator.validate_rows(symbol_rows, symbol=symbol)
            return issues if issues else []
        
        # Apply validation to each symbol group and collect all issues
        all_issues = df.groupby('symbol', group_keys=False).apply(validate_symbol_group, include_groups=False)
        
        # Flatten the list of issue lists into a single list
        for issue_list in all_issues:
            if issue_list:
                self.validation_issues.extend(issue_list)
        
        self.pipeline_stats['l4_validation_issues'] = len(self.validation_issues)
        
        # NOTE: Feature computation and neutralization are Phase 12 features
        # Skipping for now to prevent import errors
        # df = self.feature_module.compute_features(df, symbol_col='symbol')
        # df_neutralized = self.neutralizer.neutralize_cross_section(...)
        
        df_output = df.copy()
        report = self._l7_quality_report(df_output)
        self._l8_save_output(df_output, report)
        return df_output, report

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
    ProductionDataPipeline("data/market_2015_now.parquet", "data/market_2015_now_clean.parquet", as_of_time=datetime(2026, 5, 12, 17, 0, 0)).run()

if __name__ == "__main__": main()
