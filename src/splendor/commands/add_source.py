"""Implementation for `splendor add-source`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from splendor.schemas.types import StorageMode
from splendor.state.source_registry import register_source


@dataclass(frozen=True)
class AddSourceResult:
    source_id: str
    manifest_path: Path
    stored_path: Path | None
    storage_mode: StorageMode
    source_ref: str
    already_registered: bool


def add_source(
    root: Path,
    source_path: Path,
    *,
    storage_mode: StorageMode | None = None,
    capture_source_commit: bool | None = None,
) -> AddSourceResult:
    registered = register_source(
        root,
        source_path,
        storage_mode=storage_mode,
        capture_source_commit=capture_source_commit,
    )
    return AddSourceResult(
        source_id=registered.record.source_id,
        manifest_path=registered.manifest_path,
        stored_path=registered.stored_path,
        storage_mode=registered.storage_mode,
        source_ref=registered.source_ref,
        already_registered=registered.already_registered,
    )
