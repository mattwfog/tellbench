"""Canonical column enumeration for judge extraction.

Every single-shot family in judge scope shares the same 90-column
canonical layout, pinned by the family audits (e.g.
docs/family-reports/rewrite_reflex.md:16): 8 Claude models × 6 efforts
as `*_rerun3` assembled thinking-era files, opus-5 × 6 as plain-named
files, and 36 codex columns as plain-named files. Enumeration asserts
the audited totals — a missing or extra file dies loudly instead of
silently shrinking a denominator.

false_pushback and constraint_decay are NOT enumerated here: pushback
judge items ride runs/false_pushback_flips.jsonl (its own reconstruction
scope), and decay has no judge item on this data (family report §5.2 —
moot; the breaks are refusals).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, NamedTuple

RUNS = Path(__file__).resolve().parents[3] / "runs"

EFFORTS: tuple[str | None, ...] = (None, "low", "medium", "high", "xhigh", "max")

CLAUDE_RERUN3_MODELS = (
    "claude-fable-5",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
    "claude-sonnet-5",
)
OPUS5 = "claude-opus-5"
EXPECTED_CODEX_COLUMNS = 36
EXPECTED_TOTAL_COLUMNS = 90


class Column(NamedTuple):
    family: str
    model: str
    effort: str | None
    path: Path


def _claude_columns(family: str) -> Iterator[Column]:
    for model in CLAUDE_RERUN3_MODELS:
        for effort in EFFORTS:
            eff = f"_{effort}" if effort else ""
            yield Column(
                family, model, effort, RUNS / f"{family}_{model}{eff}_rerun3.jsonl"
            )
    for effort in EFFORTS:
        eff = f"_{effort}" if effort else ""
        yield Column(family, OPUS5, effort, RUNS / f"{family}_{OPUS5}{eff}.jsonl")


def _codex_columns(family: str) -> Iterator[Column]:
    for path in sorted(RUNS.glob(f"{family}_codex-*.jsonl")):
        name = path.name
        if ".errors." in name or "_clean" in name:
            continue
        stem = name[len(family) + 1 : -len(".jsonl")]
        parts = stem.rsplit("_", 1)
        known_efforts = ("low", "medium", "high", "xhigh", "max", "ultra")
        if len(parts) == 2 and parts[1] in known_efforts:
            yield Column(family, parts[0], parts[1], path)
        else:
            yield Column(family, stem, None, path)


def canonical_columns(family: str) -> tuple[Column, ...]:
    """The family's 90 canonical columns, existence-checked and counted."""
    columns = tuple(_claude_columns(family)) + tuple(_codex_columns(family))
    missing = [c.path.name for c in columns if not c.path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"{family}: {len(missing)} canonical files missing, e.g. {missing[:3]}"
        )
    n_codex = sum(1 for c in columns if c.model.startswith("codex-"))
    if n_codex != EXPECTED_CODEX_COLUMNS or len(columns) != EXPECTED_TOTAL_COLUMNS:
        raise AssertionError(
            f"{family}: {len(columns)} columns ({n_codex} codex); audited layout is "
            f"{EXPECTED_TOTAL_COLUMNS} ({EXPECTED_CODEX_COLUMNS} codex) — see the "
            "family report's coverage line before touching this map"
        )
    return columns
