"""Regenerate an InstanceManifest from a stored instance_id.

Traces are the source of truth; manifests are derived. instance_id
round-trips to generator arguments (seeded generators), so any consumer
of stored runs — rescoring, judge extraction — can rebuild the manifest
without ever having persisted it. Lifted verbatim from
scripts/rescore_runs.py (2026-08-02) so the judge layer shares one
implementation; rescore imports from here.
"""

from __future__ import annotations

import importlib
import re

from tellbench.schema.manifest import InstanceFrame, InstanceManifest

_INSTANCE_ID = re.compile(
    r"^(?P<family>[a-z_]+)-(?P<seed>\d{6})-(?P<frame>eval_coded|prod_coded)"
    r"(?P<rest>(?:-.+)?)$"
)


def manifest_for(instance_id: str) -> InstanceManifest:
    match = _INSTANCE_ID.match(instance_id)
    if match is None:
        raise ValueError(f"unparseable instance_id: {instance_id!r}")
    family = match.group("family")
    seed = int(match.group("seed"))
    frame = InstanceFrame(match.group("frame"))
    rest = match.group("rest")

    module = importlib.import_module(f"tellbench.probes.families.{family}.generate")
    if family == "clarification_grid":
        cell = rest.lstrip("-").split("-")
        if len(cell) != 2 or cell[1] not in ("ambiguous", "clear"):
            raise ValueError(f"unparseable grid cell in {instance_id!r}")
        bundle = module.generate_instance(
            seed, frame, stakes=cell[0], ambiguous=cell[1] == "ambiguous"
        )
    elif family == "approach_stability":
        specificity = rest.lstrip("-")
        if specificity not in ("vague", "molecular"):
            raise ValueError(f"unparseable specificity in {instance_id!r}")
        bundle = module.generate_instance(seed, frame, specificity=specificity)
    elif rest == "-baseline":
        bundle = module.generate_instance(seed, frame, baseline=True)
    elif rest == "":
        # multiturn families (one_at_a_time, rewrite_reflex, consensus_
        # distance, constraint_decay, iteration_diversity) have no baseline
        # variant and take no baseline kwarg — passing baseline=False broke
        # their round-trip (2026-08-26: 1,050 combined_panel rows kept
        # unchanged on rescore)
        try:
            bundle = module.generate_instance(seed, frame, baseline=False)
        except TypeError:
            bundle = module.generate_instance(seed, frame)
    else:
        raise ValueError(f"unexpected instance_id suffix in {instance_id!r}")

    if bundle.manifest.instance_id != instance_id:
        raise ValueError(
            f"regenerated manifest mismatch: {bundle.manifest.instance_id!r} "
            f"!= {instance_id!r}"
        )
    return bundle.manifest
