"""Implementation for `splendor lint`."""

from __future__ import annotations

from pathlib import Path

from splendor.commands.maintenance import MaintenanceCheckResult
from splendor.layout import ResolvedLayout, required_directories
from splendor.schemas import MaintenanceIssue


def run_lint_checks(root: Path, layout: ResolvedLayout) -> MaintenanceCheckResult:
    issues: list[MaintenanceIssue] = []
    checked_count = 0

    for directory in required_directories(layout):
        checked_count += 1
        if directory.is_dir():
            continue
        issues.append(
            MaintenanceIssue(
                code="missing-directory",
                message="Required workspace directory is missing",
                path=str(directory),
                check_name="workspace-layout",
            )
        )

    required_files = [layout.index_file, layout.log_file]
    for path in required_files:
        checked_count += 1
        if path.is_file():
            continue
        issues.append(
            MaintenanceIssue(
                code="missing-file",
                message="Required bootstrap file is missing",
                path=str(path),
                check_name="workspace-bootstrap",
            )
        )

    return MaintenanceCheckResult(checked_count=checked_count, issues=issues)
