"""Scripted plain-chat solver: fixed user turns, no tools.

Used by constraint_decay (escalating-inconvenience turns) and
iteration_diversity ("meaningfully different" repeated). The initial
task_prompt is the sample input; each scripted turn is appended after the
model's reply. assistant_texts() extracts the per-turn texts for Trace.
"""

from __future__ import annotations

from inspect_ai.model import ChatMessageUser
from inspect_ai.solver import Generate, Solver, TaskState, solver


@solver
def scripted_chat(turns: tuple[str, ...]) -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state = await generate(state, tool_calls="none")
        for turn in turns:
            state.messages.append(ChatMessageUser(content=turn))
            state = await generate(state, tool_calls="none")
        return state

    return solve


def assistant_texts(messages: object) -> tuple[str, ...]:
    texts: list[str] = []
    for message in messages:  # type: ignore[attr-defined]
        if getattr(message, "role", None) == "assistant":
            text = str(getattr(message, "text", "") or "")
            if text.strip():
                texts.append(text)
    return tuple(texts)
