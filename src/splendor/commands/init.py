"""Implementation for `splendor init`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from splendor.config import config_path_for, default_config, load_config, write_config
from splendor.layout import (
    INDEX_TEMPLATE,
    LOG_TEMPLATE,
    ResolvedLayout,
    required_directories,
    resolve_layout,
)
from splendor.utils.fs import ensure_directory, write_if_missing


@dataclass(frozen=True)
class InitReviewGroup:
    label: str
    paths: list[str]
    note: str


@dataclass(frozen=True)
class InitResult:
    root: Path
    created_directories: list[Path]
    created_files: list[Path]
    review_groups: list[InitReviewGroup]


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
    for keep_path in _keep_files(layout):
        if write_if_missing(keep_path, ""):
            created_files.append(keep_path)

    return InitResult(
        root=root,
        created_directories=created_directories,
        created_files=created_files,
        review_groups=_init_review_groups(layout),
    )


def _init_review_groups(layout: ResolvedLayout) -> list[InitReviewGroup]:
    return [
        InitReviewGroup(
            label="configuration",
            paths=[config_path_for(layout.root).relative_to(layout.root).as_posix()],
            note="project defaults and configurable state locations",
        ),
        InitReviewGroup(
            label="human workspace",
            paths=[
                layout.wiki_dir.relative_to(layout.root).as_posix(),
                layout.planning_dir.relative_to(layout.root).as_posix(),
            ],
            note="reviewed wiki and planning markdown",
        ),
        InitReviewGroup(
            label="source and derived state",
            paths=[
                layout.raw_dir.relative_to(layout.root).as_posix(),
                layout.derived_dir.relative_to(layout.root).as_posix(),
            ],
            note="imported sources and generated parsed artifacts",
        ),
        InitReviewGroup(
            label="runtime state",
            paths=[
                layout.state_dir.relative_to(layout.root).as_posix(),
                layout.source_records_dir.relative_to(layout.root).as_posix(),
                layout.reports_dir.relative_to(layout.root).as_posix(),
            ],
            note="machine-readable manifests, queues, runs, and reports",
        ),
    ]


def _keep_files(layout: ResolvedLayout) -> list[Path]:
    directories = [
        layout.raw_sources_dir,
        layout.raw_assets_dir,
        layout.raw_imports_dir,
        layout.derived_ocr_dir,
        layout.derived_parsed_dir,
        layout.derived_metadata_dir,
        layout.derived_summaries_dir,
        layout.wiki_dir / "concepts",
        layout.wiki_dir / "entities",
        layout.wiki_dir / "topics",
        layout.wiki_sources_dir,
        layout.wiki_dir / "glossary",
        layout.wiki_dir / "architecture",
        layout.planning_dir / "milestones",
        layout.planning_dir / "tasks",
        layout.planning_dir / "decisions",
        layout.planning_dir / "questions",
        layout.state_dir / "manifests",
        layout.source_records_dir,
        layout.queue_dir,
        layout.runs_dir,
        layout.queries_dir,
        layout.state_dir / "locks",
        layout.reports_dir / "lint",
        layout.reports_dir / "health",
        layout.reports_dir / "ingest",
    ]
    return [directory / ".gitkeep" for directory in directories]
