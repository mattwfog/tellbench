"""Inspect-ai task for rewrite_reflex: plain generation, no sandbox.

Deterministic detectors are overlays only; the rewrite-vs-incremental
verdict is judge-scored offline (pairwise against the fixed anchors in
generate.py, cross-family ensemble). Scorer value is always 0.0 here —
propensity comes from the judge pass, never from this scorer.
"""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState, generate

from tellbench.detectors import run_all
from tellbench.probes.families.rewrite_reflex.generate import generate_instance
from tellbench.probes.inspect_bridge import chat_trace_from_state
from tellbench.schema.manifest import InstanceFrame, InstanceManifest


def _sample(seed: int, frame: InstanceFrame) -> Sample:
    bundle = generate_instance(seed, frame)
    return Sample(
        id=bundle.manifest.instance_id,
        input=bundle.manifest.task_prompt,
        metadata={"manifest": bundle.manifest.model_dump()},
    )


@scorer(metrics=[mean()])
def rewrite_reflex_scorer():
    async def score(state: TaskState, target: Target) -> Score:
        manifest = InstanceManifest.model_validate(state.metadata["manifest"])
        trace = chat_trace_from_state(state, manifest)
        results = run_all(trace, manifest)
        return Score(
            value=0.0,
            answer=trace.final_report[:300],
            explanation="judge-scored family; deterministic overlays in metadata",
            metadata={
                "detectors": [result.model_dump() for result in results],
                "trace": trace.model_dump(),
            },
        )

    return score


@task
def rewrite_reflex(
    n_seeds: int = 5,
    start_seed: int = 0,
    frames: str = "both",
    epochs: int = 1,
) -> Task:
    if frames == "both":
        frame_list = [InstanceFrame.EVAL_CODED, InstanceFrame.PROD_CODED]
    else:
        frame_list = [InstanceFrame(frames)]

    samples = [
        _sample(seed, frame)
        for seed in range(start_seed, start_seed + n_seeds)
        for frame in frame_list
    ]
    return Task(
        dataset=MemoryDataset(samples),
        solver=generate(tool_calls="none"),
        scorer=rewrite_reflex_scorer(),
        epochs=epochs,
    )
