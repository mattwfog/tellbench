"""The scored projection of a run: what detectors consume.

A Trace is not the full transcript — it is the deterministic projection
(tool calls, end-state file deltas, final report) plus a pointer back to
the full log for judges and audits.
"""

from __future__ import annotations

from tellbench.schema.events import FileChange, FrozenModel, ToolCall
from tellbench.schema.manifest import InstanceFrame


class RunMeta(FrozenModel):
    run_id: str
    model: str
    family: str
    instance_id: str
    frame: InstanceFrame
    k_index: int
    started_at: str


class Trace(FrozenModel):
    """assistant_turns carries every assistant text turn for multi-turn
    families (constraint decay curves, iteration novelty). injection_at is
    the tool-call index after which a scripted mid-task user turn landed
    (false_pushback). cycle_marks is the cumulative processed-item count
    captured after each confirmation cycle (one_at_a_time). thinking_turns
    carries reasoning-block text in message order — best-effort: present
    only when the provider returns thinking text (empty blocks are never
    stored), so detectors over it measure signal presence, not absence."""

    meta: RunMeta
    tool_calls: tuple[ToolCall, ...] = ()
    file_changes: tuple[FileChange, ...] = ()
    final_report: str = ""
    transcript_ref: str = ""
    assistant_turns: tuple[str, ...] = ()
    thinking_turns: tuple[str, ...] = ()
    injection_at: int | None = None
    cycle_marks: tuple[int, ...] = ()
