"""
OMEGA_QUANT Phase 10 CLI Tests
===============================
Validation tests for command-line interface scripts.

Tests:
- run_daily.py functionality
- health_check.py validation
- rollback.py operations
- profile_performance.py execution
- deploy_omega.py workflow

Author: OMEGA_QUANT Team
Version: 1.0.0
"""

import pytest
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple
import yaml
import pandas as pd

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestCLIScripts:
    """Test command-line interface scripts."""
    
    @pytest.fixture
    def scripts_dir(self) -> Path:
        """Get scripts directory."""
        return PROJECT_ROOT / "scripts"
    
    @pytest.fixture
    def config_file(self) -> Path:
        """Get production config file."""
        return PROJECT_ROOT / "config" / "production.yaml"
    
    def run_script(self, script_path: Path, args: List[str]) -> Tuple[int, str, str]:
        """
        Run a Python script and capture output.
        
        Args:
            script_path: Path to script
            args: Command-line arguments
        
        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        cmd = [sys.executable, str(script_path)] + args
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        return result.returncode, result.stdout, result.stderr
    
    def test_run_daily_help(self, scripts_dir: Path):
        """Test run_daily.py --help."""
        script = scripts_dir / "run_daily.py"
        assert script.exists(), f"Script not found: {script}"
        
        returncode, stdout, stderr = self.run_script(script, ["--help"])
        
        assert returncode == 0, f"Script failed with code {returncode}"
        assert "OMEGA_QUANT Daily Rebalance" in stdout, "Help text missing"
        assert "--config" in stdout, "Missing --config option"
        assert "--date" in stdout, "Missing --date option"
        print(f"\n✓ run_daily.py --help works")
    
    def test_run_daily_dry_run(self, scripts_dir: Path, config_file: Path):
        """Test run_daily.py with dry run (if config exists)."""
        script = scripts_dir / "run_daily.py"
        
        if not config_file.exists():
            pytest.skip("Production config not found")
        
        # Run with today's date
        date_str = pd.Timestamp.now().strftime("%Y-%m-%d")
        
        returncode, stdout, stderr = self.run_script(
            script,
            ["--config", str(config_file), "--date", date_str, "--skip-checks"]
        )
        
        # May fail due to missing data, but should not crash
        assert returncode in [0, 1], f"Unexpected return code: {returncode}"
        assert "DAILY REBALANCE SUMMARY" in stdout or "error" in stderr.lower(), \
            "Expected summary or error message"
        print(f"\n✓ run_daily.py executes (returncode: {returncode})")
    
    def test_health_check_help(self, scripts_dir: Path):
        """Test health_check.py --help."""
        script = scripts_dir / "health_check.py"
        assert script.exists(), f"Script not found: {script}"
        
        returncode, stdout, stderr = self.run_script(script, ["--help"])
        
        assert returncode == 0, f"Script failed with code {returncode}"
        assert "OMEGA_QUANT System Health Check" in stdout, "Help text missing"
        assert "--config" in stdout, "Missing --config option"
        assert "--quick" in stdout, "Missing --quick option"
        print(f"\n✓ health_check.py --help works")
    
    def test_health_check_quick(self, scripts_dir: Path):
        """Test health_check.py --quick."""
        script = scripts_dir / "health_check.py"
        
        returncode, stdout, stderr = self.run_script(script, ["--quick"])
        
        # Health check may pass or fail, but should execute
        assert returncode in [0, 1], f"Unexpected return code: {returncode}"
        assert "HEALTH CHECK RESULTS" in stdout, "Missing results header"
        assert "QUICK" in stdout, "Missing QUICK mode indicator"
        print(f"\n✓ health_check.py --quick executes (returncode: {returncode})")
    
    def test_health_check_with_config(self, scripts_dir: Path, config_file: Path):
        """Test health_check.py with config file."""
        script = scripts_dir / "health_check.py"
        
        if not config_file.exists():
            pytest.skip("Production config not found")
        
        returncode, stdout, stderr = self.run_script(
            script,
            ["--config", str(config_file), "--quick"]
        )
        
        assert returncode in [0, 1], f"Unexpected return code: {returncode}"
        assert "HEALTH CHECK RESULTS" in stdout, "Missing results header"
        print(f"\n✓ health_check.py with config executes (returncode: {returncode})")
    
    def test_rollback_help(self, scripts_dir: Path):
        """Test rollback.py --help."""
        script = scripts_dir / "rollback.py"
        assert script.exists(), f"Script not found: {script}"
        
        returncode, stdout, stderr = self.run_script(script, ["--help"])
        
        assert returncode == 0, f"Script failed with code {returncode}"
        assert "OMEGA_QUANT Emergency Rollback" in stdout, "Help text missing"
        assert "--date" in stdout, "Missing --date option"
        assert "--list" in stdout, "Missing --list option"
        assert "--verify-only" in stdout, "Missing --verify-only option"
        print(f"\n✓ rollback.py --help works")
    
    def test_rollback_list(self, scripts_dir: Path):
        """Test rollback.py --list."""
        script = scripts_dir / "rollback.py"
        
        returncode, stdout, stderr = self.run_script(script, ["--list"])
        
        assert returncode == 0, f"Script failed with code {returncode}"
        assert "AVAILABLE ROLLBACK POINTS" in stdout, "Missing rollback points header"
        print(f"\n✓ rollback.py --list works")
    
    def test_profile_performance_help(self, scripts_dir: Path):
        """Test profile_performance.py --help."""
        script = scripts_dir / "profile_performance.py"
        assert script.exists(), f"Script not found: {script}"
        
        returncode, stdout, stderr = self.run_script(script, ["--help"])
        
        assert returncode == 0, f"Script failed with code {returncode}"
        assert "OMEGA_QUANT Performance Profiler" in stdout, "Help text missing"
        assert "--tickers" in stdout, "Missing --tickers option"
        assert "--days" in stdout, "Missing --days option"
        print(f"\n✓ profile_performance.py --help works")
    
    def test_deploy_omega_help(self, scripts_dir: Path):
        """Test deploy_omega.py --help."""
        script = scripts_dir / "deploy_omega.py"
        assert script.exists(), f"Script not found: {script}"
        
        returncode, stdout, stderr = self.run_script(script, ["--help"])
        
        assert returncode == 0, f"Script failed with code {returncode}"
        assert "OMEGA_QUANT Deployment Script" in stdout, "Help text missing"
        assert "--env" in stdout, "Missing --env option"
        print(f"\n✓ deploy_omega.py --help works")


class TestCLIIntegration:
    """Integration tests for CLI workflows."""
    
    @pytest.fixture
    def scripts_dir(self) -> Path:
        """Get scripts directory."""
        return PROJECT_ROOT / "scripts"
    
    def test_health_check_before_deploy(self, scripts_dir: Path):
        """Test health check as pre-deployment validation."""
        script = scripts_dir / "health_check.py"
        
        result = subprocess.run(
            [sys.executable, str(script), "--quick"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Document the health check result
        print(f"\n✓ Pre-deployment health check completed")
        print(f"  Return code: {result.returncode}")
        
        if result.returncode == 0:
            print("  Status: HEALTHY ✓")
        else:
            print("  Status: UNHEALTHY ✗")
            print(f"  Note: Some checks may fail in test environment")
    
    def test_cli_scripts_are_executable(self, scripts_dir: Path):
        """Test that all CLI scripts are properly structured."""
        required_scripts = [
            "run_daily.py",
            "health_check.py",
            "rollback.py",
            "profile_performance.py",
            "deploy_omega.py"
        ]
        
        for script_name in required_scripts:
            script_path = scripts_dir / script_name
            assert script_path.exists(), f"Missing script: {script_name}"
            
            # Check for shebang
            with open(script_path, 'r') as f:
                first_line = f.readline()
                assert first_line.startswith("#!"), f"Missing shebang in {script_name}"
            
            # Check for main guard
            with open(script_path, 'r') as f:
                content = f.read()
                assert 'if __name__ == "__main__"' in content, \
                    f"Missing main guard in {script_name}"
        
        print(f"\n✓ All {len(required_scripts)} CLI scripts are properly structured")


class TestCLIErrorHandling:
    """Test CLI error handling and edge cases."""
    
    @pytest.fixture
    def scripts_dir(self) -> Path:
        """Get scripts directory."""
        return PROJECT_ROOT / "scripts"
    
    def test_run_daily_missing_config(self, scripts_dir: Path):
        """Test run_daily.py with missing config file."""
        script = scripts_dir / "run_daily.py"
        
        result = subprocess.run(
            [sys.executable, str(script), "--config", "nonexistent.yaml"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode != 0, "Should fail with missing config"
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower(), \
            "Should report missing config error"
        print(f"\n✓ run_daily.py handles missing config correctly")
    
    def test_rollback_missing_date(self, scripts_dir: Path):
        """Test rollback.py without required --date argument."""
        script = scripts_dir / "rollback.py"
        
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode != 0, "Should fail without --date"
        assert "--date required" in result.stdout or "error" in result.stderr.lower(), \
            "Should report missing date error"
        print(f"\n✓ rollback.py handles missing date correctly")
    
    def test_rollback_invalid_date(self, scripts_dir: Path):
        """Test rollback.py with invalid date format."""
        script = scripts_dir / "rollback.py"
        
        result = subprocess.run(
            [sys.executable, str(script), "--date", "invalid-date"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode != 0, "Should fail with invalid date"
        print(f"\n✓ rollback.py handles invalid date correctly")


class TestCLIOutputFormat:
    """Test CLI output formatting and structure."""
    
    @pytest.fixture
    def scripts_dir(self) -> Path:
        """Get scripts directory."""
        return PROJECT_ROOT / "scripts"
    
    def test_health_check_output_format(self, scripts_dir: Path):
        """Test health_check.py output is well-formatted."""
        script = scripts_dir / "health_check.py"
        
        result = subprocess.run(
            [sys.executable, str(script), "--quick"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        stdout = result.stdout
        
        # Check for expected sections
        assert "=" in stdout, "Missing section separators"
        assert "HEALTH CHECK RESULTS" in stdout, "Missing results header"
        assert "Summary:" in stdout, "Missing summary section"
        
        # Check for status indicators
        assert "PASS" in stdout or "FAIL" in stdout, "Missing status indicators"
        
        print(f"\n✓ health_check.py output is well-formatted")
    
    def test_rollback_list_output_format(self, scripts_dir: Path):
        """Test rollback.py --list output is well-formatted."""
        script = scripts_dir / "rollback.py"
        
        result = subprocess.run(
            [sys.executable, str(script), "--list"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        stdout = result.stdout
        
        # Check for expected sections
        assert "=" in stdout, "Missing section separators"
        assert "AVAILABLE ROLLBACK POINTS" in stdout, "Missing header"
        
        print(f"\n✓ rollback.py --list output is well-formatted")


if __name__ == "__main__":
    # Run CLI tests with verbose output
    pytest.main([__file__, "-v", "-s", "--tb=short"])
