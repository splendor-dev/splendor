"""Wiki page schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from splendor.schemas.common import StrictRecord
from splendor.schemas.provenance import ProvenanceLink
from splendor.schemas.types import PageReviewState


class KnowledgePageFrontmatter(StrictRecord):
    kind: Literal["concept", "entity", "topic", "source-summary", "architecture", "glossary"]
    title: str
    page_id: str
    status: Literal["draft", "active", "stale"] = "draft"
    review_state: PageReviewState = "draft"
    source_refs: list[str] = Field(default_factory=list)
    generated_by_run_ids: list[str] = Field(default_factory=list)
    last_generated_at: str | None = None
    last_reviewed_at: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    related_pages: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    provenance_links: list[ProvenanceLink] = Field(default_factory=list)
