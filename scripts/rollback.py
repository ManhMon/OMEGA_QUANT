#!/usr/bin/env python3
"""
OMEGA_QUANT Emergency Rollback Script
======================================
Safely rollback to previous portfolio state in case of deployment issues.

USAGE:
    python scripts/rollback.py --date 2024-01-15
    python scripts/rollback.py --list  # Show available rollback points
    python scripts/rollback.py --verify-only  # Dry run

FEATURES:
- Restore previous portfolio state
- Verify rollback integrity
- Audit trail preservation
- Automatic backup before rollback

Author: OMEGA_QUANT Team
Version: 1.0.0
"""

import argparse
import logging
import sys
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml
import pandas as pd
import json

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "data" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "observability" / "src"))

from omega.utils.logger import setup_logger


class RollbackManager:
    """Emergency rollback orchestrator with safety checks."""
    
    def __init__(self, verify_only: bool = False):
        """
        Initialize rollback manager.
        
        Args:
            verify_only: If True, only verify without executing
        """
        self.verify_only = verify_only
        self.logger = setup_logger("rollback", level=logging.INFO)
        
        self.data_dir = PROJECT_ROOT / "data"
        self.rebalance_dir = self.data_dir / "rebalance"
        self.holdings_dir = self.data_dir / "holdings"
        self.backup_dir = self.data_dir / "backups"
        
        # Ensure directories exist
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
    def list_rollback_points(self) -> List[Dict[str, Any]]:
        """
        List available rollback points.
        
        Returns:
            List of rollback point metadata
        """
        if not self.rebalance_dir.exists():
            self.logger.warning("No rebalance directory found")
            return []
        
        rollback_points = []
        
        for date_dir in sorted(self.rebalance_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue
            
            portfolio_file = date_dir / "portfolio.csv"
            orders_file = date_dir / "orders.csv"
            execution_file = date_dir / "execution.yaml"
            
            if portfolio_file.exists():
                # Parse date from directory name
                try:
                    date_str = date_dir.name
                    date = pd.Timestamp(f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}")
                    
                    # Load portfolio info
                    portfolio = pd.read_csv(portfolio_file, index_col=0)
                    num_positions = len(portfolio)
                    
                    # Load execution info if available
                    execution_status = "UNKNOWN"
                    if execution_file.exists():
                        with open(execution_file, 'r') as f:
                            exec_data = yaml.safe_load(f)
                            execution_status = exec_data.get('status', 'UNKNOWN')
                    
                    rollback_points.append({
                        'date': date,
                        'date_str': date.strftime('%Y-%m-%d'),
                        'path': date_dir,
                        'num_positions': num_positions,
                        'execution_status': execution_status,
                        'has_orders': orders_file.exists(),
                        'has_execution': execution_file.exists()
                    })
                    
                except Exception as e:
                    self.logger.warning(f"Could not parse {date_dir}: {e}")
        
        return rollback_points
    
    def verify_rollback_point(self, date: pd.Timestamp) -> Dict[str, Any]:
        """
        Verify a rollback point is valid.
        
        Args:
            date: Target rollback date
        
        Returns:
            Verification results
        """
        date_str = date.strftime("%Y%m%d")
        rollback_dir = self.rebalance_dir / date_str
        
        checks = {
            'directory_exists': rollback_dir.exists(),
            'portfolio_exists': (rollback_dir / "portfolio.csv").exists(),
            'orders_exists': (rollback_dir / "orders.csv").exists(),
            'execution_exists': (rollback_dir / "execution.yaml").exists(),
            'portfolio_valid': False,
            'data_integrity': False
        }
        
        # Verify portfolio file
        if checks['portfolio_exists']:
            try:
                portfolio = pd.read_csv(rollback_dir / "portfolio.csv", index_col=0)
                
                # Check required columns
                required_cols = ['ticker', 'weight']
                if all(col in portfolio.columns for col in required_cols):
                    checks['portfolio_valid'] = True
                    
                    # Check data integrity
                    total_weight = portfolio['weight'].sum()
                    if 0.99 <= total_weight <= 1.01:  # Allow small rounding errors
                        checks['data_integrity'] = True
                    else:
                        checks['integrity_error'] = f"Weights sum to {total_weight:.4f}, expected ~1.0"
                        
            except Exception as e:
                checks['portfolio_error'] = str(e)
        
        checks['valid'] = all([
            checks['directory_exists'],
            checks['portfolio_exists'],
            checks['portfolio_valid'],
            checks['data_integrity']
        ])
        
        return checks
    
    def create_backup(self) -> Path:
        """
        Create backup of current state before rollback.
        
        Returns:
            Path to backup directory
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"pre_rollback_{timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Creating backup at {backup_path}")
        
        # Backup current holdings
        current_holdings = self.holdings_dir / "current.csv"
        if current_holdings.exists():
            shutil.copy2(current_holdings, backup_path / "holdings_current.csv")
        
        # Backup recent rebalance data
        if self.rebalance_dir.exists():
            recent_dirs = sorted(self.rebalance_dir.iterdir(), reverse=True)[:3]
            for i, date_dir in enumerate(recent_dirs):
                if date_dir.is_dir():
                    backup_subdir = backup_path / f"rebalance_{i}_{date_dir.name}"
                    shutil.copytree(date_dir, backup_subdir)
        
        # Save backup metadata
        metadata = {
            'timestamp': timestamp,
            'backup_path': str(backup_path),
            'reason': 'pre_rollback',
            'created_by': 'rollback.py'
        }
        
        with open(backup_path / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
        
        self.logger.info(f"Backup completed: {backup_path}")
        return backup_path
    
    def execute_rollback(self, target_date: pd.Timestamp) -> Dict[str, Any]:
        """
        Execute rollback to target date.
        
        Args:
            target_date: Date to rollback to
        
        Returns:
            Rollback execution results
        """
        self.logger.info(f"Starting rollback to {target_date.date()}")
        
        # Step 1: Verify rollback point
        verification = self.verify_rollback_point(target_date)
        if not verification['valid']:
            return {
                'status': 'FAILED',
                'reason': 'Invalid rollback point',
                'verification': verification
            }
        
        # Step 2: Create backup
        if not self.verify_only:
            backup_path = self.create_backup()
        else:
            backup_path = None
            self.logger.info("VERIFY ONLY: Skipping backup creation")
        
        # Step 3: Load target portfolio
        date_str = target_date.strftime("%Y%m%d")
        rollback_dir = self.rebalance_dir / date_str
        target_portfolio = pd.read_csv(rollback_dir / "portfolio.csv", index_col=0)
        
        self.logger.info(f"Target portfolio: {len(target_portfolio)} positions")
        
        # Step 4: Restore holdings
        if not self.verify_only:
            self.holdings_dir.mkdir(parents=True, exist_ok=True)
            
            # Save as current holdings
            target_portfolio.to_csv(self.holdings_dir / "current.csv")
            
            # Also save with timestamp
            restore_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_portfolio.to_csv(
                self.holdings_dir / f"restored_{restore_timestamp}.csv"
            )
            
            self.logger.info("Holdings restored successfully")
        else:
            self.logger.info("VERIFY ONLY: Would restore holdings")
        
        # Step 5: Create rollback audit log
        audit_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': 'ROLLBACK',
            'target_date': target_date.isoformat(),
            'verify_only': self.verify_only,
            'backup_path': str(backup_path) if backup_path else None,
            'num_positions': len(target_portfolio),
            'verification': verification
        }
        
        if not self.verify_only:
            audit_log_path = self.data_dir / "rollback_audit.jsonl"
            with open(audit_log_path, 'a') as f:
                f.write(json.dumps(audit_entry) + '\n')
            
            self.logger.info(f"Audit log updated: {audit_log_path}")
        else:
            self.logger.info("VERIFY ONLY: Would write audit log")
        
        return {
            'status': 'SUCCESS' if not self.verify_only else 'VERIFIED',
            'target_date': target_date.isoformat(),
            'backup_path': str(backup_path) if backup_path else None,
            'num_positions': len(target_portfolio),
            'verification': verification,
            'audit': audit_entry
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="OMEGA_QUANT Emergency Rollback",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target rollback date YYYY-MM-DD"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available rollback points"
    )
    
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify rollback without executing (dry run)"
    )
    
    args = parser.parse_args()
    
    # Initialize manager
    manager = RollbackManager(verify_only=args.verify_only)
    
    # List mode
    if args.list:
        print("\n" + "="*70)
        print("AVAILABLE ROLLBACK POINTS")
        print("="*70)
        
        rollback_points = manager.list_rollback_points()
        
        if not rollback_points:
            print("No rollback points found.")
        else:
            for point in rollback_points:
                print(f"\nDate: {point['date_str']}")
                print(f"  Positions: {point['num_positions']}")
                print(f"  Execution: {point['execution_status']}")
                print(f"  Has Orders: {point['has_orders']}")
                print(f"  Path: {point['path']}")
        
        print("="*70 + "\n")
        sys.exit(0)
    
    # Rollback mode
    if not args.date:
        print("Error: --date required for rollback (or use --list)")
        sys.exit(1)
    
    target_date = pd.Timestamp(args.date)
    
    # Execute rollback
    result = manager.execute_rollback(target_date)
    
    # Print results
    print("\n" + "="*70)
    print(f"ROLLBACK {'VERIFICATION' if args.verify_only else 'EXECUTION'}")
    print("="*70)
    print(f"Target Date: {target_date.date()}")
    print(f"Status: {result['status']}")
    
    if result['status'] in ['SUCCESS', 'VERIFIED']:
        print(f"Positions: {result['num_positions']}")
        if result['backup_path']:
            print(f"Backup: {result['backup_path']}")
        
        if args.verify_only:
            print("\nVERIFY ONLY MODE - No changes made")
            print("Run without --verify-only to execute rollback")
    else:
        print(f"Reason: {result.get('reason', 'Unknown')}")
        print(f"Verification: {result.get('verification', {})}")
    
    print("="*70 + "\n")
    
    # Exit code
    sys.exit(0 if result['status'] in ['SUCCESS', 'VERIFIED'] else 1)


if __name__ == "__main__":
    main()
