"""Source registration and manifest persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from splendor import __version__
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import SourceRecord
from splendor.utils.fs import copy_file_if_missing, ensure_directory
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
        existing_stored_path = root / existing.path
        return RegisteredSource(
            record=existing,
            manifest_path=manifest_path,
            stored_path=existing_stored_path,
            copied=False,
            already_registered=True,
        )

    copied = copy_file_if_missing(candidate, stored_path)
    record = SourceRecord(
        source_id=source_id,
        title=candidate.stem.replace("_", " ").replace("-", " ").strip() or candidate.name,
        source_type=candidate.suffix.lstrip(".") or "file",
        path=str(stored_path.relative_to(root)),
        checksum=checksum,
        added_at=utc_now_iso(),
        pipeline_version=__version__,
        original_path=str(candidate),
    )
    manifest_path.write_text(
        json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return RegisteredSource(
        record=record,
        manifest_path=manifest_path,
        stored_path=stored_path,
        copied=copied,
        already_registered=False,
    )
