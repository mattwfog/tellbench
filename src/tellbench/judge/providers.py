"""CLI judge providers: claude -p and codex exec, subscription-billed.

Cross-family routing is structural: claude-* targets are judged via the
codex CLI, codex-* targets via the claude CLI. Judge processes run with
cwd OUTSIDE the operator's home (the operator-config contamination
mechanism applies to judges too — docs/contamination-audit.md) and
`--setting-sources project` on the claude side, mirroring the probe
runners' clean invocation. CODEX_HOME is never redirected (capture
contract: rollouts are the codex capture source).

Verdict parsing is strict: the expected token must appear as a
standalone word in the response tail; anything else records verdict
None (a parse failure to retry), never a guess.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

JUDGE_WORKDIR = Path("/private/var/tmp/tellbench-judge")
CLAUDE_JUDGE_DEFAULT = "claude-opus-5"
CODEX_JUDGE_DEFAULT = "gpt-5.4"
TIMEOUT_S = 240


# false_pushback flips-file stems name Claude models by short alias
# (runs/false_pushback_haiku_xhigh.jsonl etc.) — routing on a bare
# "claude-" prefix sent all haiku pushback instances to the CLAUDE judge
# (same-vendor, hygiene violation; caught 2026-08-19, 460 slots archived
# to *.retired.jsonl and re-judged).
_CLAUDE_SHORT_STEMS = frozenset({"haiku", "sonnet", "opus", "fable"})


def is_claude_family_target(target_model: str) -> bool:
    if target_model.startswith("claude-"):
        return True
    return target_model.split("_", 1)[0] in _CLAUDE_SHORT_STEMS


def judge_provider_for_target(target_model: str) -> str:
    """codex judges claude-family targets; claude judges all others."""
    return "codex" if is_claude_family_target(target_model) else "claude"


def parse_verdict(output: str, tokens: tuple[str, str]) -> str | None:
    tail = output.strip().splitlines()[-6:]
    found: set[str] = set()
    for token in tokens:
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])")
        if any(pattern.search(line) for line in tail):
            found.add(token)
    return found.pop() if len(found) == 1 else None


def _run(cmd: list[str]) -> str:
    JUDGE_WORKDIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        cmd,
        cwd=JUDGE_WORKDIR,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} exited {proc.returncode}: {proc.stderr[-400:]}")
    return proc.stdout


def call_judge(provider: str, model: str, prompt: str) -> str:
    if provider == "claude":
        return _run(
            [
                "claude",
                "-p",
                prompt,
                "--model",
                model,
                "--setting-sources",
                "project",
            ]
        )
    if provider == "codex":
        return _run(
            [
                "codex",
                "exec",
                "--model",
                model,
                "--skip-git-repo-check",
                prompt,
            ]
        )
    raise ValueError(f"unknown judge provider {provider!r}")
