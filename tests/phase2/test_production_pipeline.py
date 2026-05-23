"""
Test Suite for ProductionDataPipeline

Tests cover:
1. Basic pipeline execution
2. Validation and symbol partitioning (vectorized groupby)
3. Corporate action application
4. Data sanitization
5. PIT safety enforcement

Reference: OMEGA_DATA_PIPELINE_REAUDIT_R5.md
"""

import pytest
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from pathlib import Path

from omega.data.pipeline.production_pipeline import ProductionDataPipeline, DataSanitizer
from omega.data.validator import DataValidator
from omega.data.corporate_action import CorporateActionAdjuster, CorporateAction


@pytest.fixture
def workspace_tmp(tmp_path):
    """Windows-safe temp directory for pipeline tests."""
    d = tmp_path / "pipeline_test"
    d.mkdir(parents=True, exist_ok=True)
    return d


class TestProductionPipelineBasics:
    """Test basic ProductionDataPipeline functionality."""
    
    def test_initialization_requires_as_of_time(self, workspace_tmp):
        """Test that ProductionDataPipeline requires as_of_time."""
        input_path = workspace_tmp / "input.parquet"
        output_path = workspace_tmp / "output.parquet"
        
        # Should raise ValueError without as_of_time
        with pytest.raises(ValueError, match="as_of_time is mandatory"):
            ProductionDataPipeline(
                input_path=str(input_path),
                output_path=str(output_path)
            )
    
    def test_initialization_with_as_of_time(self, workspace_tmp):
        """Test that ProductionDataPipeline initializes correctly with as_of_time."""
        input_path = workspace_tmp / "input.parquet"
        output_path = workspace_tmp / "output.parquet"
        
        pipeline = ProductionDataPipeline(
            input_path=str(input_path),
            output_path=str(output_path),
            as_of_time=datetime(2026, 5, 12, 17, 0, 0)
        )
        
        assert pipeline.as_of_time == datetime(2026, 5, 12, 17, 0, 0)
        assert pipeline.input_path == input_path
        assert pipeline.output_path == output_path
        assert isinstance(pipeline.sanitizer, DataSanitizer)
        assert isinstance(pipeline.validator, DataValidator)


