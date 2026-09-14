from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceType(str, Enum):
    PAPER = "paper"
    BLOG = "blog"
    VIDEO = "video"
    PATENT = "patent"
    REPOSITORY = "repository"


class Reliability(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class Difficulty(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class Timestamp(BaseModel):
    time: str
    label: str


class SourceSummary(BaseModel):
    tldr: str
    problem: str | None = None
    approach: str | None = None
    key_findings: list[str] = Field(default_factory=list)
    methodology: str | None = None
    results: str | None = None
    limitations: str | None = None
    why_it_matters: str | None = None
    prerequisites: str | None = None
    difficulty: Difficulty | None = None
    main_argument: str | None = None
    important_concepts: list[str] = Field(default_factory=list)
    technical_takeaways: list[str] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)
    timestamps: list[Timestamp] = Field(default_factory=list)

    @field_validator(
        "key_findings",
        "important_concepts",
        "technical_takeaways",
        "key_concepts",
        "timestamps",
        mode="before",
    )
    @classmethod
    def empty_list_if_null(cls, value: object) -> object:
        return [] if value is None else value


class SourceItem(BaseModel):
    type: SourceType
    title: str
    url: str
    source_name: str
    reliability: Reliability
    relevance_score: float = Field(ge=0, le=10)
    verified: bool
    unavailable_reason: str | None = None
    canonical_id: str | None = None
    authors: list[str] | None = None
    published_date: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    channel: str | None = None
    duration: str | None = None
    author: str | None = None
    website: str | None = None
    summary: SourceSummary

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("url must be an http(s) link")
        return value

    @model_validator(mode="after")
    def unverified_must_explain(self) -> SourceItem:
        if not self.verified and not self.unavailable_reason:
            self.unavailable_reason = "Unable to verify this source."
            if not self.summary.tldr:
                self.summary.tldr = "Unable to verify this source."
        return self


class ResearchReport(BaseModel):
    query: str
    summary: str
    sources: list[SourceItem] = Field(min_length=1)

    @field_validator("sources")
    @classmethod
    def drop_invalid_keep_order(cls, items: list[SourceItem]) -> list[SourceItem]:
        return sorted(items, key=lambda item: item.relevance_score, reverse=True)
