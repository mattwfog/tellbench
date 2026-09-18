"""Bridge inspect-ai run state to a tellbench Trace — family-agnostic.

Tool calls come from assistant messages; file changes from the shared
end-state git logic in tellbench.adapters.gitstate, executed inside the
sandbox. Parsing helpers are pure and unit-tested without a sandbox.
"""

from __future__ import annotations

from collections.abc import Iterable

from inspect_ai.solver import TaskState
from inspect_ai.util import sandbox

from tellbench.adapters.gitstate import (
    agent_file_changes,
    expected_initial_status,
    parse_git_status,
    parse_numstat,
)
from tellbench.schema.events import ToolCall
from tellbench.schema.manifest import InstanceManifest
from tellbench.schema.trace import RunMeta, Trace

WORKSPACE = "/workspace"

__all__ = [
    "chat_trace_from_state",
    "thinking_from_messages",
    "tool_calls_from_messages",
    "trace_from_state",
]


OUTPUT_EXCERPT_CHARS = 400


def _tool_outputs_by_id(messages: Iterable[object]) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for message in messages:
        if getattr(message, "role", None) != "tool":
            continue
        call_id = getattr(message, "tool_call_id", None)
        if call_id is None:
            continue
        outputs[str(call_id)] = str(getattr(message, "text", "") or "")
    return outputs


def tool_calls_from_messages(messages: Iterable[object]) -> tuple[ToolCall, ...]:
    """Output excerpts matter: on real traces the blocker often surfaces only
    in a tool result (FileNotFoundError naming the missing fixture), never in
    any command's arguments."""

    materialized = tuple(messages)
    outputs = _tool_outputs_by_id(materialized)
    calls: list[ToolCall] = []
    index = 0
    for message in materialized:
        if getattr(message, "role", None) != "assistant":
            continue
        for call in getattr(message, "tool_calls", None) or ():
            arguments = call.arguments
            if isinstance(arguments, dict):
                rendered = " ".join(str(value) for value in arguments.values())
            else:
                rendered = str(arguments)
            calls.append(
                ToolCall(
                    index=index,
                    name=call.function,
                    arguments=rendered,
                    output_excerpt=outputs.get(str(call.id), "")[:OUTPUT_EXCERPT_CHARS],
                )
            )
            index += 1
    return tuple(calls)


def thinking_from_messages(messages: Iterable[object]) -> tuple[str, ...]:
    """Reasoning-block text from assistant messages, in message order.

    inspect-ai surfaces provider thinking as ContentReasoning items on the
    assistant message's content list (`reasoning` carries the text; models
    that only return summaries put them in `summary`). Empty and redacted
    blocks are dropped — an entry in thinking_turns is always real text.
    """

    turns: list[str] = []
    for message in messages:
        if getattr(message, "role", None) != "assistant":
            continue
        content = getattr(message, "content", None)
        if isinstance(content, str):
            continue
        for item in content or ():
            if getattr(item, "type", None) != "reasoning":
                continue
            if getattr(item, "redacted", False):
                continue
            text = str(getattr(item, "reasoning", "") or "") or str(
                getattr(item, "summary", "") or ""
            )
            if text.strip():
                turns.append(text)
    return tuple(turns)


def _run_meta(state: TaskState, manifest: InstanceManifest) -> "RunMeta":
    return RunMeta(
        run_id=f"{state.sample_id}-e{state.epoch}",
        model=str(getattr(state, "model", "")),
        family=manifest.family,
        instance_id=manifest.instance_id,
        frame=manifest.frame,
        k_index=state.epoch,
        started_at="",
    )


def chat_trace_from_state(
    state: TaskState,
    manifest: InstanceManifest,
    assistant_turns: tuple[str, ...] = (),
) -> Trace:
    """Trace for sandbox-free chat families: no tools, no file state."""

    return Trace(
        meta=_run_meta(state, manifest),
        final_report=state.output.completion if state.output else "",
        transcript_ref=str(state.sample_id),
        assistant_turns=assistant_turns,
        thinking_turns=thinking_from_messages(state.messages),
    )


async def trace_from_state(state: TaskState, manifest: InstanceManifest) -> Trace:
    env = sandbox()
    status = await env.exec(["git", "status", "--porcelain"], cwd=WORKSPACE)
    numstat = await env.exec(["git", "diff", "HEAD", "--numstat"], cwd=WORKSPACE)
    file_changes = agent_file_changes(
        parse_git_status(status.stdout if status.success else ""),
        parse_numstat(numstat.stdout if numstat.success else ""),
        expected_initial_status(manifest),
    )
    return Trace(
        meta=_run_meta(state, manifest),
        tool_calls=tool_calls_from_messages(state.messages),
        file_changes=file_changes,
        final_report=state.output.completion if state.output else "",
        transcript_ref=str(state.sample_id),
        thinking_turns=thinking_from_messages(state.messages),
    )
