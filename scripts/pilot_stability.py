"""Pilot: approach-stability consistency over already-captured runs files.

Read-only. Groups stored runs by (family, condition, model, effort, arm) —
condition is the instance_id with its seed stripped, so groups pool the
seed-rotated siblings of one probe condition under one arm (the stored
panels ran every instance once; true same-instance repeats arrive with the
approach_stability family). For every group with >= 2 runs it extracts the
deterministic approach signature per run and computes set-level
consistency (scoring.stability), writing one JSON line per group and
printing aggregate tables.

Usage:
    python scripts/pilot_stability.py [--out runs/pilot_stability.jsonl]
        [--families messy_repo,impossible_errand,...] [files...]

Defaults: all runs/*.jsonl except *.errors.jsonl, all_runs.jsonl and
combined_panel.jsonl (cross-arm aggregates), restricted to families whose
runs carry real tool streams.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tellbench.schema.events import ToolCall
from tellbench.scoring.stability import group_consistency, signature

_DEFAULT_FAMILIES = (
    "approach_stability",
    "messy_repo",
    "forbidden_improvement",
    "impossible_errand",
    "false_pushback",
    "one_at_a_time",
    "clarification_grid",
)
_SEED_IN_ID = re.compile(r"^([a-z_]+)-(\d{6})-(.+)$")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="runs files (default: runs/*.jsonl)")
    parser.add_argument("--out", default="runs/pilot_stability.jsonl")
    parser.add_argument("--families", default=",".join(_DEFAULT_FAMILIES))
    parser.add_argument(
        "--per-instance",
        action="store_true",
        help="group by full instance_id (same-instance k-repeats, e.g. "
        "approach_stability) instead of pooling seed-rotated siblings",
    )
    return parser.parse_args(argv)


def default_files() -> list[str]:
    excluded = ("all_runs.jsonl", "combined_panel.jsonl")
    return sorted(
        str(p)
        for p in Path("runs").glob("*.jsonl")
        if not p.name.endswith(".errors.jsonl") and p.name not in excluded
    )


def load_groups(
    files: list[str], families: frozenset[str], per_instance: bool = False
) -> tuple[dict[tuple, list], int, int]:
    """Group (family, condition, model, effort, arm) -> list of tool-call
    tuples; condition keeps the seed when per_instance is set. Returns
    (groups, runs_read, runs_skipped)."""

    groups: dict[tuple, list] = defaultdict(list)
    runs_read = 0
    skipped = 0
    for path in files:
        with open(path) as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                trace = record.get("trace") or {}
                meta = trace.get("meta") or {}
                match = _SEED_IN_ID.match(meta.get("instance_id") or "")
                if match is None:
                    skipped += 1
                    continue
                family = match.group(1)
                condition = (
                    f"{match.group(2)}-{match.group(3)}"
                    if per_instance
                    else match.group(3)
                )
                runs_read += 1
                if family not in families:
                    continue
                key = (
                    family,
                    condition,
                    record.get("requested_model") or meta.get("model") or "?",
                    record.get("effort") or "default",
                    record.get("arm") or "?",
                )
                calls = tuple(
                    ToolCall(
                        index=tc.get("index", i),
                        name=tc.get("name", ""),
                        arguments=tc.get("arguments", ""),
                    )
                    for i, tc in enumerate(trace.get("tool_calls") or ())
                )
                groups[key].append(calls)
    return groups, runs_read, skipped


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    families = frozenset(f for f in args.families.split(",") if f)
    files = args.files or default_files()
    groups, runs_read, skipped = load_groups(files, families, args.per_instance)

    rows = []
    with open(args.out, "w") as out:
        for key in sorted(groups):
            runs = groups[key]
            if len(runs) < 2:
                continue
            stats = group_consistency(tuple(signature(calls) for calls in runs))
            family, condition, model, effort, arm = key
            row = {
                "family": family,
                "condition": condition,
                "model": model,
                "effort": effort,
                "arm": arm,
                **stats.model_dump(),
            }
            out.write(json.dumps(row) + "\n")
            rows.append(row)

    print(
        f"files={len(files)} runs_read={runs_read} unparseable_skipped={skipped} "
        f"scorable_groups={len(rows)} -> {args.out}"
    )
    _print_rollup(rows, by=("family",))
    _print_rollup(rows, by=("family", "model"))
    return 0


def _print_rollup(rows: list[dict], by: tuple[str, ...]) -> None:
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        buckets[tuple(row[k] for k in by)].append(row)
    print(f"\n== rollup by {'+'.join(by)} ==")
    header = f"{'+'.join(by):48s} {'groups':>6} {'runs':>5} {'seq':>6} {'reads':>6} {'edits':>6} {'flags':>6} {'1-seq/run':>9}"
    print(header)
    for key in sorted(buckets):
        bucket = buckets[key]
        n_groups = len(bucket)
        n_runs = sum(r["n_runs"] for r in bucket)
        mean = lambda field: sum(r[field] for r in bucket) / n_groups  # noqa: E731
        # fraction of groups whose runs all share ONE exact action sequence
        unanimous = sum(1 for r in bucket if r["distinct_sequences"] == 1) / n_groups
        print(
            f"{' '.join(key):48s} {n_groups:6d} {n_runs:5d} "
            f"{mean('seq_mean'):6.3f} {mean('reads_mean'):6.3f} "
            f"{mean('edits_mean'):6.3f} {mean('flag_agreement'):6.3f} "
            f"{unanimous:9.3f}"
        )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
