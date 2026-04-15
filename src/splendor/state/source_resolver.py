"""Source content resolution for ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from splendor.schemas import SourceRecord
from splendor.state.source_registry import (
    resolve_manifest_storage_path,
    validate_stored_source_location,
)
from splendor.utils.hashing import sha256_file


@dataclass(frozen=True)
class ResolvedSource:
    canonical_ref: str
    canonical_ref_kind: str
    storage_mode: str
    resolved_path: Path
    resolved_ref: str
    content_origin_label: str


def _resolve_workspace_source(root: Path, source: SourceRecord) -> ResolvedSource:
    if not source.source_ref:
        msg = "Workspace-backed source is missing source_ref"
        raise ValueError(msg)
    if source.source_ref_kind != "workspace_path":
        msg = (
            "Workspace-backed source must use source_ref_kind=workspace_path; "
            f"got {source.source_ref_kind!r}"
        )
        raise ValueError(msg)

    source_ref_path = Path(source.source_ref)
    if source_ref_path.is_absolute():
        msg = f"Workspace source path must be repo-relative: {source.source_ref}"
        raise ValueError(msg)
    if ".." in source_ref_path.parts:
        msg = f"Workspace source path escapes workspace root: {source.source_ref}"
        raise ValueError(msg)

    resolved_path = (root / source_ref_path).resolve()
    workspace_root = root.resolve()
    try:
        resolved_path.relative_to(workspace_root)
    except ValueError as exc:
        msg = f"Workspace source path escapes workspace root: {source.source_ref}"
        raise ValueError(msg) from exc

    if not resolved_path.exists():
        msg = f"Workspace source is missing: {source.source_ref}"
        raise ValueError(msg)
    if sha256_file(resolved_path) != source.checksum:
        msg = f"Workspace source checksum mismatch for ingestion: {source.source_ref}"
        raise ValueError(msg)

    return ResolvedSource(
        canonical_ref=source.source_ref,
        canonical_ref_kind="workspace_path",
        storage_mode="none",
        resolved_path=resolved_path,
        resolved_ref=source.source_ref,
        content_origin_label="Workspace source",
    )


def _resolve_copied_source(
    root: Path, source: SourceRecord, raw_sources_dir: Path
) -> ResolvedSource:
    stored_path_value = source.storage_path or source.path
    resolved_path = resolve_manifest_storage_path(root, stored_path_value)
    validate_stored_source_location(
        resolved_path,
        raw_sources_dir,
        source.source_id,
        stored_path_value,
    )
    if not resolved_path.exists():
        msg = f"Stored source copy is missing: {resolved_path}"
        raise ValueError(msg)
    if sha256_file(resolved_path) != source.checksum:
        msg = f"Stored source checksum mismatch for ingestion: {resolved_path}"
        raise ValueError(msg)

    return ResolvedSource(
        canonical_ref=source.source_ref or source.original_path or source.path,
        canonical_ref_kind=source.source_ref_kind or "stored_artifact",
        storage_mode="copy",
        resolved_path=resolved_path,
        resolved_ref=stored_path_value,
        content_origin_label="Stored source",
    )


def resolve_source_content(
    root: Path, source: SourceRecord, raw_sources_dir: Path
) -> ResolvedSource:
    if source.storage_mode in {"symlink", "pointer"}:
        msg = f"Unsupported storage mode for ingestion: {source.storage_mode}"
        raise ValueError(msg)

    if source.storage_mode == "none":
        return _resolve_workspace_source(root, source)

    if source.storage_mode == "copy":
        return _resolve_copied_source(root, source, raw_sources_dir)

    return _resolve_copied_source(root, source, raw_sources_dir)
