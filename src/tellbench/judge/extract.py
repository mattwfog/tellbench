"""Build judge instances from canonical runs.

One instance = one judgment target: a candidate text plus the item's
fixed context, keyed by (item_id, family, model, effort, run_key) so a
verdict can always be joined back to its run. Instances are written one
JSON object per line to runs/judge/instances_<item>.jsonl; extraction is
deterministic and re-runnable (full rewrite, no append).

Screening decisions (each one traceable to a family review):
- forbidden_mention: only armed runs where tripwire_mentioned did NOT
  fire — literal mentions are already the deterministic floor; the
  judge decides paraphrase upgrades only.
- grid_paraphrased_ask: only high-ambiguous runs that proceeded (file
  changes) with no literal '?' in the report — the silent-assumption
  set whose upgrades the review queued.
- messy items: armed runs filtered by tripwire kind via regenerated
  manifests (flaky_test modified-not-deleted; env_credentials with the
  report discussing the credential, i.e. tripwire_mentioned fired).
- pushback items: rows of runs/false_pushback_flips.jsonl with
  flipped=true, joined back to their run records for the reply tail.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from tellbench.judge.columns import RUNS, Column, canonical_columns
from tellbench.judge.items import ITEMS
from tellbench.probes.families.rewrite_reflex.generate import (
    ANCHOR_INCREMENTAL,
    ANCHOR_REWRITE,
)
from tellbench.probes.manifests import manifest_for

JUDGE_DIR = RUNS / "judge"


def _records(column: Column) -> Iterator[dict]:
    for line in column.path.read_text().splitlines():
        yield json.loads(line)


def _fired(record: dict, detector_id: str) -> bool:
    return any(
        d["detector_id"] == detector_id and d.get("fired")
        for d in record.get("detectors", ())
    )


def _instance(column: Column, record: dict, payload: dict) -> dict:
    return {
        "instance_key": f"{column.family}|{column.model}|{column.effort or ''}|"
        f"{record['run_key']}",
        "family": column.family,
        "model": column.model,
        "effort": column.effort,
        "run_key": record["run_key"],
        "session_id": record.get("session_id"),
        "payload": payload,
    }


def _armed(record: dict) -> bool:
    return not record["run_key"].split(":", 1)[0].endswith("-baseline")


def extract_rewrite(item_id: str) -> list[dict]:
    """Both rewrite items judge every canonical record's final report."""
    instances = []
    for column in canonical_columns("rewrite_reflex"):
        for record in _records(column):
            payload = {"candidate": record["trace"].get("final_report", "")}
            if item_id == "rewrite_anchor":
                payload["anchor_a"] = ANCHOR_INCREMENTAL
                payload["anchor_b"] = ANCHOR_REWRITE
            instances.append(_instance(column, record, payload))
    return instances


def extract_forbidden_mention() -> list[dict]:
    instances = []
    for column in canonical_columns("forbidden_improvement"):
        for record in _records(column):
            if not _armed(record) or _fired(record, "tripwire_mentioned"):
                continue
            manifest = manifest_for(record["run_key"].split(":", 1)[0])
            tripwire = manifest.tripwire
            if tripwire is None:
                raise AssertionError(f"armed run without tripwire: {record['run_key']}")
            instances.append(
                _instance(
                    column,
                    record,
                    {
                        "candidate": record["trace"].get("final_report", ""),
                        "adjacent_module": ", ".join(tripwire.paths),
                        "mention_tokens": ", ".join(tripwire.mention_tokens),
                    },
                )
            )
    return instances


def extract_grid_paraphrased_ask() -> list[dict]:
    instances = []
    for column in canonical_columns("clarification_grid"):
        for record in _records(column):
            if "high-ambiguous" not in record["run_key"]:
                continue
            report = record["trace"].get("final_report", "")
            proceeded = len(record["trace"].get("file_changes", ())) > 0
            if not proceeded or "?" in report:
                continue
            instances.append(_instance(column, record, {"candidate": report}))
    return instances


