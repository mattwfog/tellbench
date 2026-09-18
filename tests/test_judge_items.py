"""Judge item registry and extraction-helper invariants (no runs/ data)."""

from __future__ import annotations

from tellbench.judge.columns import (
    CLAUDE_RERUN3_MODELS,
    EFFORTS,
    EXPECTED_TOTAL_COLUMNS,
    _claude_columns,
)
from tellbench.judge.extract import _armed, _fired
from tellbench.judge.items import ITEMS
from tellbench.probes.manifests import manifest_for


def test_items_registry_shape():
    assert len(ITEMS) == 8
    for item in ITEMS.values():
        assert item.item_id in ITEMS
        assert item.mode in ("pairwise_anchor", "verdict")
        assert len(item.verdict_tokens) == 2
        assert "No explanation" in item.question  # hygiene: verdict-only


def test_pairwise_anchor_only_rewrite():
    pairwise = [i for i in ITEMS.values() if i.mode == "pairwise_anchor"]
    assert [i.item_id for i in pairwise] == ["rewrite_anchor"]
    assert pairwise[0].verdict_tokens == ("A", "B")


def test_claude_column_layout():
    columns = list(_claude_columns("rewrite_reflex"))
    # 8 rerun3 models + opus-5, x 6 efforts = 54 Claude columns of the 90
    assert len(columns) == (len(CLAUDE_RERUN3_MODELS) + 1) * len(EFFORTS)
    assert len(columns) == EXPECTED_TOTAL_COLUMNS - 36
    rerun3 = [c for c in columns if c.model != "claude-opus-5"]
    assert all(c.path.name.endswith("_rerun3.jsonl") for c in rerun3)
    opus5 = [c for c in columns if c.model == "claude-opus-5"]
    assert all("rerun" not in c.path.name for c in opus5)


def test_armed_and_fired_helpers():
    armed = {"run_key": "messy_repo-000005-eval_coded:subscription:0"}
    baseline = {"run_key": "messy_repo-000005-eval_coded-baseline:subscription:0"}
    assert _armed(armed) and not _armed(baseline)
    record = {
        "detectors": [
            {"detector_id": "tripwire_mentioned", "fired": True},
            {"detector_id": "tripwire_fired", "fired": False},
        ]
    }
    assert _fired(record, "tripwire_mentioned")
    assert not _fired(record, "tripwire_fired")
    assert not _fired({"detectors": []}, "tripwire_mentioned")


def test_manifest_roundtrip_shared_module():
    manifest = manifest_for("forbidden_improvement-000001-eval_coded")
    assert manifest.instance_id == "forbidden_improvement-000001-eval_coded"
    assert manifest.tripwire is not None
    assert manifest.tripwire.paths
    grid = manifest_for("clarification_grid-000002-prod_coded-high-ambiguous")
    assert grid.instance_id.endswith("high-ambiguous")
