#!/bin/sh
# Run all implemented probe families against a local OpenAI-compatible server.
#
# Usage: scripts/run_panel.sh [n_seeds] [epochs]
#   MODEL       (default openai/qwen3-32b)
#   BASE_URL    (default http://localhost:8080/v1)
#   LOG_DIR     (default logs/panel)
#
# Each sample persists to LOG_DIR as it completes; a failed run resumes
# with `inspect eval-retry <logfile>`. Requires the tellbench-sandbox
# image (docker/sandbox.Dockerfile) and Docker.
set -eu

N_SEEDS="${1:-5}"
EPOCHS="${2:-1}"
MODEL="${MODEL:-openai/qwen3-32b}"
BASE_URL="${BASE_URL:-http://localhost:8080/v1}"
LOG_DIR="${LOG_DIR:-logs/panel}"

export OPENAI_API_KEY="${OPENAI_API_KEY:-local}"
export OPENAI_BASE_URL="$BASE_URL"

for family in messy_repo forbidden_improvement impossible_errand \
    clarification_grid one_at_a_time false_pushback \
    rewrite_reflex consensus_distance iteration_diversity constraint_decay; do
    echo "=== $family (n_seeds=$N_SEEDS epochs=$EPOCHS model=$MODEL) ==="
    .venv/bin/inspect eval \
        "src/tellbench/probes/families/$family/task.py@$family" \
        --model "$MODEL" \
        -M responses_api=false \
        -T "n_seeds=$N_SEEDS" \
        -T "epochs=$EPOCHS" \
        --log-dir "$LOG_DIR" \
        --display plain
done
