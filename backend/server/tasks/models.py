"""Version one contracts for persistent research tasks and events."""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, StringConstraints,
    field_validator,
)

from traceable_deep_researcher.utils.enum import ReportSource, ReportType, Tone


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
SequenceNumber = Annotated[int, Field(strict=True, ge=1)]
Cursor = Annotated[int, Field(strict=True, ge=0)]
ToneName = Enum("ToneName", {tone.name: tone.name for tone in Tone}, type=str)


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_REVIEW = "waiting_for_review"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class ReviewStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class ExportStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Budget(ContractModel):
    max_tool_calls: PositiveInt = 20
    max_seconds: Annotated[float, Field(gt=0, strict=True)] = 300
    max_tokens: PositiveInt | None = None
    max_cost_usd: Annotated[float, Field(gt=0, strict=True)] | None = None


class SourcePolicy(ContractModel):
    """Declared permissions; execution adapters must separately enforce them."""

    allowed_kinds: Annotated[list[ReportSource], Field(min_length=1)] = Field(
        default_factory=lambda: [ReportSource.Web])
    network_allowed: bool = True


class ResearchTaskRequest(ContractModel):
    task: NonEmptyString
    report_type: str = ReportType.ResearchReport.value
    report_source: ReportSource = ReportSource.Web
    tone: ToneName = ToneName.Objective
    source_urls: list[NonEmptyString] = Field(default_factory=list)
    document_urls: list[NonEmptyString] = Field(default_factory=list)
    query_domains: list[NonEmptyString] = Field(default_factory=list)
    source_policy: SourcePolicy = Field(default_factory=SourcePolicy)
    budget: Budget = Field(default_factory=Budget)
    mcp_enabled: bool = False
    # Only identifiers of server-managed configurations cross this boundary.
    mcp_config_refs: list[NonEmptyString] = Field(default_factory=list)
    include_human_feedback: bool = False
    max_search_results: Annotated[int, Field(strict=True, ge=1, le=20)] | None = None
    mcp_strategy: Literal['fast', 'deep'] = 'fast'

    @field_validator("report_type")
    @classmethod
    def supported_report_type(cls, value: str) -> str:
        if value not in {item.value for item in ReportType} | {"multi_agents"}:
            raise ValueError("unsupported report_type")
        return value


class VersionedModel(ContractModel):
    version: Literal[1] = 1

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("version must be the integer 1")
        return value


class TaskEvent(VersionedModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    research_id: NonEmptyString
    attempt_id: NonEmptyString | None = None
    seq: SequenceNumber
    type: NonEmptyString
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class SubscribeCommand(VersionedModel):
    type: Literal["subscribe"] = "subscribe"
    research_id: NonEmptyString
    after_seq: Cursor = 0
