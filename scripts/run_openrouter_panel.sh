#!/bin/sh
# OpenRouter arm panel: the full Claude-arm scope (mirrors the
# claude-sonnet-4-6 arm's coverage) for one OpenRouter model, via
# run_family_panel.sh with TELLBENCH_RUNNER_ARMS=openrouter.
#   OPENROUTER_API_KEY  required (env, never in the tree)
#   OPENROUTER_MODEL    e.g. stealth/ox-alpha (default)
#   OPENROUTER_LABEL    runs-file label (default: model basename)
# Stages run sequentially; each stage is the resumable family driver.
set -u
cd "$(dirname "$0")/.."
: "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY required}"
export OPENROUTER_MODEL="${OPENROUTER_MODEL:-stealth/ox-alpha}"
LABEL="${OPENROUTER_LABEL:-${OPENROUTER_MODEL##*/}}"
export TELLBENCH_RUNNER_ARMS=openrouter
export TELLBENCH_ARMS="$LABEL:$OPENROUTER_MODEL:"
export TELLBENCH_JOBS="${TELLBENCH_JOBS:-1}"

echo "OPENROUTER PANEL START model=$OPENROUTER_MODEL label=$LABEL $(date -u +%FT%TZ)"
# single-shot, seeds 0-2 k=1
TELLBENCH_FAMILIES="messy_repo forbidden_improvement impossible_errand clarification_grid rewrite_reflex consensus_distance" \
  TELLBENCH_SEEDS=0-2 TELLBENCH_K=1 sh scripts/run_family_panel.sh
# approach_stability: seed 0, k=10
TELLBENCH_FAMILIES="approach_stability" TELLBENCH_SEEDS=0 TELLBENCH_K=10 \
  sh scripts/run_family_panel.sh
# multi-turn families, seeds 0-4 k=1
TELLBENCH_RUNNER_MODULE=tellbench.runners.claude_code_multiturn \
  TELLBENCH_FAMILIES="one_at_a_time false_pushback iteration_diversity constraint_decay" \
  TELLBENCH_SEEDS=0-4 TELLBENCH_K=1 sh scripts/run_family_panel.sh
echo "OPENROUTER PANEL COMPLETE $(date -u +%FT%TZ)"
