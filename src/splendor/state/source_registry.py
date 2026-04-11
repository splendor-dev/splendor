"""Source registration and manifest persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from splendor import __version__
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import SourceRecord
from splendor.utils.fs import copy_file_if_missing, ensure_directory, write_text_atomic
from splendor.utils.hashing import sha256_file
from splendor.utils.ids import stable_source_id
from splendor.utils.time import utc_now_iso


@dataclass(frozen=True)
class RegisteredSource:
    record: SourceRecord
    manifest_path: Path
    stored_path: Path
    copied: bool
    already_registered: bool


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


def register_source(root: Path, source_path: Path) -> RegisteredSource:
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
    stored_path = layout.raw_sources_dir / source_id / candidate.name

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
        existing_stored_path = resolve_manifest_storage_path(root, existing.path)
        validate_stored_source_location(
            existing_stored_path,
            layout.raw_sources_dir,
            source_id,
            existing.path,
        )
        if not existing_stored_path.exists():
            msg = f"Stored source copy is missing for existing manifest: {existing_stored_path}"
            raise FileNotFoundError(msg)
        existing_stored_checksum = sha256_file(existing_stored_path)
        if existing_stored_checksum != existing.checksum:
            msg = (
                f"Stored source checksum mismatch for existing manifest {manifest_path}: "
                f"expected {existing.checksum}, got {existing_stored_checksum}"
            )
            raise ValueError(msg)
        return RegisteredSource(
            record=existing,
            manifest_path=manifest_path,
            stored_path=existing_stored_path,
            copied=False,
            already_registered=True,
        )

    copied = copy_file_if_missing(candidate, stored_path)
    stored_checksum = sha256_file(stored_path)
    if stored_checksum != checksum:
        msg = (
            f"Stored source checksum mismatch for {stored_path}: "
            f"expected {checksum}, got {stored_checksum}"
        )
        raise ValueError(msg)
    record = SourceRecord(
        source_id=source_id,
        title=candidate.stem.replace("_", " ").replace("-", " ").strip() or candidate.name,
        source_type=candidate.suffix.lstrip(".") or "file",
        path=stored_path.relative_to(root).as_posix(),
        checksum=checksum,
        added_at=utc_now_iso(),
        pipeline_version=__version__,
        original_path=manifest_original_path(root, source_path),
    )
    write_source_record(manifest_path, record)
    return RegisteredSource(
        record=record,
        manifest_path=manifest_path,
        stored_path=stored_path,
        copied=copied,
        already_registered=False,
    )
