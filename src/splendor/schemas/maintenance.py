"""Schemas for deterministic maintenance reports."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from splendor.schemas.common import StrictRecord


class MaintenanceIssue(StrictRecord):
    kind: Literal["maintenance_issue"] = "maintenance_issue"
    code: str
    message: str
    path: str | None = None
    record_id: str | None = None
    check_name: str | None = None


class MaintenanceReport(StrictRecord):
    kind: Literal["maintenance_report"] = "maintenance_report"
    command: Literal["lint", "health"]
    created_at: str
    status: Literal["passed", "failed", "error"]
    checked_count: int = Field(ge=0)
    issue_count: int = Field(ge=0)
    issues: list[MaintenanceIssue] = Field(default_factory=list)
    fatal_error: str | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> MaintenanceReport:
        if self.issue_count != len(self.issues):
            raise ValueError(
                f"issue_count must equal the number of issues; got {self.issue_count} "
                f"for {len(self.issues)} issues"
            )
        if self.status == "passed":
            if self.issues or self.issue_count != 0:
                raise ValueError("passed reports must not contain issues")
            if self.fatal_error is not None:
                raise ValueError("passed reports must not contain fatal_error")
        elif self.status == "failed":
            if not self.issues or self.issue_count == 0:
                raise ValueError("failed reports must contain at least one issue")
            if self.fatal_error is not None:
                raise ValueError("failed reports must not contain fatal_error")
        elif self.status == "error":
            if self.fatal_error is None:
                raise ValueError("error reports must contain fatal_error")
            if self.issues or self.issue_count != 0:
                raise ValueError("error reports must not contain issues")
        return self
