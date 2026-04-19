"""Repository layout helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from splendor.config import SplendorConfig

INDEX_TEMPLATE = """# Splendor Wiki Index

This wiki is maintained by Splendor.

## Navigation

- `wiki/sources/` for deterministic source summary pages.
- `planning/` for milestones, tasks, decisions, and questions.
- `state/` for machine-readable queue, run, and manifest records.
"""

LOG_TEMPLATE = """# Splendor Wiki Log

## Timeline

- Initialized Splendor workspace.
"""


@dataclass(frozen=True)
class ResolvedLayout:
    root: Path
    raw_dir: Path
    raw_sources_dir: Path
    raw_assets_dir: Path
    raw_imports_dir: Path
    derived_dir: Path
    derived_ocr_dir: Path
    derived_parsed_dir: Path
    derived_metadata_dir: Path
    derived_summaries_dir: Path
    wiki_dir: Path
    planning_dir: Path
    state_dir: Path
    reports_dir: Path
    source_records_dir: Path

    @property
    def index_file(self) -> Path:
        return self.wiki_dir / "index.md"

    @property
    def log_file(self) -> Path:
        return self.wiki_dir / "log.md"

    @property
    def wiki_sources_dir(self) -> Path:
        return self.wiki_dir / "sources"

    @property
    def queue_dir(self) -> Path:
        return self.state_dir / "queue"

    @property
    def runs_dir(self) -> Path:
        return self.state_dir / "runs"

    @property
    def queries_dir(self) -> Path:
        return self.state_dir / "queries"


def resolve_layout(root: Path, config: SplendorConfig) -> ResolvedLayout:
    layout = config.layout
    return ResolvedLayout(
        root=root,
        raw_dir=root / layout.raw_dir,
        raw_sources_dir=root / layout.raw_sources_dir,
        raw_assets_dir=root / layout.raw_assets_dir,
        raw_imports_dir=root / layout.raw_imports_dir,
        derived_dir=root / layout.derived_dir,
        derived_ocr_dir=root / layout.derived_ocr_dir,
        derived_parsed_dir=root / layout.derived_parsed_dir,
        derived_metadata_dir=root / layout.derived_metadata_dir,
        derived_summaries_dir=root / layout.derived_summaries_dir,
        wiki_dir=root / layout.wiki_dir,
        planning_dir=root / layout.planning_dir,
        state_dir=root / layout.state_dir,
        reports_dir=root / layout.reports_dir,
        source_records_dir=root / layout.source_records_dir,
    )


def required_directories(layout: ResolvedLayout) -> list[Path]:
    return [
        layout.raw_dir,
        layout.raw_sources_dir,
        layout.raw_assets_dir,
        layout.raw_imports_dir,
        layout.derived_dir,
        layout.derived_ocr_dir,
        layout.derived_parsed_dir,
        layout.derived_metadata_dir,
        layout.derived_summaries_dir,
        layout.wiki_dir,
        layout.wiki_dir / "concepts",
        layout.wiki_dir / "entities",
        layout.wiki_dir / "topics",
        layout.wiki_dir / "sources",
        layout.wiki_dir / "glossary",
        layout.wiki_dir / "architecture",
        layout.planning_dir,
        layout.planning_dir / "milestones",
        layout.planning_dir / "tasks",
        layout.planning_dir / "decisions",
        layout.planning_dir / "questions",
        layout.state_dir,
        layout.state_dir / "queue",
        layout.state_dir / "runs",
        layout.state_dir / "queries",
        layout.state_dir / "locks",
        layout.state_dir / "manifests",
        layout.source_records_dir,
        layout.reports_dir,
        layout.reports_dir / "lint",
        layout.reports_dir / "health",
        layout.reports_dir / "ingest",
    ]
