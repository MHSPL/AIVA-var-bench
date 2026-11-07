#!/bin/bash
# Gemini 3.8 Flash on the 2,627-variant subset the Sonnet rerun covered, concurrency 10.
# Resume is on: each pass re-reads the output dir and skips rows already done for this
# model, so a pass that dies loses one variant, not the batch.
#
# Launch it detached so it outlives the terminal (or agent session) that started it:
#   python3 detach_run.py ./run_gemini_flash_2627.sh
cd "$(dirname "$0")" || exit 1

set -a; source .env; set +a
model="google/gemini-3.8-flash"
out="Results_Gemini_3_8_Flash_Analysis/gemini_flash_2627.jsonl"
mkdir -p "$(dirname "$out")"
passlog="$(mktemp -t gemini_flash_pass)"
trap 'rm -f "$passlog"' EXIT
# Up to 5 resume passes so a transient gateway failure does not end the run.
for pass in 1 2 3 4 5; do
  echo "=== $(date '+%F %T')  pass $pass  $model ==="
  python3 -u scripts/classify.py \
    --input data/erepo_subset_2627.jsonl \
    --output "$out" --model "$model" --concurrency 10 | tee "$passlog"
  rc=${PIPESTATUS[0]}
  echo "=== $(date '+%F %T')  pass $pass finished (exit $rc) ==="
  if grep -q "Nothing left to classify" "$passlog"; then
    break
  fi
  sleep 60
done
echo "=== $(date '+%F %T')  ALL DONE ==="
