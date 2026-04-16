"""Implementation for `splendor health`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.state.source_compat import effective_storage_mode
from splendor.state.source_registry import load_source_record
from splendor.state.source_resolver import resolve_source_content


@dataclass(frozen=True)
class HealthIssue:
    source_id: str
    message: str


@dataclass(frozen=True)
class HealthResult:
    checked_sources: int
    issues: list[HealthIssue]


def _validate_storage_policy(source) -> None:
    storage_mode = effective_storage_mode(source)
    if storage_mode == "none" and source.source_ref_kind != "workspace_path":
        msg = (
            "Storage mode 'none' requires source_ref_kind=workspace_path; "
            f"got {source.source_ref_kind!r}"
        )
        raise ValueError(msg)
    if storage_mode in {"pointer", "symlink"} and source.source_ref_kind != "workspace_path":
        msg = (
            f"Storage mode {storage_mode!r} requires source_ref_kind=workspace_path; "
            f"got {source.source_ref_kind!r}"
        )
        raise ValueError(msg)
    if storage_mode == "copy" and not source.path:
        raise ValueError("Copied source is missing path")


def run_health(root: Path) -> HealthResult:
    config = load_config(root)
    layout = resolve_layout(root, config)
    issues: list[HealthIssue] = []
    checked_sources = 0

    for manifest_path in sorted(layout.source_records_dir.glob("*.json")):
        checked_sources += 1
        source_id = manifest_path.stem
        try:
            source = load_source_record(manifest_path)
            _validate_storage_policy(source)
            resolve_source_content(root, source, layout.raw_sources_dir)
        except Exception as exc:
            issues.append(HealthIssue(source_id=source_id, message=str(exc)))

    return HealthResult(checked_sources=checked_sources, issues=issues)
