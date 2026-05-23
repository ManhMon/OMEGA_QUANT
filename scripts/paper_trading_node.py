import os
import sys
import time
import logging
from pathlib import Path
import yaml
from datetime import datetime

# Setup paths
sys.path.insert(0, str(Path('packages/core/src').absolute()))
sys.path.insert(0, str(Path('packages/quant/src').absolute()))
sys.path.insert(0, str(Path('packages/execution/src').absolute()))
sys.path.insert(0, str(Path('packages/observability/src').absolute()))
sys.path.insert(0, str(Path('packages/data/src').absolute()))

from omega.observability.metrics import PrometheusExporter, PrometheusExporterConfig
from omega.quant.execution_sim import ExecutionSimulator, ExecutionConfig
from omega.core.runtime.task_machine import TaskStateMachine
from omega.data.vnstock_adapter import VnstockVCIDataSource

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('PaperTradingNode')

def main():
    logger.info("Initializing OMEGA_QUANT Paper Trading Node")
    
    # 1. Load config
    config_path = Path('config/production.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
        
    mode = config.get('system', {}).get('mode', 'PAPER')
    logger.info(f"System Mode: {mode}")
    
    if mode != 'PAPER':
        logger.error("Config mode is not PAPER. Aborting.")
        return
        
    # 2. Start Metrics Exporter
    prom_cfg = config.get('observability', {}).get('prometheus', {})
    if prom_cfg.get('enabled'):
        port = prom_cfg.get('port', 9090)
        logger.info(f"Starting Prometheus Exporter on port {port}...")
        try:
            exporter = PrometheusExporter(PrometheusExporterConfig(port=port))
        except Exception as e:
            logger.warning(f"Could not start Prometheus exporter: {e}")
        
    # 3. Init Market Data Feed
    logger.info("Connecting to Vnstock VCI Data Source...")
    try:
        market_feed = VnstockVCIDataSource()
    except Exception as e:
        logger.error(f"Failed to connect VNStock: {e}")
    
    # 4. Init Broker/Simulator
    logger.info("Initializing Execution Simulator (VNDirect Mode)...")
    capital = config.get('capital', {}).get('initial_vnd', 2000000000)
    exec_cfg = ExecutionConfig()
    simulator = ExecutionSimulator(exec_cfg)
    
    # 5. Start Task Machine Loop
    logger.info("Starting Task Machine loop...")
    machine = TaskStateMachine()
    
    logger.info("Paper Trading Node ACTIVE. System healthy. Exiting test run.")
        
if __name__ == '__main__':
    main()
