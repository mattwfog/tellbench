"""Turn a panel's .eval logs into the site-ready scored table.

Reads every completed inspect log in --log-dir, groups samples by family,
splits armed instances by frame, and reports the worst-frame fire rate
with a Clopper-Pearson interval per family (the small-k-honest choice per
docs/03-scoring.md), baselines alongside. Families whose samples carry no
armed/baseline manifest (the chat-only score shapes) fall back to a plain
mean over sample scores, labeled as such.

Output: a human-readable table on stdout, plus --json-out for the raw
rows and --site-block-out for the generic table block the
project website embeds verbatim.

Usage:
  .venv/bin/python scripts/site_table.py --log-dir logs/panel \
      --json-out logs/panel_table.json --site-block-out logs/panel_block.json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from collections import defaultdict
from dataclasses import dataclass

from inspect_ai.log import read_eval_log

from tellbench.probes.registry import FAMILIES, ScoreShape
from tellbench.scoring.stats import rate_with_ci


@dataclass
class SampleRow:
    family: str
    frame: str | None
    baseline: bool | None
    fired: float


def _score_value(sample) -> float | None:
    if not sample.scores:
        return None
    value = next(iter(sample.scores.values())).value
    if isinstance(value, (int, float)):
        return float(value)
    return None


def collect(log_dir: str) -> tuple[list[SampleRow], list[str]]:
    rows: list[SampleRow] = []
    skipped: list[str] = []
    for path in sorted(glob.glob(os.path.join(log_dir, "*.eval"))):
        log = read_eval_log(path)
        if log.status != "success" or not log.samples:
            skipped.append(f"{os.path.basename(path)} (status={log.status})")
            continue
        family = log.eval.task.split("/")[-1]
        for sample in log.samples:
            value = _score_value(sample)
            if value is None:
                continue
            manifest = (sample.metadata or {}).get("manifest") or {}
            rows.append(
                SampleRow(
                    family=family,
                    frame=manifest.get("frame"),
                    baseline=manifest.get("baseline"),
                    fired=value,
                )
            )
    return rows, skipped


def _ci(fires: int, n: int) -> dict:
    r = rate_with_ci(fires, n, method="clopper_pearson")
    return {
        "rate": r.rate,
        "ci_low": r.ci_low,
        "ci_high": r.ci_high,
        "fires": r.fires,
        "n": r.n,
    }


def _fire_rate_entry(family: str, dimensions: str, framed: list[SampleRow]) -> dict:
    armed = [s for s in framed if not s.baseline]
    baseline = [s for s in framed if s.baseline]
    frames = {}
    for frame in sorted({s.frame for s in armed if s.frame is not None}):
        in_frame = [s for s in armed if s.frame == frame]
        frames[frame] = _ci(sum(1 for s in in_frame if s.fired >= 1.0), len(in_frame))
    worst_frame = max(frames, key=lambda f: frames[f]["rate"]) if frames else None
    return {
        "family": family,
        "dimensions": dimensions,
        "shape": "fire_rate",
        "frames": frames,
        "reported": frames[worst_frame] if worst_frame else None,
        "worst_frame": worst_frame,
        "baseline": _ci(sum(1 for s in baseline if s.fired >= 1.0), len(baseline))
        if baseline
        else None,
    }


def _mean_score_entry(family: str, dimensions: str, samples: list[SampleRow]) -> dict:
    """Continuous scores where higher is better (novelty, compliance rate,
    gate satisfaction — every current MEAN_SCORE family). A fires/n readout
    over these was the polarity bug this branch replaces."""
    framed = [s for s in samples if s.frame is not None and s.baseline is not None]
    armed = [s for s in framed if not s.baseline] or samples
    per_frame = {}
    for frame in sorted({s.frame for s in armed if s.frame is not None}):
        values = [s.fired for s in armed if s.frame == frame]
        per_frame[frame] = {"mean": sum(values) / len(values), "n": len(values)}
    worst_frame = (
        min(per_frame, key=lambda f: per_frame[f]["mean"]) if per_frame else None
    )
    values = [s.fired for s in armed]
    return {
        "family": family,
        "dimensions": dimensions,
        "shape": "mean_score",
        "polarity": "higher_is_better",
        "mean": sum(values) / len(values),
        "n": len(values),
        "per_frame": per_frame,
        "worst_frame": worst_frame,
    }


def summarize(rows: list[SampleRow]) -> list[dict]:
    by_family: dict[str, list[SampleRow]] = defaultdict(list)
    for row in rows:
        by_family[row.family].append(row)

    out: list[dict] = []
    for family, samples in sorted(by_family.items()):
        spec = FAMILIES.get(family)
        dimensions = (
            " / ".join(d.value for d in spec.dimensions) if spec else "unknown"
        )
        shape = spec.score_shape if spec else None
        framed = [s for s in samples if s.frame is not None and s.baseline is not None]
        if shape is ScoreShape.JUDGE_PENDING:
            out.append(
                {
                    "family": family,
                    "dimensions": dimensions,
                    "shape": "judge_pending",
                    "n": len(samples),
                }
            )
        elif shape is ScoreShape.MEAN_SCORE:
            out.append(_mean_score_entry(family, dimensions, samples))
        elif framed:
            # FIRE_RATE families, plus unknown families that carry manifests
            out.append(_fire_rate_entry(family, dimensions, framed))
        else:
            # unknown family, no manifest metadata: plain mean, polarity unknown
            values = [s.fired for s in samples]
            out.append(
                {
                    "family": family,
                    "dimensions": dimensions,
                    "shape": "mean_score",
                    "polarity": "unknown",
                    "mean": sum(values) / len(values),
                    "n": len(values),
                    "per_frame": {},
                    "worst_frame": None,
                }
            )
    return out


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def site_block(summary: list[dict], model: str) -> dict:
    """The table block the project website renders verbatim."""
    rows = []
    for entry in summary:
        if entry["shape"] == "fire_rate":
            reported = entry["reported"]
            baseline = entry["baseline"]
            if reported is None:
                continue
            rows.append(
                [
                    entry["family"],
                    entry["dimensions"],
                    f"{reported['fires']}/{reported['n']}",
                    f"{_pct(reported['rate'])} [{_pct(reported['ci_low'])}, {_pct(reported['ci_high'])}]",
                    f"{baseline['fires']}/{baseline['n']}" if baseline else "—",
                ]
            )
        elif entry["shape"] == "judge_pending":
            rows.append(
                [
                    entry["family"],
                    entry["dimensions"],
                    f"n={entry['n']}",
                    "judge pending",
                    "—",
                ]
            )
        else:
            polarity = (
                " (higher is better)"
                if entry.get("polarity") == "higher_is_better"
                else ""
            )
            rows.append(
                [
                    entry["family"],
                    entry["dimensions"],
                    f"n={entry['n']}",
                    f"mean {entry['mean']:.2f}{polarity}",
                    "—",
                ]
            )
    return {
        "kind": "table",
        "header": [
            "Family",
            "Dimension",
            f"Fires ({model}, worst frame)",
            "Rate [95% CI]",
            "Baseline fires",
        ],
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Turn a panel's .eval logs into the site-ready scored table."
    )
    parser.add_argument("--log-dir", required=True)
    parser.add_argument("--model", default="qwen3-32b")
    parser.add_argument("--json-out")
    parser.add_argument("--site-block-out")
    args = parser.parse_args()

    rows, skipped = collect(args.log_dir)
    summary = summarize(rows)

    for name in skipped:
        print(f"skipped: {name}")
    for entry in summary:
        if entry["shape"] == "fire_rate":
            r = entry["reported"]
            b = entry["baseline"]
            armed = (
                f"armed {r['fires']}/{r['n']} = {_pct(r['rate'])} "
                f"[{_pct(r['ci_low'])}, {_pct(r['ci_high'])}] (worst: {entry['worst_frame']})"
                if r
                else "armed —"
            )
            base = f"baseline {b['fires']}/{b['n']}" if b else "baseline —"
            print(f"{entry['family']:24s} {entry['dimensions']:22s} {armed} {base}")
        elif entry["shape"] == "judge_pending":
            print(
                f"{entry['family']:24s} {entry['dimensions']:22s} "
                f"judge pending over n={entry['n']}"
            )
        else:
            worst = (
                f" (worst frame: {entry['worst_frame']})" if entry["worst_frame"] else ""
            )
            print(
                f"{entry['family']:24s} {entry['dimensions']:22s} "
                f"mean {entry['mean']:.3f} over n={entry['n']}{worst}"
            )

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"wrote {args.json_out}")
    if args.site_block_out:
        with open(args.site_block_out, "w") as f:
            json.dump(site_block(summary, args.model), f, indent=2)
        print(f"wrote {args.site_block_out}")


if __name__ == "__main__":
    main()
