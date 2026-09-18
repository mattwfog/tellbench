import json
import subprocess
from pathlib import Path

import pytest

from tellbench.adapters.gitstate import parse_git_status, parse_numstat
from tellbench.runners.claude_code import (
    ARM_API,
    ARM_KIMI,
    ARM_OPENROUTER,
    ARM_SUBSCRIPTION,
    CAPTURE_PROXY_URL,
    KIMI_CAPTURE_PROXY_URL,
    OPENROUTER_BASE_URL,
    build_env,
    cc_command,
    load_done_keys,
    plan_runs,
    restore_baseline,
    tool_calls_from_transcript,
    transcript_path,
)
from tellbench.schema.events import ChangeType
from tellbench.schema.manifest import InstanceFrame


def _sh(cwd, *args):
    subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)


def test_subscription_arm_strips_api_credentials():
    env = build_env(
        ARM_SUBSCRIPTION,
        {
            "PATH": "/bin",
            "ANTHROPIC_API_KEY": "sk-x",
            "ANTHROPIC_BASE_URL": "http://proxy",
            "CLAUDECODE": "1",
        },
    )
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDECODE" not in env
    assert env["PATH"] == "/bin"
    # inherited value stripped, capture proxy pinned deterministically
    assert env["ANTHROPIC_BASE_URL"] == CAPTURE_PROXY_URL


def test_api_arm_requires_key_and_strips_overrides():
    with pytest.raises(ValueError):
        build_env(ARM_API, {"PATH": "/bin"})
    env = build_env(ARM_API, {"ANTHROPIC_API_KEY": "sk-x", "ANTHROPIC_BASE_URL": "http://proxy"})
    assert env["ANTHROPIC_API_KEY"] == "sk-x"
    assert env["ANTHROPIC_BASE_URL"] == CAPTURE_PROXY_URL


def test_kimi_arm_maps_key_and_pins_kimi_capture_proxy():
    with pytest.raises(ValueError):
        build_env(ARM_KIMI, {"PATH": "/bin", "ANTHROPIC_API_KEY": "sk-ant"})
    env = build_env(
        ARM_KIMI,
        {
            "PATH": "/bin",
            "KIMI_API_KEY": "sk-kimi-x",
            # inherited Anthropic credentials/overrides must not leak through
            "ANTHROPIC_API_KEY": "sk-ant",
            "ANTHROPIC_BASE_URL": "http://proxy",
            "ANTHROPIC_AUTH_TOKEN": "tok",
        },
    )
    assert env["ANTHROPIC_API_KEY"] == "sk-kimi-x"
    assert env["ANTHROPIC_BASE_URL"] == KIMI_CAPTURE_PROXY_URL
    assert "ANTHROPIC_AUTH_TOKEN" not in env


def test_openrouter_arm_maps_key_direct_and_pins_model_slots():
    with pytest.raises(ValueError):
        build_env(ARM_OPENROUTER, {"PATH": "/bin", "OPENROUTER_MODEL": "stealth/ox-alpha"})
    with pytest.raises(ValueError):
        build_env(ARM_OPENROUTER, {"PATH": "/bin", "OPENROUTER_API_KEY": "sk-or-x"})
    env = build_env(
        ARM_OPENROUTER,
        {
            "PATH": "/bin",
            "OPENROUTER_API_KEY": "sk-or-x",
            "OPENROUTER_MODEL": "stealth/ox-alpha",
            "ANTHROPIC_API_KEY": "sk-ant",
            "ANTHROPIC_BASE_URL": "http://proxy",
            "ANTHROPIC_AUTH_TOKEN": "tok",
        },
    )
    assert env["ANTHROPIC_API_KEY"] == "sk-or-x"
    assert env["ANTHROPIC_BASE_URL"] == OPENROUTER_BASE_URL
    assert env["ANTHROPIC_BASE_URL"].startswith("https://openrouter.ai")
    assert env["ANTHROPIC_SMALL_FAST_MODEL"] == "stealth/ox-alpha"
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "stealth/ox-alpha"
    assert "ANTHROPIC_AUTH_TOKEN" not in env


