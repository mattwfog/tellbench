"""scripts/site_table.py: score-shape routing in summarize and site_block.

Regression tests for the shape-conflation bug: continuous-score families
(chat families carry frame + baseline manifests) used to flow through the
fire_rate branch, where `value >= 1.0` read a 0.6 novelty as a non-fire and
rewrite_reflex's judge-pending 0.0 as a clean 0% rate.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "site_table.py"
_spec = importlib.util.spec_from_file_location("site_table", _SCRIPT)
assert _spec is not None and _spec.loader is not None
st = importlib.util.module_from_spec(_spec)
sys.modules["site_table"] = st  # dataclass annotation resolution needs this
_spec.loader.exec_module(st)


def row(family: str, fired: float, frame="eval_coded", baseline=False):
    return st.SampleRow(family=family, frame=frame, baseline=baseline, fired=fired)


def by_family(summary):
    return {entry["family"]: entry for entry in summary}


def test_fire_rate_family_reports_worst_frame_and_baseline():
    rows = [
        row("messy_repo", 1.0, "eval_coded"),
        row("messy_repo", 0.0, "eval_coded"),
        row("messy_repo", 0.0, "prod_coded"),
        row("messy_repo", 0.0, "prod_coded"),
        row("messy_repo", 1.0, "eval_coded", baseline=True),
    ]
    entry = by_family(st.summarize(rows))["messy_repo"]
    assert entry["shape"] == "fire_rate"
    assert entry["worst_frame"] == "eval_coded"
    assert entry["reported"]["fires"] == 1
    assert entry["reported"]["n"] == 2
    assert entry["baseline"]["fires"] == 1


def test_mean_score_family_never_flows_through_fire_branch():
    # chat families set frame + baseline=False, which used to trip the
    # fire_rate branch: 0.6 novelty counted as no-fire -> 0% forever
    rows = [
        row("iteration_diversity", 0.6, "eval_coded"),
        row("iteration_diversity", 0.3, "prod_coded"),
    ]
    entry = by_family(st.summarize(rows))["iteration_diversity"]
    assert entry["shape"] == "mean_score"
    assert entry["polarity"] == "higher_is_better"
    assert entry["mean"] == pytest.approx(0.45)
    assert entry["n"] == 2
    # worst frame for higher-is-better is the LOWER mean
    assert entry["worst_frame"] == "prod_coded"
    assert entry["per_frame"]["prod_coded"]["mean"] == pytest.approx(0.3)


def test_judge_pending_family_publishes_no_number():
    rows = [row("rewrite_reflex", 0.0), row("rewrite_reflex", 0.0)]
    entry = by_family(st.summarize(rows))["rewrite_reflex"]
    assert entry["shape"] == "judge_pending"
    assert entry["n"] == 2
    assert "mean" not in entry
    assert "reported" not in entry


def test_unknown_family_with_manifest_still_fire_rate():
    rows = [row("mystery_family", 1.0), row("mystery_family", 0.0)]
    entry = by_family(st.summarize(rows))["mystery_family"]
    assert entry["shape"] == "fire_rate"
    assert entry["reported"]["fires"] == 1


def test_unknown_family_without_manifest_falls_back_to_unlabeled_mean():
    rows = [
        st.SampleRow(family="mystery_family", frame=None, baseline=None, fired=0.4),
        st.SampleRow(family="mystery_family", frame=None, baseline=None, fired=0.8),
    ]
    entry = by_family(st.summarize(rows))["mystery_family"]
    assert entry["shape"] == "mean_score"
    assert entry["polarity"] == "unknown"
    assert entry["mean"] == pytest.approx(0.6)


def test_site_block_renders_all_three_shapes():
    rows = [
        row("messy_repo", 1.0),
        row("messy_repo", 0.0, baseline=True),
        row("iteration_diversity", 0.5),
        row("rewrite_reflex", 0.0),
    ]
    block = st.site_block(st.summarize(rows), model="haiku")
    rendered = {r[0]: r for r in block["rows"]}
    assert rendered["messy_repo"][2] == "1/1"
    assert rendered["iteration_diversity"][3] == "mean 0.50 (higher is better)"
    assert rendered["rewrite_reflex"][3] == "judge pending"
    assert block["kind"] == "table"
