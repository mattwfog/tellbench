"""Inspect-ai task for constraint_decay: scripted multi-turn chat.

Scorer value = per-turn compliance rate from the constraint_held
detector; the full 1/0 curve rides detector detail for offline half-life
computation.
"""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState

from tellbench.detectors import run_all
from tellbench.probes.chatloop import assistant_texts, scripted_chat
from tellbench.probes.families.constraint_decay.generate import (
    _PRESSURE_TURNS,
    generate_instance,
)
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
def constraint_decay_scorer():
    async def score(state: TaskState, target: Target) -> Score:
        manifest = InstanceManifest.model_validate(state.metadata["manifest"])
        turns = assistant_texts(state.messages)
        trace = chat_trace_from_state(state, manifest, assistant_turns=turns)
        results = run_all(trace, manifest)
        by_id = {result.detector_id: result for result in results}
        held = by_id["constraint_held"]
        return Score(
            value=held.value if held.value is not None else 0.0,
            answer=(turns[-1] if turns else "")[:300],
            explanation=f"compliance curve {held.detail}",
            metadata={
                "detectors": [result.model_dump() for result in results],
                "trace": trace.model_dump(),
            },
        )

    return score


@task
def constraint_decay(
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
        solver=scripted_chat(_PRESSURE_TURNS),
        scorer=constraint_decay_scorer(),
        epochs=epochs,
    )
