"""
OMEGA_QUANT Phase 10 Configuration Tests
=========================================
Validation tests for production configuration files.

Tests:
- production.yaml structure and validity
- .env.example completeness
- Configuration parameter ranges
- Required fields presence
- Type validation
- Security settings

Author: OMEGA_QUANT Team
Version: 1.0.0
"""

import pytest
import yaml
from pathlib import Path
from typing import Dict, Any
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestProductionConfig:
    """Test production configuration file."""
    
    @pytest.fixture
    def config_path(self) -> Path:
        """Get production config path."""
        return PROJECT_ROOT / "config" / "production.yaml"
    
    @pytest.fixture
    def config(self, config_path: Path) -> Dict[str, Any]:
        """Load production configuration."""
        assert config_path.exists(), f"Config not found: {config_path}"
        
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def test_config_file_exists(self, config_path: Path):
        """Test that production.yaml exists."""
        assert config_path.exists(), "production.yaml not found"
        print(f"\n✓ production.yaml exists at {config_path}")
    
    def test_config_is_valid_yaml(self, config_path: Path):
        """Test that production.yaml is valid YAML."""
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        assert isinstance(config, dict), "Config should be a dictionary"
        assert len(config) > 0, "Config should not be empty"
        print(f"\n✓ production.yaml is valid YAML with {len(config)} top-level keys")
    
    def test_required_sections_present(self, config: Dict[str, Any]):
        """Test that all required sections are present."""
        required_sections = [
            "data",
            "portfolio",
            "risk",
            "execution",
            "logging",
            "monitoring",
            "backup",
            "performance",
            "security"
        ]
        
        for section in required_sections:
            assert section in config, f"Missing required section: {section}"
        
        print(f"\n✓ All {len(required_sections)} required sections present")
    
    def test_data_section_valid(self, config: Dict[str, Any]):
        """Test data section configuration."""
        data = config.get("data", {})
        
        # Check required fields
        assert "source" in data, "Missing data.source"
        assert "pit_safety" in data, "Missing data.pit_safety"
        
        # Check PIT safety settings
        pit = data["pit_safety"]
        assert pit.get("enabled") is True, "PIT safety must be enabled in production"
        assert pit.get("strict_mode") is True, "PIT strict mode must be enabled"
        assert pit.get("lag_days", 0) >= 1, "PIT lag must be at least 1 day"
        
        print(f"\n✓ Data section valid (PIT safety: enabled, lag: {pit.get('lag_days')} days)")
    
    def test_portfolio_section_valid(self, config: Dict[str, Any]):
        """Test portfolio section configuration."""
        portfolio = config.get("portfolio", {})
        
        # Check required fields
        assert "initial_capital" in portfolio, "Missing portfolio.initial_capital"
        assert "max_positions" in portfolio, "Missing portfolio.max_positions"
        assert "min_position_size" in portfolio, "Missing portfolio.min_position_size"
        assert "max_position_size" in portfolio, "Missing portfolio.max_position_size"
        
        # Validate ranges
        assert portfolio["initial_capital"] > 0, "Initial capital must be positive"
        assert portfolio["max_positions"] > 0, "Max positions must be positive"
        assert 0 < portfolio["min_position_size"] < 1, "Min position size must be between 0 and 1"
        assert 0 < portfolio["max_position_size"] < 1, "Max position size must be between 0 and 1"
        assert portfolio["min_position_size"] < portfolio["max_position_size"], \
            "Min position size must be less than max"
        
        print(f"\n✓ Portfolio section valid (capital: ${portfolio['initial_capital']:,.0f}, max positions: {portfolio['max_positions']})")
    
    def test_risk_section_valid(self, config: Dict[str, Any]):
        """Test risk section configuration."""
        risk = config.get("risk", {})
        
        # Check required fields
        assert "max_portfolio_volatility" in risk, "Missing risk.max_portfolio_volatility"
        assert "max_drawdown" in risk, "Missing risk.max_drawdown"
        assert "max_leverage" in risk, "Missing risk.max_leverage"
        
        # Validate ranges
        assert 0 < risk["max_portfolio_volatility"] <= 1.0, \
            "Max portfolio volatility must be between 0 and 1"
        assert 0 < risk["max_drawdown"] <= 1.0, \
            "Max drawdown must be between 0 and 1"
        assert risk["max_leverage"] >= 1.0, "Max leverage must be >= 1.0"
        
        # Production should have conservative leverage
        assert risk["max_leverage"] <= 2.0, \
            "Production leverage should be conservative (<= 2.0)"
        
        print(f"\n✓ Risk section valid (vol: {risk['max_portfolio_volatility']:.1%}, dd: {risk['max_drawdown']:.1%}, lev: {risk['max_leverage']:.1f}x)")
    
    def test_execution_section_valid(self, config: Dict[str, Any]):
        """Test execution section configuration."""
        execution = config.get("execution", {})
        
        # Check required fields
        assert "broker" in execution, "Missing execution.broker"
        assert "dry_run" in execution, "Missing execution.dry_run"
        assert "order_type" in execution, "Missing execution.order_type"
        
        # Validate broker
        valid_brokers = ["mock", "interactive_brokers", "alpaca"]
        assert execution["broker"] in valid_brokers, \
            f"Invalid broker: {execution['broker']}"
        
        # Validate order type
        valid_order_types = ["market", "limit", "stop"]
        assert execution["order_type"] in valid_order_types, \
            f"Invalid order type: {execution['order_type']}"
        
        print(f"\n✓ Execution section valid (broker: {execution['broker']}, dry_run: {execution['dry_run']})")
    
    def test_logging_section_valid(self, config: Dict[str, Any]):
        """Test logging section configuration."""
        logging = config.get("logging", {})
        
        # Check required fields
        assert "level" in logging, "Missing logging.level"
        assert "format" in logging, "Missing logging.format"
        assert "audit" in logging, "Missing logging.audit"
        
        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        assert logging["level"] in valid_levels, f"Invalid log level: {logging['level']}"
        
        # Audit logging must be enabled in production
        assert logging["audit"].get("enabled") is True, \
            "Audit logging must be enabled in production"
        
        print(f"\n✓ Logging section valid (level: {logging['level']}, audit: enabled)")
    
    def test_monitoring_section_valid(self, config: Dict[str, Any]):
        """Test monitoring section configuration."""
        monitoring = config.get("monitoring", {})
        
        # Check required fields
        assert "health_check" in monitoring, "Missing monitoring.health_check"
        assert "metrics" in monitoring, "Missing monitoring.metrics"
        assert "alerts" in monitoring, "Missing monitoring.alerts"
        
        # Health checks should be enabled
        assert monitoring["health_check"].get("enabled") is True, \
            "Health checks must be enabled in production"
        
        print(f"\n✓ Monitoring section valid (health_check: enabled)")
    
    def test_backup_section_valid(self, config: Dict[str, Any]):
        """Test backup section configuration."""
        backup = config.get("backup", {})
        
        # Check required fields
        assert "enabled" in backup, "Missing backup.enabled"
        assert "retention_days" in backup, "Missing backup.retention_days"
        
        # Backups should be enabled in production
        assert backup["enabled"] is True, "Backups must be enabled in production"
        assert backup["retention_days"] >= 7, \
            "Backup retention should be at least 7 days"
        
        print(f"\n✓ Backup section valid (enabled: True, retention: {backup['retention_days']} days)")
    
    def test_performance_section_valid(self, config: Dict[str, Any]):
        """Test performance section configuration."""
        performance = config.get("performance", {})
        
        # Check required fields
        assert "num_workers" in performance, "Missing performance.num_workers"
        assert "vectorization" in performance, "Missing performance.vectorization"
        
        # Vectorization must be enabled
        assert performance["vectorization"] is True, \
            "Vectorization must be enabled for performance"
        
        # Reasonable worker count
        assert 1 <= performance["num_workers"] <= 16, \
            "Worker count should be between 1 and 16"
        
        print(f"\n✓ Performance section valid (workers: {performance['num_workers']}, vectorization: enabled)")
    
    def test_security_section_valid(self, config: Dict[str, Any]):
        """Test security section configuration."""
        security = config.get("security", {})
        
        # Check required fields
        assert "api_key_required" in security, "Missing security.api_key_required"
        
        # API key should be required in production
        assert security["api_key_required"] is True, \
            "API key must be required in production"
        
        print(f"\n✓ Security section valid (api_key_required: True)")
    
    def test_compliance_section_valid(self, config: Dict[str, Any]):
        """Test compliance section configuration."""
        compliance = config.get("compliance", {})
        
        if compliance:
            # Check audit trail
            if "audit_trail" in compliance:
                audit = compliance["audit_trail"]
                assert audit.get("enabled") is True, \
                    "Audit trail must be enabled for compliance"
                assert audit.get("retention_years", 0) >= 7, \
                    "Audit retention must be at least 7 years (SEC requirement)"
            
            print(f"\n✓ Compliance section valid")
    
    def test_no_hardcoded_secrets(self, config_path: Path):
        """Test that no secrets are hardcoded in config."""
        with open(config_path, 'r') as f:
            content = f.read().lower()
        
        # Check for common secret patterns
        forbidden_patterns = [
            "password:",
            "api_key:",
            "secret:",
            "token:",
            "credential:"
        ]
        
        for pattern in forbidden_patterns:
            if pattern in content:
                # Check if it's set to null or placeholder
                lines = content.split('\n')
                for line in lines:
                    if pattern in line:
                        assert "null" in line or "your_" in line or "[]" in line, \
                            f"Potential hardcoded secret found: {line.strip()}"
        
        print(f"\n✓ No hardcoded secrets detected")


