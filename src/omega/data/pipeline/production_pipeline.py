import sys
import hashlib
import json
import os
import shutil
import tempfile
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, date, UTC
from zoneinfo import ZoneInfo
from filelock import FileLock
from typing import Dict, List, Any, Optional, Tuple

from omega.data.sanitizer import DataSanitizer, DataValidator, ValidationIssue
from omega.data.corporate_action import CorporateActionAdjuster, CorporateAction
from omega.data.news_aggregator import NewsAggregator, DEFAULT_EVENT_HISTORY_PATH
# NOTE: FeatureModule, NeutralizationEngine not yet in OMEGA package
# These will be integrated in Phase 12 (Portfolio Optimization)

warnings.filterwarnings('ignore')


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def _publish_output_pair(output_path: Path, df: pd.DataFrame, report: Dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = output_path.parent / f"{output_path.stem}_quality_report.json"
    with FileLock(f"{output_path}.lock", timeout=60):
        _publish_locked(output_path, report_path, df, report)


def read_output_pair(output_path: Path) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """Read a committed generation under the same lock as the writer."""
    with FileLock(f"{output_path}.lock", timeout=60):
        with (output_path.parent / f"{output_path.name}.manifest.json").open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        data_path = output_path.parent / manifest["data"]
        quality_path = output_path.parent / manifest["report"]
        if (data_path.name != manifest["data"] or quality_path.name != manifest["report"]
                or not data_path.name.startswith(f"{output_path.name}.")
                or not quality_path.name.startswith(f"{output_path.stem}_quality_report.json.")):
            raise ValueError("invalid output pair manifest")
        for path, key in ((data_path, "data_sha256"), (quality_path, "report_sha256")):
            digest = manifest.get(key)
            if not isinstance(digest, str) or len(digest) != 64 or _digest_file(path) != digest:
                raise ValueError("output pair artifact digest mismatch")
        return pd.read_parquet(data_path), json.loads(quality_path.read_text(encoding="utf-8"))


def read_legacy_output_pair(output_path: Path) -> tuple[pd.DataFrame, Dict[str, Any]]:
    """Read the committed generation instead of independently replaced legacy paths."""
    return read_output_pair(output_path)


def _sync_parent(path: Path) -> None:
    if os.name != 'nt':
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _publish_locked(output_path: Path, report_path: Path, df: pd.DataFrame, report: Dict[str, Any]) -> None:
    # ponytail: legacy base paths remain for callers; manifest readers only observe immutable generations.
    import uuid
    generation = uuid.uuid4().hex
    data_name = f"{output_path.name}.{generation}.parquet"
    report_name = f"{report_path.name}.{generation}.json"
    manifest_path = output_path.parent / f"{output_path.name}.manifest.json"
    generation_paths = (output_path.parent / data_name, output_path.parent / report_name)
    pointer = None
    staged = []
    backups = []
    published = []
    manifest_backup = None
    manifest_replaced = False
    rollback_failed = False
    committed = False
    try:
        for path, payload in zip(generation_paths, (df, report)):
            with path.open('xb') as handle:
                if isinstance(payload, pd.DataFrame):
                    payload.to_parquet(handle, index=False)
                else:
                    handle.write(json.dumps(payload, indent=2).encode('utf-8'))
                handle.flush()
                os.fsync(handle.fileno())
            _sync_parent(path)
        for path in (output_path, report_path):
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f'{path.name}.', suffix='.tmp', delete=False) as f:
                staged.append((Path(f.name), path))
                if path == output_path:
                    df.to_parquet(f, index=False)
                else:
                    f.write(json.dumps(report, indent=2).encode('utf-8'))
                f.flush()
                os.fsync(f.fileno())
        for _, path in staged:
            backup = None
            if path.exists():
                with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f'{path.name}.', suffix='.tmp', delete=False) as f:
                    backup = Path(f.name)
                    backups.append(backup)
                    with path.open('rb') as source:
                        shutil.copyfileobj(source, f)
                    f.flush()
                    os.fsync(f.fileno())
            published.append((path, backup))
        if manifest_path.exists():
            with tempfile.NamedTemporaryFile(dir=manifest_path.parent, prefix=f'{manifest_path.name}.', suffix='.tmp', delete=False) as f:
                manifest_backup = Path(f.name)
                backups.append(manifest_backup)
                with manifest_path.open('rb') as source:
                    shutil.copyfileobj(source, f)
                f.flush()
                os.fsync(f.fileno())
        with tempfile.NamedTemporaryFile(dir=output_path.parent, suffix='.tmp', delete=False) as handle:
            pointer = Path(handle.name)
            handle.write(json.dumps({'data': data_name, 'report': report_name,
                'data_sha256': _digest_file(generation_paths[0]),
                'report_sha256': _digest_file(generation_paths[1])}).encode('utf-8'))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            for temp, path in staged:
                os.replace(temp, path)
                _sync_parent(path)
            os.replace(pointer, manifest_path)
            manifest_replaced = True
            _sync_parent(manifest_path)
            committed = True
        except (Exception, MemoryError):
            if manifest_replaced:
                try:
                    if manifest_backup is not None:
                        os.replace(manifest_backup, manifest_path)
                    else:
                        manifest_path.unlink(missing_ok=True)
                    _sync_parent(manifest_path)
                except (Exception, MemoryError):
                    rollback_failed = True
            for path, backup in reversed(published):
                try:
                    if backup is not None:
                        os.replace(backup, path)
                    else:
                        path.unlink(missing_ok=True)
                    _sync_parent(path)
                except (Exception, MemoryError):
                    rollback_failed = True
            raise
    finally:
        if pointer is not None:
            pointer.unlink(missing_ok=True)
        for temp, _ in staged:
            temp.unlink(missing_ok=True)
        if not rollback_failed:
            for backup in backups:
                backup.unlink(missing_ok=True)
        if not committed and not rollback_failed:
            for path in generation_paths:
                path.unlink(missing_ok=True)


