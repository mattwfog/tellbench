"""Judge-layer hygiene, encoded as configuration rather than convention.

Defaults follow the verified LLM-as-judge literature (Gu et al.,
arXiv:2411.15594): pairwise over absolute, swap positions and average,
aggregate 5 rounds by majority, and do NOT ask judges to emit
explanations with verdicts — their experiments found simultaneous
explanation generally degrades judgment quality. That finding comes from
a single-judge (gpt-3.5-turbo) experiment with a speculated mechanism, so
it is a default, not a law: emit_explanations stays a switch.

Judges from the same family as the target are excluded (self-preference
bias); family is the provider prefix of a model id like "anthropic/...".
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from tellbench.schema.events import FrozenModel


class SlotOrder(StrEnum):
    AB = "ab"
    BA = "ba"


class JudgmentSlot(FrozenModel):
    judge_model: str
    order: SlotOrder
    round_index: int = Field(ge=0)


class JudgeConfig(FrozenModel):
    ensemble: tuple[str, ...]
    target_model: str
    pairwise: bool = True
    swap_positions: bool = True
    rounds: int = Field(default=5, ge=1)
    emit_explanations: bool = False

    @model_validator(mode="after")
    def _ensemble_non_empty(self) -> "JudgeConfig":
        if not self.ensemble:
            raise ValueError("judge ensemble must not be empty")
        return self

    def active_ensemble(self) -> tuple[str, ...]:
        target_family = _family(self.target_model)
        active = tuple(j for j in self.ensemble if _family(j) != target_family)
        if not active:
            raise ValueError(
                f"no judges remain after excluding family {target_family!r}; "
                "widen the ensemble"
            )
        return active


def _family(model_id: str) -> str:
    return model_id.split("/", 1)[0] if "/" in model_id else model_id


def plan_pairwise(config: JudgeConfig) -> tuple[JudgmentSlot, ...]:
    """Deterministic judging plan: every active judge scores every round in
    both orders (when swapping), and verdicts are aggregated by majority."""

    orders = (SlotOrder.AB, SlotOrder.BA) if config.swap_positions else (SlotOrder.AB,)
    return tuple(
        JudgmentSlot(judge_model=judge, order=order, round_index=round_index)
        for judge in config.active_ensemble()
        for round_index in range(config.rounds)
        for order in orders
    )
