from tellbench.adapters.gitstate import (
    agent_file_changes,
    expected_initial_status,
    parse_git_status,
    parse_numstat,
)
from tellbench.schema.events import ChangeType, TripwireKind
from tests.helpers import make_manifest, make_tripwire


def test_parse_git_status_kinds():
    porcelain = " M src/app/billing.py\n D tests/test_flaky.py\n?? notes.md\nR  a.py -> b.py\n"
    parsed = parse_git_status(porcelain)
    assert parsed["src/app/billing.py"] == ChangeType.MODIFIED
    assert parsed["tests/test_flaky.py"] == ChangeType.DELETED
    assert parsed["notes.md"] == ChangeType.ADDED
    assert parsed["b.py"] == ChangeType.MODIFIED


def test_parse_git_status_staged_add_is_added():
    # what a restore_baseline'd agent commit looks like: staged, not '??'
    parsed = parse_git_status("A  fixtures/recorded.json\nAM sketch.py\n")
    assert parsed["fixtures/recorded.json"] == ChangeType.ADDED
    assert parsed["sketch.py"] == ChangeType.ADDED


def test_runtime_artifacts_are_not_agent_activity():
    porcelain = (
        "?? src/app/__pycache__/billing.cpython-312.pyc\n"
        "?? .pytest_cache/README.md\n"
        "?? tests/fixtures/settlements.json\n"
    )
    parsed = parse_git_status(porcelain)
    assert list(parsed) == ["tests/fixtures/settlements.json"]


def test_parse_numstat_handles_binary_dashes():
    parsed = parse_numstat("3\t1\tsrc/app/billing.py\n-\t-\tassets/logo.png\n")
    assert parsed["src/app/billing.py"] == (3, 1)
    assert parsed["assets/logo.png"] == (0, 0)


def test_planted_wip_dirt_is_not_agent_activity():
    manifest = make_manifest(
        make_tripwire(kind=TripwireKind.FOREIGN_WIP, paths=("src/app/reconcile.py",))
    )
    expected = expected_initial_status(manifest)
    observed = {"src/app/reconcile.py": ChangeType.MODIFIED}
    assert agent_file_changes(observed, {}, expected) == ()


def test_cleaned_wip_dirt_is_agent_activity():
    manifest = make_manifest(
        make_tripwire(kind=TripwireKind.FOREIGN_WIP, paths=("src/app/reconcile.py",))
    )
    expected = expected_initial_status(manifest)
    changes = agent_file_changes({}, {}, expected)
    assert len(changes) == 1
    assert changes[0].path == "src/app/reconcile.py"
    assert changes[0].change_type == ChangeType.MODIFIED


def test_unrelated_deletion_is_captured_with_line_counts():
    changes = agent_file_changes(
        {"docs/notes.md": ChangeType.DELETED},
        {"docs/notes.md": (0, 12)},
        {},
    )
    assert changes[0].change_type == ChangeType.DELETED
    assert changes[0].lines_removed == 12
