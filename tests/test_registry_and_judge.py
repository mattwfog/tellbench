import pytest

import tellbench.detectors as detectors_pkg
from tellbench.detectors.base import DETECTORS
from tellbench.judge.hygiene import JudgeConfig, SlotOrder, plan_pairwise
from tellbench.probes.registry import FAMILIES, FamilyStatus


def test_all_detectors_registered():
    assert detectors_pkg is not None
    assert {
        "tripwire_fired",
        "tripwire_inspected",
        "tripwire_mentioned",
        "blocked_burn",
        "unsolicited_destruction",
        "unrequested_diff",
        "forbidden_touched",
        "unsupported_claims",
        "report_density",
    } <= set(DETECTORS)


def test_registry_implemented_families_match_code():
    implemented = [f for f in FAMILIES.values() if f.status == FamilyStatus.IMPLEMENTED]
    assert len(implemented) == 11
    assert len(FAMILIES) == 11


def test_judge_plan_excludes_target_family_and_swaps():
    config = JudgeConfig(
        ensemble=("openai/gpt-5", "anthropic/claude-sonnet-5", "moonshot/kimi-k2"),
        target_model="anthropic/claude-fable-5",
        rounds=2,
    )
    slots = plan_pairwise(config)
    judges = {s.judge_model for s in slots}
    assert "anthropic/claude-sonnet-5" not in judges
    assert judges == {"openai/gpt-5", "moonshot/kimi-k2"}
    assert len(slots) == 2 * 2 * 2
    assert {s.order for s in slots} == {SlotOrder.AB, SlotOrder.BA}


def test_judge_config_requires_cross_family_headroom():
    config = JudgeConfig(
        ensemble=("anthropic/claude-sonnet-5",),
        target_model="anthropic/claude-fable-5",
    )
    with pytest.raises(ValueError):
        config.active_ensemble()


def test_explanations_default_off():
    config = JudgeConfig(
        ensemble=("openai/gpt-5",), target_model="anthropic/claude-fable-5"
    )
    assert config.emit_explanations is False
