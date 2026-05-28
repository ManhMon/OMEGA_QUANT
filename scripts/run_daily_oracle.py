#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase C: Unattended Daily Cronjob (Personal Signal Oracle)
Sequentially executes Data Update -> Model Retraining -> Signal Generation.

Run this script daily at 16:00 via Windows Task Scheduler or cron.

Author: DevOps Engineer (Role 11)
Date: 2026-05-24
"""

import subprocess
import sys
import logging
import json
from pathlib import Path
from datetime import datetime

ALERT_LOG = Path(__file__).parent.parent / '.ly_state' / 'session' / 'oracle_alerts.jsonl'

PROJECT_ROOT = Path(__file__).parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] ORACLE: %(message)s")
logger = logging.getLogger("daily_oracle")

def send_alert(step_name: str, error_msg: str):
    """Log alert to JSONL file. In production, this would send Telegram/email."""
    alert = {
        'timestamp': datetime.now().isoformat(),
        'severity': 'CRITICAL',
        'pipeline': 'daily_oracle',
        'failed_step': step_name,
        'error': error_msg,
        'status': 'UNRESOLVED'
    }
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERT_LOG, 'a') as f:
        f.write(json.dumps(alert) + '\n')
    logger.critical(f'ALERT FIRED: {step_name} failed - {error_msg}')


def run_step(script_name: str, args: list = None) -> bool:
    script_path = PROJECT_ROOT / "scripts" / script_name
    if not script_path.exists():
        logger.error(f"Script {script_name} not found!")
        return False
        
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)
        
    logger.info(f"Executing: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info(f"Success. Output:\n{result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed (exit code {e.returncode}). Error:\n{e.stderr.strip()}")
        return False

def run_daily_oracle():
    today_str = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"=== STARTING DAILY ORACLE WORKFLOW FOR {today_str} ===")
    
    # 1. Update Market Data
    logger.info("--> STEP 1: Updating Market Data")
    if not run_step("update_market_data.py"):
        logger.error("Halted at Step 1.")
        send_alert('update_market_data', 'Data ingestion failed')
        sys.exit(1)

    # 2. Continuous Learning (Train Model)
    logger.info("--> STEP 2: Retraining XGBoost Model (Phase 6)")
    target_date = today_str
    if not run_step("run_phase6_continuous_learning.py", ["--date", target_date]):
        logger.error("Halted at Step 2.")
        send_alert('continuous_learning', 'Model retraining failed')
        sys.exit(1)

    # 3. Signal Generation & Telegram Batch (Shadow Live)
    logger.info("--> STEP 3: Generating Signals & Sending Telegram (Stage 5)")
    if not run_step("run_stage5_shadow_live.py", ["--date", target_date]):
        logger.error("Halted at Step 3.")
        send_alert('shadow_live', 'Signal generation failed')
        sys.exit(1)

    logger.info("=== ORACLE WORKFLOW COMPLETE ===")
    logger.info(f'All steps completed successfully. No alerts fired.')
    sys.exit(0)

if __name__ == "__main__":
    run_daily_oracle()