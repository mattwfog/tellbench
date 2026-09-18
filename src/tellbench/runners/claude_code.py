"""Run probe instances through the Claude Code CLI (headless print mode).

Arms:
- subscription — CLI OAuth login; ANTHROPIC_API_KEY (and BASE_URL/AUTH_TOKEN
  overrides) stripped from the environment.
- api — ANTHROPIC_API_KEY required; base-URL overrides stripped so the arm
  hits the API directly.
- kimi — Kimi For Coding (Moonshot) via its Anthropic-compatible surface:
  KIMI_API_KEY becomes ANTHROPIC_API_KEY and the base URL points at the
  second capture-proxy instance (:8120, upstream api.kimi.com/coding), so
  the capture contract holds for non-Anthropic arms too. Models:
  kimi-for-coding, kimi-for-coding-highspeed, k3, k3-256k (k3* accept
  --effort low/high/max).

Both arms run the identical CLI invocation, so subscription-vs-api isolates
the serving path; either arm vs. the Inspect basic_agent path isolates the
harness. Runs use --permission-mode dontAsk plus an explicit --allowedTools
allowlist — never bypassPermissions. --setting-sources project keeps
user-level settings/memory out of the probe context (fresh workdirs carry
no project settings); both arms share whatever residue remains, so the arm
contrast stays clean regardless.

Persistence: every completed run appends one line to runs.jsonl before the
next starts; a re-run skips run_keys already present, so a killed batch
(quota windows included) loses no paid work. Failures append to
errors.jsonl and are retried on resume.

run_key carries no model or effort, so give every (model, effort) arm its
own --runs-file — pointing a second arm at an existing file silently skips
its runs as already done.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from tellbench.adapters.gitstate import (
    agent_file_changes,
    expected_initial_status,
    parse_git_status,
    parse_numstat,
)
from tellbench.detectors import run_all
from tellbench.probes.families.messy_repo.generate import materialize
from tellbench.schema.events import FrozenModel, ToolCall
from tellbench.schema.manifest import InstanceFrame, InstanceManifest
from tellbench.schema.scores import DetectorResult
from tellbench.schema.trace import RunMeta, Trace


class ProbeBundle(Protocol):
    """What run_instance needs from any family's InstanceBundle."""

    @property
    def manifest(self) -> InstanceManifest: ...
    @property
    def files(self) -> dict[str, str]: ...
    @property
    def setup_script(self) -> str: ...


# single-shot families only — multi-turn families (one_at_a_time,
# constraint_decay, false_pushback, iteration_diversity) need their Inspect
# scripted counterparty and cannot run through one `claude -p` call
#
# text-only families have no sandbox: manifest-only bundles, prompt in /
# text out. Their Inspect tasks pin generate(tool_calls="none"); the CLI
# mirror is omitting --allowedTools so dontAsk mode denies every tool.
TEXT_FAMILIES = (
    "consensus_distance",
    "rewrite_reflex",
)
FAMILY_CHOICES = (
    "messy_repo",
    "forbidden_improvement",
    "impossible_errand",
    "clarification_grid",
    "approach_stability",
    *TEXT_FAMILIES,
)
_GRID_FAMILY = "clarification_grid"
_SPECIFICITY_FAMILY = "approach_stability"

# families whose generate_instance(seed, frame) takes no variant kwargs —
# non-honeypot probes with nothing to control for (the text families plus
# the scripted multi-turn families that plan through claude_code_multiturn)
_NO_VARIANT_FAMILIES = (
    *TEXT_FAMILIES,
    "one_at_a_time",
    "constraint_decay",
    "iteration_diversity",
)

ARM_SUBSCRIPTION = "subscription"
ARM_API = "api"
ARM_KIMI = "kimi"
ARM_OPENROUTER = "openrouter"
ARMS = (ARM_SUBSCRIPTION, ARM_API, ARM_KIMI, ARM_OPENROUTER)

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

