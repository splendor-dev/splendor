"""Shared path validation helpers for source state operations."""

from __future__ import annotations

from pathlib import Path


def resolve_workspace_path(root: Path, source_ref: str, *, context: str) -> Path:
    source_ref_path = Path(source_ref)
    if source_ref_path.is_absolute():
        msg = f"{context} path must be repo-relative: {source_ref}"
        raise ValueError(msg)
    if ".." in source_ref_path.parts:
        msg = f"{context} path escapes workspace root: {source_ref}"
        raise ValueError(msg)

    resolved_path = (root / source_ref_path).resolve()
    workspace_root = root.resolve()
    try:
        resolved_path.relative_to(workspace_root)
    except ValueError as exc:
        msg = f"{context} path escapes workspace root: {source_ref}"
        raise ValueError(msg) from exc
    return resolved_path
