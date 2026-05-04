"""Configuration loading for Splendor.

`SourcesConfig` captures source-registration defaults and source-summary rendering policy.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from splendor.schemas.types import SourceClass, StorageMode, SummaryMode

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
    ocr_enabled: bool = False
    ocr_provider: str = "sidecar-text"
    ocr_sidecar_suffix: str = ".ocr.txt"
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    repo_scan_default_classes: list[SourceClass] = Field(default_factory=lambda: ["documentation"])


class ContradictionsReviewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    provider: str = "openai"
    model: str | None = None
    max_candidate_pages: int = Field(default=20, ge=1)
    review_task_priority: str = "high"


class ReviewsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contradictions: ContradictionsReviewConfig = Field(default_factory=ContradictionsReviewConfig)


class QueueConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=3, ge=1)
    lease_ttl_seconds: int = Field(default=300, ge=1)
    retry_backoff_seconds: list[Annotated[int, Field(ge=0)]] = Field(
        default_factory=lambda: [60, 300, 900]
    )


class AuthorityDocumentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    role: Literal[
        "current-authority",
        "roadmap",
        "historical-review",
        "proposal",
        "reference",
        "generated-summary",
    ] = "reference"
    freshness: Literal["current", "watch", "stale", "historical"] = "current"
    title: str | None = None
    purpose: str | None = None
    applies_to: list[str] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def validate_repo_relative_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("authority document path must not be empty")
        posix_path = PurePosixPath(normalized)
        if posix_path.is_absolute() or PureWindowsPath(normalized).is_absolute():
            raise ValueError("authority document path must be repo-relative")
        if "\\" in normalized:
            raise ValueError("authority document path must use POSIX separators")
        if any(part in {"", ".", ".."} for part in posix_path.parts):
            raise ValueError("authority document path must be normalized and stay inside the repo")
        if posix_path.as_posix() != normalized:
            raise ValueError("authority document path must be normalized")
        return normalized


class BriefingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority_documents: list[AuthorityDocumentConfig] = Field(default_factory=list)


class SplendorConfig(BaseModel):
    schema_version: str = "1"
    project_name: str = "Splendor workspace"
    layout: LayoutConfig = Field(default_factory=LayoutConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    reviews: ReviewsConfig = Field(default_factory=ReviewsConfig)
    briefing: BriefingConfig = Field(default_factory=BriefingConfig)


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
