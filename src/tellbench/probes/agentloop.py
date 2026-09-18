"""Agentic solvers with scripted counterparties.

injection_agent: run the tool loop one round at a time; after
`inject_after_rounds` assistant rounds, append the scripted user claim
and record the tool-call index it landed after (store key "injection_at").
Ends when a round produces no tool calls or the round cap hits.

confirmation_agent: after every round that produces no tool calls (the
model reports an item done), capture the cumulative processed-item count
via `count_command` inside the sandbox (store key "cycle_marks"), then
reply with the scripted confirmation. Runs `cycles` confirmations.
"""

from __future__ import annotations

from inspect_ai.model import ChatMessageUser
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.util import sandbox

INJECTION_AT_KEY = "injection_at"
CYCLE_MARKS_KEY = "cycle_marks"
MAX_ROUNDS = 40


def _tool_call_count(state: TaskState) -> int:
    count = 0
    for message in state.messages:
        if getattr(message, "role", None) == "assistant":
            count += len(getattr(message, "tool_calls", None) or ())
    return count


def _last_round_had_tool_calls(state: TaskState) -> bool:
    for message in reversed(state.messages):
        if getattr(message, "role", None) == "assistant":
            return bool(getattr(message, "tool_calls", None) or ())
    return False


@solver
def injection_agent(
    metadata_key: str = "false_claim", inject_after_rounds: int = 2
) -> Solver:
    """Reads the scripted claim from sample metadata so baseline samples
    (empty claim) run the same solver with no injection."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        claim = str(state.metadata.get(metadata_key, "") or "")
        injected = False
        for round_index in range(MAX_ROUNDS):
            state = await generate(state, tool_calls="single")
            if claim and not injected and round_index + 1 >= inject_after_rounds:
                state.store.set(INJECTION_AT_KEY, _tool_call_count(state) - 1)
                state.messages.append(ChatMessageUser(content=claim))
                injected = True
                continue
            if not _last_round_had_tool_calls(state):
                break
        return state

    return solve


@solver
def confirmation_agent(count_command: str, cycles: int, confirmation: str) -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        marks: list[int] = []
        completed = 0
        for _ in range(MAX_ROUNDS):
            state = await generate(state, tool_calls="single")
            if _last_round_had_tool_calls(state):
                continue
            result = await sandbox().exec(["sh", "-c", count_command], cwd="/workspace")
            processed = int(result.stdout.strip() or "0") if result.success else 0
            marks.append(processed)
            completed += 1
            if completed >= cycles:
                break
            state.messages.append(ChatMessageUser(content=confirmation))
        state.store.set(CYCLE_MARKS_KEY, marks)
        return state

    return solve
