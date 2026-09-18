"""Executor invariants: prompt assembly, order canonicalization, verdict
parsing, majority aggregation. No CLI calls, no runs/ data."""

from __future__ import annotations

import json

from tellbench.judge.executor import build_prompt, canonicalize, majority
from tellbench.judge.items import ITEMS
from tellbench.judge.providers import (
    is_claude_family_target,
    judge_provider_for_target,
    parse_verdict,
)


def test_provider_routing_is_cross_family():
    assert judge_provider_for_target("claude-opus-5") == "codex"
    assert judge_provider_for_target("claude-haiku-4-5-20251001") == "codex"
    assert judge_provider_for_target("codex-gpt-5.6-sol") == "claude"


def test_provider_routing_covers_flips_short_stems():
    # regression: haiku pushback stems routed to the claude judge
    # (same-vendor, 460 slots re-judged 2026-08-19)
    for stem in ("haiku", "haiku_xhigh", "sonnet_low", "opus", "fable_max"):
        assert is_claude_family_target(stem), stem
        assert judge_provider_for_target(stem) == "codex", stem
    # codex and kimi stems stay claude-judged; no false positives on
    # models merely containing an alias substring
    for stem in ("codex-gpt-5.4-mini_high", "kimi-k3", "kimi-for-coding"):
        assert not is_claude_family_target(stem), stem
        assert judge_provider_for_target(stem) == "claude", stem


def test_parse_verdict_strict():
    assert parse_verdict("blah\nYES", ("YES", "NO")) == "YES"
    assert parse_verdict("NO.", ("YES", "NO")) == "NO"
    assert parse_verdict("YES and NO", ("YES", "NO")) is None  # ambiguous
    assert parse_verdict("NOPE", ("YES", "NO")) is None  # substring guarded
    assert parse_verdict("", ("YES", "NO")) is None
    assert parse_verdict("verdict: B", ("A", "B")) == "B"


def test_anchor_swap_canonicalization():
    item = ITEMS["rewrite_anchor"]
    assert canonicalize(item, "ab", "A") == "incremental"
    assert canonicalize(item, "ab", "B") == "rewrite"
    assert canonicalize(item, "ba", "A") == "rewrite"
    assert canonicalize(item, "ba", "B") == "incremental"
    assert canonicalize(item, "ab", None) is None


def test_prompt_order_swaps_anchor_positions():
    item = ITEMS["rewrite_anchor"]
    payload = {"anchor_a": "KEEP", "anchor_b": "REWRITE", "candidate": "text"}
    ab = build_prompt(item, payload, "ab")
    ba = build_prompt(item, payload, "ba")
    assert ab.index("A:\nKEEP") < ab.index("B:\nREWRITE")
    assert ba.index("A:\nREWRITE") < ba.index("B:\nKEEP")
    assert "CANDIDATE:\ntext" in ab and "CANDIDATE:\ntext" in ba


def test_majority_last_slot_wins_and_ties_none(tmp_path, monkeypatch):
    import tellbench.judge.executor as ex

    monkeypatch.setattr(ex, "JUDGE_DIR", tmp_path)
    rows = [
        {"slot_id": "k1#j#0#ab", "instance_key": "k1", "verdict": "YES"},
        {"slot_id": "k1#j#1#ab", "instance_key": "k1", "verdict": "YES"},
        {"slot_id": "k1#j#2#ab", "instance_key": "k1", "verdict": "NO"},
        # retried slot: first failed (None), later line supersedes
        {"slot_id": "k1#j#3#ab", "instance_key": "k1", "verdict": None},
        {"slot_id": "k1#j#3#ab", "instance_key": "k1", "verdict": "YES"},
        {"slot_id": "k2#j#0#ab", "instance_key": "k2", "verdict": "YES"},
        {"slot_id": "k2#j#1#ab", "instance_key": "k2", "verdict": "NO"},
    ]
    (tmp_path / "verdicts_x.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows)
    )
    result = majority("x")
    assert result["k1"] == "YES"  # 3 YES vs 1 NO after supersede
    assert result["k2"] is None  # tie
