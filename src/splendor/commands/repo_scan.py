"""Implementation for `splendor repo scan`."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from splendor.commands.ingest import SUPPORTED_SOURCE_TYPES
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas.types import SourceClass
from splendor.state.source_registry import register_source

_CODE_EXTENSIONS = SUPPORTED_SOURCE_TYPES - {"json", "md", "txt", "yaml", "yml"}
_CONFIG_EXTENSIONS = {"json", "yaml", "yml"}
_IGNORED_TOP_LEVEL_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}


@dataclass(frozen=True)
class RepoScanItem:
    path: str
    source_id: str
    source_class: SourceClass
    source_labels: list[str]
    status: str


@dataclass(frozen=True)
class RepoScanResult:
    scanned: int
    registered: int
    already_registered: int
    unsupported: int
    ignored: int
    class_counts: dict[str, int]
    touched_sources: list[RepoScanItem]


def scan_repo(root: Path) -> RepoScanResult:
    config = load_config(root)
    layout = resolve_layout(root, config)
    supported_paths: list[Path] = []
    ignored = 0
    unsupported = 0

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current_dir = Path(dirpath)
        dirnames[:] = [
            dirname
            for dirname in sorted(dirnames)
            if not _is_ignored_dir(current_dir / dirname, root, layout)
        ]
        ignored += len(filenames) - len(
            [
                filename
                for filename in filenames
                if not _is_ignored_path(current_dir / filename, root, layout)
            ]
        )
        for filename in sorted(filenames):
            path = current_dir / filename
            if _is_ignored_path(path, root, layout):
                continue
            if path.suffix.lstrip(".") not in SUPPORTED_SOURCE_TYPES:
                unsupported += 1
                continue
            supported_paths.append(path)

    touched_sources: list[RepoScanItem] = []
    class_counts = {name: 0 for name in ("code", "documentation", "configuration", "other")}
    registered = 0
    already_registered = 0

    for path in supported_paths:
        relative_path = path.relative_to(root).as_posix()
        source_class = _classify_path(path, relative_path)
        source_labels = _labels_for(relative_path)
        registered_source = register_source(
            root,
            path,
            source_class=source_class,
            source_labels=source_labels,
            discovered_by="repo_scan",
            refresh_existing_metadata=True,
        )
        status = "already_registered" if registered_source.already_registered else "registered"
        if registered_source.already_registered:
            already_registered += 1
        else:
            registered += 1
        class_counts[source_class] += 1
        touched_sources.append(
            RepoScanItem(
                path=relative_path,
                source_id=registered_source.record.source_id,
                source_class=source_class,
                source_labels=source_labels,
                status=status,
            )
        )

    return RepoScanResult(
        scanned=len(supported_paths),
        registered=registered,
        already_registered=already_registered,
        unsupported=unsupported,
        ignored=ignored,
        class_counts=class_counts,
        touched_sources=touched_sources,
    )


def render_repo_scan_json(result: RepoScanResult) -> str:
    payload = {
        "scanned": result.scanned,
        "registered": result.registered,
        "already_registered": result.already_registered,
        "unsupported": result.unsupported,
        "ignored": result.ignored,
        "class_counts": result.class_counts,
        "touched_sources": [
            {
                "path": item.path,
                "source_id": item.source_id,
                "source_class": item.source_class,
                "source_labels": item.source_labels,
                "status": item.status,
            }
            for item in result.touched_sources
        ],
    }
    return json.dumps(payload, indent=2)


def _is_ignored_path(path: Path, root: Path, layout) -> bool:
    relative = path.relative_to(root)
    if not relative.parts:
        return False
    first = relative.parts[0]
    return first in _ignored_top_level_dirs(root, layout)


def _is_ignored_dir(path: Path, root: Path, layout) -> bool:
    relative = path.relative_to(root)
    if not relative.parts:
        return False
    if len(relative.parts) == 1:
        return relative.parts[0] in _ignored_top_level_dirs(root, layout)
    return False


def _ignored_top_level_dirs(root: Path, layout) -> set[str]:
    ignored_top_level_dirs = _IGNORED_TOP_LEVEL_DIRS | {
        layout.raw_dir.relative_to(root).parts[0],
        layout.derived_dir.relative_to(root).parts[0],
        layout.state_dir.relative_to(root).parts[0],
        layout.reports_dir.relative_to(root).parts[0],
        layout.wiki_dir.relative_to(root).parts[0],
        layout.planning_dir.relative_to(root).parts[0],
    }
    return ignored_top_level_dirs


def _classify_path(path: Path, relative_path: str) -> SourceClass:
    suffix = path.suffix.lstrip(".")
    if suffix in {"md", "txt"}:
        return "documentation"
    if suffix in _CONFIG_EXTENSIONS or relative_path.startswith(".github/workflows/"):
        return "configuration"
    if suffix in _CODE_EXTENSIONS:
        return "code"
    return "other"


def _labels_for(relative_path: str) -> list[str]:
    labels: list[str] = []
    name = Path(relative_path).name
    if relative_path.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py"):
        labels.append("test")
    if relative_path.startswith("examples/"):
        labels.append("example")
    if relative_path.startswith(".github/workflows/"):
        labels.append("automation")
    if relative_path in {"AGENTS.md", "llms.txt"}:
        labels.append("agent-instructions")
    return labels
