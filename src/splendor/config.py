"""Configuration loading for Splendor.

`SourcesConfig` captures policy defaults for the upcoming source-resolution model. Runtime
registration and ingest do not consume it yet in this release.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from splendor.schemas.types import StorageMode, SummaryMode

CONFIG_FILENAME = "splendor.yaml"


class LayoutConfig(BaseModel):
    raw_dir: str = "raw"
    raw_sources_dir: str = "raw/sources"
    raw_assets_dir: str = "raw/assets"
    raw_imports_dir: str = "raw/imports"
    derived_dir: str = "derived"
    derived_ocr_dir: str = "derived/ocr"
    derived_parsed_dir: str = "derived/parsed"
    derived_metadata_dir: str = "derived/metadata"
    derived_summaries_dir: str = "derived/summaries"
    wiki_dir: str = "wiki"
    planning_dir: str = "planning"
    state_dir: str = "state"
    reports_dir: str = "reports"
    source_records_dir: str = "state/manifests/sources"


class SourcesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    in_repo_storage_mode: StorageMode = "none"
    external_storage_mode: StorageMode = "copy"
    imported_storage_mode: StorageMode = "copy"
    capture_source_commit: bool = True
    summarize_in_repo_extracts_as: SummaryMode = "excerpt"
    summarize_external_extracts_as: SummaryMode = "full"


class SplendorConfig(BaseModel):
    schema_version: str = "1"
    project_name: str = "Splendor workspace"
    layout: LayoutConfig = Field(default_factory=LayoutConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)


def config_path_for(root: Path) -> Path:
    return root / CONFIG_FILENAME


def default_config(*, project_name: str | None = None) -> SplendorConfig:
    config = SplendorConfig()
    if project_name:
        config.project_name = project_name
    return config


def load_config(root: Path) -> SplendorConfig:
    path = config_path_for(root)
    if not path.exists():
        return default_config(project_name=root.name)

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = SplendorConfig.model_validate(raw)
    if not config.project_name:
        config.project_name = root.name
    return config


def write_config(root: Path, config: SplendorConfig) -> Path:
    path = config_path_for(root)
    path.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return path
