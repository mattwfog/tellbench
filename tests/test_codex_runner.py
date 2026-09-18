import json

from tellbench.runners.codex_cli import codex_command, parse_events

# verbatim-shaped events from a captured codex-cli 0.144.1 session
# (2026-07-11, codex exec --json on a scratch repo)
_EVENTS = "\n".join(
    [
        json.dumps({"type": "thread.started", "thread_id": "019f5181-0358-7583"}),
        json.dumps({"type": "turn.started"}),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "agent_message",
                    "text": "I'll inspect the file and fix it.",
                },
            }
        ),
        json.dumps(
            {
                "type": "item.started",
                "item": {
                    "id": "item_1",
                    "type": "command_execution",
                    "command": "/bin/zsh -lc \"cat greeting.txt\"",
                },
            }
        ),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "command_execution",
                    "command": "/bin/zsh -lc \"cat greeting.txt\"",
                    "aggregated_output": "helo world",
                },
            }
        ),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_2",
                    "type": "file_change",
                    "changes": [{"path": "/w/repo/greeting.txt"}],
                },
            }
        ),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_3",
                    "type": "agent_message",
                    "text": "Fixed the typo in greeting.txt.",
                },
            }
        ),
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 77743, "output_tokens": 424},
            }
        ),
        "not json at all",
    ]
)


def test_parse_events_extracts_calls_in_order():
    parsed = parse_events(_EVENTS)
    assert [c.name for c in parsed.tool_calls] == ["command_execution", "file_change"]
    assert parsed.tool_calls[0].arguments == '/bin/zsh -lc "cat greeting.txt"'
    assert parsed.tool_calls[0].output_excerpt == "helo world"
    assert parsed.tool_calls[0].index == 0
    assert parsed.tool_calls[1].arguments == "/w/repo/greeting.txt"


def test_parse_events_started_items_are_not_double_counted():
    parsed = parse_events(_EVENTS)
    # item_1 appears as item.started AND item.completed; only completed counts
    assert len([c for c in parsed.tool_calls if c.name == "command_execution"]) == 1


def test_parse_events_collects_messages_thread_and_usage():
    parsed = parse_events(_EVENTS)
    assert parsed.agent_messages[-1] == "Fixed the typo in greeting.txt."
    assert parsed.thread_id == "019f5181-0358-7583"
    assert parsed.usage["output_tokens"] == 424
    assert parsed.thinking == ()


def test_codex_command_shape(tmp_path):
    command = codex_command("do the task", tmp_path, tmp_path / "last.txt")
    assert command[0:3] == ["codex", "exec", "--json"]
    assert "-s" in command and "workspace-write" in command
    assert command[-1] == "do the task"
    assert "-m" not in command

    with_model = codex_command("p", tmp_path, tmp_path / "l.txt", model="gpt-5.6-sol")
    assert with_model[with_model.index("-m") + 1] == "gpt-5.6-sol"

    with_effort = codex_command(
        "p", tmp_path, tmp_path / "l.txt", model="gpt-5.5", effort="high"
    )
    assert with_effort[with_effort.index("-c") + 1] == "model_reasoning_effort=high"
    assert with_effort[-1] == "p"
