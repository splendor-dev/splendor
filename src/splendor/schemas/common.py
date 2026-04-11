"""Common schema types."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = Field(default="1")
