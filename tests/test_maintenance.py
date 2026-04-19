import json
from pathlib import Path

import pytest

from splendor.commands.maintenance import (
    MaintenanceCheckResult,
    execute_maintenance_command,
    write_report_artifacts,
)
from splendor.config import default_config
from splendor.layout import resolve_layout
from splendor.schemas import MaintenanceIssue, MaintenanceReport


def test_write_report_artifacts_does_not_leave_dangling_json_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = resolve_layout(tmp_path, default_config(project_name=tmp_path.name))
    report_dir = layout.reports_dir / "lint"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = MaintenanceReport(
        command="lint",
        created_at="2026-04-19T08:00:00+00:00",
        status="passed",
        checked_count=1,
        issue_count=0,
        issues=[],
    )

    original_replace = Path.replace
    replace_calls = {"count": 0}

    def flaky_replace(self: Path, target: Path) -> Path:
        replace_calls["count"] += 1
        if replace_calls["count"] == 2:
            raise OSError("simulated markdown replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    with pytest.raises(OSError, match="simulated markdown replace failure"):
        write_report_artifacts(layout, report)

    assert list(report_dir.glob("*.json")) == []
    assert list(report_dir.glob("*.md")) == []


def test_execute_maintenance_command_normalizes_unexpected_exceptions(tmp_path: Path) -> None:
    layout = resolve_layout(tmp_path, default_config(project_name=tmp_path.name))
    for directory in (
        layout.reports_dir,
        layout.reports_dir / "lint",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    def boom(root: Path, resolved_layout) -> MaintenanceCheckResult:
        raise KeyError("unexpected crash")

    result = execute_maintenance_command(
        tmp_path,
        command="lint",
        run_checks=boom,
    )

    assert result.exit_code == 1
    assert result.report.status == "error"
    assert "unexpected crash" in result.report.fatal_error
    assert result.json_path is not None
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert "unexpected crash" in payload["fatal_error"]


def test_maintenance_report_rejects_passed_report_with_issues() -> None:
    with pytest.raises(ValueError, match="passed reports must not contain issues"):
        MaintenanceReport(
            command="lint",
            created_at="2026-04-19T08:00:00+00:00",
            status="passed",
            checked_count=1,
            issue_count=1,
            issues=[
                MaintenanceIssue(
                    code="bad",
                    message="bad",
                )
            ],
        )


def test_maintenance_report_rejects_error_report_without_fatal_error() -> None:
    with pytest.raises(ValueError, match="error reports must contain fatal_error"):
        MaintenanceReport(
            command="health",
            created_at="2026-04-19T08:00:00+00:00",
            status="error",
            checked_count=0,
            issue_count=0,
            issues=[],
        )


def test_maintenance_report_rejects_failed_report_without_issues() -> None:
    with pytest.raises(ValueError, match="failed reports must contain at least one issue"):
        MaintenanceReport(
            command="health",
            created_at="2026-04-19T08:00:00+00:00",
            status="failed",
            checked_count=1,
            issue_count=0,
            issues=[],
        )