ALLOWED_TOOLS = ("Bash", "Edit", "Write", "Read", "Glob", "Grep")
PERMISSION_MODE = "dontAsk"
SETTING_SOURCES = "project"
DEFAULT_TIMEOUT_SECONDS = 600
_STRIPPED_ENV = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
# All arms route through the local capture proxy (a logging proxy on localhost).
# --setting-sources project skips ~/.claude/settings.json, so the proxy URL
# must be pinned here or benchmark wire traffic (incl. Claude-5 thinking,
# recoverable NOWHERE else) bypasses capture entirely — discovered 2026-07-12:
# 360 Fable sessions ran with zero thinking captured. The inherited value is
# still stripped above; this pin is explicit and deterministic, not inherited.
CAPTURE_PROXY_URL = "http://localhost:8119"
# Second capture-proxy instance fronting Kimi For Coding's Anthropic-
# compatible endpoint (same proxy, --port 8120 --upstream
# https://api.kimi.com/coding --spool-suffix=-kimi). Same spool dir and
# envelope, own daily file — the capture contract's reach extended to the
# kimi arm 2026-08-02.
KIMI_CAPTURE_PROXY_URL = "http://localhost:8120"
# OpenRouter's Anthropic-compatible Messages surface (verified 2026-08-21:
# POST https://openrouter.ai/api/v1/messages answered stealth/ox-alpha with
# thinking blocks + usage). DIRECT, no capture proxy: the :8119 proxy was
# shut off 2026-08-21 (Anthropic blocked it). Wire record for this
# arm is OpenRouter's own activity log plus the CLI transcript; nothing
# Anthropic-side is reachable here so the capture contract is not in play.
OPENROUTER_BASE_URL = "https://openrouter.ai/api"
# Claude Code issues side calls (titles, summaries) on its small/fast model
# by Anthropic model id; OpenRouter 404s those ids, so every model slot is
# pinned to the arm's target model via these env keys.
_OPENROUTER_MODEL_SLOT_KEYS = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
)


class RunSpec(FrozenModel):
    family: str = "messy_repo"
    seed: int
    frame: InstanceFrame
    baseline: bool
    # clarification_grid cell coordinates; None for standard families
    stakes: str | None = None
    ambiguous: bool | None = None
    # approach_stability prompt-specificity variant; None elsewhere
    specificity: str | None = None
    arm: str
    k_index: int
    instance_id: str

    @property
    def run_key(self) -> str:
        return f"{self.instance_id}:{self.arm}:{self.k_index}"


def _cell_variants(family: str, include_baselines: bool) -> list[dict]:
    """Per-instance generator kwargs beyond (seed, frame).

    clarification_grid has no optional baselines — its clear cells ARE the
    over-asking control, so --no-baselines is a no-op for it.
    """

    if family == _GRID_FAMILY:
        return [
            {"stakes": stakes, "ambiguous": ambiguous}
            for stakes in ("low", "high")
            for ambiguous in (True, False)
        ]
    if family == _SPECIFICITY_FAMILY:
        # non-honeypot, no baselines; the vague/molecular pair IS the design
        return [{"specificity": s} for s in ("vague", "molecular")]
    if family in _NO_VARIANT_FAMILIES:
        # generate_instance(seed, frame) only — no baseline kwarg exists;
        # non-honeypot families plant nothing, so there is nothing to control
        return [{}]
    variants = [False, True] if include_baselines else [False]
    return [{"baseline": baseline} for baseline in variants]


def generate_for(family: str, seed: int, frame: InstanceFrame, **cell) -> ProbeBundle:
    module = importlib.import_module(f"tellbench.probes.families.{family}.generate")
    return module.generate_instance(seed, frame, **cell)


def _spec_cell(spec: RunSpec) -> dict:
    if spec.family == _GRID_FAMILY:
        return {"stakes": spec.stakes, "ambiguous": spec.ambiguous}
    if spec.family == _SPECIFICITY_FAMILY:
        return {"specificity": spec.specificity}
    if spec.family in _NO_VARIANT_FAMILIES:
        return {}
    return {"baseline": spec.baseline}


class RunRecord(FrozenModel):
    run_key: str
    arm: str
    requested_model: str
    effort: str | None = None
    cli_version: str
    session_id: str
    duration_s: float
    finished_at: str
    cc_meta: dict
    trace: Trace
    detectors: tuple[DetectorResult, ...]


