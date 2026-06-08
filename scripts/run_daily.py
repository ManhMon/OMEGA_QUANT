#!/usr/bin/env python3
"""
OMEGA_QUANT Daily Rebalance Entry Point
========================================
Production-ready daily execution script with health checks, logging, and error handling.

USAGE:
    python scripts/run_daily.py --config config/production.yaml --date 2024-01-15

FEATURES:
- Pre-flight health checks
- PIT-safe execution
- Comprehensive logging
- Error recovery
- Performance metrics
- Audit trail

Author: OMEGA_QUANT Team
Version: 1.0.0
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
import pandas as pd
import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

from omega.core.portfolio_manager import PortfolioManager
from omega.core.risk_manager import RiskManager
from omega.data.loader import DataLoader
from omega.utils.logger import setup_logger


class DailyRunner:
    """Daily rebalance orchestrator with production safeguards."""
    
    def __init__(self, config_path: str, run_date: Optional[str] = None):
        """
        Initialize daily runner.
        
        Args:
            config_path: Path to production config YAML
            run_date: Target date (YYYY-MM-DD), defaults to T-1 (yesterday)
        """
        self.config_path = Path(config_path)
        # Enforce T-1 lag: default to yesterday, not today
        if run_date:
            self.run_date = pd.Timestamp(run_date)
        else:
            self.run_date = pd.Timestamp.now() - pd.Timedelta(days=1)
        
        self.logger = setup_logger("daily_runner", level=logging.INFO)
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize components
        data_config = self.config.get("data", {})
        self.data_loader = DataLoader(
            cache_dir=data_config.get("cache_dir", "data/cache"),
            quality_threshold=0.8,
            outlier_std_threshold=5.0,
            enable_pit_enforcement=True
        )
        self.portfolio_mgr = PortfolioManager(self.config.get("portfolio", {}))
        self.risk_mgr = RiskManager(self.config.get("risk", {}))
        
        # Metrics
        self.metrics: Dict[str, Any] = {}
        
    def _load_config(self) -> Dict[str, Any]:
        """Load and validate production configuration."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Validate required sections
        required = ["data", "portfolio", "risk", "execution"]
        missing = [s for s in required if s not in config]
        if missing:
            raise ValueError(f"Missing config sections: {missing}")
        
        self.logger.info(f"Loaded config from {self.config_path}")
        return config
    
    def pre_flight_checks(self) -> bool:
        """
        Run pre-flight health checks.
        
        Returns:
            True if all checks pass
        """
        self.logger.info("Running pre-flight checks...")
        checks_passed = True
        
        # Check 0: Enforce T-1 lag (PIT safety)
        today = pd.Timestamp.now().normalize()
        if self.run_date >= today:
            self.logger.error(f"PIT SAFETY VIOLATION: run_date {self.run_date.date()} must be < today {today.date()}")
            self.logger.error("OMEGA_QUANT enforces T-1 lag to prevent look-ahead bias")
            return False
        else:
            self.logger.info(f"PIT check passed: run_date {self.run_date.date()} < today {today.date()}")
        
        # Check 1: Data availability
        try:
            # Get tickers from config or use default
            tickers = self.config.get("data", {}).get("universe", ["VNM", "FPT", "VCB"])
            data = self.data_loader.load_market_data(
                start_date=self.run_date - pd.Timedelta(days=30),
                end_date=self.run_date,
                tickers=tickers,
                as_of_time=self.run_date.to_pydatetime()
            )
            if data.empty:
                self.logger.error("No market data available")
                return False
            else:
                self.logger.info(f"Market data: {len(data)} rows")
        except Exception as e:
            self.logger.error(f"Data check failed: {e}")
            return False
        
        # Check 2: PIT safety (verify no future data leak)
        latest_data_date = data.index.get_level_values('date').max()
        if latest_data_date > self.run_date:
            self.logger.error(f"PIT violation: data from {latest_data_date} > run_date {self.run_date}")
            return False
        else:
            self.logger.info(f"Data PIT check passed: latest data {latest_data_date}")
        
        # Check 3: Risk limits
        risk_config = self.config.get("risk", {})
        if not risk_config.get("max_position_size"):
            self.logger.warning("No max_position_size configured")
        
        # Check 4: Execution settings
        exec_config = self.config.get("execution", {})
        if not exec_config.get("broker"):
            self.logger.warning("No broker configured")
        
        return checks_passed
    
    def run_rebalance(self) -> Dict[str, Any]:
        """
        Execute daily rebalance with full safeguards.
        
        Returns:
            Execution results and metrics
        """
        start_time = datetime.now()
        self.logger.info(f"Starting daily rebalance for {self.run_date}")
        
        try:
            # Step 1: Load data (PIT-safe)
            self.logger.info("Loading market data...")
            tickers = self.config.get("data", {}).get("universe", ["VNM", "FPT", "VCB"])
            data = self.data_loader.load_market_data(
                start_date=self.run_date - pd.Timedelta(days=252),
                end_date=self.run_date,
                tickers=tickers,
                as_of_time=self.run_date.to_pydatetime()
            )
            self.metrics['data_rows'] = len(data)
            
            # Step 2: Generate signals
            self.logger.info("Generating signals...")
            signals = self.portfolio_mgr.generate_signals(data, as_of_date=self.run_date)
            self.metrics['num_signals'] = len(signals)
            
            # Step 3: Construct portfolio
            self.logger.info("Constructing portfolio...")
            portfolio = self.portfolio_mgr.construct_portfolio(
                signals=signals,
                data=data,
                as_of_date=self.run_date
            )
            self.metrics['num_positions'] = len(portfolio)
            
            # Step 4: Risk checks
            self.logger.info("Running risk checks...")
            risk_report = self.risk_mgr.check_portfolio(portfolio, data)
            
            if not risk_report.get('passed', False):
                self.logger.error(f"Risk checks failed: {risk_report.get('violations', [])}")
                return {
                    'status': 'FAILED',
                    'reason': 'Risk violations',
                    'risk_report': risk_report,
                    'metrics': self.metrics
                }
            
            self.metrics['risk_score'] = risk_report.get('score', 0.0)
            
            # Step 5: Generate orders
            self.logger.info("Generating orders...")
            orders = self.portfolio_mgr.generate_orders(
                target_portfolio=portfolio,
                current_holdings=self._get_current_holdings()
            )
            self.metrics['num_orders'] = len(orders)
            
            # Step 6: Execute (dry-run in test mode)
            if self.config.get("execution", {}).get("dry_run", True):
                self.logger.info("DRY RUN: Orders not executed")
                execution_result = {'status': 'DRY_RUN', 'orders': orders}
            else:
                self.logger.info("Executing orders...")
                execution_result = self._execute_orders(orders)
            
            # Step 7: Record results
            self._save_results(portfolio, orders, execution_result)
            
            # Calculate metrics
            elapsed = (datetime.now() - start_time).total_seconds()
            self.metrics['elapsed_seconds'] = elapsed
            
            self.logger.info(f"Rebalance completed in {elapsed:.2f}s")
            
            return {
                'status': 'SUCCESS',
                'portfolio': portfolio,
                'orders': orders,
                'execution': execution_result,
                'metrics': self.metrics
            }
            
        except Exception as e:
            self.logger.error(f"Rebalance failed: {e}", exc_info=True)
            return {
                'status': 'ERROR',
                'error': str(e),
                'metrics': self.metrics
            }
    
    def _get_current_holdings(self) -> pd.DataFrame:
        """Load current portfolio holdings."""
        holdings_path = PROJECT_ROOT / "data" / "holdings" / "current.csv"
        
        if holdings_path.exists():
            return pd.read_csv(holdings_path, index_col=0)
        else:
            # Empty holdings for first run
            return pd.DataFrame(columns=['ticker', 'shares', 'value'])
    
    def _execute_orders(self, orders: pd.DataFrame) -> Dict[str, Any]:
        """
        Execute orders via broker API.
        
        Args:
            orders: DataFrame with columns [ticker, action, shares, limit_price]
        
        Returns:
            Execution results
        """
        # Placeholder for broker integration
        self.logger.warning("Broker execution not implemented - using mock")
        
        return {
            'status': 'MOCK',
            'orders_submitted': len(orders),
            'orders_filled': len(orders),
            'fills': orders.to_dict('records')
        }
    
    def _save_results(
        self,
        portfolio: pd.DataFrame,
        orders: pd.DataFrame,
        execution: Dict[str, Any]
    ) -> None:
        """Save rebalance results to disk."""
        output_dir = PROJECT_ROOT / "data" / "rebalance" / self.run_date.strftime("%Y%m%d")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save portfolio
        portfolio.to_csv(output_dir / "portfolio.csv")
        
        # Save orders
        orders.to_csv(output_dir / "orders.csv")
        
        # Save execution log
        with open(output_dir / "execution.yaml", 'w') as f:
            yaml.dump(execution, f)
        
        self.logger.info(f"Results saved to {output_dir}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="OMEGA_QUANT Daily Rebalance",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config/production.yaml",
        help="Path to production config (default: config/production.yaml)"
    )
    
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date YYYY-MM-DD (default: yesterday for T-1 lag)"
    )
    
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip pre-flight checks (DANGEROUS - use only for testing)"
    )
    
    args = parser.parse_args()
    
    # Initialize runner
    runner = DailyRunner(config_path=args.config, run_date=args.date)
    
    # Pre-flight checks (MANDATORY unless --skip-checks)
    if not args.skip_checks:
        if not runner.pre_flight_checks():
            print("Pre-flight checks FAILED. Aborting.")
            sys.exit(1)
    else:
        runner.logger.warning("SKIPPING PRE-FLIGHT CHECKS (--skip-checks flag)")
    
    # Run rebalance
    result = runner.run_rebalance()
    
    # Print summary
    print("\n" + "="*60)
    print(f"DAILY REBALANCE SUMMARY - {runner.run_date.date()}")
    print("="*60)
    print(f"Status: {result['status']}")
    
    if result['status'] == 'SUCCESS':
        print(f"Positions: {result['metrics'].get('num_positions', 0)}")
        print(f"Orders: {result['metrics'].get('num_orders', 0)}")
        print(f"Risk Score: {result['metrics'].get('risk_score', 0.0):.2f}")
        print(f"Elapsed: {result['metrics'].get('elapsed_seconds', 0):.2f}s")
    else:
        print(f"Error: {result.get('error', 'Unknown')}")
    
    print("="*60)
    
    # Exit code
    sys.exit(0 if result['status'] == 'SUCCESS' else 1)


if __name__ == "__main__":
    main()
