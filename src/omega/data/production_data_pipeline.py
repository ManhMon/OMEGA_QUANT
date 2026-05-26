import sys
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Tuple

from omega.data.data_validator import DataValidator, ValidationIssue
from omega.quant.feature_factory import FeatureFactory
from omega.quant.neutralization_engine import NeutralizationEngine
from omega.data.corporate_action import CorporateActionAdjuster, CorporateAction

warnings.filterwarnings('ignore')

class DataSanitizer:
    def __init__(self, max_fill_days: int = 3, outlier_sigma: float = 3.0, min_price: float = 0.01):
        self.max_fill_days = max_fill_days
        self.outlier_sigma = outlier_sigma
        self.min_price = min_price
        self.fitted_stats: Dict[str, Dict[str, float]] = {}
        self.sanitization_stats: Dict[str, int] = {}

    def fit(self, df: pd.DataFrame, symbol_col: str = 'ticker', date_col: str = 'timestamp') -> None:
        print(f"  [DataSanitizer] Fitting on {len(df):,} rows, {df[symbol_col].nunique()} symbols...")
        for sym in df[symbol_col].unique():
            sym_df = df[df[symbol_col] == sym].copy()
            stats = {}
            for col in ['open', 'high', 'low', 'close']:
                if col in sym_df.columns:
                    values = sym_df[col].dropna()
                    if len(values) > 0:
                        mean = values.mean()
                        std = values.std()
                        stats[f'{col}_lower'] = max(self.min_price, mean - self.outlier_sigma * std)
                        stats[f'{col}_upper'] = mean + self.outlier_sigma * std
            self.fitted_stats[sym] = stats
        print(f"  [DataSanitizer] Fitted on {len(self.fitted_stats)} symbols")

    def apply(self, df: pd.DataFrame, symbol_col: str = 'ticker', date_col: str = 'timestamp') -> pd.DataFrame:
        print(f"  [DataSanitizer] Applying sanitization to {len(df):,} rows...")
        df_clean = df.copy()
        self.sanitization_stats = {'outliers_clipped': 0, 'missing_filled': 0, 'ohlc_fixed': 0}
        for sym in df_clean[symbol_col].unique():
            mask = df_clean[symbol_col] == sym
            sym_df = df_clean[mask].copy()
            stats = self.fitted_stats.get(sym, {})
            if not stats:
                for col in ['open', 'high', 'low', 'close']:
                    if col in sym_df.columns:
                        values = sym_df[col].dropna()
                        if len(values) > 0:
                            mean = values.mean()
                            std = values.std()
                            stats[f'{col}_lower'] = max(self.min_price, mean - self.outlier_sigma * std)
                            stats[f'{col}_upper'] = mean + self.outlier_sigma * std
            for col in ['open', 'high', 'low', 'close']:
                if col in sym_df.columns and f'{col}_lower' in stats:
                    before = sym_df[col].copy()
                    sym_df[col] = sym_df[col].clip(lower=stats[f'{col}_lower'], upper=stats[f'{col}_upper'])
                    self.sanitization_stats['outliers_clipped'] += (before != sym_df[col]).sum()
            sym_df = sym_df.sort_values(date_col)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in sym_df.columns:
                    before_na = sym_df[col].isna().sum()
                    sym_df[col] = sym_df[col].ffill(limit=self.max_fill_days)
                    self.sanitization_stats['missing_filled'] += (before_na - sym_df[col].isna().sum())
            if all(c in sym_df.columns for c in ['open', 'high', 'low', 'close']):
                before_h, before_l = sym_df['high'].copy(), sym_df['low'].copy()
                sym_df['high'] = sym_df[['high', 'open', 'close']].max(axis=1)
                sym_df['low'] = sym_df[['low', 'open', 'close']].min(axis=1)
                self.sanitization_stats['ohlc_fixed'] += ((before_h != sym_df['high']) | (before_l != sym_df['low'])).sum()
            df_clean.loc[mask, sym_df.columns] = sym_df
        print(f"  [DataSanitizer] Sanitization complete: {self.sanitization_stats}")
        return df_clean

class ProductionDataPipeline:
    def __init__(self, input_path: str, output_path: str, cache_dir: str = "V21_QUANT/data/cache", as_of_time: Optional[datetime] = None):
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT compliance in ProductionDataPipeline")
        self.input_path, self.output_path, self.cache_dir, self.as_of_time = Path(input_path), Path(output_path), Path(cache_dir), as_of_time
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sanitizer = DataSanitizer()
        self.validator = DataValidator()
        self.feature_module = FeatureFactory()
        self.neutralizer = NeutralizationEngine()
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
        df = self.sanitizer.apply(df, symbol_col='symbol')
        self.validation_issues = self.validator.validate(df, symbol_col='symbol')
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
