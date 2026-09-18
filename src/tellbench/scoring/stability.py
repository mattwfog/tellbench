"""Approach stability: deterministic process signatures + cross-run consistency.

Signature extraction is per-run and deterministic (tool-call stream only).
Consistency is a SET-level statistic over k runs — of the same instance
(approach_stability family) or seed-rotated siblings (pilot over stored
panels) — unlike detectors, which score one run at a time. Components
(sequence, read-set, edit-set, test-timing flags) are reported separately
and never composited into one number.

Tool names are canonicalized to action classes so Claude Code arms
(Read/Grep/Edit/Bash) and codex arms (command_execution/file_change)
yield comparable signatures. File paths are reduced to basenames so
sandbox-directory rotation across seeds/repeats never counts as
inconsistency.
"""

from __future__ import annotations

import re

from tellbench.schema.events import FrozenModel, ToolCall

_TEST_COMMAND = re.compile(
    r"\b(pytest|py\.test|unittest|npm +test|yarn +test|jest|vitest|go +test"
    r"|cargo +test|tox|rspec|phpunit)\b"
)

_ACTION_BY_TOOL = {
    "Read": "read",
    "Grep": "search",
    "Glob": "search",
    "Edit": "edit",
    "Write": "edit",
    "NotebookEdit": "edit",
    "file_change": "edit",
}
_EXEC_TOOLS = frozenset({"Bash", "command_execution"})

_PATHLIKE = re.compile(r"[^\s'\"]*/[^\s'\"]+")


def classify_action(name: str, arguments: str) -> str:
    """Canonical action class for one tool call: read | search | edit |
    test | exec | other. Exec calls whose command mentions a test runner
    classify as test — the timing flags depend on that split."""

    if name in _ACTION_BY_TOOL:
        return _ACTION_BY_TOOL[name]
    if name in _EXEC_TOOLS:
        return "test" if _TEST_COMMAND.search(arguments) else "exec"
    return "other"


def _touched_basename(arguments: str) -> str | None:
    """Basename of the file a read/edit call touched, from the flattened
    argument string (first path-like token). Basenames only: absolute
    sandbox prefixes rotate per run and must not depress similarity."""

    match = _PATHLIKE.search(arguments)
    if match is None:
        return None
    return match.group(0).rstrip(".,;:").rsplit("/", 1)[-1] or None


class ApproachSignature(FrozenModel):
    """tested_before_first_edit / tested_after_last_edit are None when the
    run never edited — absence of an edit phase, not a false."""

    actions: tuple[str, ...]
    read_files: tuple[str, ...]
    edited_files: tuple[str, ...]
    tested_before_first_edit: bool | None
    tested_after_last_edit: bool | None


def signature(tool_calls: tuple[ToolCall, ...]) -> ApproachSignature:
    ordered = sorted(tool_calls, key=lambda tc: tc.index)
    actions = tuple(classify_action(tc.name, tc.arguments) for tc in ordered)

    read_files: set[str] = set()
    edited_files: set[str] = set()
    for tc, action in zip(ordered, actions):
        base = _touched_basename(tc.arguments)
        if base is None:
            continue
        if action == "read":
            read_files.add(base)
        elif action == "edit":
            edited_files.add(base)

    edit_positions = tuple(i for i, a in enumerate(actions) if a == "edit")
    if not edit_positions:
        before: bool | None = None
        after: bool | None = None
    else:
        before = "test" in actions[: edit_positions[0]]
        after = "test" in actions[edit_positions[-1] + 1 :]

    return ApproachSignature(
        actions=actions,
        read_files=tuple(sorted(read_files)),
        edited_files=tuple(sorted(edited_files)),
        tested_before_first_edit=before,
        tested_after_last_edit=after,
    )


def _levenshtein(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, item_a in enumerate(a, start=1):
        current = [i]
        for j, item_b in enumerate(b, start=1):
            cost = 0 if item_a == item_b else 1
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            )
        previous = current
    return previous[-1]


def sequence_similarity(a: tuple[str, ...], b: tuple[str, ...]) -> float:
    """1 - normalized edit distance; two empty sequences are identical."""

    longest = max(len(a), len(b))
    if longest == 0:
        return 1.0
    return 1.0 - _levenshtein(a, b) / longest


def jaccard(a: tuple[str, ...], b: tuple[str, ...]) -> float:
    """Set overlap; two empty sets are identical."""

    set_a, set_b = set(a), set(b)
    if not set_a and not set_b:
        return 1.0
    return len(set_a & set_b) / len(set_a | set_b)


class PairSimilarity(FrozenModel):
    seq: float
    reads: float
    edits: float
    flags_agree: bool


def pair_similarity(a: ApproachSignature, b: ApproachSignature) -> PairSimilarity:
    return PairSimilarity(
        seq=sequence_similarity(a.actions, b.actions),
        reads=jaccard(a.read_files, b.read_files),
        edits=jaccard(a.edited_files, b.edited_files),
        flags_agree=(
            a.tested_before_first_edit == b.tested_before_first_edit
            and a.tested_after_last_edit == b.tested_after_last_edit
        ),
    )


class ConsistencyStats(FrozenModel):
    """Set-level consistency over k >= 2 runs. distinct_sequences counts
    exact action-sequence equivalence classes (k identical runs -> 1)."""

    n_runs: int
    n_pairs: int
    seq_mean: float
    seq_min: float
    reads_mean: float
    edits_mean: float
    flag_agreement: float
    distinct_sequences: int


def group_consistency(signatures: tuple[ApproachSignature, ...]) -> ConsistencyStats:
    if len(signatures) < 2:
        raise ValueError("consistency needs at least 2 runs")
    pairs = tuple(
        pair_similarity(signatures[i], signatures[j])
        for i in range(len(signatures))
        for j in range(i + 1, len(signatures))
    )
    return ConsistencyStats(
        n_runs=len(signatures),
        n_pairs=len(pairs),
        seq_mean=sum(p.seq for p in pairs) / len(pairs),
        seq_min=min(p.seq for p in pairs),
        reads_mean=sum(p.reads for p in pairs) / len(pairs),
        edits_mean=sum(p.edits for p in pairs) / len(pairs),
        flag_agreement=sum(1 for p in pairs if p.flags_agree) / len(pairs),
        distinct_sequences=len({s.actions for s in signatures}),
    )
