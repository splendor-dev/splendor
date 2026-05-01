"""Implementation for `splendor add-source`."""

from __future__ import annotations

from dataclasses import dataclass
from glob import glob
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


def _sort_key(root: Path, path: Path) -> tuple[str, str]:
    resolved = path.expanduser().resolve()
    try:
        return ("workspace", resolved.relative_to(root.resolve()).as_posix())
    except ValueError:
        return ("external", str(resolved))


def expand_source_paths(
    root: Path,
    *,
    source_path: Path | None = None,
    glob_patterns: list[str] | None = None,
    directories: list[Path] | None = None,
) -> list[Path]:
    """Expand add-source selectors into a deterministic file list."""
    candidates: list[Path] = []
    if source_path is not None:
        candidates.append(source_path)

    for pattern in glob_patterns or []:
        expanded_pattern = str(Path(pattern).expanduser())
        if Path(expanded_pattern).is_absolute():
            matches = [Path(match) for match in glob(expanded_pattern, recursive=True)]
        else:
            matches = list(root.glob(expanded_pattern))
        candidates.extend(match for match in matches if match.is_file())

    for directory in directories or []:
        resolved_dir = directory.expanduser()
        if not resolved_dir.is_absolute():
            resolved_dir = root / resolved_dir
        if not resolved_dir.exists():
            msg = f"Source directory does not exist: {directory}"
            raise FileNotFoundError(msg)
        if not resolved_dir.is_dir():
            msg = f"Source directory must be a directory: {directory}"
            raise NotADirectoryError(msg)
        candidates.extend(path for path in resolved_dir.iterdir() if path.is_file())

    unique: dict[Path, Path] = {}
    for candidate in candidates:
        resolved = candidate.expanduser()
        if not resolved.is_absolute():
            resolved = root / resolved
        unique[resolved.resolve()] = resolved

    return sorted(unique.values(), key=lambda path: _sort_key(root, path))


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
