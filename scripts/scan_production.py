"""Run tellbench's deterministic claim detectors over PRODUCTION traces.

Standalone entrypoint for scoring captured agent sessions from any capture
pipeline. Reads one session per stdin line as JSON, emits one finding per
(session, detector) as JSON on stdout. No DB driver, no network, nothing
stored — the caller owns export and persistence, and no trace data ever
lands in this repo.

Production traces have no planted manifest, so only the manifest-free
checks are meaningful here: unsupported_claims (report says tests
passed / files deleted / commands ran — did the trace actually show it?)
and report_density (long trajectory, claim-free report).

Input line shape:
  {"session_id": ..., "model": ..., "project": ..., "started_at": ...,
   "turns": [{"role": ..., "content": ..., "tool_inputs": [{"name":..., "input":...}]}]}

Output line shape:
  {"session_id": ..., "detector_id": ..., "fired": bool, "value": float,
   "detail": str | null}
"""

from __future__ import annotations

import json
import sys

from tellbench.detectors.claims import report_density, unsupported_claims
from tellbench.schema.events import ChangeType, FileChange, ToolCall
from tellbench.schema.manifest import InstanceFrame, InstanceManifest
from tellbench.schema.trace import RunMeta, Trace

# Production sessions carry no planted instance; this stub satisfies the
# detector signature and marks provenance unmistakably.
_PROD_MANIFEST = InstanceManifest(
    instance_id="production",
    family="production_trace",
    seed=0,
    frame=InstanceFrame.PROD_CODED,
    baseline=True,
    cover_story="live production session from a capture pipeline",
    task_prompt="",
    target_paths=(),
    canary="production-no-canary",
    honeypot=False,
)


def _file_changes(tool_calls: list[dict]) -> tuple[FileChange, ...]:
    """End-state git diffs don't exist for production sessions; approximate
    from tool calls: Write=added, Edit=modified, `rm` in Bash=deleted.
    Good enough for claim support (the detector matches paths substring-wise)."""
    changes: dict[str, FileChange] = {}
    for call in tool_calls:
        name = call.get("name") or ""
        inp = call.get("input") or {}
        if not isinstance(inp, dict):
            continue
        if name == "Write" and inp.get("file_path"):
            changes[inp["file_path"]] = FileChange(
                path=inp["file_path"], change_type=ChangeType.ADDED
            )
        elif name in ("Edit", "NotebookEdit") and inp.get("file_path"):
            changes.setdefault(
                inp["file_path"],
                FileChange(path=inp["file_path"], change_type=ChangeType.MODIFIED),
            )
        elif name == "Bash":
            cmd = inp.get("command") or ""
            if isinstance(cmd, str):
                for tok in _rm_targets(cmd):
                    changes[tok] = FileChange(path=tok, change_type=ChangeType.DELETED)
    return tuple(changes.values())


def _rm_targets(cmd: str) -> list[str]:
    targets: list[str] = []
    for part in cmd.split("&&"):
        words = part.strip().split()
        if not words or words[0] != "rm":
            continue
        targets.extend(w for w in words[1:] if not w.startswith("-"))
    return targets


def _to_trace(session: dict) -> Trace:
    tool_calls: list[dict] = []
    assistant_turns: list[str] = []
    for turn in session.get("turns") or ():
        if turn.get("role") == "assistant" and turn.get("content"):
            assistant_turns.append(turn["content"])
        for ti in turn.get("tool_inputs") or ():
            tool_calls.append(ti)

    calls = tuple(
        ToolCall(
            index=i,
            name=tc.get("name") or "?",
            arguments=json.dumps(tc.get("input"), ensure_ascii=False)
            if tc.get("input") is not None
            else "",
        )
        for i, tc in enumerate(tool_calls)
    )

    return Trace(
        meta=RunMeta(
            run_id=session["session_id"],
            model=session.get("model") or "?",
            family="production_trace",
            instance_id="production",
            frame=InstanceFrame.PROD_CODED,
            k_index=0,
            started_at=str(session.get("started_at") or ""),
        ),
        tool_calls=calls,
        file_changes=_file_changes(tool_calls),
        final_report=assistant_turns[-1] if assistant_turns else "",
        transcript_ref=session["session_id"],
        assistant_turns=tuple(assistant_turns),
    )


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            session = json.loads(line)
            trace = _to_trace(session)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            print(
                json.dumps({"error": str(exc), "line_prefix": line[:80]}),
                file=sys.stderr,
            )
            continue
        for det in (unsupported_claims, report_density):
            result = det(trace, _PROD_MANIFEST)
            detail = (result.detail or "")[:500]
            print(
                json.dumps(
                    {
                        "session_id": session["session_id"],
                        "detector_id": result.detector_id,
                        "fired": result.fired,
                        "value": result.value,
                        "detail": detail if detail else None,
                    },
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    main()
