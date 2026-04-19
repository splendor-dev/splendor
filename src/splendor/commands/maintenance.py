"""Shared maintenance command/reporting helpers."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from splendor.config import default_config, load_config
from splendor.layout import ResolvedLayout, resolve_layout
from splendor.schemas import MaintenanceIssue, MaintenanceReport
from splendor.utils.fs import ensure_directory, write_text_atomic
from splendor.utils.time import utc_now_iso


@dataclass(frozen=True)
class MaintenanceCheckResult:
    checked_count: int
    issues: list[MaintenanceIssue]


@dataclass(frozen=True)
class MaintenanceCommandResult:
    report: MaintenanceReport
    exit_code: int
    json_path: Path | None
    markdown_path: Path | None


MaintenanceChecks = Callable[[Path, ResolvedLayout], MaintenanceCheckResult]


def render_report_json(report: MaintenanceReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def render_report_markdown(report: MaintenanceReport) -> str:
    title = f"Splendor {report.command.title()} Report"
    lines = [
        f"# {title}",
        "",
        f"- Generated: `{report.created_at}`",
        f"- Status: `{report.status}`",
        f"- Checked: `{report.checked_count}`",
        f"- Issues: `{report.issue_count}`",
    ]
    if report.fatal_error is not None:
        lines.extend(["", "## Fatal Error", "", report.fatal_error])
    if report.issues:
        lines.extend(["", "## Issues", ""])
        for issue in report.issues:
            detail_parts = [f"[{issue.code}] {issue.message}"]
            if issue.record_id:
                detail_parts.append(f"record: `{issue.record_id}`")
            if issue.path:
                detail_parts.append(f"path: `{issue.path}`")
            if issue.check_name:
                detail_parts.append(f"check: `{issue.check_name}`")
            lines.append(f"- {'; '.join(detail_parts)}")
    return "\n".join(lines) + "\n"


def _report_basename(report_dir: Path) -> str:
    base = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    candidate = base
    suffix = 1
    while (report_dir / f"{candidate}.json").exists() or (report_dir / f"{candidate}.md").exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def write_report_artifacts(layout: ResolvedLayout, report: MaintenanceReport) -> tuple[Path, Path]:
    report_dir = ensure_directory(layout.reports_dir / report.command)
    basename = _report_basename(report_dir)
    json_path = report_dir / f"{basename}.json"
    markdown_path = report_dir / f"{basename}.md"
    write_text_atomic(json_path, render_report_json(report))
    write_text_atomic(markdown_path, render_report_markdown(report))
    return json_path, markdown_path


def execute_maintenance_command(
    root: Path,
    *,
    command: str,
    run_checks: MaintenanceChecks,
) -> MaintenanceCommandResult:
    created_at = utc_now_iso()
    layout: ResolvedLayout | None = None
    try:
        config = load_config(root)
        layout = resolve_layout(root, config)
        check_result = run_checks(root, layout)
        report = MaintenanceReport(
            command=command,
            created_at=created_at,
            status="passed" if not check_result.issues else "failed",
            checked_count=check_result.checked_count,
            issue_count=len(check_result.issues),
            issues=check_result.issues,
        )
    except (ValueError, RuntimeError, OSError, yaml.YAMLError) as exc:
        if layout is None:
            layout = resolve_layout(root, default_config(project_name=root.name))
        report = MaintenanceReport(
            command=command,
            created_at=created_at,
            status="error",
            checked_count=0,
            issue_count=0,
            issues=[],
            fatal_error=str(exc),
        )

    try:
        json_path, markdown_path = write_report_artifacts(layout, report)
    except OSError as exc:
        report = MaintenanceReport(
            command=command,
            created_at=created_at,
            status="error",
            checked_count=report.checked_count,
            issue_count=report.issue_count,
            issues=report.issues,
            fatal_error=f"Failed to write report artifacts: {exc}",
        )
        return MaintenanceCommandResult(
            report=report,
            exit_code=1,
            json_path=None,
            markdown_path=None,
        )

    return MaintenanceCommandResult(
        report=report,
        exit_code=0 if report.status == "passed" else 1,
        json_path=json_path,
        markdown_path=markdown_path,
    )
