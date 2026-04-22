"""Shared schema and config type aliases."""

from __future__ import annotations

from typing import Literal

StorageMode = Literal["none", "copy", "symlink", "pointer"]
SummaryMode = Literal["none", "excerpt", "full"]
SourceRefKind = Literal["workspace_path", "external_path", "url", "imported", "stored_artifact"]
PageReviewState = Literal["draft", "machine-generated", "human-reviewed", "contested", "stale"]
SourceReviewState = Literal[
    "unreviewed",
    "draft",
    "machine-generated",
    "human-reviewed",
    "contested",
    "stale",
]
ProvenanceRole = Literal["input", "output", "supports", "generated-from", "generated-page"]

STORAGE_MODES = ("none", "copy", "symlink", "pointer")
