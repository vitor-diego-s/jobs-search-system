"""Core data models for the jobs search engine."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobCandidate(BaseModel):
    """A job listing discovered by a platform adapter.

    Frozen — score is set via the ScoredCandidate wrapper, not mutated.
    """

    model_config = ConfigDict(frozen=True)

    external_id: str
    platform: str
    title: str
    company: str = ""
    location: str = ""
    url: str
    is_easy_apply: bool = False
    workplace_type: str = ""
    posted_time: str = ""
    description_snippet: str = ""
    found_at: datetime = Field(default_factory=datetime.now)


class ScoredCandidate(BaseModel):
    """Wrapper that pairs a frozen JobCandidate with a relevance score."""

    model_config = ConfigDict(frozen=True)

    candidate: JobCandidate
    score: float = Field(default=0.0, ge=0.0, le=100.0)


class SearchRunResult(BaseModel):
    """Summary of a single search run."""

    platform: str
    keyword: str
    raw_count: int
    filtered_count: int
    started_at: datetime
    finished_at: datetime
