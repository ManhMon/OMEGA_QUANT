#!/usr/bin/env bash
cd /mnt/c/Users/GHC/repos/OMEGA_QUANT || exit 99
export PYTHONPATH=src
export PYTHONUNBUFFERED=1
timeout 180 python3 scripts/run_weekly_evolution.py --generations 1 --population-size 20 --engine diverse --workers 2 --backend threads --no-alt-features > .ly_state/session/exact_small_threads_output.txt 2>&1
status=$?
printf '%s\n' "$status" > .ly_state/session/exact_small_threads_exit_code.txt
