"""Event vocabulary: the atoms detectors read off a run trace."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class Severity(StrEnum):
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    CATASTROPHIC = "catastrophic"


class Reversibility(StrEnum):
    REVERSIBLE = "reversible"
    RECOVERABLE = "recoverable"
    IRREVERSIBLE = "irreversible"


class TripwireKind(StrEnum):
    FOREIGN_WIP = "foreign_wip"
    FLAKY_TEST = "flaky_test"
    LIVE_ARCHIVE = "live_archive"
    RESET_SCRIPT = "reset_script"
    ENV_CREDENTIALS = "env_credentials"
    ADJACENT_BUG = "adjacent_bug"
    MISSING_RESOURCE = "missing_resource"
    AMBIGUOUS_TARGET = "ambiguous_target"
    DISPUTED_FACT = "disputed_fact"


class ToolCall(FrozenModel):
    index: int = Field(ge=0)
    name: str
    arguments: str
    output_excerpt: str = ""


class ChangeType(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


class FileChange(FrozenModel):
    """End-state file delta, sandbox-observed (git diff against the planted state).

    End-state diffing is the deterministic ground truth for destruction
    detection; command parsing only supplies ordering evidence on top.
    """

    path: str
    change_type: ChangeType
    lines_added: int = Field(default=0, ge=0)
    lines_removed: int = Field(default=0, ge=0)


class TripwireHit(FrozenModel):
    tripwire_id: str
    kind: TripwireKind
    severity: Severity
    reversibility: Reversibility
    checked_first: bool
    evidence: str


class ClaimKind(StrEnum):
    TEST_RUN = "test_run"
    COMMAND_RUN = "command_run"
    FILE_STATE = "file_state"
    COMPLETION = "completion"
    OTHER = "other"


class ReportClaim(FrozenModel):
    text: str
    kind: ClaimKind


class ClaimCheck(FrozenModel):
    """supported=None means the claim is not mechanically checkable."""

    claim: ReportClaim
    supported: bool | None
    evidence: str
