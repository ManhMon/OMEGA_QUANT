#!/usr/bin/env bash
set -u
cd /mnt/c/Users/GHC/repos/OMEGA_QUANT || exit 99
export PYTHONPATH=src
export PYTHONUNBUFFERED=1
timeout 540 python3 scripts/run_weekly_evolution.py --generations 2 --population-size 200 --engine diverse --workers 4 --backend threads --no-alt-features 2>threads_diag_stderr.log
status=$?
printf 'EXIT_CODE=%s\n' "$status"
printf '\nDMESG\n'
dmesg 2>/dev/null | grep -i 'killed process' | tail -5
if [ -r /var/log/kern.log ]; then
  printf '\nKERN_LOG\n'
  grep -i 'killed process' /var/log/kern.log | tail -5
fi
