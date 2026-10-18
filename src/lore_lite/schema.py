"""Validated data contracts for extraction, storage, configuration, and results."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal, Self

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    """Base contract: reject undeclared fields and implicit type coercion."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class SourceKind(str, Enum):
    MARKDOWN = "markdown"
    IMAGE = "image"


class Modality(str, Enum):
    MUST = "MUST"
    SHOULD = "SHOULD"
    MAY = "MAY"
    MUST_NOT = "MUST_NOT"


class RuleStatus(str, Enum):
    ACTIVE = "active"
    OVERRIDDEN = "overridden"


class EvidenceStatus(str, Enum):
    SATISFIED = "satisfied"
    PENDING = "pending"
    MISSING = "missing"


class ResultState(str, Enum):
    CONFLICTING = "conflicting"
    INSUFFICIENT = "insufficient"
    QUALIFIED = "qualified"
    SUPPORTED = "supported"
    NO_KNOWLEDGE = "no_knowledge"


class Directive(str, Enum):
    ASK_USER = "ask_user"
    PROCEED_AND_CITE = "proceed_and_cite"
    PROCEED = "proceed"


class Rule(StrictModel):
    """Gemma-facing rule shape; contains no code-assigned provenance fields."""

    statement: str = Field(min_length=1)
    component: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    modality: Modality
    value: str | None
    severity: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class RuleExtractionResponse(StrictModel):
    """JSON response wrapper used for structured Gemma extraction."""

    rules: list[Rule] = Field(default_factory=list)


class RuleRecord(Rule):
    """A verified extracted rule with provenance and code-owned governance data."""

    rule_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_location: str | None = None
    authority: str = Field(min_length=1)
    authority_rank: Annotated[int, Field(ge=0)]
    source_kind: SourceKind = SourceKind.MARKDOWN
    effective_date: date | None = None
    provenance: Literal["source_text", "image-transcript", "image-ocr"] = "source_text"
    status: RuleStatus = RuleStatus.ACTIVE
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value


class SourceRecord(StrictModel):
    """Imported source metadata; authority is supplied outside the model."""

    id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    kind: SourceKind
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority: str = Field(min_length=1)
    owner: str | None = None
    imported_at: datetime
    effective_date: date | None = None

    @field_validator("imported_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("source dates must include a timezone")
        return value


class EvidenceItem(StrictModel):
    id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    status: EvidenceStatus
    source_id: str | None = None


class DecisionRecord(StrictModel):
    id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    state: ResultState
    rule_ids: list[str] = Field(default_factory=list)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value


class ResultItem(StrictModel):
    rule_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    source: str = Field(min_length=1)
    authority: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)
    provenance: Literal["source_text", "image-transcript", "image-ocr"] = "source_text"


class OverriddenRule(StrictModel):
    rule_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ResultEnvelope(StrictModel):
    schema_version: Literal["lore-lite.result/1"] = Field(
        default="lore-lite.result/1",
        validation_alias=AliasChoices("schema", "schema_version"),
        serialization_alias="schema",
    )
    state: ResultState
    directive: Directive
    items: list[ResultItem] = Field(default_factory=list)
    overridden: list[OverriddenRule] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    decision_id: str = Field(min_length=1)


class DecisionTypeConfig(StrictModel):
    required_evidence: list[str] = Field(default_factory=list)


class LoreConfig(StrictModel):
    authority_ladder: dict[str, Annotated[int, Field(ge=0)]] = Field(min_length=1)
    decision_types: dict[str, DecisionTypeConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def require_named_entries(self) -> Self:
        if any(not name.strip() for name in self.authority_ladder):
            raise ValueError("configuration names must not be empty")
        if any(not name.strip() for name in self.decision_types):
            raise ValueError("configuration names must not be empty")
        return self
