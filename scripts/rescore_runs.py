"""Re-run the deterministic detectors over captured runs files, in place.

Traces are the source of truth; detector outputs are derived. Whenever a
detector changes, this script recomputes the `detectors` array for every
record from the stored trace plus a manifest regenerated from the seeded
family generator (instance_id round-trips to generator arguments).

Usage:
    python scripts/rescore_runs.py runs/runs_sonnet.jsonl [more files...]

Each file is rewritten atomically (tmp + replace). Records whose
instance_id cannot be parsed or regenerated are kept unchanged and
reported — never dropped. A per-detector fire delta is printed per file.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tellbench.detectors import run_all
from tellbench.probes.manifests import manifest_for
from tellbench.schema.manifest import InstanceFrame
from tellbench.schema.trace import Trace

def rescore_file(path: Path) -> None:
    before: Counter[str] = Counter()
    after: Counter[str] = Counter()
    kept_unchanged: list[str] = []
    out_lines: list[str] = []

    for line in path.read_text().splitlines():
        record = json.loads(line)
        for det in record["detectors"]:
            if det["fired"]:
                before[det["detector_id"]] += 1
        try:
            trace = Trace.model_validate(record["trace"])
            manifest = manifest_for(trace.meta.instance_id)
            results = run_all(trace, manifest)
        except Exception as error:  # noqa: BLE001 — report and keep the record
            kept_unchanged.append(f"{record.get('run_key', '?')}: {error}")
            for det in record["detectors"]:
                if det["fired"]:
                    after[det["detector_id"]] += 1
            out_lines.append(line)
            continue
        rescored = {
            **record,
            "detectors": [json.loads(d.model_dump_json()) for d in results],
        }
        for det in rescored["detectors"]:
            if det["fired"]:
                after[det["detector_id"]] += 1
        out_lines.append(json.dumps(rescored))

    tmp = path.with_suffix(path.suffix + ".rescore-tmp")
    tmp.write_text("\n".join(out_lines) + "\n")
    os.replace(tmp, path)

    print(f"── {path} ({len(out_lines)} records)")
    for det in sorted(set(before) | set(after)):
        if before[det] != after[det]:
            print(f"   {det}: {before[det]} -> {after[det]}")
    if not any(before[d] != after[d] for d in set(before) | set(after)):
        print("   no fire deltas")
    for issue in kept_unchanged:
        print(f"   KEPT UNCHANGED (rescore failed): {issue}")


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        raise SystemExit("usage: rescore_runs.py <runs.jsonl> [more...]")
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise SystemExit(f"missing files: {', '.join(map(str, missing))}")
    for path in paths:
        rescore_file(path)


if __name__ == "__main__":
    main()
