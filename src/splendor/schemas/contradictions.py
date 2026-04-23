"""Contradiction annotation schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from splendor.schemas.common import StrictRecord


class ContradictionEvidence(StrictRecord):
    page_id: str
    source_id: str | None = None
    run_id: str | None = None
    path_ref: str | None = None
    excerpt: str = Field(min_length=1)


class ContradictionAnnotation(StrictRecord):
    kind: Literal["contradiction"] = "contradiction"
    contradiction_id: str
    summary: str = Field(min_length=1)
    detected_at: str
    related_page_ids: list[str] = Field(default_factory=list)
    related_source_ids: list[str] = Field(default_factory=list)
    review_task_id: str
    evidence: list[ContradictionEvidence] = Field(default_factory=list)
