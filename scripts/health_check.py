#!/usr/bin/env python3
"""
OMEGA_QUANT System Health Check
================================
Comprehensive health validation for production deployment.

USAGE:
    python scripts/health_check.py --config config/production.yaml
    python scripts/health_check.py --quick  # Fast checks only

CHECKS:
- Data pipeline connectivity
- Model integrity
- Configuration validity
- Disk space and memory
- PIT safety compliance
- Risk manager functionality

Author: OMEGA_QUANT Team
Version: 1.0.0
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any
import yaml
import pandas as pd
import numpy as np
import psutil

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "data" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "observability" / "src"))

from omega.core.portfolio_manager import PortfolioManager
from omega.core.risk_manager import RiskManager
from omega.data.loader import DataLoader
from omega.utils.logger import setup_logger


class HealthChecker:
    """System health validation with comprehensive checks."""
    
    def __init__(self, config_path: str = None, quick: bool = False):
        """
        Initialize health checker.
        
        Args:
            config_path: Path to config YAML (optional)
            quick: Run only fast checks
        """
        self.config_path = Path(config_path) if config_path else None
        self.quick = quick
        self.logger = setup_logger("health_check", level=logging.INFO)
        
        self.results: List[Tuple[str, bool, str]] = []
        self.config: Dict[str, Any] = {}
        
        if self.config_path and self.config_path.exists():
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
    
    def run_all_checks(self) -> bool:
        """
        Run all health checks.
        
        Returns:
            True if all checks pass
        """
        self.logger.info("Starting health checks...")
        
        # System checks
        self._check_system_resources()
        self._check_disk_space()
        
        # Configuration checks
        if self.config_path:
            self._check_config_validity()
        
        # Data checks
        self._check_data_availability()
        
        if not self.quick:
            # Comprehensive checks (slower)
            self._check_data_quality()
            self._check_model_integrity()
            self._check_risk_manager()
            self._check_pit_safety()
        
        # Print results
        self._print_results()
        
        # Return overall status
        return all(passed for _, passed, _ in self.results)
    
    def _check_system_resources(self) -> None:
        """Check CPU, memory, and system load."""
        try:
            # Memory check
            mem = psutil.virtual_memory()
            mem_available_gb = mem.available / (1024**3)
            mem_percent = mem.percent
            
            if mem_available_gb < 2.0:
                self.results.append((
                    "Memory",
                    False,
                    f"Low memory: {mem_available_gb:.1f}GB available ({mem_percent:.1f}% used)"
                ))
            else:
                self.results.append((
                    "Memory",
                    True,
                    f"{mem_available_gb:.1f}GB available ({mem_percent:.1f}% used)"
                ))
            
            # CPU check
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > 90:
                self.results.append((
                    "CPU",
                    False,
                    f"High CPU usage: {cpu_percent:.1f}%"
                ))
            else:
                self.results.append((
                    "CPU",
                    True,
                    f"CPU usage: {cpu_percent:.1f}%"
                ))
                
        except Exception as e:
            self.results.append(("System Resources", False, f"Error: {e}"))
    
    def _check_disk_space(self) -> None:
        """Check available disk space."""
        try:
            disk = psutil.disk_usage(str(PROJECT_ROOT))
            free_gb = disk.free / (1024**3)
            percent_used = disk.percent
            
            if free_gb < 5.0:
                self.results.append((
                    "Disk Space",
                    False,
                    f"Low disk space: {free_gb:.1f}GB free ({percent_used:.1f}% used)"
                ))
            else:
                self.results.append((
                    "Disk Space",
                    True,
                    f"{free_gb:.1f}GB free ({percent_used:.1f}% used)"
                ))
                
        except Exception as e:
            self.results.append(("Disk Space", False, f"Error: {e}"))
    
    def _check_config_validity(self) -> None:
        """Validate configuration file."""
        try:
            required_sections = ["data", "portfolio", "risk", "execution"]
            missing = [s for s in required_sections if s not in self.config]
            
            if missing:
                self.results.append((
                    "Config Validity",
                    False,
                    f"Missing sections: {missing}"
                ))
            else:
                self.results.append((
                    "Config Validity",
                    True,
                    f"All required sections present"
                ))
                
        except Exception as e:
            self.results.append(("Config Validity", False, f"Error: {e}"))
    
    def _check_data_availability(self) -> None:
        """Check if data sources are accessible."""
        try:
            data_config = self.config.get("data", {})
            data_loader = DataLoader(
                cache_dir=data_config.get("cache_dir", "data/cache"),
                quality_threshold=0.8,
                outlier_std_threshold=5.0,
                enable_pit_enforcement=True
            )
            
            # Try loading recent data
            end_date = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
            start_date = end_date - pd.Timedelta(days=5)
            tickers = data_config.get("universe", ["FPT", "VCB"])
            
            data = data_loader.load_market_data(
                start_date=start_date,
                end_date=end_date,
                tickers=tickers,
                as_of_time=end_date.to_pydatetime()
            )
            
            if data.empty:
                self.results.append((
                    "Data Availability",
                    False,
                    "No data returned from loader"
                ))
            else:
                num_tickers = data.index.get_level_values('ticker').nunique()
                num_dates = data.index.get_level_values('date').nunique()
                self.results.append((
                    "Data Availability",
                    True,
                    f"{num_tickers} tickers, {num_dates} dates"
                ))
                
        except Exception as e:
            self.results.append(("Data Availability", False, f"Error: {e}"))
    
    def _check_data_quality(self) -> None:
        """Check data quality and completeness."""
        try:
            data_config = self.config.get("data", {})
            data_loader = DataLoader(
                cache_dir=data_config.get("cache_dir", "data/cache"),
                quality_threshold=0.8,
                outlier_std_threshold=5.0,
                enable_pit_enforcement=True
            )
            
            end_date = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
            start_date = end_date - pd.Timedelta(days=30)
            tickers = data_config.get("universe", ["FPT", "VCB"])
            
            data = data_loader.load_market_data(
                start_date=start_date,
                end_date=end_date,
                tickers=tickers,
                as_of_time=end_date.to_pydatetime()
            )
            
            # Check for missing values
            missing_pct = (data.isnull().sum() / len(data) * 100).max()
            
            # Check for outliers (vectorized)
            numeric_cols = data.select_dtypes(include=[np.number]).columns
            z_scores = np.abs((data[numeric_cols] - data[numeric_cols].mean()) / data[numeric_cols].std())
            outlier_pct = (z_scores > 5).sum().sum() / (len(data) * len(numeric_cols)) * 100
            
            if missing_pct > 5.0 or outlier_pct > 1.0:
                self.results.append((
                    "Data Quality",
                    False,
                    f"Missing: {missing_pct:.2f}%, Outliers: {outlier_pct:.2f}%"
                ))
            else:
                self.results.append((
                    "Data Quality",
                    True,
                    f"Missing: {missing_pct:.2f}%, Outliers: {outlier_pct:.2f}%"
                ))
                
        except Exception as e:
            self.results.append(("Data Quality", False, f"Error: {e}"))
    
    def _check_model_integrity(self) -> None:
        """Verify model components are functional using production data only."""
        self.results.append((
            "Model Integrity",
            False,
            "NotImplemented: production model integrity check requires real feature pipeline inputs"
        ))
    
    def _check_risk_manager(self) -> None:
        """Verify risk manager functionality using production portfolio state only."""
        self.results.append((
            "Risk Manager",
            False,
            "NotImplemented: production risk manager check requires live portfolio state"
        ))
    
    def _check_pit_safety(self) -> None:
        """Verify point-in-time safety compliance."""
        try:
            data_config = self.config.get("data", {})
            data_loader = DataLoader(
                cache_dir=data_config.get("cache_dir", "data/cache"),
                quality_threshold=0.8,
                outlier_std_threshold=5.0,
                enable_pit_enforcement=True
            )
            
            # Test with historical date
            test_date = pd.Timestamp.now().normalize() - pd.Timedelta(days=10)
            start_date = test_date - pd.Timedelta(days=30)
            tickers = data_config.get("universe", ["FPT", "VCB"])
            
            data = data_loader.load_market_data(
                start_date=start_date,
                end_date=test_date,
                tickers=tickers,
                as_of_time=test_date.to_pydatetime()
            )
            
            # Verify no future data
            max_date = data.index.get_level_values('date').max()
            
            if max_date > test_date:
                self.results.append((
                    "PIT Safety",
                    False,
                    f"Future data leak: max_date {max_date} > test_date {test_date}"
                ))
            else:
                self.results.append((
                    "PIT Safety",
                    True,
                    f"No future data leak detected"
                ))
                
        except Exception as e:
            self.results.append(("PIT Safety", False, f"Error: {e}"))
    
    def _print_results(self) -> None:
        """Print formatted health check results."""
        print("\n" + "="*70)
        print("OMEGA_QUANT HEALTH CHECK RESULTS")
        print("="*70)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Mode: {'QUICK' if self.quick else 'COMPREHENSIVE'}")
        print("-"*70)
        
        passed_count = sum(1 for _, passed, _ in self.results if passed)
        total_count = len(self.results)
        
        for check_name, passed, message in self.results:
            status = "[PASS]" if passed else "[FAIL]"
            print(f"{status:8} | {check_name:25} | {message}")
        
        print("-"*70)
        print(f"Summary: {passed_count}/{total_count} checks passed")
        
        if passed_count == total_count:
            print("Status: HEALTHY")
        else:
            print("Status: UNHEALTHY")
        
        print("="*70 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="OMEGA_QUANT System Health Check",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config YAML (optional)"
    )
    
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only fast checks"
    )
    
    args = parser.parse_args()
    
    # Run health checks
    checker = HealthChecker(config_path=args.config, quick=args.quick)
    all_passed = checker.run_all_checks()
    
    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
