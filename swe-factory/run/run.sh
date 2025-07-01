#!/bin/bash
set -euo pipefail

MODEL="deepseek/deepseek-chat-v3-0324"
# You can change MODEL to your preferred LLM, e.g., "gpt-3.5-turbo-0125"

# Path to your single dataset file
TASKS_MAP="/home/zohaib/Zohaib/Skylabs AI/swe-factory/swe-factory/data_collection/collect/data/catchorg/Catch2/instances_versions.jsonl"
SETUP_DIR="testbed"
ROUND=5
NUM_PROCS=5
TEMP=0.2

if [ ! -f "$TASKS_MAP" ]; then
  echo "❌ Missing file: $TASKS_MAP"
  exit 1
fi

cleanup() {
  docker ps -a -q | xargs -r docker rm -f || true
  docker image prune -af || true
  rm -rf "$SETUP_DIR"
}

cleanup

OUT_DIR="output_test1/catchorg_Catch2/${MODEL}/round_${ROUND}"
RESULT_DIR="output_test1/catchorg_Catch2/${MODEL}/results"
mkdir -p "$OUT_DIR"

python app/main.py swe-bench \
  --model "$MODEL" \
  --tasks-map "$TASKS_MAP" \
  --num-processes "$NUM_PROCS" \
  --model-temperature "$TEMP" \
  --conv-round-limit "$ROUND" \
  --output-dir "$OUT_DIR" \
  --setup-dir "$SETUP_DIR" \
  --results-path "$RESULT_DIR"
