"""Source schemas.

`path` remains the active runtime field in this release. The additional source-resolution fields are
schema scaffolding for the upcoming resolver-based migration.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from splendor.schemas.common import StrictRecord
from splendor.schemas.types import SourceRefKind, StorageMode


class SourceRecord(StrictRecord):
    kind: Literal["source"] = "source"
    source_id: str
    title: str
    source_type: str
    # Legacy runtime field. Current registration and ingest still read from `path`.
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
    source_ref: str | None = None
    source_ref_kind: SourceRefKind | None = None
    storage_mode: StorageMode | None = None
    storage_path: str | None = None
    materialized_at: str | None = None
    source_commit: str | None = None