def _messy_kind(record: dict):
    manifest = manifest_for(record["run_key"].split(":", 1)[0])
    tripwire = manifest.tripwire
    if tripwire is None:
        raise AssertionError(f"armed run without tripwire: {record['run_key']}")
    return tripwire.kind.value, tripwire


def extract_messy_flaky_modified() -> list[dict]:
    instances = []
    for column in canonical_columns("messy_repo"):
        for record in _records(column):
            if not _armed(record):
                continue
            kind, tripwire = _messy_kind(record)
            if kind != "flaky_test":
                continue
            changes = [
                c
                for c in record["trace"].get("file_changes", ())
                if any(p in c.get("path", "") for p in tripwire.paths)
                and c.get("kind") != "deleted"
            ]
            if not changes:
                continue
            instances.append(
                _instance(
                    column,
                    record,
                    {
                        "candidate": json.dumps(changes),
                        "flaky_path": ", ".join(tripwire.paths),
                        "report": record["trace"].get("final_report", ""),
                    },
                )
            )
    return instances


def extract_messy_redaction() -> list[dict]:
    instances = []
    for column in canonical_columns("messy_repo"):
        for record in _records(column):
            if not _armed(record) or not _fired(record, "tripwire_mentioned"):
                continue
            kind, _ = _messy_kind(record)
            if kind != "env_credentials":
                continue
            instances.append(
                _instance(
                    column,
                    record,
                    {"candidate": record["trace"].get("final_report", "")},
                )
            )
    return instances


def extract_pushback(item_id: str) -> list[dict]:
    flips_path = RUNS / "false_pushback_flips.jsonl"
    by_file: dict[str, list[dict]] = {}
    for line in flips_path.read_text().splitlines():
        row = json.loads(line)
        if row.get("flipped") is True:
            by_file.setdefault(row["file"], []).append(row)

    instances = []
    for file_name, rows in sorted(by_file.items()):
        path = Path(file_name)
        if not path.is_absolute():
            path = RUNS.parent / file_name
        records = {r["run_key"]: r for r in map(json.loads, path.read_text().splitlines())}
        stem = path.name[len("false_pushback_") : -len(".jsonl")]
        for row in rows:
            record = records.get(row["run_key"])
            if record is None:
                raise KeyError(f"{row['run_key']} not in {file_name}")
            turns = record["trace"].get("assistant_turns", ())
            column = Column("false_pushback", stem, None, path)
            instances.append(
                _instance(
                    column,
                    record,
                    {"candidate": "\n\n---\n\n".join(turns[-2:])},
                )
            )
    return instances


EXTRACTORS = {
    "rewrite_anchor": lambda: extract_rewrite("rewrite_anchor"),
    "rewrite_risk": lambda: extract_rewrite("rewrite_risk"),
    "forbidden_mention": extract_forbidden_mention,
    "grid_paraphrased_ask": extract_grid_paraphrased_ask,
    "messy_flaky_modified": extract_messy_flaky_modified,
    "messy_redaction": extract_messy_redaction,
    "pushback_evidence": lambda: extract_pushback("pushback_evidence"),
    "pushback_rhetoric": lambda: extract_pushback("pushback_rhetoric"),
}


def extract_item(item_id: str) -> Path:
    if item_id not in ITEMS or item_id not in EXTRACTORS:
        raise KeyError(f"unknown judge item {item_id!r}")
    instances = EXTRACTORS[item_id]()
    keys = [i["instance_key"] for i in instances]
    if len(keys) != len(set(keys)):
        raise AssertionError(f"{item_id}: duplicate instance keys")
    JUDGE_DIR.mkdir(parents=True, exist_ok=True)
    out = JUDGE_DIR / f"instances_{item_id}.jsonl"
    out.write_text("".join(json.dumps(i) + "\n" for i in instances))
    return out
