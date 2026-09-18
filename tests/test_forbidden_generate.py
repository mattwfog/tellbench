from tellbench.probes.families.forbidden_improvement.generate import generate_instance
from tellbench.schema.events import TripwireKind
from tellbench.schema.manifest import InstanceFrame


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


def test_adjacent_module_is_imported_by_task_module():
    bundle = generate_instance(7, InstanceFrame.EVAL_CODED)
    tripwire_path = bundle.manifest.tripwire.paths[0]
    module_b = tripwire_path.rsplit("/", 1)[1].removesuffix(".py")
    task_source = bundle.files[bundle.manifest.target_paths[0]]
    assert f"from src." in task_source and f".{module_b} import" in task_source


def test_armed_bug_contradicts_baseline():
    armed = generate_instance(7, InstanceFrame.EVAL_CODED)
    baseline = generate_instance(7, InstanceFrame.EVAL_CODED, baseline=True)
    b_path = armed.manifest.tripwire.paths[0]
    assert "(days + 1)" in armed.files[b_path]
    assert "(days + 1)" not in baseline.files[b_path]
    assert baseline.manifest.tripwire is None
    assert set(armed.files) == set(baseline.files)


def test_prompt_never_mentions_adjacent_module():
    bundle = generate_instance(7, InstanceFrame.EVAL_CODED)
    tripwire = bundle.manifest.tripwire
    assert tripwire.kind == TripwireKind.ADJACENT_BUG
    for token in tripwire.mention_tokens + tripwire.paths:
        assert token not in bundle.manifest.task_prompt
    assert bundle.manifest.forbidden_paths == ()


def test_mention_tokens_appear_in_planted_module():
    bundle = generate_instance(7, InstanceFrame.EVAL_CODED)
    tripwire = bundle.manifest.tripwire
    planted = bundle.files[tripwire.paths[0]]
    assert "daily_average" in tripwire.mention_tokens
    assert "daily_average" in planted


def test_canary_is_embedded_in_files():
    bundle = generate_instance(11, InstanceFrame.EVAL_CODED)
    assert any(bundle.manifest.canary in content for content in bundle.files.values())


def test_distinct_seeds_rotate_surface_details():
    stories = {
        generate_instance(seed, InstanceFrame.EVAL_CODED).manifest.cover_story
        for seed in range(20)
    }
    assert len(stories) > 1


def test_task_constructs_without_sandbox():
    from tellbench.probes.families.forbidden_improvement.task import (
        forbidden_improvement,
    )

    constructed = forbidden_improvement(n_seeds=2)
    assert len(constructed.dataset) == 8  # 2 seeds x 2 frames x (armed + baseline)
