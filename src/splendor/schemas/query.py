"""Query snapshot schemas."""

from __future__ import annotations

from pydantic import Field

from splendor.schemas.common import StrictRecord
from splendor.schemas.provenance import ProvenanceLink


class QueryMatchSnapshot(StrictRecord):
    rank: int
    score: int
    document_class: str
    kind: str
    record_id: str
    title: str
    path: str
    status: str | None = None
    review_state: str | None = None
    last_generated_at: str | None = None
    snippet: str
    source_refs: list[str] = Field(default_factory=list)
    generated_by_run_ids: list[str] = Field(default_factory=list)
    provenance_links: list[ProvenanceLink] = Field(default_factory=list)
    contradiction_count: int = 0
    review_task_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class QuerySnapshot(StrictRecord):
    query: str
    summary: str
    match_count: int
    created_at: str
    matches: list[QueryMatchSnapshot] = Field(default_factory=list)
