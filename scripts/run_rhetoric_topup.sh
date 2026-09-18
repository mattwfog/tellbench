#!/bin/sh
# pushback_rhetoric judge completion + firm-up (2026-08-19):
#   1) resume the haiku re-judge (executor skips persisted slots)
#   2) top up every non-unanimous rhetoric instance to 9 rounds
#      (majority over odd rounds -> no ties; slot ids carry the round
#      index, so this is resumable and idempotent like every run)
# Launch detached so a supervising process cannot reap a long run:
#   nohup sh scripts/run_rhetoric_topup.sh > runs/judge/logs/rhetoric_topup.log 2>&1 &
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python

echo "== step 1: finish 5-round coverage $(date -u +%FT%TZ)"
$PY scripts/run_judge.py run --item pushback_rhetoric

echo "== step 2: compute non-unanimous instances"
$PY - <<'EOF'
import json
from collections import Counter
from pathlib import Path

last = {}
for l in Path("runs/judge/verdicts_pushback_rhetoric.jsonl").read_text().splitlines():
    r = json.loads(l)
    last[r["slot_id"]] = r
votes: dict[str, Counter] = {}
for r in last.values():
    if r["verdict"] is None:
        continue
    votes.setdefault(r["instance_key"], Counter())[r["verdict"]] += 1
split = sorted(k for k, c in votes.items() if len(c) > 1)
Path("runs/judge/rhetoric_topup.keys").write_text("\n".join(split) + "\n")
arms = Counter(k.split("|")[1] for k in split)
print(f"{len(split)} non-unanimous instances -> rhetoric_topup.keys "
      f"(~{4 * len(split)} new slots); by arm: {dict(sorted(arms.items()))}")
EOF

echo "== step 3: top up to 9 rounds $(date -u +%FT%TZ)"
$PY scripts/run_judge.py run --item pushback_rhetoric \
  --keys-file runs/judge/rhetoric_topup.keys --rounds 9

echo "RHETORIC JUDGE COMPLETE $(date -u +%FT%TZ)"
