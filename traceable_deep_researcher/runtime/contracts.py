"""Small dependency-injection contracts shared by research execution adapters.

These types do not implement event persistence, checkpoint recovery or review
delivery. Implementations are injected by the hosting application. Values passed
to the protocols must be JSON-compatible snapshots, not live researcher objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal, Mapping, Protocol, runtime_checkable
from uuid import uuid4


@runtime_checkable
class EventSink(Protocol):
    """Accept an event snapshot; the hosting adapter owns envelope validation."""

    async def emit(self, event: Mapping[str, Any]) -> None: ...


@runtime_checkable
class CheckpointStore(Protocol):
    """Store snapshots scoped by research, attempt and a caller-selected key."""

    async def load(self, context: RunContext, key: str) -> dict[str, Any] | None: ...

    async def save(self, context: RunContext, key: str, checkpoint: Mapping[str, Any]) -> None: ...


@dataclass(frozen=True)
class ReviewRequest:
    review_id: str
    research_id: str
    attempt_id: str
    prompt: str
    context_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewResponse:
    review_id: str
    decision: Literal["approve", "revise", "reject"]
    comment: str = ""


@runtime_checkable
class ReviewInbox(Protocol):
    """Publish a request and poll its response; None means still awaiting review.

    Durable delivery and single-consumption semantics belong to an implementation.
    """

    async def request(self, review: ReviewRequest) -> None: ...

    async def response(self, review_id: str) -> ReviewResponse | None: ...


@dataclass(frozen=True)
class RunContext:
    research_id: str
    attempt_id: str
    span_id: str = field(default_factory=lambda: uuid4().hex)
    parent_span_id: str | None = None
    event_sink: EventSink | None = None
    checkpoint_store: CheckpointStore | None = None
    review_inbox: ReviewInbox | None = None
    checkpoint_scope: str = 'root'

    def child(self, *, scope: str | None = None) -> RunContext:
        """Create a distinct span in the same attempt, retaining injected services."""
        return replace(self, span_id=uuid4().hex, parent_span_id=self.span_id,
                       checkpoint_scope=self.checkpoint_scope+'/'+(scope or uuid4().hex))


@dataclass
class ResearchResult:
    report_markdown: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    context_refs: list[str] = field(default_factory=list)
    cost_summary: dict[str, Any] = field(default_factory=dict)
    review_status: str = "not_requested"
    warnings: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
