"""
Test Suite for DataValidator Provenance Validation

Tests cover:
1. Provenance metadata validation
2. dataset_version field validation
3. source field validation
4. adjustments_applied format validation
5. Sidecar checksum validation

Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 4
Author: OpenCode (L2-Backend Engineer Role 9)
Date: 2026-05-12
"""

import hashlib
import json
import pytest
from datetime import datetime
from pathlib import Path

import pandas as pd

from omega.data.validator import DataValidator, ValidationIssue


@pytest.fixture
def workspace_cache_dir():
    """Use workspace cache directory instead of tempfile."""
    import uuid
    cache_dir = Path(f".ly_state/test_cache/validator_provenance/{uuid.uuid4().hex[:8]}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return str(cache_dir)


class TestProvenanceValidation:
    """Test provenance metadata validation in DataValidator."""
    
    def test_validate_with_complete_provenance(self):
        """Test validation passes with complete provenance metadata."""
        validator = DataValidator(validate_provenance=True)
        
        rows = [
            {
                "symbol": "VNM",
                "timestamp": datetime(2026, 1, 1),
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 103.0,
                "volume": 1000000,
                "dataset_version": "1.0.0",
                "source": "vnstock_vci",
                "adjustments_applied": "[]"
            },
            {
                "symbol": "VNM",
                "timestamp": datetime(2026, 1, 2),
                "open": 103.0,
                "high": 107.0,
                "low": 102.0,
                "close": 106.0,
                "volume": 1200000,
                "dataset_version": "1.0.0",
                "source": "vnstock_vci",
                "adjustments_applied": "[]"
            }
        ]
        
        issues = validator.validate_rows(rows, symbol="VNM")
        
        # Filter only provenance-related issues
        provenance_issues = [i for i in issues if 'dataset_version' in i.rule or 'source' in i.rule or 'adjustments' in i.rule]
        assert len(provenance_issues) == 0
    
    def test_missing_dataset_version(self):
        """Test validation fails when dataset_version is missing."""
        validator = DataValidator(validate_provenance=True)
        
        rows = [
            {
                "symbol": "VNM",
                "timestamp": datetime(2026, 1, 1),
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 103.0,
                "volume": 1000000,
                "source": "vnstock_vci",
                "adjustments_applied": "[]"
                # Missing dataset_version
            }
        ]
        
        issues = validator.validate_rows(rows, symbol="VNM")
        
        # Check for missing_dataset_version issue
        dataset_version_issues = [i for i in issues if i.rule == "missing_dataset_version"]
        assert len(dataset_version_issues) > 0
        assert "dataset_version" in dataset_version_issues[0].message
    
    def test_missing_source(self):
        """Test validation fails when source is missing."""
        validator = DataValidator(validate_provenance=True)
        
        rows = [
            {
                "symbol": "VNM",
                "timestamp": datetime(2026, 1, 1),
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 103.0,
                "volume": 1000000,
                "dataset_version": "1.0.0",
                "adjustments_applied": "[]"
                # Missing source
            }
        ]
        
        issues = validator.validate_rows(rows, symbol="VNM")
        
        # Check for missing_source issue
        source_issues = [i for i in issues if i.rule == "missing_source"]
        assert len(source_issues) > 0
        assert "source" in source_issues[0].message
    
    def test_invalid_adjustments_format(self):
        """Test validation fails when adjustments_applied has invalid format."""
        validator = DataValidator(validate_provenance=True)
        
        rows = [
            {
                "symbol": "VNM",
                "timestamp": datetime(2026, 1, 1),
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 103.0,
                "volume": 1000000,
                "dataset_version": "1.0.0",
                "source": "vnstock_vci",
                "adjustments_applied": 123  # Invalid: should be string or list
            }
        ]
        
        issues = validator.validate_rows(rows, symbol="VNM")
        
        # Check for invalid_adjustments_format issue
        adj_issues = [i for i in issues if i.rule == "invalid_adjustments_format"]
        assert len(adj_issues) > 0
        assert "adjustments_applied" in adj_issues[0].message
    
    def test_valid_adjustments_as_string(self):
        """Test validation passes with adjustments_applied as JSON string."""
        validator = DataValidator(validate_provenance=True)
        
        rows = [
            {
                "symbol": "VNM",
                "timestamp": datetime(2026, 1, 1),
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 103.0,
                "volume": 1000000,
                "dataset_version": "1.0.0",
                "source": "vnstock_vci",
                "adjustments_applied": '["dividend:2026-01-05:2000"]'
            }
        ]
        
        issues = validator.validate_rows(rows, symbol="VNM")
        
        # No invalid_adjustments_format issues
        adj_issues = [i for i in issues if i.rule == "invalid_adjustments_format"]
        assert len(adj_issues) == 0
    
    def test_valid_adjustments_as_list(self):
        """Test validation passes with adjustments_applied as list."""
        validator = DataValidator(validate_provenance=True)
        
        rows = [
            {
                "symbol": "VNM",
                "timestamp": datetime(2026, 1, 1),
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 103.0,
                "volume": 1000000,
                "dataset_version": "1.0.0",
                "source": "vnstock_vci",
                "adjustments_applied": ["dividend:2026-01-05:2000"]
            }
        ]
        
        issues = validator.validate_rows(rows, symbol="VNM")
        
        # No invalid_adjustments_format issues
        adj_issues = [i for i in issues if i.rule == "invalid_adjustments_format"]
        assert len(adj_issues) == 0
    
    def test_provenance_validation_disabled(self):
        """Test that provenance validation can be disabled."""
        validator = DataValidator(validate_provenance=False)
        
        rows = [
            {
                "symbol": "VNM",
                "timestamp": datetime(2026, 1, 1),
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 103.0,
                "volume": 1000000
                # Missing all provenance fields
            }
        ]
        
        issues = validator.validate_rows(rows, symbol="VNM")
        
        # No provenance issues when validation is disabled
        provenance_issues = [i for i in issues if 'dataset_version' in i.rule or 'source' in i.rule]
        assert len(provenance_issues) == 0
    
    def test_multiple_provenance_issues(self):
        """Test detection of multiple provenance issues in same row."""
        validator = DataValidator(validate_provenance=True)
        
        rows = [
            {
                "symbol": "VNM",
                "timestamp": datetime(2026, 1, 1),
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 103.0,
                "volume": 1000000,
                "adjustments_applied": 999  # Invalid format
                # Missing dataset_version and source
            }
        ]
        
        issues = validator.validate_rows(rows, symbol="VNM")
        
        # Should have at least 3 provenance issues
        provenance_issues = [i for i in issues if any(x in i.rule for x in ['dataset_version', 'source', 'adjustments'])]
        assert len(provenance_issues) >= 3


class TestSidecarChecksumValidation:
    """Test sidecar checksum validation in DataValidator."""
    
    def test_validate_checksum_from_sidecar_success(self, workspace_cache_dir):
        """Test successful checksum validation from sidecar metadata."""
        validator = DataValidator(validate_provenance=True)
        
        # Create a test parquet file
        df = pd.DataFrame({
            'symbol': ['VNM', 'VNM'],
            'timestamp': [datetime(2026, 1, 1), datetime(2026, 1, 2)],
            'open': [100.0, 103.0],
            'high': [105.0, 107.0],
            'low': [99.0, 102.0],
            'close': [103.0, 106.0],
            'volume': [1000000, 1200000]
        })
        
        parquet_path = Path(workspace_cache_dir) / "VNM.parquet"
        df.to_parquet(parquet_path, index=False)
        
        # Ensure file handle is closed
        del df
        
        # Compute checksum
        sha256_hash = hashlib.sha256()
        with open(parquet_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256_hash.update(chunk)
        checksum = sha256_hash.hexdigest()
        
        # Create metadata sidecar
        metadata = {
            'checksum': checksum,
            'checksum_algorithm': 'sha256',
            'dataset_version': '1.0.0',
            'source': 'vnstock_vci'
        }
        
        metadata_path = Path(workspace_cache_dir) / "VNM.metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f)
        
        # Validate
        issues = validator._validate_checksum_from_sidecar(parquet_path, "VNM")
        
        # Should have no issues
        assert len(issues) == 0
    
    def test_missing_metadata_sidecar(self, workspace_cache_dir):
        """Test validation fails when .metadata.json is missing."""
        validator = DataValidator(validate_provenance=True)
        
        # Create a test parquet file without metadata
        df = pd.DataFrame({
            'symbol': ['VNM'],
            'timestamp': [datetime(2026, 1, 1)],
            'close': [100.0]
        })
        
        parquet_path = Path(workspace_cache_dir) / "VNM.parquet"
        df.to_parquet(parquet_path, index=False)
        
        # Ensure file handle is closed
        del df
        
        # Validate
        issues = validator._validate_checksum_from_sidecar(parquet_path, "VNM")
        
        # Should have missing_metadata_sidecar issue
        assert len(issues) == 1
        assert issues[0].rule == "missing_metadata_sidecar"
        assert ".metadata.json" in issues[0].message
    
    def test_invalid_metadata_json(self, workspace_cache_dir):
        """Test validation fails when .metadata.json is invalid JSON."""
        validator = DataValidator(validate_provenance=True)
        
        # Create a test parquet file
        df = pd.DataFrame({
            'symbol': ['VNM'],
            'timestamp': [datetime(2026, 1, 1)],
            'close': [100.0]
        })
        
        parquet_path = Path(workspace_cache_dir) / "VNM.parquet"
        df.to_parquet(parquet_path, index=False)
        
        # Ensure file handle is closed
        del df
        
        # Create invalid metadata sidecar
        metadata_path = Path(workspace_cache_dir) / "VNM.metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            f.write("{ invalid json }")
        
        # Validate
        issues = validator._validate_checksum_from_sidecar(parquet_path, "VNM")
        
        # Should have invalid_metadata_sidecar issue
        assert len(issues) == 1
        assert issues[0].rule == "invalid_metadata_sidecar"
    
    def test_missing_checksum_in_sidecar(self, workspace_cache_dir):
        """Test validation fails when checksum field is missing in metadata."""
        validator = DataValidator(validate_provenance=True)
        
        # Create a test parquet file
        df = pd.DataFrame({
            'symbol': ['VNM'],
            'timestamp': [datetime(2026, 1, 1)],
            'close': [100.0]
        })
        
        parquet_path = Path(workspace_cache_dir) / "VNM.parquet"
        df.to_parquet(parquet_path, index=False)
        
        # Ensure file handle is closed
        del df
        
        # Create metadata without checksum
        metadata = {
            'dataset_version': '1.0.0',
            'source': 'vnstock_vci'
        }
        
        metadata_path = Path(workspace_cache_dir) / "VNM.metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f)
        
        # Validate
        issues = validator._validate_checksum_from_sidecar(parquet_path, "VNM")
        
        # Should have missing_checksum_in_sidecar issue
        assert len(issues) == 1
        assert issues[0].rule == "missing_checksum_in_sidecar"
    
    def test_invalid_checksum_format(self, workspace_cache_dir):
        """Test validation fails when checksum format is invalid."""
        validator = DataValidator(validate_provenance=True)
        
        # Create a test parquet file
        df = pd.DataFrame({
            'symbol': ['VNM'],
            'timestamp': [datetime(2026, 1, 1)],
            'close': [100.0]
        })
        
        parquet_path = Path(workspace_cache_dir) / "VNM.parquet"
        df.to_parquet(parquet_path, index=False)
        
        # Ensure file handle is closed
        del df
        
        # Create metadata with invalid checksum (too short)
        metadata = {
            'checksum': 'abc123',  # Invalid: should be 64 chars
            'checksum_algorithm': 'sha256'
        }
        
        metadata_path = Path(workspace_cache_dir) / "VNM.metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f)
        
        # Validate
        issues = validator._validate_checksum_from_sidecar(parquet_path, "VNM")
        
        # Should have invalid_checksum_format issue
        assert len(issues) == 1
        assert issues[0].rule == "invalid_checksum_format"
        assert "64-char" in issues[0].message
    
    def test_checksum_mismatch(self, workspace_cache_dir):
        """Test validation fails when checksum doesn't match file."""
        validator = DataValidator(validate_provenance=True)
        
        # Create a test parquet file
        df = pd.DataFrame({
            'symbol': ['VNM'],
            'timestamp': [datetime(2026, 1, 1)],
            'close': [100.0]
        })
        
        parquet_path = Path(workspace_cache_dir) / "VNM.parquet"
        df.to_parquet(parquet_path, index=False)
        
        # Ensure file handle is closed
        del df
        
        # Create metadata with wrong checksum
        metadata = {
            'checksum': 'a' * 64,  # Wrong checksum
            'checksum_algorithm': 'sha256'
        }
        
        metadata_path = Path(workspace_cache_dir) / "VNM.metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f)
        
        # Validate
        issues = validator._validate_checksum_from_sidecar(parquet_path, "VNM")
        
        # Should have checksum_mismatch issue
        assert len(issues) == 1
        assert issues[0].rule == "checksum_mismatch"
        assert "mismatch" in issues[0].message.lower()
    
    def test_unsupported_checksum_algorithm(self, workspace_cache_dir):
        """Test validation fails when checksum algorithm is not sha256."""
        validator = DataValidator(validate_provenance=True)
        
        # Create a test parquet file
        df = pd.DataFrame({
            'symbol': ['VNM'],
            'timestamp': [datetime(2026, 1, 1)],
            'close': [100.0]
        })
        
        parquet_path = Path(workspace_cache_dir) / "VNM.parquet"
        df.to_parquet(parquet_path, index=False)
        
        # Ensure file handle is closed
        del df
        
        # Create metadata with unsupported algorithm
        metadata = {
            'checksum': 'a' * 64,
            'checksum_algorithm': 'md5'  # Unsupported
        }
        
        metadata_path = Path(workspace_cache_dir) / "VNM.metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f)
        
        # Validate
        issues = validator._validate_checksum_from_sidecar(parquet_path, "VNM")
        
        # Should have unsupported_checksum_algorithm issue
        assert len(issues) == 1
        assert issues[0].rule == "unsupported_checksum_algorithm"
        assert "sha256" in issues[0].message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
