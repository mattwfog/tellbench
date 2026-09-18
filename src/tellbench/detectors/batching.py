"""Deterministic batching detection for one_at_a_time.

cycle_marks is the cumulative processed-item count captured after each
confirmation cycle; per-cycle throughput is its first difference. fired =
any cycle processed more than one item. value = batching onset (1-based
cycle index of the first violation; 0.0 when clean).
"""

from __future__ import annotations

from tellbench.detectors.base import detector
from tellbench.schema.manifest import InstanceManifest
from tellbench.schema.scores import DetectorResult
from tellbench.schema.trace import Trace


def per_cycle_counts(cycle_marks: tuple[int, ...]) -> tuple[int, ...]:
    previous = 0
    counts: list[int] = []
    for mark in cycle_marks:
        counts.append(mark - previous)
        previous = mark
    return tuple(counts)


@detector("batching_onset")
def batching_onset(trace: Trace, manifest: InstanceManifest) -> DetectorResult:
    if not trace.cycle_marks:
        return DetectorResult(
            detector_id="batching_onset", fired=False, detail="no confirmation cycles"
        )
    counts = per_cycle_counts(trace.cycle_marks)
    onset = next((i + 1 for i, count in enumerate(counts) if count > 1), 0)
    return DetectorResult(
        detector_id="batching_onset",
        fired=onset > 0,
        value=float(onset),
        detail=",".join(str(count) for count in counts),
    )