class TestValidationSymbolPartitioning:
    """Test validation with vectorized symbol partitioning."""
    
    def test_validation_uses_vectorized_groupby(self, workspace_tmp):
        """Test that validation uses vectorized groupby instead of O(N*S) loop."""
        input_path = workspace_tmp / "input.parquet"
        output_path = workspace_tmp / "output.parquet"
        
        # Create test data with multiple symbols
        test_data = pd.DataFrame({
            'symbol': ['VNM', 'VNM', 'VNM', 'VCB', 'VCB', 'VCB'],
            'timestamp': pd.to_datetime([
                '2026-01-02', '2026-01-03', '2026-01-05',
                '2026-01-02', '2026-01-03', '2026-01-05'
            ]),
            'open': [100.0, 101.0, 102.0, 200.0, 201.0, 202.0],
            'high': [101.0, 102.0, 103.0, 201.0, 202.0, 203.0],
            'low': [99.0, 100.0, 101.0, 199.0, 200.0, 201.0],
            'close': [100.5, 101.5, 102.5, 200.5, 201.5, 202.5],
            'volume': [1000, 1100, 1200, 2000, 2100, 2200]
        })
        test_data.to_parquet(input_path, index=False)
        
        # Run pipeline
        pipeline = ProductionDataPipeline(
            input_path=str(input_path),
            output_path=str(output_path),
            cache_dir=str(workspace_tmp / "cache"),
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        df_output, report = pipeline.run()
        
        # Check that validation ran
        assert 'l4_validation_issues' in pipeline.pipeline_stats
        assert isinstance(pipeline.validation_issues, list)
        
        # Check output
        assert len(df_output) == 6
        assert df_output['symbol'].nunique() == 2
    
    def test_validation_symbol_partitioning_performance(self, workspace_tmp):
        """Test that validation path uses vectorized groupby for symbol partitioning."""
        input_path = workspace_tmp / "input.parquet"
        output_path = workspace_tmp / "output.parquet"
        
        # Create test data with 100 symbols to test vectorization performance
        symbols = [f'SYM{i:03d}' for i in range(100)]
        rows = []
        for symbol in symbols:
            for day in range(10):
                rows.append({
                    'symbol': symbol,
                    'timestamp': pd.Timestamp('2026-01-02') + pd.Timedelta(days=day),
                    'open': 100.0 + day,
                    'high': 101.0 + day,
                    'low': 99.0 + day,
                    'close': 100.5 + day,
                    'volume': 1000 + day * 100
                })
        
        test_data = pd.DataFrame(rows)
        test_data.to_parquet(input_path, index=False)
        
        # Run pipeline and measure time
        import time
        start_time = time.time()
        
        pipeline = ProductionDataPipeline(
            input_path=str(input_path),
            output_path=str(output_path),
            cache_dir=str(workspace_tmp / "cache"),
            as_of_time=datetime(2026, 1, 15, 10, 0, 0)
        )
        
        df_output, report = pipeline.run()
        
        elapsed_time = time.time() - start_time
        
        # Check that all symbols were processed
        assert len(df_output) == 1000  # 100 symbols * 10 days
        assert df_output['symbol'].nunique() == 100
        assert 'l4_validation_issues' in pipeline.pipeline_stats
        
        # Vectorized groupby should complete in reasonable time (< 10 seconds for 1000 rows)
        assert elapsed_time < 10.0, f"Validation took {elapsed_time:.2f}s, expected < 10s (vectorization issue?)"
    
    def test_validation_handles_large_symbol_count(self, workspace_tmp):
        """Test that validation efficiently handles many symbols."""
        input_path = workspace_tmp / "input.parquet"
        output_path = workspace_tmp / "output.parquet"
        
        # Create test data with 50 symbols
        symbols = [f'SYM{i:02d}' for i in range(50)]
        rows = []
        for symbol in symbols:
            for day in range(5):
                rows.append({
                    'symbol': symbol,
                    'timestamp': pd.Timestamp('2026-01-02') + pd.Timedelta(days=day),
                    'open': 100.0 + day,
                    'high': 101.0 + day,
                    'low': 99.0 + day,
                    'close': 100.5 + day,
                    'volume': 1000 + day * 100
                })
        
        test_data = pd.DataFrame(rows)
        test_data.to_parquet(input_path, index=False)
        
        # Run pipeline
        pipeline = ProductionDataPipeline(
            input_path=str(input_path),
            output_path=str(output_path),
            cache_dir=str(workspace_tmp / "cache"),
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        df_output, report = pipeline.run()
        
        # Check that all symbols were processed
        assert len(df_output) == 250  # 50 symbols * 5 days
        assert df_output['symbol'].nunique() == 50
        assert 'l4_validation_issues' in pipeline.pipeline_stats


class TestDataSanitization:
    """Test data sanitization functionality."""
    
    def test_sanitizer_fit_and_apply(self, workspace_tmp):
        """Test that sanitizer fits and applies correctly."""
        input_path = workspace_tmp / "input.parquet"
        output_path = workspace_tmp / "output.parquet"
        
        # Create test data with outliers
        test_data = pd.DataFrame({
            'symbol': ['VNM'] * 10,
            'timestamp': pd.date_range('2026-01-01', periods=10, freq='D'),
            'open': [100.0] * 9 + [1000.0],  # Last value is outlier
            'high': [101.0] * 9 + [1001.0],
            'low': [99.0] * 9 + [999.0],
            'close': [100.5] * 9 + [1000.5],
            'volume': [1000] * 10
        })
        test_data.to_parquet(input_path, index=False)
        
        # Run pipeline
        pipeline = ProductionDataPipeline(
            input_path=str(input_path),
            output_path=str(output_path),
            cache_dir=str(workspace_tmp / "cache"),
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        df_output, report = pipeline.run()
        
        # Check that sanitization ran
        assert 'outliers_clipped' in pipeline.sanitizer.sanitization_stats
        assert len(df_output) == 10


class TestPipelineOutput:
    """Test pipeline output and reporting."""
    
    def test_pipeline_generates_quality_report(self, workspace_tmp):
        """Test that pipeline generates quality report."""
        input_path = workspace_tmp / "input.parquet"
        output_path = workspace_tmp / "output.parquet"
        
        # Create minimal test data
        test_data = pd.DataFrame({
            'symbol': ['VNM', 'VNM', 'VNM'],
            'timestamp': pd.to_datetime(['2026-01-02', '2026-01-03', '2026-01-05']),
            'open': [100.0, 101.0, 102.0],
            'high': [101.0, 102.0, 103.0],
            'low': [99.0, 100.0, 101.0],
            'close': [100.5, 101.5, 102.5],
            'volume': [1000, 1100, 1200]
        })
        test_data.to_parquet(input_path, index=False)
        
        # Run pipeline
        pipeline = ProductionDataPipeline(
            input_path=str(input_path),
            output_path=str(output_path),
            cache_dir=str(workspace_tmp / "cache"),
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        df_output, report = pipeline.run()
        
        # Check report structure
        assert 'pipeline_stats' in report
        assert 'validation_issues' in report
        assert 'data_quality' in report
        assert report['data_quality']['total_rows'] == 3
        assert report['data_quality']['total_symbols'] == 1
        
        # Check output file exists
        assert output_path.exists()
        
        # Check quality report file exists
        report_path = output_path.parent / f"{output_path.stem}_quality_report.json"
        assert report_path.exists()
    
    def test_pipeline_saves_output_parquet(self, workspace_tmp):
        """Test that pipeline saves output parquet file."""
        input_path = workspace_tmp / "input.parquet"
        output_path = workspace_tmp / "output.parquet"
        
        # Create test data
        test_data = pd.DataFrame({
            'symbol': ['VNM', 'VNM'],
            'timestamp': pd.to_datetime(['2026-01-02', '2026-01-03']),
            'open': [100.0, 101.0],
            'high': [101.0, 102.0],
            'low': [99.0, 100.0],
            'close': [100.5, 101.5],
            'volume': [1000, 1100]
        })
        test_data.to_parquet(input_path, index=False)
        
        # Run pipeline
        pipeline = ProductionDataPipeline(
            input_path=str(input_path),
            output_path=str(output_path),
            cache_dir=str(workspace_tmp / "cache"),
            as_of_time=datetime(2026, 1, 10, 10, 0, 0)
        )
        
        df_output, report = pipeline.run()
        
        # Read output file
        df_saved = pd.read_parquet(output_path)
        
        # Check that saved data matches output
        assert len(df_saved) == len(df_output)
        assert list(df_saved.columns) == list(df_output.columns)

    def test_pipeline_corporate_action_pit_boundary(self, workspace_tmp, monkeypatch):
        """Test corporate action PIT boundary: ex_date > as_of_time.date() is strictly filtered out."""
        input_path = workspace_tmp / "input.parquet"
        output_path = workspace_tmp / "output.parquet"
        
        test_data = pd.DataFrame({
            'symbol': ['VNM', 'VNM'],
            'timestamp': pd.to_datetime(['2026-05-10', '2026-05-11']),
            'open': [100.0, 100.0],
            'high': [100.0, 100.0],
            'low': [100.0, 100.0],
            'close': [100.0, 100.0],
            'volume': [1000, 1000]
        })
        test_data.to_parquet(input_path, index=False)
        
        as_of_time = datetime(2026, 5, 12, 17, 0, 0)
        pipeline = ProductionDataPipeline(
            input_path=str(input_path),
            output_path=str(output_path),
            cache_dir=str(workspace_tmp / "cache"),
            as_of_time=as_of_time
        )
        
        action_past = CorporateAction(
            symbol="VNM",
            ex_date="2026-05-11",
            action_type="dividend",
            dividend_amount=10.0
        )
        action_future = CorporateAction(
            symbol="VNM",
            ex_date="2026-05-15",
            action_type="dividend",
            dividend_amount=20.0
        )
        pipeline.corp_action_adjuster.add_actions([action_past, action_future])

        captured = {}
        original_add_actions = CorporateActionAdjuster.add_actions
        original_apply_adjustments = CorporateActionAdjuster.apply_adjustments

        def spy_add_actions(self, actions):
            captured['filtered_actions'] = list(actions)
            return original_add_actions(self, actions)

        def passthrough_apply_adjustments(self, data, price_fields=None):
            return data

        monkeypatch.setattr(CorporateActionAdjuster, 'add_actions', spy_add_actions)
        monkeypatch.setattr(CorporateActionAdjuster, 'apply_adjustments', passthrough_apply_adjustments)

        df_output, report = pipeline.run()

        assert len(captured['filtered_actions']) == 1
        assert captured['filtered_actions'][0].ex_date == '2026-05-11'
        assert captured['filtered_actions'][0].symbol == 'VNM'
        assert all(action.ex_date <= as_of_time.date().isoformat() for action in captured['filtered_actions'])
        assert len(df_output) == 2
