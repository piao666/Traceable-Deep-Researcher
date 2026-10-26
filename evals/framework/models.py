"""Versioned evaluation inputs and explicit scored/unscored outcomes."""

from copy import deepcopy
from datetime import date
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class EvalBudget(Contract):
    max_tool_calls: int = Field(default=20, gt=0, strict=True)
    max_seconds: float = Field(default=300, gt=0, strict=True)


class SourcePolicy(Contract):
    allowed_kinds: list[Literal["web", "local", "mcp"]] = Field(default_factory=lambda: ["local"], min_length=1)
    network_allowed: bool = False


class Requirement(Contract):
    id: NonEmpty
    text: NonEmpty
    weight: float = Field(default=1, gt=0)


class GoldFact(Contract):
    id: NonEmpty
    fact: NonEmpty


class Case(Contract):
    schema_version: Literal[1] = 1
    case_id: NonEmpty
    dataset_version: NonEmpty
    split: Literal["dev", "calibration", "holdout"]
    group_id: NonEmpty
    source_bundle: NonEmpty
    replay_key: NonEmpty
    budget: EvalBudget = Field(default_factory=EvalBudget)
    tags: list[str] = Field(default_factory=list)


class TaskCase(Case):
    query: NonEmpty
    as_of: date
    report_type: Literal["research_report", "detailed_report", "deep", "multi_agents"] = "research_report"
    source_policy: SourcePolicy = Field(default_factory=SourcePolicy)
    requirements: list[Requirement] = Field(default_factory=list)
    gold_facts: list[GoldFact] = Field(default_factory=list)
    gold_evidence: list[str] = Field(default_factory=list)
    faults: list[str] = Field(default_factory=list)

    def agent_input(self) -> dict[str, Any]:
        """Only user-visible inputs, never evaluation labels or gold evidence."""
        return self.model_dump(mode="json", include={"query", "as_of", "report_type", "source_policy", "budget"})


class AgentCase(Case):
    node_kind: Literal["planner", "retriever", "context_selector", "writer", "reviewer", "reviser", "mcp_selector", "orchestrator"]
    input_artifact: dict[str, Any]
    allowed_tools: list[str] = Field(default_factory=list)
    expected_constraints: dict[str, Any] = Field(default_factory=dict)
    gold_output_refs: list[str] = Field(default_factory=list)

    def agent_input(self) -> dict[str, Any]:
        return {"node_kind": self.node_kind, "input_artifact": deepcopy(self.input_artifact),
                "allowed_tools": self.allowed_tools.copy(), "budget": self.budget.model_dump(mode="json")}


class ResultStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"


class EvalResult(Contract):
    name: NonEmpty
    status: ResultStatus
    score: float | None = Field(default=None, ge=0, le=1, strict=True)
    reason: str = ""
    denominator: int | None = Field(default=None, ge=0, strict=True)
    trace_refs: list[str] = Field(default_factory=list)
    breakdown: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_score_state(self):
        scored = self.status in {ResultStatus.PASSED, ResultStatus.FAILED}
        if scored != (self.score is not None):
            raise ValueError("only passed/failed results must have a score")
        if not scored and not self.reason.strip():
            raise ValueError("unscored results require a reason")
        return self
