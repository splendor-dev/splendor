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


def logical_source_id_for_ref(
    source_ref: str | None, source_ref_kind: SourceRefKind | str | None
) -> str | None:
    if source_ref_kind != "workspace_path" or source_ref is None:
        return None
    return f"source:{source_ref}"


def effective_logical_id(source: SourceRecord) -> str | None:
    return source.logical_id or logical_source_id_for_ref(source.source_ref, source.source_ref_kind)


def effective_aliases(source: SourceRecord) -> list[str]:
    aliases = list(source.aliases)
    logical_id = effective_logical_id(source)
    if logical_id is not None:
        aliases.append(logical_id)
    source_ref = canonical_source_ref(source)
    if source.source_ref_kind == "workspace_path":
        aliases.append(source_ref)

    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        if alias and alias not in seen:
            seen.add(alias)
            deduped.append(alias)
    return deduped


def is_superseded_source(source: SourceRecord) -> bool:
    return source.superseded_by is not None


def effective_stored_path(source: SourceRecord) -> str | None:
    if effective_storage_mode(source) != "copy":
        return None
    return source.storage_path or source.path


def effective_materialized_path(source: SourceRecord) -> str | None:
    if effective_storage_mode(source) not in {"copy", "pointer", "symlink"}:
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


def symlink_source_error_label(source: SourceRecord) -> str:
    if is_legacy_copied_manifest(source):
        return "Legacy stored source symlink"
    return "Source symlink artifact"
