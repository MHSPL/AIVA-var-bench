#!/bin/bash
# Overnight runner for Gemini Argon (google/gemini-4-argon) in a detached screen session
# Runs on the frozen 2,894 AIVA Bench v1 variants (data/aiva_bench_variants_v1_input.jsonl)
# Concurrency: 7

cd "$(dirname "$0")/.." || exit 1
mkdir -p Results_Gemini_4_Argon_Analysis

PYTHON_BIN="/Users/arunbodd/miniconda3/bin/python3"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

INPUT_FILE="data/aiva_bench_variants_v1_input.jsonl"
LOG="Results_Gemini_4_Argon_Analysis/argon_run.log"
SCREEN_NAME="argon_run"

# Check if screen session already exists
if screen -list | grep -q "\.${SCREEN_NAME}[[:space:]]"; then
    echo "Warning: A screen session named '$SCREEN_NAME' is already running!"
    echo "Attach to it with: screen -r $SCREEN_NAME"
    exit 1
fi

echo "=========================================================="
echo " Launching Gemini Argon (google/gemini-4-argon) [Concurrency 7]"
echo " Screen Name: $SCREEN_NAME"
echo " Dataset:     2,894 variants ($INPUT_FILE)"
echo " Concurrency: 7"
echo " Log file:    $LOG"
echo "=========================================================="

screen -dmS "$SCREEN_NAME" bash -c "cd '$(pwd)' && '$PYTHON_BIN' -u scripts/run_argon_overnight.py --input '$INPUT_FILE' --concurrency 7 2>&1 | tee -a '$LOG'"

sleep 1

if screen -list | grep -q "\.${SCREEN_NAME}[[:space:]]"; then
    echo "Screen session '$SCREEN_NAME' successfully launched!"
    echo ""
    echo "Commands to monitor and manage:"
    echo "  1. Attach to screen:       screen -r $SCREEN_NAME  (detach anytime with Ctrl+A, D)"
    echo "  2. Follow live log:        tail -f $LOG"
    echo "  3. Check completed count:  wc -l Results_Gemini_4_Argon_Analysis/argon_full.jsonl"
    echo "  4. List running screens:   screen -list"
    echo "  5. Stop screen session:    screen -X -S $SCREEN_NAME quit"
    echo "=========================================================="
else
    echo "Fallback to nohup background run..."
    nohup "$PYTHON_BIN" -u scripts/run_argon_overnight.py --input "$INPUT_FILE" --concurrency 7 >> "$LOG" 2>&1 &
    PID=$!
    echo "Runner started in background! PID: $PID"
fi
