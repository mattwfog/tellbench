#!/bin/sh
# Codex model x reasoning-effort matrix over the probe families.
#
# Same shape as run_family_panel.sh: arms parallel in waves within a
# family, families sequential, per-arm runs/errors/log files, resumable
# via the runner's done-key skip, disk-floor guard. Arm list is
# label:model:effort; empty effort = the user's config default.
#
# Model list source of truth: the CLI's own embedded metadata (slugs in
# the vendored codex binary) — session history proved unreliable
# (2026-07-11: archived gpt-5.2-codex/5.3-codex no longer exist in
# codex-cli 0.144.1 and error out; gpt-5.4-mini/5.6-luna/5.6-terra were
# missing from history).

set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python

if [ "${TELLBENCH_DRY_RUN:-}" = "1" ]; then
    PY="echo DRY .venv/bin/python"
fi

FAMILIES="${TELLBENCH_FAMILIES:-messy_repo forbidden_improvement impossible_errand clarification_grid}"

_default_arms() {
    for pair in \
        gpt-5.6-sol gpt-5.6-luna gpt-5.6-terra gpt-5.5 gpt-5.4 gpt-5.4-mini gpt-5.2; do
        printf '%s:%s: ' "codex-$pair" "$pair"
        for tier in low medium high xhigh; do
            printf '%s:%s:%s ' "codex-${pair}_$tier" "$pair" "$tier"
        done
    done
}

ARMS="${TELLBENCH_ARMS:-$(_default_arms)}"
JOBS="${TELLBENCH_JOBS:-4}"
SEEDS="${TELLBENCH_SEEDS:-0-2}"
K="${TELLBENCH_K:-1}"

DISK_FLOOR_KIB=1048576 # 1 GiB

check_disk() {
    while :; do
        avail=$(df -k . | awk 'NR==2 {print $4}')
        if [ "$avail" -ge "$DISK_FLOOR_KIB" ]; then
            break
        fi
        echo "DISK LOW: ${avail}KiB available, pausing 300s"
        sleep 300
    done
}

run_arm() {
    family=$1
    label=$2
    model=$3
    effort=$4
    armlog="runs/${family}_${label}.log"
    set -- --family "$family" \
        --seeds "$SEEDS" --frames both --k "$K" \
        --runs-file "runs/${family}_${label}.jsonl" \
        --errors-file "runs/${family}_${label}.errors.jsonl"
    # empty model = the user's config.toml default (label "codex");
    # empty effort = the model's config-default reasoning tier
    if [ -n "$model" ]; then
        set -- "$@" --model "$model"
    fi
    if [ -n "$effort" ]; then
        set -- "$@" --effort "$effort"
    fi
    $PY -m tellbench.runners.codex_cli "$@" < /dev/null >> "$armlog" 2>&1
    echo "ARM DONE family=$family arm=$label exit=$? $(date -u +%FT%TZ)"
}

echo "CODEX MATRIX START jobs=$JOBS $(date -u +%FT%TZ)"
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
echo "CODEX MATRIX COMPLETE $(date -u +%FT%TZ)"
