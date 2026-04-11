"""Implementation for `splendor init`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from splendor.config import config_path_for, default_config, load_config, write_config
from splendor.layout import INDEX_TEMPLATE, LOG_TEMPLATE, required_directories, resolve_layout
from splendor.utils.fs import ensure_directory, write_if_missing

KEEP_FILES = [
    "raw/sources/.gitkeep",
    "raw/assets/.gitkeep",
    "raw/imports/.gitkeep",
    "derived/ocr/.gitkeep",
    "derived/parsed/.gitkeep",
    "derived/metadata/.gitkeep",
    "derived/summaries/.gitkeep",
    "wiki/concepts/.gitkeep",
    "wiki/entities/.gitkeep",
    "wiki/topics/.gitkeep",
    "wiki/sources/.gitkeep",
    "wiki/glossary/.gitkeep",
    "wiki/architecture/.gitkeep",
    "planning/milestones/.gitkeep",
    "planning/tasks/.gitkeep",
    "planning/decisions/.gitkeep",
    "planning/questions/.gitkeep",
    "state/manifests/.gitkeep",
    "state/manifests/sources/.gitkeep",
    "state/queue/.gitkeep",
    "state/runs/.gitkeep",
    "state/locks/.gitkeep",
    "reports/lint/.gitkeep",
    "reports/health/.gitkeep",
    "reports/ingest/.gitkeep",
]


@dataclass(frozen=True)
class InitResult:
    root: Path
    created_directories: list[Path]
    created_files: list[Path]


def initialize_workspace(root: Path) -> InitResult:
    config_path = config_path_for(root)
    config = load_config(root) if config_path.exists() else default_config(project_name=root.name)
    should_rewrite_config = False
    if config_path.exists():
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        should_rewrite_config = not raw_config.get("project_name")

    layout = resolve_layout(root, config)
    created_directories: list[Path] = []
    created_files: list[Path] = []

    for directory in required_directories(layout):
        if not directory.exists():
            created_directories.append(directory)
        ensure_directory(directory)

    if not config_path.exists():
        created_files.append(write_config(root, config))
    elif should_rewrite_config:
        write_config(root, config)

    if write_if_missing(layout.index_file, INDEX_TEMPLATE):
        created_files.append(layout.index_file)
    if write_if_missing(layout.log_file, LOG_TEMPLATE):
        created_files.append(layout.log_file)
    for keep_file in KEEP_FILES:
        keep_path = root / keep_file
        if write_if_missing(keep_path, ""):
            created_files.append(keep_path)

    return InitResult(
        root=root, created_directories=created_directories, created_files=created_files
    )
