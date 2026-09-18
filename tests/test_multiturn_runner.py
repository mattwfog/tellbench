import json

from tellbench.runners.claude_code import ARM_SUBSCRIPTION, cc_command, plan_runs
from tellbench.runners.claude_code_multiturn import (
    MULTITURN_FAMILIES,
    _episode_meta,
    assistant_texts_from_transcript,
)
from tellbench.schema.manifest import InstanceFrame


def _assistant_line(*blocks) -> str:
    return json.dumps(
        {"type": "assistant", "message": {"content": [dict(b) for b in blocks]}}
    )


def test_assistant_texts_orders_and_joins_blocks():
    lines = [
        json.dumps({"type": "user", "message": {"content": "task"}}),
        _assistant_line({"type": "text", "text": "first reply"}),
        json.dumps({"type": "user", "message": {"content": "again"}}),
        _assistant_line(
            {"type": "thinking", "thinking": "hmm"},
            {"type": "text", "text": "second"},
            {"type": "text", "text": "reply"},
        ),
        _assistant_line({"type": "text", "text": "   "}),  # whitespace-only: dropped
    ]
    texts = assistant_texts_from_transcript("\n".join(lines))
    assert texts == ("first reply", "second\nreply")


def test_cc_command_resume_swaps_session_flag():
    pinned = cc_command("t", "sonnet", "sid-1", "/bin/claude")
    assert pinned[pinned.index("--session-id") + 1] == "sid-1"
    assert "--resume" not in pinned
    resumed = cc_command("t", "sonnet", "sid-1", "/bin/claude", resume=True)
    assert resumed[resumed.index("--resume") + 1] == "sid-1"
    assert "--session-id" not in resumed


def test_plan_runs_multiturn_variants():
    # scripted-turn families carry no baseline kwarg — exactly one variant
    for family in ("one_at_a_time", "constraint_decay", "iteration_diversity"):
        specs = plan_runs(
            seeds=[0],
            frames=[InstanceFrame.EVAL_CODED, InstanceFrame.PROD_CODED],
            arms=[ARM_SUBSCRIPTION],
            k=1,
            include_baselines=True,
            done_keys=set(),
            family=family,
        )
        assert len(specs) == 2  # 2 frames x 1 variant
        assert all(not s.baseline for s in specs)
    # false_pushback keeps its planted/baseline pair
    specs = plan_runs(
        seeds=[0],
        frames=[InstanceFrame.EVAL_CODED],
        arms=[ARM_SUBSCRIPTION],
        k=1,
        include_baselines=True,
        done_keys=set(),
        family="false_pushback",
    )
    assert len(specs) == 2
    assert {s.baseline for s in specs} == {False, True}


def test_episode_meta_sums_costs_and_tolerates_missing():
    meta = _episode_meta(
        [
            {"subtype": "success", "total_cost_usd": 0.01, "num_turns": 3, "is_error": False},
            {"subtype": "success", "total_cost_usd": None, "num_turns": 1, "is_error": False},
            {"subtype": "success", "total_cost_usd": 0.02, "num_turns": 2, "is_error": False},
        ]
    )
    assert meta["episodes"] == 3
    assert abs(meta["total_cost_usd"] - 0.03) < 1e-9
    assert len(meta["per_episode"]) == 3


def test_family_registry_covers_all_families():
    from tellbench.runners.claude_code import FAMILY_CHOICES

    assert set(FAMILY_CHOICES) | set(MULTITURN_FAMILIES) == {
        "messy_repo",
        "forbidden_improvement",
        "impossible_errand",
        "clarification_grid",
        "approach_stability",
        "consensus_distance",
        "rewrite_reflex",
        "one_at_a_time",
        "constraint_decay",
        "false_pushback",
        "iteration_diversity",
    }
