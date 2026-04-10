"""Implementation for `splendor add-source`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from splendor.state.source_registry import register_source


@dataclass(frozen=True)
class AddSourceResult:
    source_id: str
    manifest_path: Path
    stored_path: Path
    already_registered: bool


def add_source(root: Path, source_path: Path) -> AddSourceResult:
    registered = register_source(root, source_path)
    return AddSourceResult(
        source_id=registered.record.source_id,
        manifest_path=registered.manifest_path,
        stored_path=registered.stored_path,
        already_registered=registered.already_registered,
    )
