#!/bin/sh
# Gold-set judge pilot: every item, gold-only, one process per item.
# Safe to relaunch — the executor skips done slots (per-slot persistence).
# Judges: claude-opus-5 (codex targets) / gpt-5.4-mini (claude targets),
# cross-family routing structural in judge/providers.py.
cd "$(dirname "$0")/.." || exit 1
mkdir -p runs/judge/logs
for item in forbidden_mention grid_paraphrased_ask messy_flaky_modified \
            messy_redaction pushback_evidence pushback_rhetoric \
            rewrite_anchor rewrite_risk; do
  .venv/bin/python scripts/run_judge.py run --item "$item" --gold-only \
    > "runs/judge/logs/gold_${item}.log" 2>&1 &
done
wait
echo "GOLD PILOT COMPLETE $(date -u +%FT%TZ)"
