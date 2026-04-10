"""Common schema types."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StrictRecord(BaseModel):
    schema_version: str = Field(default="1")


StatusType = Literal["draft", "active", "completed", "failed", "registered", "queued", "done"]
