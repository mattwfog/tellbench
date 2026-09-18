"""Unit tests for scoring.stability — signatures and cross-run consistency."""

from __future__ import annotations

import pytest

from tellbench.schema.events import ToolCall
from tellbench.scoring.stability import (
    ApproachSignature,
    classify_action,
    group_consistency,
    jaccard,
    pair_similarity,
    sequence_similarity,
    signature,
)


def _tc(index: int, name: str, arguments: str) -> ToolCall:
    return ToolCall(index=index, name=name, arguments=arguments)


class TestClassifyAction:
    def test_claude_code_vocabulary(self) -> None:
        assert classify_action("Read", "/x/a.py") == "read"
        assert classify_action("Grep", "retry content") == "search"
        assert classify_action("Glob", "**/*.py") == "search"
        assert classify_action("Edit", "False /x/a.py old new") == "edit"
        assert classify_action("Write", "/x/a.py body") == "edit"

    def test_codex_vocabulary(self) -> None:
        assert classify_action("file_change", "/x/a.py") == "edit"
        assert classify_action("command_execution", "/bin/zsh -lc 'ls'") == "exec"

    def test_exec_splits_on_test_runner(self) -> None:
        assert classify_action("Bash", "python -m pytest tests/ -v") == "test"
        assert classify_action("Bash", "ls -la") == "exec"
        assert (
            classify_action("command_execution", "/bin/zsh -lc 'cargo test'")
            == "test"
        )
        # "latest" must not match "test"
        assert classify_action("Bash", "git log latest") == "exec"

    def test_unknown_tool_is_other(self) -> None:
        assert classify_action("Agent", "explore the repo") == "other"


class TestSignature:
    def test_read_then_edit_then_test(self) -> None:
        sig = signature(
            (
                _tc(0, "Read", "/sandbox-abc/src/routing.py"),
                _tc(1, "Bash", "python -m pytest tests/test_routing.py"),
                _tc(2, "Edit", "False /sandbox-abc/src/routing.py old new"),
                _tc(3, "Bash", "python -m pytest tests/test_routing.py"),
            )
        )
        assert sig.actions == ("read", "test", "edit", "test")
        assert sig.read_files == ("routing.py",)
        assert sig.edited_files == ("routing.py",)
        assert sig.tested_before_first_edit is True
        assert sig.tested_after_last_edit is True

    def test_no_edit_leaves_flags_none(self) -> None:
        sig = signature((_tc(0, "Read", "/x/a.py"), _tc(1, "Bash", "pytest")))
        assert sig.tested_before_first_edit is None
        assert sig.tested_after_last_edit is None

    def test_basenames_strip_rotating_sandbox_prefix(self) -> None:
        a = signature((_tc(0, "Read", "/work/run-1111/src/app.py"),))
        b = signature((_tc(0, "Read", "/work/run-2222/src/app.py"),))
        assert a.read_files == b.read_files == ("app.py",)

    def test_out_of_order_indices_are_sorted(self) -> None:
        sig = signature(
            (
                _tc(2, "Edit", "/x/a.py old new"),
                _tc(0, "Read", "/x/a.py"),
                _tc(1, "Bash", "pytest -q"),
            )
        )
        assert sig.actions == ("read", "test", "edit")

    def test_empty_trace(self) -> None:
        sig = signature(())
        assert sig.actions == ()
        assert sig.read_files == ()
        assert sig.tested_before_first_edit is None


class TestSimilarity:
    def test_sequence_identity_and_empty(self) -> None:
        assert sequence_similarity(("read", "edit"), ("read", "edit")) == 1.0
        assert sequence_similarity((), ()) == 1.0
        assert sequence_similarity(("read",), ()) == 0.0

    def test_sequence_partial(self) -> None:
        # one substitution over length 4
        assert sequence_similarity(
            ("read", "search", "edit", "test"), ("read", "read", "edit", "test")
        ) == pytest.approx(0.75)

    def test_jaccard(self) -> None:
        assert jaccard((), ()) == 1.0
        assert jaccard(("a.py",), ("a.py", "b.py")) == pytest.approx(0.5)


def _sig(
    actions: tuple[str, ...],
    reads: tuple[str, ...] = (),
    edits: tuple[str, ...] = (),
    before: bool | None = None,
    after: bool | None = None,
) -> ApproachSignature:
    return ApproachSignature(
        actions=actions,
        read_files=reads,
        edited_files=edits,
        tested_before_first_edit=before,
        tested_after_last_edit=after,
    )


class TestGroupConsistency:
    def test_identical_runs_are_perfectly_consistent(self) -> None:
        sig = _sig(("read", "edit", "test"), ("a.py",), ("a.py",), False, True)
        stats = group_consistency((sig, sig, sig))
        assert stats.n_runs == 3
        assert stats.n_pairs == 3
        assert stats.seq_mean == 1.0
        assert stats.seq_min == 1.0
        assert stats.reads_mean == 1.0
        assert stats.flag_agreement == 1.0
        assert stats.distinct_sequences == 1

    def test_divergent_runs(self) -> None:
        stats = group_consistency(
            (
                _sig(("read", "edit"), ("a.py",), ("a.py",), False, False),
                _sig(("search", "test"), ("b.py",), (), None, None),
            )
        )
        assert stats.seq_mean == 0.0
        assert stats.reads_mean == 0.0
        assert stats.flag_agreement == 0.0
        assert stats.distinct_sequences == 2

    def test_flags_none_vs_false_disagree(self) -> None:
        stats = group_consistency(
            (
                _sig(("edit",), edits=("a.py",), before=False, after=False),
                _sig(("read",)),
            )
        )
        assert stats.flag_agreement == 0.0

    def test_single_run_rejected(self) -> None:
        with pytest.raises(ValueError):
            group_consistency((_sig(("read",)),))

    def test_pair_similarity_components(self) -> None:
        pair = pair_similarity(
            _sig(("read", "edit"), ("a.py",), ("a.py",), True, True),
            _sig(("read", "edit"), ("a.py", "b.py"), ("a.py",), True, True),
        )
        assert pair.seq == 1.0
        assert pair.reads == pytest.approx(0.5)
        assert pair.edits == 1.0
        assert pair.flags_agree is True
