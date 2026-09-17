#!/usr/bin/env bash
set -euo pipefail

cd /mnt/c/Users/GHC/repos/OMEGA_QUANT
activate_path="$HOME/.venv/bin/activate"

if [[ -f "$activate_path" ]]; then
  source "$activate_path"
elif [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
elif [[ -f venv/bin/activate ]]; then
  source venv/bin/activate
else
  echo "Missing virtualenv activation script. Checked: $activate_path, .venv/bin/activate, venv/bin/activate" >&2
  exit 97
fi

export PYTHONPATH=src
export PYTHONUNBUFFERED=1

python3 scripts/run_weekly_evolution.py \
  --engine diverse \
  --regime sideways \
  --generations 1 \
  --population-size 20 \
  --workers 1 \
  --backend threads \
  --orthogonalize promoted
