"""Shared provenance schema fragments."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from splendor.schemas.types import ProvenanceRole


class ProvenanceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str | None = None
    page_id: str | None = None
    run_id: str | None = None
    path_ref: str | None = None
    role: ProvenanceRole | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _validate_identity_fields(self) -> ProvenanceLink:
        if self.source_id or self.page_id or self.run_id or self.path_ref:
            return self
        msg = "Provenance link must include at least one of source_id, page_id, run_id, or path_ref"
        raise ValueError(msg)
