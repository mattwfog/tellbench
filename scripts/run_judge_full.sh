#!/bin/sh
# Full judge run: every item, full instance scope, one process per item
# (one writer per verdicts file — panel lesson). Resumable: done slots
# skip on relaunch; null (failed-parse) slots retry on relaunch.
cd "$(dirname "$0")/.." || exit 1
mkdir -p runs/judge/logs
for item in forbidden_mention grid_paraphrased_ask messy_flaky_modified \
            messy_redaction pushback_evidence pushback_rhetoric \
            rewrite_anchor rewrite_risk; do
  .venv/bin/python scripts/run_judge.py run --item "$item" \
    > "runs/judge/logs/full_${item}.log" 2>&1 &
done
wait
echo "FULL JUDGE RUN COMPLETE $(date -u +%FT%TZ)"
