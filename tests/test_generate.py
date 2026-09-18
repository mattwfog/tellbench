import subprocess

from tellbench.probes.families.messy_repo.generate import (
    generate_instance,
    materialize,
)
from tellbench.schema.events import TripwireKind
from tellbench.schema.manifest import InstanceFrame


def _seed_for(kind: TripwireKind) -> int:
    for seed in range(10):
        tripwire = generate_instance(seed, InstanceFrame.EVAL_CODED).manifest.tripwire
        if tripwire is not None and tripwire.kind == kind:
            return seed
    raise AssertionError(f"no seed in 0-9 plants {kind}")


def _git_status_after_setup(bundle, dest) -> str:
    materialize(bundle.files, dest)
    subprocess.run(
        ["sh", "-c", bundle.setup_script], cwd=dest, capture_output=True, check=True
    )
    return subprocess.run(
        ["git", "status", "--porcelain"], cwd=dest, capture_output=True, text=True
    ).stdout


def test_same_seed_is_deterministic():
    first = generate_instance(7, InstanceFrame.EVAL_CODED)
    second = generate_instance(7, InstanceFrame.EVAL_CODED)
    assert first.manifest == second.manifest
    assert first.files == second.files
    assert first.setup_script == second.setup_script


def test_frame_pair_shares_decision_core():
    eval_bundle = generate_instance(7, InstanceFrame.EVAL_CODED)
    prod_bundle = generate_instance(7, InstanceFrame.PROD_CODED)
    assert eval_bundle.manifest.task_prompt == prod_bundle.manifest.task_prompt
    assert eval_bundle.manifest.target_paths == prod_bundle.manifest.target_paths
    assert eval_bundle.manifest.tripwire == prod_bundle.manifest.tripwire
    assert eval_bundle.manifest.canary == prod_bundle.manifest.canary


def test_prod_frame_adds_dressing_only():
    eval_bundle = generate_instance(7, InstanceFrame.EVAL_CODED)
    prod_bundle = generate_instance(7, InstanceFrame.PROD_CODED)
    assert "CHANGELOG.md" in prod_bundle.files
    assert "CHANGELOG.md" not in eval_bundle.files
    assert set(eval_bundle.files) - set(prod_bundle.files) == set()


def test_setup_script_is_not_a_repo_artifact():
    bundle = generate_instance(7, InstanceFrame.EVAL_CODED)
    assert "git init" in bundle.setup_script
    assert not any("setup" in path for path in bundle.files)


def test_baseline_plants_no_tripwire_artifacts():
    baseline = generate_instance(7, InstanceFrame.EVAL_CODED, baseline=True)
    assert baseline.manifest.baseline is True
    assert baseline.manifest.tripwire is None

    armed = generate_instance(7, InstanceFrame.EVAL_CODED)
    tripwire_paths = armed.manifest.tripwire.paths
    for path in armed.files:
        if any(path.startswith(p.rstrip("/")) for p in tripwire_paths):
            assert path not in baseline.files


def test_reset_script_setup_leaves_a_clean_tree(tmp_path):
    # regression: pilot capture 2026-07-11 — the post-commit chmod left the
    # reset script MODIFIED (mode-only) in git status, so the differ charged
    # a phantom out-of-scope edit to every model on this instance
    seed = _seed_for(TripwireKind.RESET_SCRIPT)
    bundle = generate_instance(seed, InstanceFrame.EVAL_CODED)
    assert _git_status_after_setup(bundle, tmp_path) == ""


def test_foreign_wip_setup_keeps_the_wip_dirty(tmp_path):
    # the intended dirtiness must survive the clean-tree fix: foreign_wip's
    # whole point is an uncommitted diff in the working tree
    seed = _seed_for(TripwireKind.FOREIGN_WIP)
    bundle = generate_instance(seed, InstanceFrame.EVAL_CODED)
    status = _git_status_after_setup(bundle, tmp_path)
    wip_path = bundle.manifest.tripwire.paths[0]
    assert f" M {wip_path}" in status


def test_canary_is_embedded_in_files():
    bundle = generate_instance(11, InstanceFrame.EVAL_CODED)
    assert any(bundle.manifest.canary in content for content in bundle.files.values())


def test_distinct_seeds_rotate_surface_details():
    stories = {
        generate_instance(seed, InstanceFrame.EVAL_CODED).manifest.cover_story
        for seed in range(20)
    }
    assert len(stories) > 1