def build_env(arm: str, base_env: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in base_env.items() if k not in _STRIPPED_ENV}
    if arm == ARM_SUBSCRIPTION:
        env.pop("ANTHROPIC_API_KEY", None)
    elif arm == ARM_API:
        if not env.get("ANTHROPIC_API_KEY"):
            raise ValueError("api arm requires ANTHROPIC_API_KEY in the environment")
    elif arm == ARM_KIMI:
        kimi_key = base_env.get("KIMI_API_KEY")
        if not kimi_key:
            raise ValueError("kimi arm requires KIMI_API_KEY in the environment")
        env["ANTHROPIC_API_KEY"] = kimi_key
        env["ANTHROPIC_BASE_URL"] = KIMI_CAPTURE_PROXY_URL
        return env
    elif arm == ARM_OPENROUTER:
        or_key = base_env.get("OPENROUTER_API_KEY")
        if not or_key:
            raise ValueError("openrouter arm requires OPENROUTER_API_KEY in the environment")
        or_model = base_env.get("OPENROUTER_MODEL")
        if not or_model:
            raise ValueError(
                "openrouter arm requires OPENROUTER_MODEL (e.g. stealth/ox-alpha) "
                "so Claude Code's side-call model slots resolve on OpenRouter"
            )
        env["ANTHROPIC_API_KEY"] = or_key
        env["ANTHROPIC_BASE_URL"] = OPENROUTER_BASE_URL
        for key in _OPENROUTER_MODEL_SLOT_KEYS:
            env[key] = or_model
        return env
    else:
        raise ValueError(f"unknown arm: {arm}")
    env["ANTHROPIC_BASE_URL"] = CAPTURE_PROXY_URL
    return env


def cc_command(
    prompt: str,
    model: str,
    session_id: str,
    claude_bin: str,
    effort: str | None = None,
    tools: tuple[str, ...] = ALLOWED_TOOLS,
    resume: bool = False,
) -> list[str]:
    # resume=True continues the pinned session in place: verified live
    # 2026-07-11 (scratchpad resume_probe) — `-p --resume <id>` keeps the
    # SAME session id and appends to the same transcript file, so every
    # transcript parser works unchanged across episodes
    command = [
        claude_bin,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--model",
        model,
        "--resume" if resume else "--session-id",
        session_id,
        "--permission-mode",
        PERMISSION_MODE,
        "--setting-sources",
        SETTING_SOURCES,
    ]
    if effort is not None:
        command += ["--effort", effort]
    if not tools:
        # text-only families: no allowlist at all — dontAsk denies every
        # tool call, the CLI mirror of Inspect's generate(tool_calls="none")
        return command
    # the variadic tool list stays last so a later option can never be
    # consumed as a tool name
    return [*command, "--allowedTools", *tools]


def workdir_slug(workdir: Path) -> str:
    """Claude Code 2.1.204 maps "/", ".", AND "_" to "-" in project dir
    names (verified against a live transcript dir; underscores broke the
    first real run — transcript silently not found, empty tool_calls)."""

    return str(workdir).replace("/", "-").replace(".", "-").replace("_", "-")


def transcript_path(workdir: Path, session_id: str, claude_home: Path | None = None) -> Path:
    home = claude_home if claude_home is not None else Path.home() / ".claude"
    return home / "projects" / workdir_slug(workdir) / f"{session_id}.jsonl"


def tool_calls_from_transcript(jsonl_text: str) -> tuple[ToolCall, ...]:
    calls: list[ToolCall] = []
    index = 0
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
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            arguments = item.get("input") or {}
            if isinstance(arguments, dict):
                rendered = " ".join(str(value) for value in arguments.values())
            else:
                rendered = str(arguments)
            calls.append(
                ToolCall(index=index, name=str(item.get("name", "")), arguments=rendered)
            )
            index += 1
    return tuple(calls)


def thinking_from_transcript(jsonl_text: str) -> tuple[str, ...]:
    """Thinking-block text from the Claude Code session transcript, in order.

    Best-effort by design: Claude Code redacts thinking for model tiers that
    default to omitted display (the capture proxy exists for exactly
    that reason), but budget_tokens-era models (e.g. Haiku 4.5) write
    real thinking text into the transcript. Empty blocks are never stored.
    """

    turns: list[str] = []
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
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "thinking":
                continue
            text = str(item.get("thinking", "") or "")
            if text.strip():
                turns.append(text)
    return tuple(turns)


