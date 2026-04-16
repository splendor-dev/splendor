"""Source content resolution for ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from splendor.schemas import SourceRecord
from splendor.state.paths import resolve_workspace_path
from splendor.state.source_compat import (
    canonical_source_ref,
    copied_source_error_label,
    effective_materialized_path,
    effective_source_ref_kind,
    effective_storage_mode,
    effective_stored_path,
    symlink_source_error_label,
)
from splendor.state.source_pointer import load_source_pointer
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


def _resolve_artifact_ref(root: Path, artifact_ref: str, *, context: str) -> Path:
    artifact_ref_path = Path(artifact_ref)
    if artifact_ref_path.is_absolute():
        msg = f"{context} path must be repo-relative: {artifact_ref}"
        raise ValueError(msg)
    if ".." in artifact_ref_path.parts:
        msg = f"{context} path escapes workspace root: {artifact_ref}"
        raise ValueError(msg)
    return root.resolve() / artifact_ref_path


def _require_workspace_source_checksum(
    resolved_path: Path, checksum: str, *, label: str, source_ref: str
) -> None:
    if not resolved_path.exists():
        msg = f"{label} is missing: {source_ref}"
        raise ValueError(msg)
    if sha256_file(resolved_path) != checksum:
        msg = f"{label} checksum mismatch for ingestion: {source_ref}"
        raise ValueError(msg)


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

    resolved_path = resolve_workspace_path(root, source.source_ref, context="Workspace source")
    _require_workspace_source_checksum(
        resolved_path,
        source.checksum,
        label="Workspace source",
        source_ref=source.source_ref,
    )

    return ResolvedSource(
        canonical_ref=source.source_ref,
        canonical_ref_kind="workspace_path",
        storage_mode="none",
        resolved_path=resolved_path,
        resolved_ref=source.source_ref,
        content_origin_label="Workspace source",
    )


def _validate_materialized_source_location(
    resolved_path: Path,
    raw_sources_dir: Path,
    source_id: str,
    stored_path_value: str,
    *,
    description: str,
) -> None:
    try:
        validate_stored_source_location(
            resolved_path,
            raw_sources_dir,
            source_id,
            stored_path_value,
        )
    except ValueError as exc:
        lowered = str(exc).replace("Stored source path", description)
        raise ValueError(lowered) from exc


def _resolve_pointer_source(
    root: Path, source: SourceRecord, raw_sources_dir: Path
) -> ResolvedSource:
    if not source.source_ref:
        msg = "Pointer-backed source is missing source_ref"
        raise ValueError(msg)
    if source.source_ref_kind != "workspace_path":
        msg = (
            "Pointer-backed source must use source_ref_kind=workspace_path; "
            f"got {source.source_ref_kind!r}"
        )
        raise ValueError(msg)

    pointer_path_value = effective_materialized_path(source)
    if pointer_path_value is None:
        msg = f"Pointer-backed source is missing a pointer artifact path: {source.source_id}"
        raise ValueError(msg)
    pointer_path = resolve_manifest_storage_path(root, pointer_path_value)
    _validate_materialized_source_location(
        pointer_path,
        raw_sources_dir,
        source.source_id,
        pointer_path_value,
        description="Pointer artifact path",
    )

    pointer = load_source_pointer(pointer_path)
    if pointer.source_id != source.source_id:
        msg = (
            "Pointer artifact source ID mismatch for "
            f"{pointer_path}: expected {source.source_id}, got {pointer.source_id}"
        )
        raise ValueError(msg)
    if pointer.source_ref_kind != "workspace_path":
        msg = (
            "Pointer artifact must use source_ref_kind=workspace_path; "
            f"got {pointer.source_ref_kind!r}"
        )
        raise ValueError(msg)
    if pointer.source_ref != source.source_ref:
        msg = (
            "Pointer artifact source_ref mismatch for "
            f"{pointer_path}: expected {source.source_ref}, got {pointer.source_ref}"
        )
        raise ValueError(msg)
    if pointer.checksum != source.checksum:
        msg = (
            "Pointer artifact checksum mismatch for "
            f"{pointer_path}: expected {source.checksum}, got {pointer.checksum}"
        )
        raise ValueError(msg)

    resolved_path = resolve_workspace_path(root, pointer.source_ref, context="Pointer target")
    _require_workspace_source_checksum(
        resolved_path,
        source.checksum,
        label="Workspace source",
        source_ref=pointer.source_ref,
    )

    return ResolvedSource(
        canonical_ref=source.source_ref,
        canonical_ref_kind="workspace_path",
        storage_mode="pointer",
        resolved_path=resolved_path,
        resolved_ref=source.source_ref,
        content_origin_label="Workspace source",
    )


def _resolve_symlink_source(
    root: Path, source: SourceRecord, raw_sources_dir: Path
) -> ResolvedSource:
    if not source.source_ref:
        msg = "Symlink-backed source is missing source_ref"
        raise ValueError(msg)
    if source.source_ref_kind != "workspace_path":
        msg = (
            "Symlink-backed source must use source_ref_kind=workspace_path; "
            f"got {source.source_ref_kind!r}"
        )
        raise ValueError(msg)

    symlink_path_value = effective_materialized_path(source)
    if symlink_path_value is None:
        msg = f"Symlink-backed source is missing a symlink artifact path: {source.source_id}"
        raise ValueError(msg)
    symlink_path = _resolve_artifact_ref(root, symlink_path_value, context="Symlink artifact")
    _validate_materialized_source_location(
        symlink_path,
        raw_sources_dir,
        source.source_id,
        symlink_path_value,
        description="Symlink artifact path",
    )

    source_label = symlink_source_error_label(source)
    if not symlink_path.exists() and not symlink_path.is_symlink():
        msg = f"{source_label} is missing: {symlink_path}"
        raise ValueError(msg)
    if not symlink_path.is_symlink():
        msg = f"{source_label} is not a symlink: {symlink_path}"
        raise ValueError(msg)

    try:
        resolved_path = symlink_path.resolve(strict=True)
    except FileNotFoundError as exc:
        msg = f"Workspace source is missing: {source.source_ref}"
        raise ValueError(msg) from exc
    except (OSError, RuntimeError) as exc:
        msg = f"{source_label} could not be resolved: {symlink_path}"
        raise ValueError(msg) from exc

    workspace_root = root.resolve()
    try:
        resolved_path.relative_to(workspace_root)
    except ValueError as exc:
        msg = f"{source_label} target escapes workspace root: {symlink_path}"
        raise ValueError(msg) from exc

    expected_path = resolve_workspace_path(root, source.source_ref, context="Workspace source")
    if resolved_path != expected_path:
        actual_ref = resolved_path.relative_to(workspace_root).as_posix()
        msg = (
            f"{source_label} target does not match manifest source_ref: "
            f"expected {source.source_ref}, got {actual_ref}"
        )
        raise ValueError(msg)

    _require_workspace_source_checksum(
        resolved_path,
        source.checksum,
        label="Workspace source",
        source_ref=source.source_ref,
    )

    return ResolvedSource(
        canonical_ref=source.source_ref,
        canonical_ref_kind="workspace_path",
        storage_mode="symlink",
        resolved_path=resolved_path,
        resolved_ref=source.source_ref,
        content_origin_label="Workspace source",
    )


def _resolve_copied_source(
    root: Path, source: SourceRecord, raw_sources_dir: Path
) -> ResolvedSource:
    stored_path_value = effective_stored_path(source)
    if stored_path_value is None:
        msg = f"Copied source is missing a stored path: {source.source_id}"
        raise ValueError(msg)
    resolved_path = resolve_manifest_storage_path(root, stored_path_value)
    _validate_materialized_source_location(
        resolved_path,
        raw_sources_dir,
        source.source_id,
        stored_path_value,
        description="Stored source path",
    )
    source_label = copied_source_error_label(source)
    if not resolved_path.exists():
        msg = f"{source_label} is missing: {resolved_path}"
        raise ValueError(msg)
    if sha256_file(resolved_path) != source.checksum:
        msg = f"{source_label} checksum mismatch for ingestion: {resolved_path}"
        raise ValueError(msg)

    return ResolvedSource(
        canonical_ref=canonical_source_ref(source),
        canonical_ref_kind=effective_source_ref_kind(source),
        storage_mode="copy",
        resolved_path=resolved_path,
        resolved_ref=stored_path_value,
        content_origin_label="Stored source",
    )


def resolve_source_content(
    root: Path, source: SourceRecord, raw_sources_dir: Path
) -> ResolvedSource:
    storage_mode = effective_storage_mode(source)
    if storage_mode == "pointer":
        return _resolve_pointer_source(root, source, raw_sources_dir)
    if storage_mode == "symlink":
        return _resolve_symlink_source(root, source, raw_sources_dir)

    if storage_mode == "none":
        return _resolve_workspace_source(root, source)

    return _resolve_copied_source(root, source, raw_sources_dir)