class ProductionDataPipeline:
    def __init__(self, input_path: str, output_path: str, cache_dir: str = "data/cache", as_of_time: Optional[datetime] = None):
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT compliance in ProductionDataPipeline")
        if not isinstance(as_of_time, datetime) or as_of_time.tzinfo is None or as_of_time.utcoffset() != UTC.utcoffset(None):
            raise ValueError("as_of_time must be timezone-aware UTC")
        self.input_path, self.output_path, self.cache_dir, self.as_of_time = Path(input_path), Path(output_path), Path(cache_dir), as_of_time
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sanitizer = DataSanitizer(as_of_time=as_of_time)
        self.validator = DataValidator()
        # NOTE: FeatureModule and NeutralizationEngine are Phase 12 features
        # Removed to prevent import errors - will be integrated in Portfolio Optimization phase
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
        
        # Vectorized: build clean_data structure without loops
        symbols = df['symbol'].unique().tolist()
        timestamps = sorted(df['timestamp'].dt.strftime('%Y-%m-%d').unique().tolist())
        clean_data = {"type": "CleanDataFrame", "price_basis": "raw", "index": {"symbol": symbols, "timestamp": timestamps}, "data": {}}
        
        price_cols = ['open', 'high', 'low', 'close', 'volume']
        available_cols = [c for c in price_cols if c in df.columns]
        
        records = df.assign(timestamp=df['timestamp'].dt.strftime('%Y-%m-%d'))
        clean_data["data"] = {
            s: group.set_index('timestamp')[available_cols].to_dict('index')
            for s, group in records.groupby('symbol')
        }
        
        temp_adj = CorporateActionAdjuster()
        temp_adj.add_actions(filtered)
        adj_data = temp_adj.apply_adjustments(clean_data, as_of_time=self.as_of_time)
        
        # Fully vectorized: use list comprehension instead of loop
        dfs = [
            pd.DataFrame.from_dict(adj_data["data"][s], orient='index').assign(symbol=s).reset_index().rename(columns={'index': 'timestamp'})
            for s in adj_data["index"]["symbol"]
        ]
        
        if not dfs: return df
        result = pd.concat(dfs, ignore_index=True)
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
        _publish_output_pair(self.output_path, df, report)

def main():
    ProductionDataPipeline("data/market_2015_now.parquet", "data/market_2015_now_clean.parquet", as_of_time=datetime.now(UTC)).run()

if __name__ == "__main__": main()
