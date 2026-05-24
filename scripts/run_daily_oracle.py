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
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] ORACLE: %(message)s")
logger = logging.getLogger("daily_oracle")

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
        return

    # 2. Continuous Learning (Train Model)
    logger.info("--> STEP 2: Retraining XGBoost Model (Phase 6)")
    # Normally today_str, but we mock "2026-05-15" to match our mock data limit in the parquet
    target_date = "2026-05-15" 
    if not run_step("run_phase6_continuous_learning.py", ["--date", target_date]):
        logger.error("Halted at Step 2.")
        return

    # 3. Signal Generation & Telegram Batch (Shadow Live)
    logger.info("--> STEP 3: Generating Signals & Sending Telegram (Stage 5)")
    if not run_step("run_stage5_shadow_live.py", ["--date", target_date]):
        logger.error("Halted at Step 3.")
        return

    logger.info("=== ORACLE WORKFLOW COMPLETE ===")

if __name__ == "__main__":
    run_daily_oracle()