"""A fixed writing-output schema probe, not a production claim validator."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class FixtureClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Text
    evidence_ids: list[Text] = Field(min_length=1)


class FixtureDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[FixtureClaim] = Field(min_length=1)


def parse_fixture_draft(value: dict, allowed_evidence: set[str]) -> FixtureDraft:
    draft = FixtureDraft.model_validate(value)
    if any(evidence not in allowed_evidence for claim in draft.claims for evidence in claim.evidence_ids):
        raise ValueError("unknown evidence ID")
    return draft
