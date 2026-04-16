"""Implementation for `splendor materialize-source`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from splendor.schemas.types import StorageMode
from splendor.state.source_registry import materialize_registered_source


@dataclass(frozen=True)
class MaterializeSourceResult:
    source_id: str
    manifest_path: Path
    stored_path: Path
    storage_mode: StorageMode
    source_ref: str


def materialize_source(
    root: Path,
    source_id: str,
    *,
    storage_mode: StorageMode | None = None,
) -> MaterializeSourceResult:
    materialized = materialize_registered_source(root, source_id, storage_mode=storage_mode)
    return MaterializeSourceResult(
        source_id=materialized.record.source_id,
        manifest_path=materialized.manifest_path,
        stored_path=materialized.stored_path,
        storage_mode=materialized.storage_mode,
        source_ref=materialized.source_ref,
    )
