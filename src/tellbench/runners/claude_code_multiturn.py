"""Run the scripted multi-turn probe families via Claude Code CLI resume.

Subscription-only path for the four families whose Inspect tasks need a
scripted counterparty: each family's counterparty logic runs HERE, in the
runner, as a loop of `claude -p` episodes over one pinned session id —
`-p --resume <id>` keeps the same session and transcript (verified live
2026-07-11, scratchpad resume_probe), so no API key and no Docker.

Family drive logic (mirrors probes/agentloop.py and probes/chatloop.py):

- constraint_decay / iteration_diversity — plain chat: episode 1 is the
  task prompt, then one resumed episode per manifest.scripted_turns entry.
  No tools (same as Inspect's tool_calls="none"), no sandbox.
- one_at_a_time — agentic sandbox: after every episode the runner runs
  COUNT_COMMAND in the workdir and records a cycle mark, then resumes with
  the scripted confirmation. Deviation from the Inspect solver: cycles
  stop early once every record is processed — the remaining confirmations
  can only append zeros to the curve, and batching_onset is already
  determined (detectors/batching.py handles variable-length marks).
- false_pushback — agentic sandbox: the false claim is injected as a
  resumed episode AFTER episode 1 completes. Timing deviation from the
  Inspect solver (which injects mid-task after 2 tool rounds): here the
  dispute reaches an agent that believes it finished. injection_at is the
  index of the last tool call before the claim, so disputed_checked reads
  identically. Baselines run episode 1 only (no claim, injection_at None).

Cross-harness note: CLI captures are comparable to each other; against the
Inspect path, one_at_a_time early-stop and false_pushback injection timing
are documented harness differences.

Persistence contract is the single-shot runner's: one line appended per
completed run before the next starts, done-key skip on resume. A run's
episodes are one unit — a mid-conversation failure errors the whole run
and it retries from episode 1 with a fresh session.
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
    ARM_SUBSCRIPTION,
    ARMS,
    DEFAULT_TIMEOUT_SECONDS,
    EFFORT_LEVELS,
    RunRecord,
    RunSpec,
    _cli_version,
    _git,
    _result_record,
    _spec_cell,
    append_record,
    build_env,
    cc_command,
    generate_for,
    load_done_keys,
    plan_runs,
    restore_baseline,
    thinking_from_transcript,
    tool_calls_from_transcript,
    transcript_path,
)
from tellbench.schema.trace import RunMeta, Trace

MULTITURN_FAMILIES = (
    "one_at_a_time",
    "constraint_decay",
    "false_pushback",
    "iteration_diversity",
)
_CHAT_FAMILIES = ("constraint_decay", "iteration_diversity")
_ONE_AT_A_TIME = "one_at_a_time"
_FALSE_PUSHBACK = "false_pushback"


def assistant_texts_from_transcript(jsonl_text: str) -> tuple[str, ...]:
    """Every assistant message's text, in order — one entry per assistant
    message, text blocks within a message joined (mirror of Inspect's
    assistant_texts over ChatMessage.text)."""

    texts: list[str] = []
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "assistant":
            continue
        content = (record.get("message") or {}).get("content") or []
        if not isinstance(content, list):
            continue
        blocks = [
            str(item.get("text", "") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        text = "\n".join(block for block in blocks if block.strip())
        if text.strip():
            texts.append(text)
    return tuple(texts)


def _episode(
    prompt: str,
    spec: RunSpec,
    model: str,
    session_id: str,
    claude_bin: str,
    workdir: Path,
    effort: str | None,
    tools: tuple[str, ...],
    timeout_s: int,
    resume: bool,
) -> dict:
    completed = subprocess.run(
        cc_command(
            prompt,
            model,
            session_id,
            claude_bin,
            effort=effort,
            tools=tools,
            resume=resume,
        ),
        cwd=workdir,
        env=build_env(spec.arm, dict(os.environ)),
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"claude exited {completed.returncode} (resume={resume}): "
            f"{(completed.stderr or completed.stdout)[:500]}"
        )
    return _result_record(json.loads(completed.stdout))


def _count_processed(workdir: Path) -> int:
    result = subprocess.run(
        ["sh", "-c", COUNT_COMMAND],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return int(result.stdout.strip() or "0") if result.returncode == 0 else 0


def _episode_meta(results: list[dict]) -> dict:
    costs = [r.get("total_cost_usd") for r in results]
    return {
        "runner": "claude_code_multiturn",
        "episodes": len(results),
        "total_cost_usd": sum(c for c in costs if c is not None),
        "per_episode": [
            {key: r.get(key) for key in ("subtype", "total_cost_usd", "num_turns", "is_error")}
            for r in results
        ],
    }


def run_instance(
    bundle,
    spec: RunSpec,
    workdir_root: Path,
    model: str,
    claude_bin: str,
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
    session_id = str(uuid.uuid4())
    started = time.monotonic()
    baseline_sha = ""
    tools: tuple[str, ...] = () if chat_only else ("Bash", "Edit", "Write", "Read", "Glob", "Grep")
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

        results: list[dict] = []
        cycle_marks: list[int] = []
        injection_at: int | None = None

        def episode(prompt: str, resume: bool) -> dict:
            result = _episode(
                prompt,
                spec,
                model,
                session_id,
                claude_bin,
                workdir,
                effort,
                tools,
                timeout_s,
                resume,
            )
            results.append(result)
            return result

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
                transcript_file = transcript_path(workdir, session_id)
                if not transcript_file.exists():
                    raise RuntimeError(f"transcript missing: {transcript_file}")
                calls_before = tool_calls_from_transcript(transcript_file.read_text())
                injection_at = len(calls_before) - 1
                episode(bundle.false_claim, resume=True)
        else:
            raise ValueError(f"unhandled multi-turn family: {family}")

        if not chat_only:
            restore_baseline(workdir, baseline_sha)

        transcript_file = transcript_path(workdir, session_id)
        if not transcript_file.exists():
            raise RuntimeError(f"transcript missing: {transcript_file}")
        transcript_text = transcript_file.read_text()
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
                model=model,
                family=family,
                instance_id=manifest.instance_id,
                frame=manifest.frame,
                k_index=spec.k_index,
                started_at=datetime.now(timezone.utc).isoformat(),
            ),
            tool_calls=tool_calls_from_transcript(transcript_text),
            file_changes=file_changes,
            final_report=str(results[-1].get("result", "")),
            transcript_ref=str(transcript_file),
            assistant_turns=assistant_texts_from_transcript(transcript_text),
            thinking_turns=thinking_from_transcript(transcript_text),
            injection_at=injection_at,
            cycle_marks=tuple(cycle_marks),
        )
        return RunRecord(
            run_key=spec.run_key,
            arm=spec.arm,
            requested_model=model,
            effort=effort,
            cli_version=cli_version,
            session_id=session_id,
            duration_s=round(time.monotonic() - started, 2),
            finished_at=datetime.now(timezone.utc).isoformat(),
            cc_meta=_episode_meta(results),
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
        description="Run scripted multi-turn probe families via Claude Code CLI resume"
    )
    parser.add_argument("--family", required=True, choices=MULTITURN_FAMILIES)
    parser.add_argument("--seeds", default="0-4")
    parser.add_argument("--frames", default="both", choices=["both", "eval_coded", "prod_coded"])
    parser.add_argument("--arms", default=ARM_SUBSCRIPTION, help="comma list: subscription,api")
    parser.add_argument("--k", type=int, default=1)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default=None, choices=EFFORT_LEVELS)
    parser.add_argument("--runs-file", type=Path, default=Path("runs/multiturn_runs.jsonl"))
    parser.add_argument("--errors-file", type=Path, default=Path("runs/multiturn_errors.jsonl"))
    parser.add_argument(
        "--workdir-root",
        type=Path,
        # OUTSIDE the repo tree (2026-07-13 escape incident) AND outside
        # the operator's home dir (2026-07-31): cwd under /Users/<operator>
        # makes ancestor discovery treat ~/.claude/CLAUDE.md as project
        # memory, which --setting-sources project keeps — the operator-
        # config contamination (docs/contamination-audit.md). Wire-verified
        # both directions on the 07-31 smoke pair.
        default=Path("/private/var/tmp/tellbench-work"),
    )
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
    from tellbench.schema.manifest import InstanceFrame

    args = _parse_args()
    claude_bin = os.environ.get("TELLBENCH_CLAUDE_BIN") or shutil.which("claude")
    if not claude_bin:
        raise SystemExit("claude CLI not found on PATH (set TELLBENCH_CLAUDE_BIN)")
    cli_version = _cli_version(claude_bin)
    frames = (
        [InstanceFrame.EVAL_CODED, InstanceFrame.PROD_CODED]
        if args.frames == "both"
        else [InstanceFrame(args.frames)]
    )
    arms = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
    for arm in arms:
        if arm not in ARMS:
            raise SystemExit(f"unknown arm {arm!r}; valid: {', '.join(ARMS)}")
        build_env(arm, dict(os.environ))

    done = load_done_keys(args.runs_file)
    pending = plan_runs(
        _parse_seeds(args.seeds),
        frames,
        arms,
        args.k,
        not args.no_baselines,
        done,
        family=args.family,
    )
    arm_label = f"{args.model}@{args.effort}" if args.effort else args.model
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
                args.model,
                claude_bin,
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
        cost = record.cc_meta.get("total_cost_usd")
        print(
            f"done {spec.run_key} episodes={episodes} cost={cost} ({position}/{len(pending)})",
            flush=True,
        )


if __name__ == "__main__":
    main()
