#!/bin/bash
# Runner for GPT Astra (openai/gpt-6-astra) in a detached screen session
# Runs on the frozen 2,894 AIVA Bench v1 variants (data/aiva_bench_variants_v1_input.jsonl)
# Concurrency: 7

cd "$(dirname "$0")/.." || exit 1
mkdir -p Results_GPT_6_Astra_Analysis

PYTHON_BIN="/Users/arunbodd/miniconda3/bin/python3"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

INPUT_FILE="data/aiva_bench_variants_v1_input.jsonl"
LOG="Results_GPT_6_Astra_Analysis/astra_run.log"
SCREEN_NAME="astra_run"

# Check if screen session already exists
if screen -list | grep -q "\.${SCREEN_NAME}[[:space:]]"; then
    echo "Warning: A screen session named '$SCREEN_NAME' is already running!"
    echo "Attach to it with: screen -r $SCREEN_NAME"
    exit 1
fi

echo "=========================================================="
echo " Launching GPT Astra (openai/gpt-6-astra) in Detached Screen"
echo " Screen Name: $SCREEN_NAME"
echo " Dataset:     2,894 variants ($INPUT_FILE)"
echo " Concurrency: 7"
echo " Log file:    $LOG"
echo "=========================================================="

screen -dmS "$SCREEN_NAME" bash -c "cd '$(pwd)' && '$PYTHON_BIN' -u scripts/run_astra_overnight.py --input '$INPUT_FILE' --concurrency 7 2>&1 | tee -a '$LOG'"

sleep 1

if screen -list | grep -q "\.${SCREEN_NAME}[[:space:]]"; then
    echo "Screen session '$SCREEN_NAME' successfully launched!"
    echo ""
    echo "Commands to monitor and manage:"
    echo "  1. Attach to screen:       screen -r $SCREEN_NAME  (detach anytime with Ctrl+A, D)"
    echo "  2. Follow live log:        tail -f $LOG"
    echo "  3. Check completed count:  wc -l Results_GPT_6_Astra_Analysis/astra_full.jsonl"
    echo "  4. List running screens:   screen -list"
    echo "  5. Stop screen session:    screen -X -S $SCREEN_NAME quit"
    echo "=========================================================="
else
    echo "Error: Failed to launch screen session '$SCREEN_NAME'."
    exit 1
fi
