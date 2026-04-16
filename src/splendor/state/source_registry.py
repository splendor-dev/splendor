"""Source registration and manifest persistence."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from splendor import __version__
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import SourcePointerArtifact, SourceRecord
from splendor.schemas.types import StorageMode
from splendor.state.paths import resolve_workspace_path
from splendor.state.source_compat import (
    canonical_source_ref,
    effective_materialized_path,
    is_legacy_copied_manifest,
)
from splendor.state.source_pointer import pointer_artifact_relpath, write_source_pointer
from splendor.utils.fs import (
    copy_file_atomic,
    copy_file_if_missing,
    ensure_directory,
    write_text_atomic,
)
from splendor.utils.git import captured_source_commit
from splendor.utils.hashing import sha256_file
from splendor.utils.ids import stable_source_id
from splendor.utils.time import utc_now_iso


@dataclass(frozen=True)
class RegisteredSource:
    record: SourceRecord
    manifest_path: Path
    stored_path: Path | None
    storage_mode: StorageMode
    source_ref: str
    copied: bool
    already_registered: bool


@dataclass(frozen=True)
class MaterializedSource:
    record: SourceRecord
    manifest_path: Path
    stored_path: Path
    storage_mode: StorageMode
    source_ref: str


def manifest_path_for(root: Path, source_id: str) -> Path:
    config = load_config(root)
    layout = resolve_layout(root, config)
    return layout.source_records_dir / f"{source_id}.json"


def load_source_record(path: Path) -> SourceRecord:
    return SourceRecord.model_validate_json(path.read_text(encoding="utf-8"))


def write_source_record(path: Path, record: SourceRecord) -> Path:
    write_text_atomic(
        path,
        json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )
    return path


def resolve_manifest_storage_path(root: Path, stored_path_value: str) -> Path:
    stored_path = Path(stored_path_value)
    if stored_path.is_absolute() or ".." in stored_path.parts:
        msg = f"Stored source path escapes workspace root: {stored_path_value}"
        raise ValueError(msg)

    resolved = (root / stored_path).resolve()
    workspace_root = root.resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        msg = f"Stored source path escapes workspace root: {stored_path_value}"
        raise ValueError(msg) from exc
    return resolved


def validate_stored_source_location(
    stored_path: Path, raw_sources_dir: Path, source_id: str, stored_path_value: str
) -> None:
    raw_sources_root = raw_sources_dir.resolve()
    try:
        relative_path = stored_path.relative_to(raw_sources_root)
    except ValueError as exc:
        msg = (
            "Stored source path is outside the configured raw source storage area: "
            f"{stored_path_value}"
        )
        raise ValueError(msg) from exc

    if not relative_path.parts or relative_path.parts[0] != source_id:
        msg = f"Stored source path is outside the expected source directory: {stored_path_value}"
        raise ValueError(msg)


def manifest_original_path(root: Path, source_path: Path) -> str:
    try:
        return source_path.expanduser().resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(source_path.expanduser())


def _title_for(candidate: Path) -> str:
    return candidate.stem.replace("_", " ").replace("-", " ").strip() or candidate.name


def _source_reference(root: Path, candidate: Path) -> tuple[str, str]:
    try:
        return candidate.relative_to(root.resolve()).as_posix(), "workspace_path"
    except ValueError:
        return str(candidate), "external_path"


def _effective_storage_mode(
    *,
    source_ref_kind: str,
    configured_storage_mode: StorageMode,
) -> StorageMode:
    if source_ref_kind == "workspace_path":
        if configured_storage_mode in {"none", "copy", "pointer", "symlink"}:
            return configured_storage_mode
        msg = (
            f"Storage mode {configured_storage_mode!r} is not implemented yet for workspace sources"
        )
        raise ValueError(msg)

    if configured_storage_mode == "copy":
        return "copy"
    if configured_storage_mode == "pointer":
        msg = (
            f"Storage mode {configured_storage_mode!r} is not implemented yet for external sources"
        )
        raise ValueError(msg)
    if configured_storage_mode == "symlink":
        msg = (
            f"Storage mode {configured_storage_mode!r} is not implemented yet for external sources"
        )
        raise ValueError(msg)
    msg = f"Storage mode {configured_storage_mode!r} is not supported for external sources"
    raise ValueError(msg)


def _storage_mode_for_source(
    *,
    source_ref_kind: str,
    config,
    storage_mode_override: StorageMode | None,
) -> StorageMode:
    configured = (
        storage_mode_override
        if storage_mode_override is not None
        else (
            config.sources.in_repo_storage_mode
            if source_ref_kind == "workspace_path"
            else config.sources.external_storage_mode
        )
    )
    return _effective_storage_mode(
        source_ref_kind=source_ref_kind,
        configured_storage_mode=configured,
    )


def _source_commit_for_registration(
    *,
    root: Path,
    candidate: Path,
    source_ref_kind: str,
    capture_source_commit_enabled: bool,
) -> str | None:
    if not capture_source_commit_enabled or source_ref_kind != "workspace_path":
        return None
    return captured_source_commit(root, candidate)


def _stored_path_for(layout, source_id: str, candidate: Path) -> Path:
    return layout.raw_sources_dir / source_id / candidate.name


def _materialized_path_for(
    layout, source_id: str, candidate: Path, storage_mode: StorageMode
) -> Path | None:
    if storage_mode in {"copy", "symlink"}:
        return _stored_path_for(layout, source_id, candidate)
    if storage_mode == "pointer":
        return layout.root / pointer_artifact_relpath(source_id)
    return None


def _replace_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        msg = f"Cannot replace existing directory with source artifact: {path}"
        raise ValueError(msg)
    if path.exists() or path.is_symlink():
        path.unlink()


def _write_workspace_symlink(stored_path: Path, candidate: Path) -> None:
    ensure_directory(stored_path.parent)
    _replace_path(stored_path)
    target = Path(os.path.relpath(candidate, start=stored_path.parent))
    stored_path.symlink_to(target)
    if not stored_path.is_symlink():
        msg = f"Failed to create source symlink artifact: {stored_path}"
        raise ValueError(msg)
    resolved_target = stored_path.resolve(strict=True)
    if resolved_target != candidate.resolve():
        msg = (
            "Source symlink artifact does not resolve to the canonical workspace source: "
            f"{stored_path}"
        )
        raise ValueError(msg)


def write_source_artifact(
    candidate: Path,
    *,
    stored_path: Path,
    source_id: str,
    source_ref: str,
    source_ref_kind: str,
    checksum: str,
    storage_mode: StorageMode,
    materialized_at: str,
    refresh: bool = False,
) -> bool:
    copied = False
    if storage_mode == "copy":
        if refresh:
            copy_file_atomic(candidate, stored_path)
            copied = True
        else:
            copied = copy_file_if_missing(candidate, stored_path)
        stored_checksum = sha256_file(stored_path)
        if stored_checksum != checksum:
            msg = (
                f"Stored source checksum mismatch for {stored_path}: "
                f"expected {checksum}, got {stored_checksum}"
            )
            raise ValueError(msg)
        return copied

    if storage_mode == "pointer":
        ensure_directory(stored_path.parent)
        write_source_pointer(
            stored_path,
            SourcePointerArtifact(
                source_id=source_id,
                source_ref=source_ref,
                source_ref_kind=source_ref_kind,
                checksum=checksum,
                created_at=materialized_at,
            ),
        )
        return False

    if storage_mode == "symlink":
        _write_workspace_symlink(stored_path, candidate)
        return False

    msg = f"Storage mode {storage_mode!r} does not materialize a source artifact"
    raise ValueError(msg)


def _validated_existing_registration(
    *,
    root: Path,
    layout,
    existing: SourceRecord,
) -> tuple[Path | None, StorageMode, str]:
    from splendor.state.source_resolver import resolve_source_content

    try:
        resolved = resolve_source_content(root, existing, layout.raw_sources_dir)
    except ValueError as exc:
        msg = (
            "Existing source manifest could not be validated during add-source "
            f"for source {existing.source_id}: {exc}"
        )
        raise ValueError(msg) from exc
    stored_path_value = effective_materialized_path(existing)
    if stored_path_value is None:
        stored_path = None
    elif resolved.storage_mode == "symlink":
        stored_path = root.resolve() / Path(stored_path_value)
    else:
        stored_path = resolve_manifest_storage_path(root, stored_path_value)
    source_ref = canonical_source_ref(existing)
    return stored_path, resolved.storage_mode, source_ref


def materializing_storage_mode_for_source(
    root: Path,
    source: SourceRecord,
    *,
    storage_mode: StorageMode | None = None,
) -> StorageMode:
    if is_legacy_copied_manifest(source):
        msg = (
            "Legacy stored-artifact manifests cannot be materialized with this workflow: "
            f"{source.source_id}"
        )
        raise ValueError(msg)
    if source.source_ref is None or source.source_ref_kind != "workspace_path":
        msg = (
            "Only workspace-backed sources can be materialized; "
            f"source {source.source_id} is {source.source_ref_kind or 'legacy'}"
        )
        raise ValueError(msg)

    if storage_mode is not None:
        selected_storage_mode = _effective_storage_mode(
            source_ref_kind="workspace_path",
            configured_storage_mode=storage_mode,
        )
    elif source.storage_mode in {"copy", "pointer", "symlink"}:
        selected_storage_mode = source.storage_mode
    else:
        config = load_config(root)
        configured_mode = config.sources.in_repo_storage_mode
        if configured_mode in {"copy", "pointer", "symlink"}:
            selected_storage_mode = configured_mode
        else:
            selected_storage_mode = "pointer"

    if selected_storage_mode == "none":
        msg = f"Storage mode {selected_storage_mode!r} does not materialize a source artifact"
        raise ValueError(msg)
    return selected_storage_mode


def materialize_registered_source(
    root: Path,
    source_id: str,
    *,
    storage_mode: StorageMode | None = None,
) -> MaterializedSource:
    manifest_path = manifest_path_for(root, source_id)
    if not manifest_path.exists():
        msg = f"Unknown source ID: {source_id}"
        raise FileNotFoundError(msg)

    source = load_source_record(manifest_path)
    if source.source_id != source_id:
        msg = f"Source manifest ID does not match requested source: {source_id}"
        raise ValueError(msg)
    if source.storage_mode is None and source.source_ref is None:
        msg = (
            "Legacy stored-artifact manifests cannot be materialized with this workflow: "
            f"{source_id}"
        )
        raise ValueError(msg)
    if source.source_ref is None or source.source_ref_kind != "workspace_path":
        msg = (
            "Only workspace-backed sources can be materialized; "
            f"source {source_id} is {source.source_ref_kind or 'legacy'}"
        )
        raise ValueError(msg)

    config = load_config(root)
    layout = resolve_layout(root, config)
    ensure_directory(layout.source_records_dir)
    ensure_directory(layout.raw_sources_dir)

    selected_storage_mode = materializing_storage_mode_for_source(
        root, source, storage_mode=storage_mode
    )
    candidate = resolve_workspace_path(root, source.source_ref, context="Workspace source")
    _require_workspace_source(candidate, source.checksum, source.source_ref)

    stored_path = _materialized_path_for(layout, source_id, candidate, selected_storage_mode)
    if stored_path is None:
        msg = f"Storage mode {selected_storage_mode!r} did not produce a storage path"
        raise ValueError(msg)
    materialized_at = utc_now_iso()
    write_source_artifact(
        candidate,
        stored_path=stored_path,
        source_id=source_id,
        source_ref=source.source_ref,
        source_ref_kind=source.source_ref_kind,
        checksum=source.checksum,
        storage_mode=selected_storage_mode,
        materialized_at=materialized_at,
        refresh=True,
    )
    updated_source = source.model_copy(
        update={
            "storage_mode": selected_storage_mode,
            "storage_path": stored_path.relative_to(root).as_posix(),
            "path": stored_path.relative_to(root).as_posix(),
            "materialized_at": materialized_at,
        }
    )
    write_source_record(manifest_path, updated_source)
    return MaterializedSource(
        record=updated_source,
        manifest_path=manifest_path,
        stored_path=stored_path,
        storage_mode=selected_storage_mode,
        source_ref=source.source_ref,
    )


def _require_workspace_source(resolved_path: Path, checksum: str, source_ref: str) -> None:
    if not resolved_path.exists():
        msg = f"Workspace source is missing: {source_ref}"
        raise ValueError(msg)
    if sha256_file(resolved_path) != checksum:
        msg = f"Workspace source checksum mismatch for materialization: {source_ref}"
        raise ValueError(msg)


def register_source(
    root: Path,
    source_path: Path,
    *,
    storage_mode: StorageMode | None = None,
    capture_source_commit: bool | None = None,
) -> RegisteredSource:
    candidate = source_path.expanduser().resolve()
    if not candidate.exists():
        msg = f"Source path does not exist: {source_path}"
        raise FileNotFoundError(msg)
    if not candidate.is_file():
        msg = f"Source path must be a file: {source_path}"
        raise IsADirectoryError(msg)

    config = load_config(root)
    layout = resolve_layout(root, config)
    ensure_directory(layout.source_records_dir)
    ensure_directory(layout.raw_sources_dir)

    checksum = sha256_file(candidate)
    source_id = stable_source_id(checksum)
    manifest_path = layout.source_records_dir / f"{source_id}.json"
    source_ref, source_ref_kind = _source_reference(root, candidate)
    selected_storage_mode = _storage_mode_for_source(
        source_ref_kind=source_ref_kind,
        config=config,
        storage_mode_override=storage_mode,
    )
    capture_commit_enabled = (
        capture_source_commit
        if capture_source_commit is not None
        else config.sources.capture_source_commit
    )
    source_commit = _source_commit_for_registration(
        root=root,
        candidate=candidate,
        source_ref_kind=source_ref_kind,
        capture_source_commit_enabled=capture_commit_enabled,
    )
    stored_path = _materialized_path_for(layout, source_id, candidate, selected_storage_mode)

    if manifest_path.exists():
        existing = load_source_record(manifest_path)
        if existing.source_id != source_id:
            msg = (
                f"Source ID mismatch for existing source manifest {manifest_path}: "
                f"expected {source_id}, got {existing.source_id}"
            )
            raise ValueError(msg)
        if existing.checksum != checksum:
            msg = (
                f"Checksum mismatch for existing source manifest {manifest_path}: "
                f"expected {existing.checksum}, got {checksum}"
            )
            raise ValueError(msg)
        existing_stored_path, existing_storage_mode, existing_source_ref = (
            _validated_existing_registration(root=root, layout=layout, existing=existing)
        )
        return RegisteredSource(
            record=existing,
            manifest_path=manifest_path,
            stored_path=existing_stored_path,
            storage_mode=existing_storage_mode,
            source_ref=existing_source_ref,
            copied=False,
            already_registered=True,
        )

    added_at = utc_now_iso()
    copied = False
    if selected_storage_mode in {"copy", "pointer", "symlink"} and stored_path is not None:
        copied = write_source_artifact(
            candidate,
            stored_path=stored_path,
            source_id=source_id,
            source_ref=source_ref,
            source_ref_kind=source_ref_kind,
            checksum=checksum,
            storage_mode=selected_storage_mode,
            materialized_at=added_at,
        )
    record = SourceRecord(
        source_id=source_id,
        title=_title_for(candidate),
        source_type=candidate.suffix.lstrip(".") or "file",
        path=(stored_path.relative_to(root).as_posix() if stored_path is not None else source_ref),
        checksum=checksum,
        added_at=added_at,
        pipeline_version=__version__,
        original_path=manifest_original_path(root, source_path),
        source_ref=source_ref,
        source_ref_kind=source_ref_kind,
        storage_mode=selected_storage_mode,
        storage_path=(
            stored_path.relative_to(root).as_posix() if stored_path is not None else None
        ),
        materialized_at=(added_at if stored_path is not None else None),
        source_commit=source_commit,
    )
    write_source_record(manifest_path, record)
    return RegisteredSource(
        record=record,
        manifest_path=manifest_path,
        stored_path=stored_path,
        storage_mode=selected_storage_mode,
        source_ref=source_ref,
        copied=copied,
        already_registered=False,
    )
