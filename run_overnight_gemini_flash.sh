#!/bin/bash
# Full-cohort classification, Gemini 3.8 Flash, concurrency 10.
# Resume is enabled: skips the 2,627 variants already completed, classifying remaining 5,760.
cd "$(dirname "$0")" || exit 1

set -a; source .env; set +a
unset SSL_CERT_FILE
export MPLCONFIGDIR=/tmp/mpl_cache
PYTHON_BIN="/tmp/aiva_env/bin/python3"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

model="google/gemini-3.8-flash"
out="Results_Gemini_3_8_Flash_Analysis/gemini_flash_full.jsonl"
mkdir -p "$(dirname "$out")"
passlog="$(mktemp -t gemini_flash_pass)"
trap 'rm -f "$passlog"' EXIT

# Up to 10 resume passes
for pass in {1..10}; do
  echo "=== $(date '+%F %T')  pass $pass  $model ==="
  "$PYTHON_BIN" -u scripts/classify.py \
    --input data/erepo_bias_intervar_merged.jsonl \
    --output "$out" --model "$model" --concurrency 10 | tee "$passlog"
  rc=${PIPESTATUS[0]}
  echo "=== $(date '+%F %T')  pass $pass finished (exit $rc) ==="
  if grep -q "Nothing left to classify" "$passlog"; then
    break
  fi
  sleep 30
done
echo "=== $(date '+%F %T')  ALL DONE ==="
