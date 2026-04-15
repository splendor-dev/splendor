"""Pointer artifact schema for workspace-backed sources."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from splendor.schemas.common import StrictRecord
from splendor.schemas.types import SourceRefKind


class SourcePointerArtifact(StrictRecord):
    kind: Literal["source-pointer"] = "source-pointer"
    source_id: str
    source_ref: str
    source_ref_kind: SourceRefKind
    checksum: str = Field(min_length=64, max_length=64)
    created_at: str
