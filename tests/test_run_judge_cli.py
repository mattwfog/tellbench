"""Regression: answers.psv keys contain '|' — label is after the LAST pipe.

The 2026-08-17 gold-pilot launch attempted 0 slots because cmd_run split
answers lines at the FIRST pipe, collapsing every piped instance_key to
its family prefix (zero overlap with instances). Both cmd_run and
cmd_validate must split from the right.
"""

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_judge.py"
_spec = importlib.util.spec_from_file_location("run_judge", _SCRIPT)
assert _spec is not None and _spec.loader is not None
rj = importlib.util.module_from_spec(_spec)
sys.modules["run_judge"] = rj
_spec.loader.exec_module(rj)

PIPED_KEY = "rewrite_reflex|codex-gpt-5.6-sol|xhigh|rewrite_reflex-000002-eval_coded:subscription:0"


def test_cmd_run_gold_keys_keep_internal_pipes(tmp_path, monkeypatch):
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "rewrite_risk.answers.psv").write_text(
        f"{PIPED_KEY}|\n{PIPED_KEY.replace('000002', '000001')}|YES\n"
    )
    monkeypatch.setattr(rj, "GOLD_DIR", gold)
    seen = _stub_executor(monkeypatch)
    rj.cmd_run("rewrite_risk", gold_only=True, limit_slots=None)
    assert seen["only_keys"] == {PIPED_KEY, PIPED_KEY.replace("000002", "000001")}


def _stub_executor(monkeypatch):
    seen = {}

    def fake_run_item(item, *, only_keys=None, limit_slots=None, rounds=5):
        seen["only_keys"] = only_keys
        seen["rounds"] = rounds
        return {"attempted": 0, "completed": 0, "failures": 0}

    stub = type(sys)("stub")
    stub.run_item = fake_run_item
    stub.ROUNDS = 5
    monkeypatch.setitem(sys.modules, "tellbench.judge.executor", stub)
    return seen


def test_cmd_run_keys_file_restricts_and_intersects_gold(tmp_path, monkeypatch):
    gold = tmp_path / "gold"
    gold.mkdir()
    other = PIPED_KEY.replace("000002", "000001")
    (gold / "rewrite_risk.answers.psv").write_text(f"{PIPED_KEY}|YES\n{other}|NO\n")
    monkeypatch.setattr(rj, "GOLD_DIR", gold)
    keys_file = tmp_path / "topup.keys"
    keys_file.write_text(f"{PIPED_KEY}\nnot-an-instance\n")
    seen = _stub_executor(monkeypatch)
    # keys-file alone
    rj.cmd_run("rewrite_risk", gold_only=False, limit_slots=None, keys_file=keys_file)
    assert seen["only_keys"] == {PIPED_KEY, "not-an-instance"}
    # keys-file intersected with gold subset
    rj.cmd_run("rewrite_risk", gold_only=True, limit_slots=None, keys_file=keys_file)
    assert seen["only_keys"] == {PIPED_KEY}


def test_cmd_run_rounds_default_and_override(tmp_path, monkeypatch):
    monkeypatch.setattr(rj, "GOLD_DIR", tmp_path)
    seen = _stub_executor(monkeypatch)
    rj.cmd_run("rewrite_risk", gold_only=False, limit_slots=None)
    assert seen["rounds"] == 5  # stub ROUNDS carried through
    rj.cmd_run("rewrite_risk", gold_only=False, limit_slots=None, rounds=9)
    assert seen["rounds"] == 9


def test_cmd_validate_labels_keep_internal_pipes(tmp_path, monkeypatch, capsys):
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "rewrite_risk.answers.psv").write_text(f"{PIPED_KEY}|YES\n")
    monkeypatch.setattr(rj, "GOLD_DIR", gold)
    stub = type(sys)("stub")
    stub.majority = lambda item, judge=None: {PIPED_KEY: "YES"}
    monkeypatch.setitem(sys.modules, "tellbench.judge.executor", stub)
    rj.cmd_validate("rewrite_risk")
    out = capsys.readouterr().out
    assert "agreement 1/1" in out


def test_cmd_validate_pairwise_case_insensitive(tmp_path, monkeypatch, capsys):
    """Regression: pairwise canon labels are lowercase ('incremental') while
    verdicts were uppercased before compare — pairwise agreement was always 0."""
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "rewrite_anchor.answers.psv").write_text(f"{PIPED_KEY}|A\n")
    monkeypatch.setattr(rj, "GOLD_DIR", gold)
    stub = type(sys)("stub")
    stub.majority = lambda item, judge=None: {PIPED_KEY: "incremental"}
    monkeypatch.setitem(sys.modules, "tellbench.judge.executor", stub)
    rj.cmd_validate("rewrite_anchor")
    assert "agreement 1/1" in capsys.readouterr().out
