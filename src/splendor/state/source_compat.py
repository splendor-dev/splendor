"""Read-only compatibility helpers for mixed source manifest shapes."""

from __future__ import annotations

from splendor.schemas import SourceRecord
from splendor.schemas.types import SourceRefKind, StorageMode


def effective_storage_mode(source: SourceRecord) -> StorageMode:
    return source.storage_mode or "copy"


def effective_source_ref_kind(source: SourceRecord) -> SourceRefKind:
    return source.source_ref_kind or "stored_artifact"


def canonical_source_ref(source: SourceRecord) -> str:
    return source.source_ref or source.original_path or source.path


def effective_stored_path(source: SourceRecord) -> str | None:
    if effective_storage_mode(source) != "copy":
        return None
    return source.storage_path or source.path


def effective_materialized_path(source: SourceRecord) -> str | None:
    if effective_storage_mode(source) not in {"copy", "pointer"}:
        return None
    return source.storage_path or source.path


def pointer_source_error_label(source: SourceRecord) -> str:
    if is_legacy_copied_manifest(source):
        return "Legacy stored source pointer"
    return "Source pointer artifact"


def is_legacy_copied_manifest(source: SourceRecord) -> bool:
    return source.storage_mode is None and source.source_ref is None


def copied_source_error_label(source: SourceRecord) -> str:
    if is_legacy_copied_manifest(source):
        return "Legacy stored source copy"
    return "Stored source copy"
