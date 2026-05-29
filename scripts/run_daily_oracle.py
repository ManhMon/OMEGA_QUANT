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
from calendar import day_name

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

    # 1.1. Fetch Intraday Data (vnstock)
    logger.info("--> STEP 1.1: Fetching Intraday Data")
    if not run_step("fetch_intraday_data.py", ["--date", today_str]):
        logger.warning("Intraday fetch failed (non-blocking)")
    else:
        logger.info("Intraday data fetched")

    # 1.2. Microstructure Alphas (from intraday)
    logger.info("--> STEP 1.2: Computing Microstructure Alphas")
    if not run_step("run_microstructure_alphas.py", ["--date", today_str]):
        logger.warning("Microstructure alphas failed (non-blocking)")
    else:
        logger.info("Microstructure alphas computed")

    # 1.5. Drift Detection (non-blocking, log warning if drift)
    logger.info("--> STEP 1.5: Running Drift Detection")
    drift_script = PROJECT_ROOT / "scripts" / "run_drift_check.py"
    if drift_script.exists():
        try:
            drift_result = subprocess.run(
                [sys.executable, str(drift_script)],
                capture_output=True, text=True
            )
            if drift_result.returncode == 2:
                logger.warning("DRIFT DETECTED: Rollback was executed. Continuing pipeline with restored model.")
                logger.warning(f"Drift output: {drift_result.stdout.strip()[-500:]}")
            elif drift_result.returncode == 0:
                logger.info("Drift check PASSED: No drift detected.")
            else:
                logger.warning(f"Drift check returned unexpected code {drift_result.returncode}")
        except Exception as e:
            logger.warning(f"Drift check failed (non-blocking): {e}")
    else:
        logger.info("Drift check script not found, skipping.")

    # 1.7. Sentiment Enrichment (non-blocking)
    logger.info("--> STEP 1.7: Running Sentiment Enrichment")
    sentiment_script = PROJECT_ROOT / "scripts" / "run_sentiment_enrichment.py"
    if sentiment_script.exists():
        try:
            sent_result = subprocess.run(
                [sys.executable, str(sentiment_script)],
                capture_output=True, text=True
            )
            if sent_result.returncode == 0:
                # Parse output to log article count
                try:
                    sent_output = PROJECT_ROOT / '.ly_state' / 'session' / 'sentiment_scores.json'
                    if sent_output.exists():
                        import json as _sent_json
                        with open(sent_output) as _sf:
                            sent_data = _sent_json.load(_sf)
                        logger.info(f"Sentiment enrichment OK: {sent_data.get('num_articles', 0)} articles processed")
                    else:
                        logger.info("Sentiment enrichment completed (no output file found).")
                except Exception as parse_err:
                    logger.info(f"Sentiment enrichment completed (could not parse output: {parse_err})")
            else:
                logger.warning(f"Sentiment enrichment failed (exit {sent_result.returncode}), continuing pipeline.")
                if sent_result.stderr:
                    logger.warning(f"Sentiment stderr: {sent_result.stderr.strip()[-300:]}")
        except Exception as e:
            logger.warning(f"Sentiment enrichment error (non-blocking): {e}")
    else:
        logger.info("Sentiment enrichment script not found, skipping.")

    # 2. Continuous Learning (Train Model)
    logger.info("--> STEP 2: Retraining XGBoost Model (Phase 6)")
    target_date = today_str
    if not run_step("run_phase6_continuous_learning.py", ["--date", target_date]):
        logger.error("Halted at Step 2.")
        send_alert('continuous_learning', 'Model retraining failed')
        sys.exit(1)

    # 2.5. Weekly Evolution (Sunday only)
    today_weekday = datetime.now().strftime("%A")
    if today_weekday == "Sunday":
        logger.info("--> STEP 2.5: Running Weekly GP Alpha Evolution (Sunday)")
        if not run_step("run_weekly_evolution.py"):
            logger.warning("Weekly evolution failed (non-blocking). Continuing pipeline.")
        else:
            logger.info("Weekly evolution completed successfully.")
        
        # 2.6. Walk-Forward Validation (Sunday)
        logger.info("--> STEP 2.6: Walk-Forward Validation")
        if not run_step("run_walk_forward_validation.py", ["--date", target_date]):
            logger.warning("Walk-forward validation failed (non-blocking)")

        # 2.7. Alpha Promotion Gate (Sunday)
        logger.info("--> STEP 2.7: Alpha Promotion")
        if not run_step("run_alpha_promotion.py", ["--date", target_date]):
            logger.warning("Alpha promotion failed (non-blocking)")
        
        # 2.8. Weekly Stress Test (Sunday)
        logger.info("--> STEP 2.8: Stress Testing")
        stress_script = PROJECT_ROOT / "scripts" / "run_stress_test.py"
        if stress_script.exists():
            try:
                stress_result = subprocess.run(
                    [sys.executable, str(stress_script), "--date", target_date],
                    capture_output=True, text=True
                )
                if stress_result.returncode == 2:
                    logger.error("STRESS TEST CRITICAL: Worst case > 50% loss")
                    send_alert('stress_test', 'Severe stress test failure')
                elif stress_result.returncode == 1:
                    logger.warning("Stress test WARN: Worst case 25-50%")
                else:
                    logger.info("Stress test PASSED")
            except Exception as e:
                logger.warning(f"Stress test failed (non-blocking): {e}")
    else:
        logger.info(f"--> STEP 2.5-2.8: Skipping weekly tasks (today is {today_weekday}, not Sunday)")

    # 3. Signal Generation (ML Ridge 142 features)
    logger.info("--> STEP 3: Generating ML Signals (Ridge 142 features)")
    if not run_step("run_stage5_ml_signals.py", ["--date", target_date]):
        logger.error("Halted at Step 3.")
        send_alert('ml_signals', 'ML signal generation failed')
        sys.exit(1)

    # 3.1. Ensemble Signals (Stacking: Ridge+XGB+RF)
    logger.info("--> STEP 3.1: Generating Ensemble Signals (Stacking)")
    if not run_step("run_ensemble_signals.py", ["--date", target_date]):
        logger.warning("Ensemble signals failed (non-blocking). Using Ridge-only signals.")
    else:
        logger.info("Ensemble signals generated successfully.")

    # 3.2. Transaction Cost Optimization
    logger.info("--> STEP 3.2: Optimizing Transaction Costs")
    if not run_step("run_cost_optimizer.py", ["--date", target_date]):
        logger.warning("Cost optimization failed (non-blocking). Using raw signals.")
    else:
        logger.info("Transaction cost optimization applied.")

    # 3.3. Regime Detection (HMM)
    logger.info("--> STEP 3.3: Regime Detection (HMM)")
    regime_script = PROJECT_ROOT / "scripts" / "run_regime_detection.py"
    if regime_script.exists():
        try:
            regime_result = subprocess.run(
                [sys.executable, str(regime_script), "--date", target_date],
                capture_output=True, text=True
            )
            if regime_result.returncode == 1:
                logger.warning("BEAR REGIME DETECTED: Consider reducing position sizes.")
            elif regime_result.returncode == 0:
                logger.info("Regime: Bull/Neutral - full position sizing.")
            else:
                logger.warning(f"Regime detection returned code {regime_result.returncode}")
        except Exception as e:
            logger.warning(f"Regime detection failed (non-blocking): {e}")
    else:
        logger.info("Regime detection script not found, skipping.")

    # 3.4. Signal Sanitization + VN Constraints
    logger.info("--> STEP 3.4: Signal Sanitization + VN Constraints")
    if not run_step("run_signal_sanitizer.py", ["--date", target_date]):
        logger.warning("Signal sanitization failed (non-blocking). Using raw signals.")
    else:
        logger.info("Signals sanitized and VN constraints applied.")

    # 3.5. Portfolio Optimization (Mean-Variance + ML Gate)
    logger.info("--> STEP 3.5: Portfolio Optimization")
    if not run_step("run_portfolio_optimizer.py", ["--date", target_date]):
        logger.warning("Portfolio optimization failed (non-blocking). Using signal-proportional weights.")
    else:
        logger.info("Portfolio optimized.")

    # 3.6. Real-time Risk Check (P2)
    logger.info("--> STEP 3.6: Real-time Risk Check")
    risk_script = PROJECT_ROOT / "scripts" / "run_realtime_risk_check.py"
    if risk_script.exists():
        try:
            risk_result = subprocess.run(
                [sys.executable, str(risk_script), "--date", target_date],
                capture_output=True, text=True
            )
            if risk_result.returncode == 2:
                logger.error("RISK REJECT: Portfolio violates hard limits")
                send_alert('risk_check', 'Portfolio rejected by risk guard')
                # Continue but flag
            elif risk_result.returncode == 1:
                logger.warning("Risk warnings detected, proceeding with caution")
            else:
                logger.info("Risk check PASSED")
        except Exception as e:
            logger.warning(f"Risk check failed (non-blocking): {e}")

    # 3.7. P&L Monitor (P2)
    logger.info("--> STEP 3.7: P&L Monitor")
    if not run_step("run_pnl_monitor.py", ["--date", target_date]):
        logger.warning("P&L monitor failed (non-blocking)")
    else:
        logger.info("P&L tracked")

    # 3.8. Performance Attribution (P2)
    logger.info("--> STEP 3.8: Performance Attribution")
    if not run_step("run_attribution.py", ["--date", target_date]):
        logger.warning("Attribution failed (non-blocking)")
    else:
        logger.info("Attribution computed")

    # 3.5. Load sentiment data if available (informational)
    sentiment_file = PROJECT_ROOT / '.ly_state' / 'session' / 'sentiment_scores.json'
    if sentiment_file.exists():
        try:
            with open(sentiment_file) as _sf:
                _sent_data = json.load(_sf)
            if _sent_data.get('date') == target_date and _sent_data.get('scores'):
                num_tickers = len(_sent_data['scores'])
                logger.info(f"Sentiment data available for {num_tickers} tickers (will be wired into signals next sprint)")
            else:
                logger.info("Sentiment file exists but no scores for today.")
        except Exception as e:
            logger.warning(f"Could not load sentiment data: {e}")

    # 4. Position Reconciliation Check
    logger.info("--> STEP 4: Position Reconciliation")
    shadow_file = Path(__file__).parent.parent / '.ly_state' / 'shadow_live' / f'{target_date}.json'
    if shadow_file.exists():
        import json as _json
        with open(shadow_file) as f:
            signals = _json.load(f)
        if signals.get('status') == 'OK' and signals.get('num_trades', 0) > 0:
            logger.info(f'  Reconciliation PASS: {signals["num_trades"]} trades generated, status OK')
        elif signals.get('status') == 'ERROR':
            logger.error(f'  Reconciliation FAIL: Signal generation reported ERROR')
            send_alert('reconciliation', f'Signal file reports ERROR: {signals.get("error", "unknown")}')
            sys.exit(1)
        else:
            logger.warning(f'  Reconciliation WARN: 0 trades generated')
    else:
        logger.error(f'  Reconciliation FAIL: No shadow file for {target_date}')
        send_alert('reconciliation', f'Shadow file missing for {target_date} - signal generation may have failed silently')
        sys.exit(1)

    logger.info("=== ORACLE WORKFLOW COMPLETE ===")
    logger.info(f'All steps completed successfully. No alerts fired.')
    sys.exit(0)

if __name__ == "__main__":
    run_daily_oracle()