"""Generator invariants + pure task construction for the seven new families."""

from tellbench.probes.families.clarification_grid.generate import (
    STAKES_HIGH,
    STAKES_LOW,
)
from tellbench.probes.families.clarification_grid.generate import (
    generate_instance as gen_grid,
)
from tellbench.probes.families.consensus_distance.generate import (
    generate_instance as gen_consensus,
)
from tellbench.probes.families.constraint_decay.generate import (
    generate_instance as gen_decay,
)
from tellbench.probes.families.false_pushback.generate import (
    DISPUTED_FUNCTION,
)
from tellbench.probes.families.false_pushback.generate import (
    generate_instance as gen_pushback,
)
from tellbench.probes.families.iteration_diversity.generate import (
    generate_instance as gen_iteration,
)
from tellbench.probes.families.one_at_a_time.generate import (
    RECORD_COUNT,
)
from tellbench.probes.families.one_at_a_time.generate import (
    generate_instance as gen_records,
)
from tellbench.probes.families.rewrite_reflex.generate import (
    generate_instance as gen_rewrite,
)
from tellbench.schema.manifest import InstanceFrame

EVAL = InstanceFrame.EVAL_CODED
PROD = InstanceFrame.PROD_CODED


def test_all_generators_are_deterministic():
    assert gen_rewrite(7, EVAL) == gen_rewrite(7, EVAL)
    assert gen_consensus(7, EVAL) == gen_consensus(7, EVAL)
    assert gen_iteration(7, EVAL) == gen_iteration(7, EVAL)
    assert gen_decay(7, EVAL) == gen_decay(7, EVAL)
    assert gen_grid(7, EVAL, STAKES_HIGH, True) == gen_grid(7, EVAL, STAKES_HIGH, True)
    assert gen_records(7, EVAL) == gen_records(7, EVAL)
    assert gen_pushback(7, EVAL) == gen_pushback(7, EVAL)


def test_rewrite_reflex_frames_share_the_code():
    eval_bundle = gen_rewrite(7, EVAL)
    prod_bundle = gen_rewrite(7, PROD)
    assert eval_bundle.legacy_code == prod_bundle.legacy_code
    assert eval_bundle.manifest.honeypot is False


def test_consensus_distance_has_ten_verbatim_elements():
    bundle = gen_consensus(7, EVAL)
    assert len(bundle.manifest.required_elements) == 10
    for element in bundle.manifest.required_elements:
        assert element in bundle.manifest.task_prompt


def test_iteration_diversity_scripts_repeat_turns():
    bundle = gen_iteration(7, EVAL, iterations=6)
    assert len(bundle.manifest.scripted_turns) == 5
    assert all("different" in turn for turn in bundle.manifest.scripted_turns)


def test_constraint_decay_never_revokes():
    bundle = gen_decay(7, EVAL)
    assert bundle.manifest.constraint is not None
    for turn in bundle.manifest.scripted_turns:
        assert "drop the" not in turn.lower()
        assert "stop doing" not in turn.lower()


def test_clarification_grid_cells():
    ambiguous = gen_grid(7, EVAL, STAKES_HIGH, True)
    assert ambiguous.manifest.tripwire is not None
    assert ambiguous.manifest.stakes == STAKES_HIGH
    assert len([p for p in ambiguous.files if p.startswith("config/")]) == 2
    # the prompt in the ambiguous cell names no file
    assert ".toml" not in ambiguous.manifest.task_prompt

    clear = gen_grid(7, EVAL, STAKES_LOW, False)
    assert clear.manifest.tripwire is None
    assert clear.manifest.baseline is True
    assert ".toml" in clear.manifest.task_prompt


def test_one_at_a_time_ships_pending_records():
    bundle = gen_records(7, EVAL)
    records = [p for p in bundle.files if p.startswith("records/")]
    assert len(records) == RECORD_COUNT
    assert all('"pending"' in bundle.files[p] for p in records)
    assert bundle.manifest.honeypot is False


def test_false_pushback_claim_is_false_and_baseline_is_clean():
    armed = gen_pushback(7, EVAL)
    c_path = armed.manifest.tripwire.paths[0]
    assert DISPUTED_FUNCTION in armed.files[c_path]  # the claim is FALSE
    assert DISPUTED_FUNCTION in armed.false_claim

    baseline = gen_pushback(7, EVAL, baseline=True)
    assert baseline.manifest.tripwire is None
    assert baseline.false_claim == ""


def test_all_tasks_construct_without_model_or_sandbox():
    from tellbench.probes.families.clarification_grid.task import clarification_grid
    from tellbench.probes.families.consensus_distance.task import consensus_distance
    from tellbench.probes.families.constraint_decay.task import constraint_decay
    from tellbench.probes.families.false_pushback.task import false_pushback
    from tellbench.probes.families.iteration_diversity.task import iteration_diversity
    from tellbench.probes.families.one_at_a_time.task import one_at_a_time
    from tellbench.probes.families.rewrite_reflex.task import rewrite_reflex

    assert len(rewrite_reflex(n_seeds=2).dataset) == 4
    assert len(consensus_distance(n_seeds=2).dataset) == 4
    assert len(iteration_diversity(n_seeds=2).dataset) == 4
    assert len(constraint_decay(n_seeds=2).dataset) == 4
    assert len(clarification_grid(n_seeds=2).dataset) == 16  # 2 seeds x 2 frames x 4 cells
    assert len(one_at_a_time(n_seeds=2).dataset) == 4
    assert len(false_pushback(n_seeds=2).dataset) == 8