def test_kimi_arm_leaves_claude_arm_pins_untouched():
    # the Claude capture pin is load-bearing (capture contract); adding the
    # kimi arm must not have changed either Claude arm's proxy URL
    base = {"ANTHROPIC_API_KEY": "sk-x", "KIMI_API_KEY": "sk-kimi-x"}
    assert build_env(ARM_SUBSCRIPTION, dict(base))["ANTHROPIC_BASE_URL"] == CAPTURE_PROXY_URL
    assert build_env(ARM_API, dict(base))["ANTHROPIC_BASE_URL"] == CAPTURE_PROXY_URL
    assert KIMI_CAPTURE_PROXY_URL != CAPTURE_PROXY_URL


def test_cc_command_never_bypasses_permissions():
    cmd = cc_command("fix it", "claude-sonnet-5", "abc-123", "/usr/local/bin/claude")
    assert "--dangerously-skip-permissions" not in cmd
    assert "bypassPermissions" not in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert cmd[cmd.index("--setting-sources") + 1] == "project"
    assert "--session-id" in cmd


def test_cc_command_effort_passthrough():
    plain = cc_command("fix it", "sonnet", "abc-123", "/usr/local/bin/claude")
    assert "--effort" not in plain
    cmd = cc_command("fix it", "sonnet", "abc-123", "/usr/local/bin/claude", effort="max")
    assert cmd[cmd.index("--effort") + 1] == "max"
    assert cmd.index("--effort") < cmd.index("--allowedTools")


def test_transcript_tool_call_extraction_preserves_order():
    lines = [
        json.dumps({"type": "user", "message": {"content": "hi"}}),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "looking"},
                        {"type": "tool_use", "name": "Bash", "input": {"command": "cat README.md"}},
                    ]
                },
            }
        ),
        "not json",
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": "a.py", "old_string": "x", "new_string": "y"}}
                    ]
                },
            }
        ),
    ]
    calls = tool_calls_from_transcript("\n".join(lines))
    assert [c.name for c in calls] == ["Bash", "Edit"]
    assert calls[0].index == 0 and calls[1].index == 1
    assert "cat README.md" in calls[0].arguments
    assert "a.py" in calls[1].arguments


def test_transcript_path_uses_workdir_slug():
    path = transcript_path(
        Path("/tmp/dispo/messy_repo-0_run.1"),
        "sess-1",
        claude_home=Path("/home/u/.claude"),
    )
    assert path == Path(
        "/home/u/.claude/projects/-tmp-dispo-messy-repo-0-run-1/sess-1.jsonl"
    )


def test_plan_runs_skips_done_keys_and_counts():
    all_specs = plan_runs(
        seeds=[0],
        frames=[InstanceFrame.EVAL_CODED],
        arms=[ARM_SUBSCRIPTION, ARM_API],
        k=2,
        include_baselines=True,
        done_keys=set(),
    )
    assert len(all_specs) == 2 * 2 * 2

    done = {all_specs[0].run_key}
    remaining = plan_runs(
        seeds=[0],
        frames=[InstanceFrame.EVAL_CODED],
        arms=[ARM_SUBSCRIPTION, ARM_API],
        k=2,
        include_baselines=True,
        done_keys=done,
    )
    assert len(remaining) == len(all_specs) - 1
    assert all(spec.run_key not in done for spec in remaining)


def test_plan_runs_dispatches_other_families():
    specs = plan_runs(
        seeds=[0],
        frames=[InstanceFrame.EVAL_CODED],
        arms=[ARM_SUBSCRIPTION],
        k=1,
        include_baselines=True,
        done_keys=set(),
        family="forbidden_improvement",
    )
    assert len(specs) == 2  # planted + baseline
    assert all(s.instance_id.startswith("forbidden_improvement-000000-") for s in specs)
    assert {s.baseline for s in specs} == {False, True}


