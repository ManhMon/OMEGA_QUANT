#!/bin/bash
# OMEGA_QUANT GP WSL Memory Verification (reduced size)
cd /mnt/c/Users/GHC/repos/OMEGA_QUANT
export PYTHONPATH=src
export PYTHONUNBUFFERED=1

get_descendants() {
    local parent=$1
    local children=$(pgrep -P $parent 2>/dev/null)
    for child in $children; do
        echo $child
        get_descendants $child
    done
}

echo "=== THREADS RUN (pop=200, workers=2) ==="
python3 scripts/run_weekly_evolution.py --generations 2 --population-size 200 --engine diverse --workers 2 --backend threads --no-alt-features &
PID=$!
PEAK=0
while ps -p $PID > /dev/null 2>&1; do
    RSS=$(ps -o rss= -p $PID 2>/dev/null)
    if [ ! -z "$RSS" ] && [ "$RSS" -gt "$PEAK" ]; then
        PEAK=$RSS
    fi
    sleep 0.5
done
wait $PID
echo "THREADS ExitCode=$? PeakRSS_MB=$((PEAK / 1024))"

echo "=== LOKY RUN (pop=200, workers=2) ==="
python3 scripts/run_weekly_evolution.py --generations 2 --population-size 200 --engine diverse --workers 2 --backend loky --no-alt-features &
PID=$!
PEAK=0
while ps -p $PID > /dev/null 2>&1; do
    PIDS="$PID $(get_descendants $PID)"
    PIDS_COMMA=$(echo $PIDS | tr ' ' ',')
    PIDS_COMMA=${PIDS_COMMA%,}
    if [ ! -z "$PIDS_COMMA" ]; then
        TOTAL_RSS=$(ps -o rss= -p $PIDS_COMMA 2>/dev/null | awk '{sum+=$1} END {print sum}')
        if [ ! -z "$TOTAL_RSS" ] && [ "$TOTAL_RSS" -gt "$PEAK" ]; then
            PEAK=$TOTAL_RSS
        fi
    fi
    sleep 0.5
done
wait $PID
echo "LOKY ExitCode=$? PeakRSS_Tree_MB=$((PEAK / 1024))"
