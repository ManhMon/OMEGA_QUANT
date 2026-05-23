#!/usr/bin/env python3
"""Debug risk check failure"""
import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import pandas as pd
from datetime import datetime
from pathlib import Path

# Add OMEGA_QUANT to path
sys.path.insert(0, str(Path(__file__).parent / "packages" / "data" / "src"))
sys.path.insert(0, str(Path(__file__).parent / "packages" / "portfolio" / "src"))
sys.path.insert(0, str(Path(__file__).parent / "packages" / "risk" / "src"))

from omega.core.portfolio_manager import PortfolioManager
from omega.core.risk_manager import RiskManager
from omega.data.loader import DataLoader

print("=" * 70)
print("RISK CHECK DEBUG - 2026-04-15")
print("=" * 70)

# Load config
def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

import yaml
config = load_config("config/development.yaml")
print(f"\n✓ Config loaded")
print(f"  max_concentration_pct: {config['risk']['position_risk']['max_concentration_pct']}")
print(f"  max_adv_pct: {config['risk']['position_risk']['max_adv_pct']}")

# Load data
data_loader = DataLoader(config)
run_date = pd.Timestamp("2026-04-15")
tickers = config.get("data", {}).get("universe", ["VNM", "FPT", "VCB"])

print(f"\n✓ Loading data for {tickers}...")
data = data_loader.load_market_data(
    start_date=run_date - pd.Timedelta(days=252),
    end_date=run_date,
    tickers=tickers,
    as_of_time=run_date.to_pydatetime()
)

print(f"  Data shape: {data.shape}")
print(f"  Data:\n{data.tail()}")

# Generate signals
portfolio_mgr = PortfolioManager(config)
print(f"\n✓ Generating signals...")
signals = portfolio_mgr.generate_signals(data, as_of_date=run_date)
print(f"  Signals: {signals}")

# Construct portfolio
print(f"\n✓ Constructing portfolio...")
portfolio = portfolio_mgr.construct_portfolio(
    signals=signals,
    data=data,
    as_of_date=run_date
)
print(f"  Portfolio:\n{portfolio}")

# Risk check
risk_mgr = RiskManager(config)
print(f"\n✓ Running risk checks...")
risk_report = risk_mgr.check_portfolio(portfolio, data)
print(f"  Risk Report:\n{risk_report}")

if not risk_report.get('passed', False):
    print(f"\n❌ RISK VIOLATIONS:")
    for violation in risk_report.get('violations', []):
        print(f"  - {violation}")
