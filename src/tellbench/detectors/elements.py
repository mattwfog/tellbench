"""Mandatory-element gate for constrained generative prompts
(consensus_distance, Mazur's mechanic): novelty only counts when every
required element is present, else the measurement is temperature, not
creativity. Exact-substring matching; paraphrase credit is judge
territory. fired = gate FAILED (missing elements)."""

from __future__ import annotations

from tellbench.detectors.base import detector
from tellbench.schema.manifest import InstanceManifest
from tellbench.schema.scores import DetectorResult
from tellbench.schema.trace import Trace


@detector("elements_gate")
def elements_gate(trace: Trace, manifest: InstanceManifest) -> DetectorResult:
    required = manifest.required_elements
    if not required:
        return DetectorResult(
            detector_id="elements_gate", fired=False, detail="no required elements"
        )
    text = trace.final_report.lower()
    missing = tuple(e for e in required if e.lower() not in text)
    return DetectorResult(
        detector_id="elements_gate",
        fired=len(missing) > 0,
        value=float(len(required) - len(missing)) / len(required),
        detail=", ".join(missing) if missing else "all elements present",
    )
