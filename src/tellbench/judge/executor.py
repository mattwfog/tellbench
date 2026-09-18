"""Judge slot execution: resumable, per-slot persisted, majority-aggregated.

Slots follow hygiene defaults (rounds=5; pairwise items also swap anchor
order). Every completed slot is appended to
runs/judge/verdicts_<item>.jsonl BEFORE the next call starts, and
existing (instance_key, judge, round, order) slots are skipped on
relaunch — a killed run loses at most the in-flight call (fetch-loop
rules). Parse failures persist with verdict null and are re-attempted on
the next relaunch (their slot line is superseded by the later success;
aggregation uses the last line per slot).

Pairwise anchor mapping: order AB presents ANCHOR_INCREMENTAL as A;
order BA swaps. Verdicts normalize to canonical labels
('incremental' / 'rewrite') at write time so aggregation never needs to
know the order.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from tellbench.judge.extract import JUDGE_DIR
from tellbench.judge.items import ITEMS, JudgeItem
from tellbench.judge.providers import (
    CLAUDE_JUDGE_DEFAULT,
    CODEX_JUDGE_DEFAULT,
    call_judge,
    is_claude_family_target,
    judge_provider_for_target,
    parse_verdict,
)

ROUNDS = 5


def build_prompt(item: JudgeItem, payload: dict, order: str) -> str:
    blocks = [item.question, ""]
    if item.mode == "pairwise_anchor":
        first, second = (
            (payload["anchor_a"], payload["anchor_b"])
            if order == "ab"
            else (payload["anchor_b"], payload["anchor_a"])
        )
        blocks += [f"A:\n{first}", "", f"B:\n{second}", ""]
    for key, value in payload.items():
        if key.startswith("anchor_"):
            continue
        blocks += [f"{key.upper()}:\n{value}", ""]
    return "\n".join(blocks)


def canonicalize(item: JudgeItem, order: str, verdict: str | None) -> str | None:
    if verdict is None or item.mode != "pairwise_anchor":
        return verdict
    mapping = (
        {"A": "incremental", "B": "rewrite"}
        if order == "ab"
        else {"A": "rewrite", "B": "incremental"}
    )
    return mapping[verdict]


def slot_id(instance_key: str, judge: str, round_index: int, order: str) -> str:
    return f"{instance_key}#{judge}#{round_index}#{order}"


def done_slots(verdicts_path: Path) -> set[str]:
    done: set[str] = set()
    if verdicts_path.is_file():
        for line in verdicts_path.read_text().splitlines():
            row = json.loads(line)
            if row.get("verdict") is not None:
                done.add(row["slot_id"])
    return done


def run_item(
    item_id: str,
    *,
    only_keys: set[str] | None = None,
    limit_slots: int | None = None,
    rounds: int = ROUNDS,
) -> dict:
    item = ITEMS[item_id]
    instances_path = JUDGE_DIR / f"instances_{item_id}.jsonl"
    verdicts_path = JUDGE_DIR / f"verdicts_{item_id}.jsonl"
    instances = [json.loads(l) for l in instances_path.read_text().splitlines()]
    if only_keys is not None:
        instances = [i for i in instances if i["instance_key"] in only_keys]

    orders = ("ab", "ba") if item.mode == "pairwise_anchor" else ("ab",)
    done = done_slots(verdicts_path)
    attempted = completed = failures = 0
    for inst in instances:
        provider = judge_provider_for_target(inst["model"])
        judge = CODEX_JUDGE_DEFAULT if provider == "codex" else CLAUDE_JUDGE_DEFAULT
        # guard on the judge MODEL NAME vs the target's family — independent
        # of the routing path, and both directions (the haiku short-stem
        # incident was an Anthropic judge on an Anthropic target; the old
        # one-directional prefix check couldn't see it)
        if is_claude_family_target(inst["model"]) == judge.startswith("claude-"):
            raise AssertionError(
                f"same-vendor pairing: judge {judge} on target {inst['model']}"
            )
        for round_index in range(rounds):
            for order in orders:
                sid = slot_id(inst["instance_key"], judge, round_index, order)
                if sid in done:
                    continue
                if limit_slots is not None and attempted >= limit_slots:
                    return {"attempted": attempted, "completed": completed,
                            "failures": failures, "stopped": "limit"}
                attempted += 1
                prompt = build_prompt(item, inst["payload"], order)
                try:
                    output = call_judge(provider, judge, prompt)
                    raw = parse_verdict(output, item.verdict_tokens)
                    error = None
                except Exception as exc:  # noqa: BLE001 — recorded, retried on relaunch
                    output, raw, error = "", None, str(exc)[-300:]
                verdict = canonicalize(item, order, raw)
                with verdicts_path.open("a") as fh:
                    fh.write(json.dumps({
                        "slot_id": sid,
                        "instance_key": inst["instance_key"],
                        "item_id": item_id,
                        "judge_model": judge,
                        "provider": provider,
                        "round": round_index,
                        "order": order,
                        "verdict": verdict,
                        "error": error,
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }) + "\n")
                if verdict is None:
                    failures += 1
                else:
                    completed += 1
    return {"attempted": attempted, "completed": completed, "failures": failures}


def majority(item_id: str, judge: str | None = None) -> dict[str, str | None]:
    """Last verdict per slot, majority per instance; ties -> None.
    judge filters to one judge model's slots (calibration comparisons)."""
    verdicts_path = JUDGE_DIR / f"verdicts_{item_id}.jsonl"
    last: dict[str, dict] = {}
    for line in verdicts_path.read_text().splitlines():
        row = json.loads(line)
        if judge is not None and row["judge_model"] != judge:
            continue
        last[row["slot_id"]] = row
    counts: dict[str, dict[str, int]] = {}
    for row in last.values():
        if row["verdict"] is None:
            continue
        by = counts.setdefault(row["instance_key"], {})
        by[row["verdict"]] = by.get(row["verdict"], 0) + 1
    result: dict[str, str | None] = {}
    for key, by in counts.items():
        ranked = sorted(by.items(), key=lambda kv: -kv[1])
        result[key] = (
            ranked[0][0]
            if len(ranked) == 1 or ranked[0][1] > ranked[1][1]
            else None
        )
    return result