class TestEnvExample:
    """Test .env.example file."""
    
    @pytest.fixture
    def env_example_path(self) -> Path:
        """Get .env.example path."""
        return PROJECT_ROOT / ".env.example"
    
    def test_env_example_exists(self, env_example_path: Path):
        """Test that .env.example exists."""
        assert env_example_path.exists(), ".env.example not found"
        print(f"\n✓ .env.example exists at {env_example_path}")
    
    def test_env_example_has_required_vars(self, env_example_path: Path):
        """Test that .env.example has required environment variables."""
        with open(env_example_path, 'r') as f:
            content = f.read()
        
        required_vars = [
            "OMEGA_ENVIRONMENT",
            "OMEGA_LOG_LEVEL",
            "MARKET_DATA_API_KEY",
            "OMEGA_BROKER",
            "ALERT_EMAIL_ENABLED",
            "AWS_ACCESS_KEY_ID",
            "OMEGA_API_KEY"
        ]
        
        for var in required_vars:
            assert var in content, f"Missing required variable: {var}"
        
        print(f"\n✓ All {len(required_vars)} required environment variables present")
    
    def test_env_example_has_placeholders(self, env_example_path: Path):
        """Test that .env.example uses placeholders, not real values."""
        with open(env_example_path, 'r') as f:
            content = f.read()
        
        # Should contain placeholder text
        assert "your_" in content.lower() or "placeholder" in content.lower(), \
            ".env.example should use placeholders"
        
        print(f"\n✓ .env.example uses placeholders")
    
    def test_env_example_has_documentation(self, env_example_path: Path):
        """Test that .env.example has documentation comments."""
        with open(env_example_path, 'r') as f:
            lines = f.readlines()
        
        comment_lines = [line for line in lines if line.strip().startswith('#')]
        
        assert len(comment_lines) > 10, \
            ".env.example should have documentation comments"
        
        print(f"\n✓ .env.example has {len(comment_lines)} documentation lines")


