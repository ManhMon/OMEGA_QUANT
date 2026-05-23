#!/usr/bin/env python3
"""
OMEGA_QUANT Backtest Engine
============================
Historical backtest from 2015 to present with real vnstock data.

Usage:
    python scripts/backtest.py --start 2015-01-01 --end 2026-05-13 --config config/development.yaml
"""

import os
import sys
# Force UTF-8 encoding for Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import argparse
import yaml
import logging
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "core" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "data" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "observability" / "src"))

from omega.core.portfolio_manager import PortfolioManager
from omega.core.risk_manager import RiskManager
from omega.data.loader import DataLoader
from omega.utils.logger import setup_logger


class BacktestEngine:
    """Historical backtest engine."""
    
    def __init__(self, config_path: str, start_date: str, end_date: str):
        """Initialize backtest."""
        self.config_path = Path(config_path)
        self.start_date = pd.Timestamp(start_date)
        self.end_date = pd.Timestamp(end_date)
        
        self.logger = setup_logger("backtest", level=logging.INFO)
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
        
        # Results tracking
        self.daily_results: List[Dict[str, Any]] = []
        self.portfolio_values: List[float] = []
        self.dates: List[pd.Timestamp] = []
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration."""
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        self.logger.info(f"Loaded config from {self.config_path}")
        return config
    
    def run(self) -> Dict[str, Any]:
        """Run backtest."""
        self.logger.info(f"Starting backtest from {self.start_date.date()} to {self.end_date.date()}")
        
        # Get trading dates (business days)
        trading_dates = pd.bdate_range(start=self.start_date, end=self.end_date)
        self.logger.info(f"Total trading days: {len(trading_dates)}")
        
        # Initial capital
        initial_capital = self.config.get("portfolio", {}).get("initial_capital", 100_000_000)
        current_value = initial_capital
        
        # Load all data upfront (for efficiency)
        self.logger.info("Loading historical data for all symbols...")
        tickers = self.config.get("data", {}).get("universe", [])
        
        try:
            all_data = self.data_loader.load_market_data(
                start_date=self.start_date,
                end_date=self.end_date,
                tickers=tickers,
                as_of_time=self.end_date.to_pydatetime()
            )
            self.logger.info(f"Loaded {len(all_data)} data points for {len(tickers)} symbols")
        except Exception as e:
            self.logger.error(f"Failed to load data: {e}")
            return {'status': 'FAILED', 'error': str(e)}
        
        # Backtest loop
        for i, date in enumerate(trading_dates):
            if i % 50 == 0:
                self.logger.info(f"Processing {date.date()} ({i}/{len(trading_dates)})")
            
            try:
                # Get data up to this date (PIT-safe)
                data_slice = all_data[all_data.index.get_level_values('date') <= date]
                
                if data_slice.empty:
                    continue
                
                # Generate signals
                signals = self.portfolio_mgr.generate_signals(data_slice, as_of_date=date)
                
                # Construct portfolio
                portfolio = self.portfolio_mgr.construct_portfolio(
                    signals=signals,
                    data=data_slice,
                    as_of_date=date
                )
                
                # Risk check
                risk_report = self.risk_mgr.check_portfolio(portfolio, data_slice)
                
                # Calculate portfolio value
                if not portfolio.empty:
                    # Map weights to latest returns in data_slice
                    latest_date = data_slice.index.get_level_values('date').max()
                    latest_data = data_slice.xs(latest_date, level='date')
                    
                    portfolio_returns = []
                    for ticker, row in portfolio.iterrows():
                        if ticker in latest_data.index:
                            ticker_return = latest_data.loc[ticker].get('returns', 0.0)
                            portfolio_returns.append(row['weight'] * ticker_return)
                    
                    daily_return = sum(portfolio_returns)
                    current_value *= (1 + daily_return)
                
                self.daily_results.append({
                    'date': date,
                    'portfolio_value': current_value,
                    'num_positions': len(portfolio),
                    'risk_passed': risk_report.get('passed', False),
                    'portfolio_vol': risk_report.get('portfolio_volatility', 0.0)
                })
                
                self.portfolio_values.append(current_value)
                self.dates.append(date)
                
            except Exception as e:
                self.logger.warning(f"Error on {date.date()}: {e}")
                continue
        
        # Calculate metrics
        returns = np.diff(self.portfolio_values) / np.array(self.portfolio_values[:-1])
        total_return = (self.portfolio_values[-1] - initial_capital) / initial_capital
        annual_return = (self.portfolio_values[-1] / initial_capital) ** (252 / len(self.dates)) - 1
        annual_vol = np.std(returns) * np.sqrt(252)
        sharpe = annual_return / annual_vol if annual_vol > 0 else 0
        max_dd = self._calculate_max_drawdown(self.portfolio_values)
        
        self.logger.info(f"\n{'='*70}")
        self.logger.info(f"BACKTEST RESULTS ({self.start_date.date()} to {self.end_date.date()})")
        self.logger.info(f"{'='*70}")
        self.logger.info(f"Initial Capital: {initial_capital:,.0f} VND")
        self.logger.info(f"Final Value: {self.portfolio_values[-1]:,.0f} VND")
        self.logger.info(f"Total Return: {total_return:.2%}")
        self.logger.info(f"Annual Return: {annual_return:.2%}")
        self.logger.info(f"Annual Volatility: {annual_vol:.2%}")
        self.logger.info(f"Sharpe Ratio: {sharpe:.2f}")
        self.logger.info(f"Max Drawdown: {max_dd:.2%}")
        self.logger.info(f"Trading Days: {len(self.dates)}")
        
        return {
            'status': 'SUCCESS',
            'initial_capital': initial_capital,
            'final_value': self.portfolio_values[-1],
            'total_return': total_return,
            'annual_return': annual_return,
            'annual_volatility': annual_vol,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'trading_days': len(self.dates),
            'daily_results': self.daily_results
        }
    
    def _calculate_max_drawdown(self, values: List[float]) -> float:
        """Calculate maximum drawdown."""
        cummax = np.maximum.accumulate(values)
        drawdown = (np.array(values) - cummax) / cummax
        return np.min(drawdown)


def main():
    parser = argparse.ArgumentParser(description="OMEGA_QUANT Backtest Engine")
    parser.add_argument("--start", default="2015-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-05-13", help="End date (YYYY-MM-DD)")
    parser.add_argument("--config", default="config/development.yaml", help="Config file")
    
    args = parser.parse_args()
    
    engine = BacktestEngine(args.config, args.start, args.end)
    results = engine.run()
    
    # Save results
    if results['status'] == 'SUCCESS':
        output_dir = Path("data/backtest")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results_df = pd.DataFrame(results['daily_results'])
        results_df.to_csv(output_dir / "daily_results.csv", index=False)
        
        with open(output_dir / "summary.txt", 'w') as f:
            f.write(f"BACKTEST SUMMARY\n")
            f.write(f"{'='*70}\n")
            f.write(f"Period: {args.start} to {args.end}\n")
            f.write(f"Initial Capital: {results['initial_capital']:,.0f} VND\n")
            f.write(f"Final Value: {results['final_value']:,.0f} VND\n")
            f.write(f"Total Return: {results['total_return']:.2%}\n")
            f.write(f"Annual Return: {results['annual_return']:.2%}\n")
            f.write(f"Annual Volatility: {results['annual_volatility']:.2%}\n")
            f.write(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}\n")
            f.write(f"Max Drawdown: {results['max_drawdown']:.2%}\n")


if __name__ == "__main__":
    main()
