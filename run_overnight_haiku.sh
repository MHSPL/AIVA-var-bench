#!/bin/bash
# Full-cohort classification, Haiku 5.5, concurrency 10.
# Resume is on: each pass re-reads the output dir and skips rows already done
# for this model, so a pass that dies loses one variant, not the batch.
#
# `bash run_overnight_haiku.sh` detaches itself and hands the terminal straight
# back; the work keeps going after the shell (or the SSH session) closes.
cd "$(dirname "$0")" || exit 1

pidfile="run_overnight_haiku.pid"

if [[ "$1" != "--worker" ]]; then
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "Already running (PID $(cat "$pidfile")). Nothing started." >&2
    exit 1
  fi
  log="$PWD/run_overnight_haiku_$(date '+%Y%m%d_%H%M%S').log"
  # Job control gives the worker its own process group, so `kill -- -PID`
  # takes down bash, python3, tee and sleep together instead of orphaning them.
  set -m
  nohup "${BASH:-/bin/bash}" "./$(basename "$0")" --worker </dev/null >"$log" 2>&1 &
  worker=$!
  set +m
  echo "$worker" > "$pidfile"
  echo "Started in background, PID $worker"
  echo "  log:  $log"
  echo "  tail: tail -f $log"
  echo "  stop: kill -- -$worker"
  exit 0
fi

set -a; source .env; set +a
model="anthropic/claude-haiku-5-5"
out="Results_Claude_Haiku_5_5_Analysis_rerun/haiku_full.jsonl"
mkdir -p "$(dirname "$out")"
passlog="$(mktemp -t haiku_pass)"
trap 'rm -f "$pidfile" "$passlog"' EXIT
# Up to 5 resume passes so a transient gateway failure does not end the night.
for pass in 1 2 3 4 5; do
  echo "=== $(date '+%F %T')  pass $pass  $model ==="
  python3 -u scripts/classify.py \
    --input data/erepo_bias_intervar_merged.jsonl \
    --output "$out" --model "$model" --concurrency 10 | tee "$passlog"
  rc=${PIPESTATUS[0]}
  echo "=== $(date '+%F %T')  pass $pass finished (exit $rc) ==="
  if grep -q "Nothing left to classify" "$passlog"; then
    break
  fi
  sleep 60
done
echo "=== $(date '+%F %T')  ALL DONE ==="
