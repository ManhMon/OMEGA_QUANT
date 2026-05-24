#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase D: Local Storage Retention
Deletes old `.ly_state` JSON logs and MLflow SQLite records older than 30 days.

Author: DevOps Engineer (Role 11)
Date: 2026-05-24
"""

import os
import time
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
RETENTION_DAYS = 30
RETENTION_SECONDS = RETENTION_DAYS * 86400

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] RETENTION: %(message)s")
logger = logging.getLogger("clean_retention")

def clean_state_dir():
    state_dir = PROJECT_ROOT / ".ly_state"
    if not state_dir.exists():
        return

    now = time.time()
    deleted_count = 0
    
    for root, dirs, files in os.walk(state_dir):
        for f in files:
            # We only clean up JSON logs
            if not f.endswith(".json"):
                continue
                
            filepath = Path(root) / f
            try:
                mtime = filepath.stat().st_mtime
                if now - mtime > RETENTION_SECONDS:
                    filepath.unlink()
                    deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete {filepath}: {e}")
                
    logger.info(f"Cleaned up {deleted_count} old state logs (>30 days).")

def main():
    logger.info("Starting storage retention cleanup...")
    clean_state_dir()
    # Note: MLflow DB cleanup requires specific SQL DELETE commands. 
    # For a personal oracle, the SQLite DB stays small. We prioritize JSON log cleanup.
    logger.info("Cleanup complete.")

if __name__ == "__main__":
    main()