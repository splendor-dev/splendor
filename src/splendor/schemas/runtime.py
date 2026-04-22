"""Queue and run schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from splendor.schemas.common import StrictRecord
from splendor.schemas.provenance import ProvenanceLink


class QueueItemRecord(StrictRecord):
    kind: Literal["queue_item"] = "queue_item"
    job_id: str
    job_type: str
    status: Literal["pending", "leased", "done", "failed"] = "pending"
    created_at: str
    updated_at: str
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    payload_ref: str
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    last_error: str | None = None


class RunRecord(StrictRecord):
    kind: Literal["run"] = "run"
    run_id: str
    job_id: str
    job_type: str
    started_at: str
    finished_at: str | None = None
    status: Literal["running", "succeeded", "failed"] = "running"
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    pipeline_version: str
    source_ids: list[str] = Field(default_factory=list)
    page_ids: list[str] = Field(default_factory=list)
    page_refs: list[str] = Field(default_factory=list)
    provenance_links: list[ProvenanceLink] = Field(default_factory=list)
