"""Deterministic procedure-adherence detector (approach_stability).

Applies only to molecular-specificity instances — the ones whose prompt
mandates the exact fix procedure. Vague instances declare no procedure,
so there is nothing to deviate from (fired=False, n/a). value is the
fraction of mandated checks satisfied; fired means at least one failed.

Read-step checks are enforced only when the trace carries any `read`
action: codex traces read via command_execution, so file reads are not
individually observable there and skipping the check is honest — a
false fire would be a vocabulary artifact, not a deviation.
"""

from __future__ import annotations

from tellbench.detectors.base import detector
from tellbench.schema.manifest import InstanceManifest
from tellbench.schema.scores import DetectorResult
from tellbench.schema.trace import Trace
from tellbench.scoring.stability import signature

_FAMILY = "approach_stability"
_MOLECULAR_SUFFIX = "-molecular"


@detector("procedure_deviation")
def procedure_deviation(trace: Trace, manifest: InstanceManifest) -> DetectorResult:
    if manifest.family != _FAMILY or not manifest.instance_id.endswith(
        _MOLECULAR_SUFFIX
    ):
        return DetectorResult(
            detector_id="procedure_deviation",
            fired=False,
            detail="no declared procedure",
        )

    sig = signature(trace.tool_calls)
    module_base = manifest.target_paths[0].rsplit("/", 1)[-1]
    test_base = f"test_{module_base}"

    checks = {
        "test_before_first_edit": sig.tested_before_first_edit is True,
        "test_after_last_edit": sig.tested_after_last_edit is True,
        "edited_only_named_file": sig.edited_files == (module_base,),
    }
    if "read" in sig.actions:
        checks["read_test_file"] = test_base in sig.read_files
        checks["read_module_file"] = module_base in sig.read_files

    failed = tuple(name for name, passed in checks.items() if not passed)
    return DetectorResult(
        detector_id="procedure_deviation",
        fired=len(failed) > 0,
        value=(len(checks) - len(failed)) / len(checks),
        detail=", ".join(failed) if failed else "procedure followed",
    )