class TestConfigIntegration:
    """Integration tests for configuration."""
    
    def test_config_can_be_loaded_by_application(self):
        """Test that config can be loaded by application code."""
        config_path = PROJECT_ROOT / "config" / "production.yaml"
        
        if not config_path.exists():
            pytest.skip("production.yaml not found")
        
        # Try loading with yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Verify it's a valid dict
        assert isinstance(config, dict), "Config should be a dictionary"
        assert len(config) > 0, "Config should not be empty"
        
        print(f"\n✓ Config can be loaded by application")
    
    def test_config_values_are_production_ready(self):
        """Test that config values are appropriate for production."""
        config_path = PROJECT_ROOT / "config" / "production.yaml"
        
        if not config_path.exists():
            pytest.skip("production.yaml not found")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Check critical production settings
        checks = []
        
        # PIT safety must be enabled
        if "data" in config and "pit_safety" in config["data"]:
            checks.append(config["data"]["pit_safety"].get("enabled") is True)
        
        # Audit logging must be enabled
        if "logging" in config and "audit" in config["logging"]:
            checks.append(config["logging"]["audit"].get("enabled") is True)
        
        # Backups must be enabled
        if "backup" in config:
            checks.append(config["backup"].get("enabled") is True)
        
        # Vectorization must be enabled
        if "performance" in config:
            checks.append(config["performance"].get("vectorization") is True)
        
        assert all(checks), "Some production-critical settings are not enabled"
        print(f"\n✓ Config values are production-ready ({len(checks)} checks passed)")


if __name__ == "__main__":
    # Run config tests with verbose output
    pytest.main([__file__, "-v", "-s", "--tb=short"])