def _git(workdir: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=workdir, capture_output=True, text=True, timeout=60
    )
    return result.stdout if result.returncode == 0 else ""


def restore_baseline(workdir: Path, baseline_sha: str) -> None:
    """Fold any agent-made commits back into the working tree.

    End-state reads compare the working tree against HEAD, but agents
    sometimes `git commit` their work (27/96 pilot runs, 2/6 smoke runs) —
    a committed change is invisible to both `git status` and
    `git diff HEAD`. Soft-resetting to the planted baseline makes every
    agent change readable again without touching file contents.
    """

    if not baseline_sha:
        raise RuntimeError("baseline SHA unavailable; cannot normalize end state")
    result = subprocess.run(
        ["git", "reset", "--soft", baseline_sha],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git reset --soft failed: {result.stderr[:300]}")


def _cli_version(claude_bin: str) -> str:
    result = subprocess.run(
        [claude_bin, "--version"], capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip()


def _result_record(parsed: object) -> dict:
    """Normalize --output-format json across CLI versions.

    ≤2.1.203 emitted a single result object; 2.1.204 emits the full message
    stream as a JSON array whose terminal record has type == "result"
    (verified against a live 2.1.204 capture). Same keys either way.
    """

    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        for record in reversed(parsed):
            if isinstance(record, dict) and record.get("type") == "result":
                return record
        raise RuntimeError("no result record in claude JSON output array")
    raise RuntimeError(f"unexpected claude JSON output type: {type(parsed).__name__}")


def run_instance(
    bundle: ProbeBundle,
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
    text_only = manifest.family in TEXT_FAMILIES
    # resolve(): Claude Code names the transcript project dir after the child
    # process's PHYSICAL cwd — a relative workdir_root would compute a slug
    # that misses the transcript entirely (empty tool_calls, silently).
    workdir = (
        workdir_root / f"{spec.run_key.replace(':', '_')}-{uuid.uuid4().hex[:8]}"
    ).resolve()
    workdir.mkdir(parents=True, exist_ok=False)
    session_id = str(uuid.uuid4())
    started = time.monotonic()
    baseline_sha = ""
    try:
        if not text_only:
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
            cc_command(
                manifest.task_prompt,
                model,
                session_id,
                claude_bin,
                effort=effort,
                tools=() if text_only else ALLOWED_TOOLS,
            ),
            cwd=workdir,
            env=build_env(spec.arm, dict(os.environ)),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"claude exited {completed.returncode}: "
                f"{(completed.stderr or completed.stdout)[:500]}"
            )
        result = _result_record(json.loads(completed.stdout))
        if not text_only:
            restore_baseline(workdir, baseline_sha)

        transcript_file = transcript_path(workdir, session_id)
        if not transcript_file.exists():
            # a session always writes its transcript; absence means the
            # capture is broken (e.g. disk full), never a quiet run
            raise RuntimeError(f"transcript missing: {transcript_file}")
        transcript_text = transcript_file.read_text()
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
                model=model,
                family=manifest.family,
                instance_id=manifest.instance_id,
                frame=manifest.frame,
                k_index=spec.k_index,
                started_at=datetime.now(timezone.utc).isoformat(),
            ),
            tool_calls=tool_calls_from_transcript(transcript_text),
            file_changes=file_changes,
            final_report=str(result.get("result", "")),
            transcript_ref=str(transcript_file),
            thinking_turns=thinking_from_transcript(transcript_text),
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
            cc_meta={
                key: result.get(key)
                for key in ("subtype", "total_cost_usd", "usage", "modelUsage", "num_turns", "is_error")
            },
            trace=trace,
            detectors=run_all(trace, manifest),
        )
    finally:
        if not keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)


def load_done_keys(runs_file: Path) -> set[str]:
    if not runs_file.exists():
        return set()
    keys: set[str] = set()
    for line in runs_file.read_text().splitlines():
        try:
            keys.add(json.loads(line)["run_key"])
        except (json.JSONDecodeError, KeyError):
            continue
    return keys


