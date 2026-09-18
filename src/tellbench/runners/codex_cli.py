"""Run probe instances through the Codex CLI (`codex exec` headless).

Interface verified against a captured session (codex-cli 0.144.1,
2026-07-11, scratchpad codex_capture): `codex exec --json` emits JSONL
events on stdout — `item.completed` items typed `command_execution`
(command + aggregated_output), `file_change` (paths), `agent_message`
(text); `thread.started` carries the session id; `turn.completed`
carries token usage. The final agent message is also written to the
`--output-last-message` file, which is authoritative for the report.

codex exec reads stdin when piped (observed: "Reading additional input
from stdin..."), the same slurp hazard that truncated the panel driver —
every invocation runs with stdin=/dev/null.

Arm: `subscription` only (ChatGPT-plan auth via ~/.codex/auth.json). An
api arm needs verified OPENAI_API_KEY-vs-auth.json precedence first.

End-state evidence is identical to the claude_code runner: git status +
diff against the planted baseline, with restore_baseline folding agent
commits back. Codex's own file_change events feed ordering evidence
only. Raw events persist per run BEFORE parsing, so a crash never loses
a paid capture.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from tellbench.adapters.gitstate import (
    agent_file_changes,
    expected_initial_status,
    parse_git_status,
    parse_numstat,
)
from tellbench.detectors import run_all
from tellbench.probes.families.messy_repo.generate import materialize
from tellbench.runners.claude_code import (
    FAMILY_CHOICES,
    TEXT_FAMILIES,
    RunRecord,
    RunSpec,
    _git,
    _spec_cell,
    append_record,
    generate_for,
    load_done_keys,
    plan_runs,
    restore_baseline,
)
from tellbench.schema.events import ToolCall
from tellbench.schema.manifest import InstanceFrame
from tellbench.schema.trace import RunMeta, Trace

ARM = "subscription"
SANDBOX_MODE = "workspace-write"
DEFAULT_TIMEOUT_SECONDS = 600
_OUTPUT_EXCERPT_CHARS = 2000
_MODEL_LABEL_DEFAULT = "codex-config-default"


class ParsedEvents(NamedTuple):
    tool_calls: tuple[ToolCall, ...]
    agent_messages: tuple[str, ...]
    thinking: tuple[str, ...]
    thread_id: str
    usage: dict


def codex_command(
    prompt: str,
    workdir: Path,
    last_message_file: Path,
    model: str | None = None,
    effort: str | None = None,
) -> list[str]:
    command = [
        "codex",
        "exec",
        "--json",
        "-s",
        SANDBOX_MODE,
        "-C",
        str(workdir),
        "-o",
        str(last_message_file),
    ]
    if model is not None:
        command += ["-m", model]
    if effort is not None:
        # config-key passthrough; the value vocabulary matches the user's
        # config.toml (model_reasoning_effort = "xhigh" observed)
        command += ["-c", f"model_reasoning_effort={effort}"]
    return [*command, prompt]


def parse_events(jsonl_text: str) -> ParsedEvents:
    calls: list[ToolCall] = []
    messages: list[str] = []
    thinking: list[str] = []
    thread_id = ""
    usage: dict = {}
    index = 0
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "thread.started":
            thread_id = str(event.get("thread_id", ""))
            continue
        if kind == "turn.completed":
            raw = event.get("usage")
            usage = raw if isinstance(raw, dict) else {}
            continue
        if kind != "item.completed":
            continue
        item = event.get("item") or {}
        item_type = item.get("type")
        if item_type == "command_execution":
            calls.append(
                ToolCall(
                    index=index,
                    name="command_execution",
                    arguments=str(item.get("command", "")),
                    output_excerpt=str(item.get("aggregated_output", "") or "")[
                        :_OUTPUT_EXCERPT_CHARS
                    ],
                )
            )
            index += 1
        elif item_type == "file_change":
            paths = ", ".join(
                str(change.get("path", ""))
                for change in item.get("changes") or []
                if isinstance(change, dict)
            )
            calls.append(ToolCall(index=index, name="file_change", arguments=paths))
            index += 1
        elif item_type == "agent_message":
            text = str(item.get("text", "") or "")
            if text.strip():
                messages.append(text)
        elif item_type == "reasoning":
            # not present in the captured sample; kept because usage reports
            # reasoning_output_tokens, so visible reasoning items may exist
            # under other config
            text = str(item.get("text", "") or "")
            if text.strip():
                thinking.append(text)
    return ParsedEvents(
        tool_calls=tuple(calls),
        agent_messages=tuple(messages),
        thinking=tuple(thinking),
        thread_id=thread_id,
        usage=usage,
    )


def _cli_version() -> str:
    result = subprocess.run(
        ["codex", "--version"], capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip() or "codex (version unknown)"


def run_instance(
    bundle,
    spec: RunSpec,
    workdir_root: Path,
    events_dir: Path,
    model: str | None,
    cli_version: str,
    effort: str | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_SECONDS,
    keep_workdir: bool = False,
) -> RunRecord:
    manifest = bundle.manifest
    text_only = manifest.family in TEXT_FAMILIES
    workdir = (
        workdir_root / f"{spec.run_key.replace(':', '_')}-{uuid.uuid4().hex[:8]}"
    ).resolve()
    workdir.mkdir(parents=True, exist_ok=False)
    events_dir.mkdir(parents=True, exist_ok=True)
    # both runner artifacts live OUTSIDE the workdir — anything we place
    # inside it reads as an agent file change (smoke 2026-07-11: the -o
    # file fired unrequested_diff as an ADDED change)
    #
    # arm-qualified filenames: run_key carries no model/effort, so a bare
    # run_key name collides across arms sharing an events dir — the 21-probe
    # pass 2026-07-11 overwrote 20 of its own event streams before parsing
    arm_tag = f"{(model or _MODEL_LABEL_DEFAULT)}_{effort or 'default'}".replace("/", "-")
    stem = f"{spec.run_key.replace(':', '_')}_{arm_tag}"
    last_message_file = (events_dir / f"{stem}.last.txt").resolve()
    events_file = events_dir / f"{stem}.jsonl"
    started = time.monotonic()
    baseline_sha = ""
    try:
        if not text_only:
            # text-only families run in the bare workdir: codex has no
            # tool_calls="none" analog, but with nothing planted and no git
            # repo, file evidence is out of scope — the last message is the
            # entire deliverable
            materialize(bundle.files, workdir)
            subprocess.run(
                ["sh", "-c", bundle.setup_script],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
            baseline_sha = _git(workdir, "rev-parse", "HEAD").strip()
        completed = subprocess.run(
            codex_command(
                manifest.task_prompt, workdir, last_message_file, model, effort=effort
            ),
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            env=dict(os.environ),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        # persist the raw event stream before any parsing can fail
        events_file.write_text(completed.stdout)
        if completed.returncode != 0:
            raise RuntimeError(
                f"codex exited {completed.returncode}: "
                f"{(completed.stderr or completed.stdout)[:500]}"
            )
        parsed = parse_events(completed.stdout)
        if not text_only:
            restore_baseline(workdir, baseline_sha)

        if last_message_file.exists():
            final_report = last_message_file.read_text()
        elif parsed.agent_messages:
            final_report = parsed.agent_messages[-1]
        else:
            final_report = ""
        file_changes = (
            ()
            if text_only
            else agent_file_changes(
                parse_git_status(_git(workdir, "status", "--porcelain")),
                parse_numstat(_git(workdir, "diff", "HEAD", "--numstat")),
                expected_initial_status(manifest),
            )
        )
        trace = Trace(
            meta=RunMeta(
                run_id=spec.run_key,
                model=model or _MODEL_LABEL_DEFAULT,
                family=manifest.family,
                instance_id=manifest.instance_id,
                frame=manifest.frame,
                k_index=spec.k_index,
                started_at=datetime.now(timezone.utc).isoformat(),
            ),
            tool_calls=parsed.tool_calls,
            file_changes=file_changes,
            final_report=final_report,
            transcript_ref=str(events_file),
            assistant_turns=parsed.agent_messages,
            thinking_turns=parsed.thinking,
        )
        return RunRecord(
            run_key=spec.run_key,
            arm=spec.arm,
            requested_model=model or _MODEL_LABEL_DEFAULT,
            effort=effort,
            cli_version=cli_version,
            session_id=parsed.thread_id,
            duration_s=round(time.monotonic() - started, 2),
            finished_at=datetime.now(timezone.utc).isoformat(),
            cc_meta={"runner": "codex", "usage": parsed.usage},
            trace=trace,
            detectors=run_all(trace, manifest),
        )
    finally:
        if not keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)


def _parse_seeds(raw: str) -> list[int]:
    if "-" in raw and "," not in raw:
        low, high = raw.split("-", 1)
        return list(range(int(low), int(high) + 1))
    return [int(part) for part in raw.split(",") if part.strip()]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run single-shot agentic probe families via the Codex CLI"
    )
    parser.add_argument(
        "--family",
        default="messy_repo",
        choices=FAMILY_CHOICES,
    )
    parser.add_argument("--seeds", default="0-4")
    parser.add_argument("--frames", default="both", choices=["both", "eval_coded", "prod_coded"])
    parser.add_argument("--k", type=int, default=1)
    parser.add_argument(
        "--model",
        default=None,
        help="codex -m value; omitted = the user's config.toml default",
    )
    parser.add_argument(
        "--effort",
        default=None,
        # full enum from the codex 0.144.1 binary (strings dump 2026-07-11):
        # minimal|low|medium|high|xhigh|max|ultra — per-model support varies,
        # an unsupported combo errors at the CLI at zero cost
        choices=("minimal", "low", "medium", "high", "xhigh", "max", "ultra"),
        help="model_reasoning_effort override; omitted = config default",
    )
    parser.add_argument("--runs-file", type=Path, default=Path("runs/codex_runs.jsonl"))
    parser.add_argument("--errors-file", type=Path, default=Path("runs/codex_errors.jsonl"))
    parser.add_argument(
        "--workdir-root",
        type=Path,
        # OUTSIDE the repo tree: on 2026-07-13 sandboxed runs walked up
        # from runs/work, edited probe generators, and committed to the
        # real repo (a756ea3). An external root leaves escapees nothing
        # to find. Pass runs/work explicitly only to extend pre-incident
        # arms era-consistently.
        default=Path.home() / "tellbench-work",
    )
    parser.add_argument("--events-dir", type=Path, default=Path("runs/codex_events"))
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--no-baselines", action="store_true")
    parser.add_argument("--keep-workdirs", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if shutil.which("codex") is None:
        raise SystemExit("codex CLI not found on PATH")
    cli_version = _cli_version()
    frames = (
        [InstanceFrame.EVAL_CODED, InstanceFrame.PROD_CODED]
        if args.frames == "both"
        else [InstanceFrame(args.frames)]
    )
    done = load_done_keys(args.runs_file)
    pending = plan_runs(
        _parse_seeds(args.seeds),
        frames,
        [ARM],
        args.k,
        not args.no_baselines,
        done,
        family=args.family,
    )
    model_label = args.model or _MODEL_LABEL_DEFAULT
    print(
        f"cli={cli_version}; family={args.family}; model={model_label}; "
        f"{len(done)} done, {len(pending)} pending"
    )
    for position, spec in enumerate(pending, start=1):
        bundle = generate_for(spec.family, spec.seed, spec.frame, **_spec_cell(spec))
        try:
            record = run_instance(
                bundle,
                spec,
                args.workdir_root,
                args.events_dir,
                args.model,
                cli_version,
                effort=args.effort,
                timeout_s=args.timeout,
                keep_workdir=args.keep_workdirs,
            )
        except Exception as error:
            append_record(
                args.errors_file,
                json.dumps(
                    {
                        "run_key": spec.run_key,
                        "error": str(error)[:1000],
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            )
            print(f"ERROR {spec.run_key}: {str(error)[:200]} ({position}/{len(pending)})", flush=True)
            continue
        append_record(args.runs_file, record.model_dump_json())
        fired = any(d.fired and d.detector_id == "tripwire_fired" for d in record.detectors)
        print(
            f"done {spec.run_key} fired={fired} tokens={record.cc_meta['usage'].get('output_tokens')} "
            f"({position}/{len(pending)})",
            flush=True,
        )


if __name__ == "__main__":
    main()
