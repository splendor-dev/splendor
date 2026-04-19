"""Implementation for `splendor health`."""

from __future__ import annotations

from pathlib import Path

from splendor.commands.maintenance import MaintenanceCheckResult, workspace_relative_path
from splendor.layout import ResolvedLayout
from splendor.schemas import MaintenanceIssue, SourceRecord
from splendor.state.source_compat import effective_storage_mode
from splendor.state.source_registry import load_source_record
from splendor.state.source_resolver import resolve_source_content


def _validate_storage_policy(source: SourceRecord) -> None:
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


def run_health_checks(root: Path, layout: ResolvedLayout) -> MaintenanceCheckResult:
    issues: list[MaintenanceIssue] = []
    checked_sources = 0

    if not layout.source_records_dir.is_dir():
        msg = f"Source manifest directory is missing or unreadable: {layout.source_records_dir}"
        raise RuntimeError(msg)

    for manifest_path in sorted(layout.source_records_dir.glob("*.json")):
        checked_sources += 1
        source_id = manifest_path.stem
        try:
            source = load_source_record(manifest_path)
            _validate_storage_policy(source)
            resolve_source_content(root, source, layout.raw_sources_dir)
        except Exception as exc:
            issues.append(
                MaintenanceIssue(
                    code="source-health-check-failed",
                    message=str(exc),
                    path=workspace_relative_path(layout.root, manifest_path),
                    record_id=source_id,
                    check_name="source-storage",
                )
            )

    return MaintenanceCheckResult(checked_count=checked_sources, issues=issues)
