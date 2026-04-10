"""Source schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from splendor.schemas.common import StrictRecord


class SourceRecord(StrictRecord):
    kind: Literal["source"] = "source"
    source_id: str
    title: str
    source_type: str
    path: str
    checksum: str = Field(min_length=64, max_length=64)
    added_at: str
    status: Literal["registered", "ingested", "failed"] = "registered"
    pipeline_version: str
    derived_artifacts: list[str] = Field(default_factory=list)
    linked_pages: list[str] = Field(default_factory=list)
    last_run_id: str | None = None
    review_state: Literal["unreviewed", "human-reviewed", "stale"] = "unreviewed"
    origin_url: str | None = None
    original_path: str | None = None