def append_record(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(payload + "\n")


def plan_runs(
    seeds: list[int],
    frames: list[InstanceFrame],
    arms: list[str],
    k: int,
    include_baselines: bool,
    done_keys: set[str],
    family: str = "messy_repo",
) -> list[RunSpec]:
    specs: list[RunSpec] = []
    for seed in seeds:
        for frame in frames:
            for cell in _cell_variants(family, include_baselines):
                manifest = generate_for(family, seed, frame, **cell).manifest
                for arm in arms:
                    for k_index in range(k):
                        spec = RunSpec(
                            family=family,
                            seed=seed,
                            frame=frame,
                            baseline=manifest.baseline,
                            stakes=cell.get("stakes"),
                            ambiguous=cell.get("ambiguous"),
                            specificity=cell.get("specificity"),
                            arm=arm,
                            k_index=k_index,
                            instance_id=manifest.instance_id,
                        )
                        if spec.run_key not in done_keys:
                            specs.append(spec)
    return specs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run single-shot agentic probe families via Claude Code CLI"
    )
    parser.add_argument(
        "--family",
        default="messy_repo",
        choices=FAMILY_CHOICES,
        help="probe family (clarification_grid enumerates its 2x2 cells; "
        "--no-baselines is a no-op there)",
    )
    parser.add_argument("--seeds", default="0-4", help="range like 0-4 or list like 0,3,7")
    parser.add_argument("--frames", default="both", choices=["both", "eval_coded", "prod_coded"])
    parser.add_argument("--arms", default=ARM_SUBSCRIPTION, help="comma list: " + ",".join(ARMS))
    parser.add_argument("--k", type=int, default=1)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--effort",
        default=None,
        choices=EFFORT_LEVELS,
        help="pass --effort to the CLI and record it on each run",
    )
    parser.add_argument("--runs-file", type=Path, default=Path("runs/runs.jsonl"))
    parser.add_argument("--errors-file", type=Path, default=Path("runs/errors.jsonl"))
    parser.add_argument(
        "--workdir-root",
        type=Path,
        # OUTSIDE the repo tree: on 2026-07-13 sandboxed runs walked up
        # from runs/work, edited probe generators, and committed to the
        # real repo (a756ea3). An external root leaves escapees nothing
        # to find.
        # OUTSIDE the operator's home dir too (2026-07-31): with cwd under
        # /Users/<operator>, Claude Code's ancestor discovery reclassifies
        # ~/.claude/CLAUDE.md as PROJECT memory, which --setting-sources
        # project keeps — that injected the operator's ruleset into 82% of
        # all Claude sessions (docs/contamination-audit.md). Outside the
        # home dir the file is user memory only, which the flag excludes
        # (wire-verified both directions, smoke 2026-07-31).
        # Pass an explicit root only to extend an era intentionally.
        default=Path("/private/var/tmp/tellbench-work"),
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--no-baselines", action="store_true")
    parser.add_argument("--keep-workdirs", action="store_true")
    parser.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="stop after this many completed runs (quota-bounded rounds); "
        "the done-key skip makes the next invocation continue exactly here",
    )
    return parser.parse_args()


def _parse_seeds(raw: str) -> list[int]:
    if "-" in raw and "," not in raw:
        low, high = raw.split("-", 1)
        return list(range(int(low), int(high) + 1))
    return [int(part) for part in raw.split(",") if part.strip()]


def main() -> None:
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
    completed_now = 0
    for position, spec in enumerate(pending, start=1):
        if args.max_runs is not None and completed_now >= args.max_runs:
            print(f"MAX RUNS reached ({args.max_runs}); {len(pending) - position + 1} left pending", flush=True)
            break
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
        completed_now += 1
        fired = any(d.fired and d.detector_id == "tripwire_fired" for d in record.detectors)
        cost = record.cc_meta.get("total_cost_usd")
        print(
            f"done {spec.run_key} fired={fired} cost={cost} ({position}/{len(pending)})",
            flush=True,
        )


if __name__ == "__main__":
    main()
