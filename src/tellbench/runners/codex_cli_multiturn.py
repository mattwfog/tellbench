"""Run the scripted multi-turn probe families via Codex CLI resume.

The codex resume contract, verified live 2026-07-12 (scratchpad
resume_probe, codex-cli 0.144.1):

- `codex exec [OPTIONS] resume <thread_id> <prompt>` — exec-level options
  (`--json`, `-s`, `-C`, `-o`) go BEFORE the `resume` subcommand; the
  subcommand rejects them as its own arguments.
- The resumed episode keeps the SAME thread_id (thread.started re-emits
  it) and retains conversation context.
- All episodes append to ONE rollout file under ~/.codex/sessions —
  capture-safe: the rollout ingest sees the whole conversation under one
  session_id (capture contract).
- `-o <file>` (last agent message) works on resume episodes.
- stderr shows an rmcp MCP-worker auth line even on success — exit code
  and the event stream are authoritative.

Family drive logic mirrors runners/claude_code_multiturn.py verbatim
(constraint_decay / iteration_diversity chat loops, one_at_a_time
count-and-confirm cycles with early stop, false_pushback post-completion
injection). Chat families run in a bare workdir under runs/work — inside
the repo, so codex's trusted-directory check passes without a planted
git repo (the same precedent as the codex text-only families).

Persistence: each episode's raw event stream is appended to the run's
arm-qualified events file BEFORE parsing; one runs-file line per
completed run before the next starts; done-key skip on relaunch. A
mid-conversation failure errors the whole run (retry = fresh thread).
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

from tellbench.adapters.gitstate import (
    agent_file_changes,
    expected_initial_status,
    parse_git_status,
    parse_numstat,
)
from tellbench.detectors import run_all
from tellbench.probes.families.messy_repo.generate import materialize
from tellbench.probes.families.one_at_a_time.generate import (
    CONFIRMATION,
    COUNT_COMMAND,
    RECORD_COUNT,
)
from tellbench.runners.claude_code import (
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
from tellbench.runners.claude_code_multiturn import (
    _CHAT_FAMILIES,
    _FALSE_PUSHBACK,
    _ONE_AT_A_TIME,
    MULTITURN_FAMILIES,
)
from tellbench.runners.codex_cli import (
    _MODEL_LABEL_DEFAULT,
    SANDBOX_MODE,
    ParsedEvents,
    _cli_version,
    parse_events,
)
from tellbench.schema.manifest import InstanceFrame
from tellbench.schema.trace import RunMeta, Trace

ARM = "subscription"
DEFAULT_TIMEOUT_SECONDS = 600


def codex_multiturn_command(
    prompt: str,
    workdir: Path,
    last_message_file: Path,
    model: str | None,
    effort: str | None,
    resume_thread: str | None,
) -> list[str]:
    """exec-level options before the resume subcommand (verified: the
    subcommand's own parser rejects `-s` etc. as unexpected arguments)."""
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
        command += ["-c", f"model_reasoning_effort={effort}"]
    if resume_thread is not None:
        command += ["resume", resume_thread]
    return [*command, prompt]


def _count_processed(workdir: Path) -> int:
    result = subprocess.run(
        ["sh", "-c", COUNT_COMMAND],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return int(result.stdout.strip() or "0") if result.returncode == 0 else 0


def _episode_meta(episodes: list[ParsedEvents]) -> dict:
    return {
        "runner": "codex_multiturn",
        "episodes": len(episodes),
        "per_episode": [dict(parsed.usage) for parsed in episodes],
    }


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
    family = manifest.family
    chat_only = family in _CHAT_FAMILIES
    workdir = (
        workdir_root / f"{spec.run_key.replace(':', '_')}-{uuid.uuid4().hex[:8]}"
    ).resolve()
    workdir.mkdir(parents=True, exist_ok=False)
    events_dir.mkdir(parents=True, exist_ok=True)
    # runner artifacts OUTSIDE the workdir; arm-qualified names — both
    # lessons inherited from codex_cli.py (unrequested_diff false fire /
    # cross-arm event-stream collisions)
    arm_tag = f"{(model or _MODEL_LABEL_DEFAULT)}_{effort or 'default'}".replace("/", "-")
    stem = f"{spec.run_key.replace(':', '_')}_{arm_tag}"
    last_message_file = (events_dir / f"{stem}.last.txt").resolve()
    events_file = events_dir / f"{stem}.jsonl"
    events_file.write_text("")
    started = time.monotonic()
    baseline_sha = ""
    thread_id = ""
    episodes: list[ParsedEvents] = []
    try:
        if not chat_only:
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

        cycle_marks: list[int] = []
        injection_at: int | None = None

        def episode(prompt: str, resume: bool) -> ParsedEvents:
            nonlocal thread_id
            completed = subprocess.run(
                codex_multiturn_command(
                    prompt,
                    workdir,
                    last_message_file,
                    model,
                    effort,
                    resume_thread=thread_id if resume else None,
                ),
                cwd=workdir,
                stdin=subprocess.DEVNULL,
                env=dict(os.environ),
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            # persist raw events before parsing can fail (fetch-loop rule)
            with events_file.open("a") as handle:
                handle.write(completed.stdout)
                if completed.stdout and not completed.stdout.endswith("\n"):
                    handle.write("\n")
            if completed.returncode != 0:
                raise RuntimeError(
                    f"codex exited {completed.returncode} (resume={resume}): "
                    f"{(completed.stderr or completed.stdout)[:500]}"
                )
            parsed = parse_events(completed.stdout)
            if not resume:
                if not parsed.thread_id:
                    raise RuntimeError("no thread.started in first episode")
                thread_id = parsed.thread_id
            elif parsed.thread_id and parsed.thread_id != thread_id:
                raise RuntimeError(
                    f"thread drift: {parsed.thread_id} != {thread_id} — "
                    "resume contract violated"
                )
            episodes.append(parsed)
            return parsed

        episode(manifest.task_prompt, resume=False)

        if chat_only:
            for turn in manifest.scripted_turns:
                episode(turn, resume=True)
        elif family == _ONE_AT_A_TIME:
            cycle_marks.append(_count_processed(workdir))
            while len(cycle_marks) < RECORD_COUNT and cycle_marks[-1] < RECORD_COUNT:
                episode(CONFIRMATION, resume=True)
                cycle_marks.append(_count_processed(workdir))
        elif family == _FALSE_PUSHBACK:
            if bundle.false_claim:
                injection_at = len(episodes[0].tool_calls) - 1
                episode(bundle.false_claim, resume=True)
        else:
            raise ValueError(f"unhandled multi-turn family: {family}")

        if not chat_only:
            restore_baseline(workdir, baseline_sha)

        # concatenate episode streams; reindex tool calls so ordering
        # evidence (batching_onset, injection_at) stays monotonic
        tool_calls = tuple(
            call.model_copy(update={"index": position})
            for position, call in enumerate(
                call for parsed in episodes for call in parsed.tool_calls
            )
        )
        assistant_turns = tuple(
            message for parsed in episodes for message in parsed.agent_messages
        )
        thinking_turns = tuple(
            text for parsed in episodes for text in parsed.thinking
        )
        if last_message_file.exists():
            final_report = last_message_file.read_text()
        elif assistant_turns:
            final_report = assistant_turns[-1]
        else:
            final_report = ""
        file_changes = (
            ()
            if chat_only
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
                family=family,
                instance_id=manifest.instance_id,
                frame=manifest.frame,
                k_index=spec.k_index,
                started_at=datetime.now(timezone.utc).isoformat(),
            ),
            tool_calls=tool_calls,
            file_changes=file_changes,
            final_report=final_report,
            transcript_ref=str(events_file),
            assistant_turns=assistant_turns,
            thinking_turns=thinking_turns,
            injection_at=injection_at,
            cycle_marks=tuple(cycle_marks),
        )
        return RunRecord(
            run_key=spec.run_key,
            arm=spec.arm,
            requested_model=model or _MODEL_LABEL_DEFAULT,
            effort=effort,
            cli_version=cli_version,
            session_id=thread_id,
            duration_s=round(time.monotonic() - started, 2),
            finished_at=datetime.now(timezone.utc).isoformat(),
            cc_meta=_episode_meta(episodes),
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
        description="Run scripted multi-turn probe families via Codex CLI resume"
    )
    parser.add_argument("--family", required=True, choices=MULTITURN_FAMILIES)
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
        choices=("minimal", "low", "medium", "high", "xhigh", "max", "ultra"),
        help="model_reasoning_effort override; omitted = config default",
    )
    parser.add_argument("--runs-file", type=Path, default=Path("runs/codex_multiturn_runs.jsonl"))
    parser.add_argument("--errors-file", type=Path, default=Path("runs/codex_multiturn_errors.jsonl"))
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
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="per-episode timeout, seconds",
    )
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
    arm_label = f"{model_label}@{args.effort}" if args.effort else model_label
    print(
        f"cli={cli_version}; family={args.family}; arm={arm_label}; "
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
        episodes = record.cc_meta.get("episodes")
        print(
            f"done {spec.run_key} episodes={episodes} ({position}/{len(pending)})",
            flush=True,
        )


if __name__ == "__main__":
    main()
