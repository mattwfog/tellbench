"""Judge-layer orchestrator.

Subcommands:
    extract      build runs/judge/instances_<item>.jsonl for every item
                 (or --item one)
    sample-gold  emit stratified gold-labeling sheets for hand-labeling

Execution (paid judge calls) is a separate subcommand added with the
executor; extraction and gold sampling are free and deterministic.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tellbench.judge.extract import EXTRACTORS, JUDGE_DIR, extract_item
from tellbench.judge.items import ITEMS

GOLD_DIR = JUDGE_DIR / "gold"
GOLD_N = 36
GOLD_SEED = 20260802


def cmd_extract(item: str | None) -> None:
    for item_id in [item] if item else sorted(EXTRACTORS):
        out = extract_item(item_id)
        n = sum(1 for _ in out.open())
        print(f"{item_id}: {n} instances -> {out}")


def cmd_sample_gold(item: str | None) -> None:
    """Stratified (by model) sample per item, emitted as a markdown sheet
    with a parallel answers PSV the operator fills in (instance_key|label)."""
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    for item_id in [item] if item else sorted(EXTRACTORS):
        src = JUDGE_DIR / f"instances_{item_id}.jsonl"
        if not src.is_file():
            raise SystemExit(f"run extract first: {src} missing")
        instances = [json.loads(line) for line in src.read_text().splitlines()]
        if not instances:
            print(f"{item_id}: 0 instances — no gold sheet")
            continue
        rng = random.Random(GOLD_SEED)
        by_model: dict[str, list[dict]] = {}
        for inst in instances:
            by_model.setdefault(inst["model"], []).append(inst)
        take = max(1, GOLD_N // len(by_model))
        sample: list[dict] = []
        for model in sorted(by_model):
            pool = by_model[model]
            sample.extend(rng.sample(pool, min(take, len(pool))))
        rng.shuffle(sample)
        sample = sample[:GOLD_N]

        spec = ITEMS[item_id]
        lines = [
            f"# Gold labeling — {item_id}",
            "",
            f"**Question the judge will answer:** {spec.question}",
            "",
            f"**Your job:** fill `{item_id}.answers.psv` with one line per",
            f"instance: `instance_key|{spec.verdict_tokens[0]}` or",
            f"`|{spec.verdict_tokens[1]}`. Sheet has {len(sample)} instances.",
            "",
        ]
        answer_lines = []
        for i, inst in enumerate(sample, 1):
            lines.append(f"---\n\n## {i}. `{inst['instance_key']}`\n")
            for key, value in inst["payload"].items():
                lines.append(f"**{key}**:\n\n```\n{value}\n```\n")
            answer_lines.append(f"{inst['instance_key']}|")
        sheet = GOLD_DIR / f"{item_id}.sheet.md"
        answers = GOLD_DIR / f"{item_id}.answers.psv"
        sheet.write_text("\n".join(lines) + "\n")
        if not answers.exists():  # never clobber labels in progress
            answers.write_text("\n".join(answer_lines) + "\n")
        print(f"{item_id}: {len(sample)} gold instances -> {sheet.name}")


def cmd_run(
    item: str,
    gold_only: bool,
    limit_slots: int | None,
    keys_file: Path | None = None,
    rounds: int | None = None,
) -> None:
    from tellbench.judge.executor import ROUNDS, run_item

    only_keys = None
    if gold_only:
        answers = GOLD_DIR / f"{item}.answers.psv"
        # instance_key itself contains '|' separators — the label is the
        # text after the LAST pipe, so split from the right.
        only_keys = {
            line.rsplit("|", 1)[0]
            for line in answers.read_text().splitlines()
            if line.strip()
        }
    if keys_file is not None:
        file_keys = {l.strip() for l in keys_file.read_text().splitlines() if l.strip()}
        only_keys = file_keys if only_keys is None else only_keys & file_keys
    stats = run_item(
        item,
        only_keys=only_keys,
        limit_slots=limit_slots,
        rounds=rounds if rounds is not None else ROUNDS,
    )
    print(f"{item}: {stats}")


def cmd_validate(item: str, judge: str | None = None) -> None:
    from tellbench.judge.executor import majority

    answers = GOLD_DIR / f"{item}.answers.psv"
    labels = {}
    for line in answers.read_text().splitlines():
        key, _, label = line.rpartition("|")
        if label.strip():
            labels[key] = label.strip().upper()
    verdicts = majority(item, judge=judge)
    both = [k for k in labels if k in verdicts and verdicts[k] is not None]
    if not both:
        print(f"{item}: no overlapping labeled+judged instances yet")
        return
    spec = ITEMS[item]
    canon = {"A": "incremental", "B": "rewrite"} if spec.mode == "pairwise_anchor" else {}
    agree = sum(
        1 for k in both
        if verdicts[k].upper() == canon.get(labels[k], labels[k]).upper()
    )
    print(f"{item}: agreement {agree}/{len(both)} = {agree/len(both):.2f} "
          f"({len(labels)} labeled, {len(verdicts)} judged)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("extract", "sample-gold"):
        p = sub.add_parser(name)
        p.add_argument("--item", default=None, choices=sorted(EXTRACTORS))
    p_run = sub.add_parser("run")
    p_run.add_argument("--item", required=True, choices=sorted(EXTRACTORS))
    p_run.add_argument("--gold-only", action="store_true")
    p_run.add_argument("--limit-slots", type=int, default=None)
    p_run.add_argument("--keys-file", type=Path, default=None,
                       help="restrict to instance_keys listed one-per-line")
    p_run.add_argument("--rounds", type=int, default=None,
                       help="rounds per instance (default executor ROUNDS; "
                            "higher tops up existing slots)")
    p_val = sub.add_parser("validate")
    p_val.add_argument("--item", required=True, choices=sorted(EXTRACTORS))
    p_val.add_argument("--judge", default=None,
                       help="restrict to one judge model's slots")
    args = parser.parse_args()
    if args.cmd == "extract":
        cmd_extract(args.item)
    elif args.cmd == "sample-gold":
        cmd_sample_gold(args.item)
    elif args.cmd == "run":
        cmd_run(args.item, args.gold_only, args.limit_slots,
                keys_file=args.keys_file, rounds=args.rounds)
    else:
        cmd_validate(args.item, judge=args.judge)


if __name__ == "__main__":
    main()
