"""Detector registry. A detector is a pure function
(Trace, InstanceManifest) -> DetectorResult; registration is import-time
and the registry is read-only after import.
"""

from __future__ import annotations

from collections.abc import Callable

from tellbench.schema.manifest import InstanceManifest
from tellbench.schema.scores import DetectorResult
from tellbench.schema.trace import Trace

DetectorFn = Callable[[Trace, InstanceManifest], DetectorResult]

DETECTORS: dict[str, DetectorFn] = {}


def detector(detector_id: str) -> Callable[[DetectorFn], DetectorFn]:
    def register(fn: DetectorFn) -> DetectorFn:
        if detector_id in DETECTORS:
            raise ValueError(f"duplicate detector id: {detector_id}")
        DETECTORS[detector_id] = fn
        return fn

    return register


def run_all(trace: Trace, manifest: InstanceManifest) -> tuple[DetectorResult, ...]:
    return tuple(fn(trace, manifest) for fn in DETECTORS.values())
