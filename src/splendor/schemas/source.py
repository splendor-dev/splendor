"""Source schemas.

`path` remains a required compatibility field in this release. New registrations now also write the
source-resolution fields, while older manifests that only carry `path` remain supported at read
time.
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
    # Compatibility field. For copied sources it is the stored artifact path; for workspace-backed
    # sources it temporarily mirrors `source_ref`.
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
