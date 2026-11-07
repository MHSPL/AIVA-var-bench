#!/bin/bash
# Full-cohort classification, Sonnet then Opus, concurrency 10.
# Resume is on: re-running this exact script picks up wherever it stopped.
set -a; source .env; set +a
cd "$(dirname "$0")"
for pair in "anthropic/claude-sonnet-5-5:Results_Claude_Sonnet_5_5_Analysis/sonnet_full.jsonl" \
            "anthropic/claude-opus-5-5:Results_Claude_Opus_5_5_Analysis/opus_full.jsonl"; do
  model="${pair%%:*}"; out="${pair#*:}"
  echo "=== $(date '+%F %T')  starting $model ==="
  python3 -u scripts/classify.py \
    --input data/erepo_bias_intervar_merged.jsonl \
    --output "$out" --model "$model" --concurrency 10
  echo "=== $(date '+%F %T')  finished $model (exit $?) ==="
done
