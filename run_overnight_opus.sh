#!/bin/bash
# Full-cohort classification, Opus 5.5, concurrency 5.
# Resume is on: each pass re-reads the output dir and skips rows already done
# for this model, so a pass that dies loses one variant, not the batch.
#
# Launch it detached so it outlives the terminal (or agent session) that
# started it:  /tmp/aiva_env/bin/python3 detach_run.py ./run_overnight_opus.sh
cd "$(dirname "$0")" || exit 1

set -a; source .env; set +a
PYTHON_BIN="/tmp/aiva_env/bin/python3"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

model="anthropic/claude-opus-5-5"
out="Results_Claude_Opus_5_5_Analysis_rerun/opus_full.jsonl"
mkdir -p "$(dirname "$out")"
passlog="$(mktemp -t opus_pass)"
trap 'rm -f "$passlog"' EXIT
# Up to 10 resume passes so a transient gateway failure does not end the run.
for pass in {1..10}; do
  echo "=== $(date '+%F %T')  pass $pass  $model ==="
  "$PYTHON_BIN" -u scripts/classify.py \
    --input data/erepo_bias_intervar_merged.jsonl \
    --output "$out" --model "$model" --concurrency 5 | tee "$passlog"
  rc=${PIPESTATUS[0]}
  echo "=== $(date '+%F %T')  pass $pass finished (exit $rc) ==="
  if grep -q "Nothing left to classify" "$passlog"; then
    break
  fi
  sleep 30
done
echo "=== $(date '+%F %T')  ALL DONE ==="
