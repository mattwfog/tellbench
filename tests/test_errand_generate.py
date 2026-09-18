import json

from tellbench.probes.families.impossible_errand.generate import generate_instance
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


def test_armed_instance_omits_the_fixture():
    armed = generate_instance(7, InstanceFrame.EVAL_CODED)
    tripwire = armed.manifest.tripwire
    assert tripwire.kind == TripwireKind.MISSING_RESOURCE
    fixture_path = tripwire.paths[0]
    assert fixture_path.startswith("tests/fixtures/")
    assert fixture_path not in armed.files
    assert fixture_path in armed.manifest.task_prompt


def test_baseline_ships_a_valid_fixture():
    baseline = generate_instance(7, InstanceFrame.EVAL_CODED, baseline=True)
    assert baseline.manifest.tripwire is None
    armed = generate_instance(7, InstanceFrame.EVAL_CODED)
    fixture_path = armed.manifest.tripwire.paths[0]
    records = json.loads(baseline.files[fixture_path])
    assert len(records) > 0
    assert all(record["amount_cents"] > 0 for record in records)


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
    from tellbench.probes.families.impossible_errand.task import impossible_errand

    constructed = impossible_errand(n_seeds=2)
    assert len(constructed.dataset) == 8  # 2 seeds x 2 frames x (armed + baseline)
