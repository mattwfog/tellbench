#!/bin/sh
# Family panel driver: arms run IN PARALLEL within a family, families
# sequential. Each arm owns its runs/errors/log files, so concurrent arms
# never contend on a write path; the driver log carries only orchestration
# lines (ARM/FAMILY/PANEL/DISK), per-run lines live in runs/<family>_<arm>.log.
#
# Resumable by construction: the runner appends each run before starting
# the next and skips run_keys already in its --runs-file, so re-running
# this script continues exactly where it stopped. One arm's failure never
# kills the panel (exit status is logged per arm).
#
# Disk guard: the Data volume has been observed at 0 bytes free; below a
# 1 GiB floor the driver pauses loudly instead of risking truncated
# transcript captures.

set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python

# TELLBENCH_DRY_RUN=1 prints the runner invocations instead of executing —
# verifies loop coverage (24 arms) without spending a run
if [ "${TELLBENCH_DRY_RUN:-}" = "1" ]; then
    PY="echo DRY .venv/bin/python"
fi

# Both lists are env-overridable so matrix runs need no script edits:
#   TELLBENCH_FAMILIES="messy_repo ..." TELLBENCH_ARMS="label:model:effort ..."
FAMILIES="${TELLBENCH_FAMILIES:-forbidden_improvement impossible_errand clarification_grid}"

# runner module: claude_code (single-shot) or claude_code_multiturn
# (scripted multi-turn families via -p --resume)
RUNNER_MODULE="${TELLBENCH_RUNNER_MODULE:-tellbench.runners.claude_code}"

# label:model:effort triples — label keys the per-arm files; empty effort =
# default. Space-separated so a plain for-loop iterates them: no while-read
# pipe, no stdin for a child to slurp.
ARMS="${TELLBENCH_ARMS:-haiku:haiku: opus:opus: sonnet:sonnet: claude-sonnet-4-5:claude-sonnet-4-5: claude-sonnet-4-6:claude-sonnet-4-6: sonnet_low:sonnet:low sonnet_medium:sonnet:medium sonnet_max:sonnet:max}"

# concurrent arms per wave; a wave must finish before the next launches
JOBS="${TELLBENCH_JOBS:-8}"

# seed range forwarded to the runner; multi-turn matrix rounds use 0-4
SEEDS="${TELLBENCH_SEEDS:-0-2}"

# k repeats per (seed, frame) key; approach_stability uses 10
K="${TELLBENCH_K:-1}"

# runner serving-path arm (claude_code.py ARMS): subscription (default),
# api, or kimi — kimi maps KIMI_API_KEY onto the Anthropic-compatible
# Kimi For Coding endpoint behind the :8120 capture proxy
RUNNER_ARMS="${TELLBENCH_RUNNER_ARMS:-subscription}"

DISK_FLOOR_KIB=1048576 # 1 GiB

check_disk() {
    while :; do
        avail=$(df -k . | awk 'NR==2 {print $4}')
        if [ "$avail" -ge "$DISK_FLOOR_KIB" ]; then
            break
        fi
        echo "DISK LOW: ${avail}KiB available on the Data volume, pausing 300s"
        sleep 300
    done
}

run_arm() {
    family=$1
    label=$2
    model=$3
    effort=$4
    armlog="runs/${family}_${label}.log"
    # < /dev/null: the runner (and the claude CLI under it) must never
    # inherit any shared stdin (observed 2026-07-11: a while-read pipe was
    # slurped and the panel silently truncated to one arm per family)
    if [ -n "$effort" ]; then
        $PY -m "$RUNNER_MODULE" \
            --family "$family" --model "$model" --effort "$effort" \
            --seeds "$SEEDS" --frames both --k "$K" --arms "$RUNNER_ARMS" \
            --runs-file "runs/${family}_${label}.jsonl" \
            --errors-file "runs/${family}_${label}.errors.jsonl" \
            < /dev/null >> "$armlog" 2>&1
    else
        $PY -m "$RUNNER_MODULE" \
            --family "$family" --model "$model" \
            --seeds "$SEEDS" --frames both --k "$K" --arms "$RUNNER_ARMS" \
            --runs-file "runs/${family}_${label}.jsonl" \
            --errors-file "runs/${family}_${label}.errors.jsonl" \
            < /dev/null >> "$armlog" 2>&1
    fi
    echo "ARM DONE family=$family arm=$label exit=$? $(date -u +%FT%TZ)"
}

echo "PANEL START parallel-arms jobs=$JOBS $(date -u +%FT%TZ)"
for family in $FAMILIES; do
    launched=0
    for spec in $ARMS; do
        check_disk
        arm_label=${spec%%:*}
        rest=${spec#*:}
        arm_model=${rest%%:*}
        arm_effort=${rest#*:}
        echo "ARM START family=$family arm=$arm_label $(date -u +%FT%TZ)"
        run_arm "$family" "$arm_label" "$arm_model" "$arm_effort" &
        launched=$((launched + 1))
        if [ $((launched % JOBS)) -eq 0 ]; then
            wait
        fi
    done
    wait
    echo "FAMILY DONE family=$family $(date -u +%FT%TZ)"
done
echo "PANEL COMPLETE $(date -u +%FT%TZ)"
