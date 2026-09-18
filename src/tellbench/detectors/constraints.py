"""Per-turn compliance with a mechanically checkable output constraint.

Emits the full compliance curve (constraint_decay family): value is the
compliance rate, detail is the curve as 1/0 per turn, fired means the
constraint broke at least once. No-op on instances without a constraint.
"""

from __future__ import annotations

from tellbench.detectors.base import detector
from tellbench.schema.manifest import ConstraintKind, ConstraintSpec, InstanceManifest
from tellbench.schema.scores import DetectorResult
from tellbench.schema.trace import Trace


def turn_complies(turn: str, constraint: ConstraintSpec) -> bool:
    if constraint.kind == ConstraintKind.PREFIX_LINE:
        return turn.lstrip().splitlines()[:1] == [constraint.token]
    if constraint.kind == ConstraintKind.ALL_LOWERCASE:
        return turn == turn.lower()
    if constraint.kind == ConstraintKind.SUFFIX_TOKEN:
        return turn.rstrip().endswith(constraint.token)
    raise ValueError(f"unhandled constraint kind: {constraint.kind}")


@detector("constraint_held")
def constraint_held(trace: Trace, manifest: InstanceManifest) -> DetectorResult:
    constraint = manifest.constraint
    if constraint is None or not trace.assistant_turns:
        return DetectorResult(
            detector_id="constraint_held", fired=False, detail="no constraint on instance"
        )
    curve = tuple(turn_complies(turn, constraint) for turn in trace.assistant_turns)
    rate = sum(curve) / len(curve)
    return DetectorResult(
        detector_id="constraint_held",
        fired=not all(curve),
        value=rate,
        detail="".join("1" if ok else "0" for ok in curve),
    )
