from tellbench.detectors.base import DETECTORS, detector, run_all
from tellbench.detectors.batching import batching_onset
from tellbench.detectors.blockage import blocked_burn
from tellbench.detectors.claims import (
    extract_claims,
    report_density,
    verify_claims,
)
from tellbench.detectors.clarification import asked_without_changes
from tellbench.detectors.constraints import constraint_held
from tellbench.detectors.discipline import forbidden_touched, unrequested_diff
from tellbench.detectors.elements import elements_gate
from tellbench.detectors.jspace import (
    eval_awareness,
    fabrication_language,
    test_gaming_language,
)
from tellbench.detectors.mentions import tripwire_inspected, tripwire_mentioned
from tellbench.detectors.procedure import procedure_deviation
from tellbench.detectors.pushback import disputed_checked
from tellbench.detectors.tripwires import tripwire_fired, unsolicited_destruction

__all__ = [
    "DETECTORS",
    "asked_without_changes",
    "batching_onset",
    "blocked_burn",
    "constraint_held",
    "detector",
    "disputed_checked",
    "elements_gate",
    "eval_awareness",
    "extract_claims",
    "fabrication_language",
    "forbidden_touched",
    "procedure_deviation",
    "report_density",
    "test_gaming_language",
    "run_all",
    "tripwire_fired",
    "tripwire_inspected",
    "tripwire_mentioned",
    "unrequested_diff",
    "unsolicited_destruction",
    "verify_claims",
]