def test_plan_runs_grid_enumerates_the_2x2_cells():
    specs = plan_runs(
        seeds=[0],
        frames=[InstanceFrame.EVAL_CODED, InstanceFrame.PROD_CODED],
        arms=[ARM_SUBSCRIPTION],
        k=1,
        include_baselines=True,
        done_keys=set(),
        family="clarification_grid",
    )
    assert len(specs) == 8  # 4 cells x 2 frames
    cells = {(s.stakes, s.ambiguous) for s in specs}
    assert cells == {("low", True), ("low", False), ("high", True), ("high", False)}
    # clear cells are the family's own baselines
    assert all(s.baseline == (not s.ambiguous) for s in specs)
    assert len({s.instance_id for s in specs}) == 8


def test_restore_baseline_makes_agent_commits_readable(tmp_path):
    # regression: smoke capture 2026-07-11 — agents that `git commit` their
    # work were invisible to status/diff-HEAD end-state reads (27/96 pilot
    # runs also committed)
    _sh(tmp_path, "git", "init", "-q", "-b", "main")
    (tmp_path / "app.py").write_text("x = 1\n")
    _sh(tmp_path, "git", "add", "-A")
    _sh(tmp_path, "git", "-c", "user.email=d@e.c", "-c", "user.name=d", "commit", "-qm", "baseline")
    baseline_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()

    # agent edits, adds a file, deletes nothing — and commits everything
    (tmp_path / "app.py").write_text("x = 2\ny = 3\n")
    (tmp_path / "new.py").write_text("z = 1\n")
    _sh(tmp_path, "git", "add", "-A")
    _sh(tmp_path, "git", "-c", "user.email=a@e.c", "-c", "user.name=a", "commit", "-qm", "agent work")

    committed_away = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert committed_away == ""  # the failure mode: clean tree, invisible work

    restore_baseline(tmp_path, baseline_sha)

    status = parse_git_status(
        subprocess.run(
            ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
        ).stdout
    )
    numstat = parse_numstat(
        subprocess.run(
            ["git", "diff", "HEAD", "--numstat"], cwd=tmp_path, capture_output=True, text=True
        ).stdout
    )
    assert status == {
        "app.py": ChangeType.MODIFIED,
        "new.py": ChangeType.ADDED,
    }
    assert numstat["app.py"] == (2, 1)


def test_restore_baseline_refuses_an_empty_sha(tmp_path):
    with pytest.raises(RuntimeError):
        restore_baseline(tmp_path, "")


def test_load_done_keys_tolerates_corrupt_tail(tmp_path):
    runs_file = tmp_path / "runs.jsonl"
    runs_file.write_text(
        json.dumps({"run_key": "a:subscription:0"})
        + "\n"
        + json.dumps({"run_key": "b:subscription:0"})
        + "\n"
        + '{"run_key": "c:subscription'
    )
    assert load_done_keys(runs_file) == {"a:subscription:0", "b:subscription:0"}


def test_plan_runs_text_families_have_no_baseline_variants():
    # consensus_distance / rewrite_reflex: generate_instance(seed, frame)
    # only — no baseline kwarg, nothing planted, one variant per (seed, frame)
    for family in ("consensus_distance", "rewrite_reflex"):
        specs = plan_runs(
            seeds=[0, 1],
            frames=[InstanceFrame.EVAL_CODED, InstanceFrame.PROD_CODED],
            arms=[ARM_SUBSCRIPTION],
            k=1,
            include_baselines=True,
            done_keys=set(),
            family=family,
        )
        assert len(specs) == 4  # 2 seeds x 2 frames x 1 variant
        assert all(not s.baseline for s in specs)
        assert all(s.instance_id.startswith(f"{family}-") for s in specs)


def test_cc_command_text_families_omit_allowed_tools():
    cmd = cc_command("write it", "sonnet", "abc-123", "/usr/local/bin/claude", tools=())
    assert "--allowedTools" not in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    # default path is unchanged
    assert "--allowedTools" in cc_command("fix it", "sonnet", "abc-123", "/usr/local/bin/claude")
